"""
Discord panel for Project Ceres — GM Assistant UI.

Connects a Discord bot to the GM Assistant for:
  • Voice channel monitoring (who's in the channel)
  • Continuous session recording + live transcription via OpenAI Whisper
  • Wake-word (Veras / Chroma) command extraction → Convector pipeline
  • Spotify control via Discord text commands (!play / !pause / !skip / !search)
  • Live transcript display + one-click save to the active Obsidian vault

Requirements (install separately):
    pip install discord.py[voice] PyNaCl openai numpy

Bot token: add  DISCORD_BOT_TOKEN=<your_token>  to variables.env

Layout
------
  ┌─ 🎙 DISCORD ──────────────────────────────────────────┐
  │ Token: [●●●●●●●●●●●●●●●●] [🔌 Connect] [✕]           │
  │ ● Connected  ·  My Server  ·  Ceres#1234              │
  ├───────────────────────────────────────────────────────│
  │ Voice Channel: [▾ Session VC          ] [Join]        │
  │ 👥  Aragorn  ·  Gimli  ·  Legolas                    │
  ├───────────────────────────────────────────────────────│
  │ [🔴 Record Session] [⏹ Stop] [💾 Save Transcript]    │
  │ 🔴 Recording  00:04:32  ·  ~1,200 words               │
  ├───────────────────────────────────────────────────────│
  │ 📜 Live Transcript                       [🗑 Clear]   │
  │ ┌─────────────────────────────────────────────────┐  │
  │ │ [14:23:01] ⚡ VERAS → add_bookmark: dragon …   │  │
  │ │ [14:24:15] The party approaches the gate…       │  │
  │ └─────────────────────────────────────────────────┘  │
  ├───────────────────────────────────────────────────────│
  │ 🎵 [  search track / artist …  ] [▶] [⏸] [⏭] [🔍]  │
  └───────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QLineEdit,
        QTextEdit, QSizePolicy, QMessageBox,
    )
    from PyQt5.QtCore import Qt, QThread, QObject, QTimer, QSettings, pyqtSignal as Signal
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QLineEdit,
        QTextEdit, QSizePolicy, QMessageBox,
    )
    from PySide6.QtCore import Qt, QThread, QObject, QTimer, QSettings, Signal  # type: ignore

from ui.theme import ACCENT, MUTED, TEXT, SUCCESS, WARNING, ERROR, PANEL, BORDER

# ── Optional dependency checks ─────────────────────────────────────────────────

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    discord = None  # type: ignore
    DISCORD_AVAILABLE = False

try:
    import numpy as _np
    NUMPY_AVAILABLE = True
except ImportError:
    _np = None  # type: ignore
    NUMPY_AVAILABLE = False

# ── Audio constants ─────────────────────────────────────────────────────────────

DISCORD_SAMPLE_RATE  = 48_000   # Hz — Discord always uses 48 kHz
DISCORD_CHANNELS     = 2        # stereo
DISCORD_SAMPLE_WIDTH = 2        # 16-bit PCM
CHUNK_SECONDS        = 30       # send a WAV chunk to Whisper every N seconds

# Emoji used for poll reactions — indices 0-3 map to candidate date options
POLL_EMOJIS: Tuple[str, ...] = ("1️⃣", "2️⃣", "3️⃣", "4️⃣")

# ── Conditional AudioSink base ─────────────────────────────────────────────────
# discord.AudioSink is the correct base when discord.py (2.x) is installed.
# When unavailable we fall back to a plain object so the class still loads.

if DISCORD_AVAILABLE and hasattr(discord, "AudioSink"):
    _SinkBase = discord.AudioSink          # type: ignore[attr-defined]
else:
    class _SinkBase:                       # type: ignore[no-redef]
        """Stub base when discord.py is absent or lacks AudioSink."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  PCM Audio Sink
# ══════════════════════════════════════════════════════════════════════════════

class _PCMSink(_SinkBase):
    """
    Accumulates raw 48 kHz 16-bit stereo PCM audio frames from Discord.

    Every CHUNK_SECONDS it:
      1. Grabs all per-user PCM buffers
      2. Mixes them into one stream (via numpy sample-sum, or fallback)
      3. Writes a temporary WAV file
      4. Invokes on_chunk_ready(wav_path)

    The caller owns the temp file and must delete it after use.
    """

    def __init__(self, on_chunk_ready: Callable[[Path], None]) -> None:
        self._on_chunk_ready = on_chunk_ready
        self._buffers: Dict[int, bytearray] = {}
        self._lock = threading.Lock()
        self._chunk_start = time.monotonic()
        self._closed = False

    # ── discord.AudioSink interface ────────────────────────────────────────────

    def write(self, data, user) -> None:      # type: ignore[override]
        """Called by discord.py for every ~20 ms PCM frame."""
        if self._closed:
            return
        uid: int = getattr(user, "id", 0)
        raw: bytes = getattr(data, "data", bytes(data))

        with self._lock:
            if uid not in self._buffers:
                self._buffers[uid] = bytearray()
            self._buffers[uid].extend(raw)

        if time.monotonic() - self._chunk_start >= CHUNK_SECONDS:
            self.flush()

    def cleanup(self) -> None:               # type: ignore[override]
        """Called by discord.py when listening stops — flush remaining audio."""
        self._closed = True
        self.flush()

    # ── Flushing ───────────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Extract buffered audio, write WAV, fire callback."""
        with self._lock:
            snapshot = {uid: bytes(buf) for uid, buf in self._buffers.items() if buf}
            self._buffers.clear()
        self._chunk_start = time.monotonic()

        if not snapshot:
            return

        pcm = self._mix_buffers(list(snapshot.values()))
        if not pcm:
            return

        wav_path = self._write_wav(pcm)
        if wav_path:
            self._on_chunk_ready(wav_path)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _mix_buffers(streams: List[bytes]) -> bytes:
        """Mix multiple 16-bit PCM streams by summing samples and clipping."""
        if not streams:
            return b""
        if len(streams) == 1:
            return streams[0]

        if NUMPY_AVAILABLE:
            arrays = [_np.frombuffer(b, dtype=_np.int16) for b in streams if b]
            if not arrays:
                return b""
            max_len = max(len(a) for a in arrays)
            mixed = _np.zeros(max_len, dtype=_np.int32)
            for arr in arrays:
                mixed[: len(arr)] += arr
            return _np.clip(mixed, -32_768, 32_767).astype(_np.int16).tobytes()
        else:
            # Numpy unavailable: use the longest single stream as best effort
            return max(streams, key=len)

    @staticmethod
    def _write_wav(pcm: bytes) -> Optional[Path]:
        """Write raw PCM bytes to a named temp WAV file and return the Path."""
        if not pcm:
            return None
        try:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix="ceres_discord_"
            )
            tmp.close()
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(DISCORD_CHANNELS)
                wf.setsampwidth(DISCORD_SAMPLE_WIDTH)
                wf.setframerate(DISCORD_SAMPLE_RATE)
                wf.writeframes(pcm)
            return Path(tmp.name)
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
#  Discord Worker  (runs inside a QThread, owns an asyncio event loop)
# ══════════════════════════════════════════════════════════════════════════════

class _DiscordWorker(QObject):
    """
    Runs a discord.py Client in a background QThread.

    Communication model:
      Qt → asyncio : call worker.join_voice_channel() etc.  These methods
                     use asyncio.run_coroutine_threadsafe() to push work
                     into the asyncio loop.
      asyncio → Qt : emit pyqtSignals (Qt queues them to the UI thread
                     automatically because the worker lives in a non-UI thread).
    """

    # ── Signals ────────────────────────────────────────────────────────────────
    connected             = Signal(str, str)   # guild_name, user_tag
    disconnected          = Signal(str)        # reason
    error                 = Signal(str)        # message
    channels_updated      = Signal(list)       # [(ch_id_str, ch_name), ...] voice
    text_channels_updated = Signal(list)       # [(ch_id_str, ch_name), ...] text
    members_updated       = Signal(list)       # [display_name, ...]
    transcript_ready      = Signal(str, str)   # timestamp_str, text
    command_detected      = Signal(str, str)   # command_type, raw_text
    spotify_command       = Signal(str, str)   # action, query
    poll_sent             = Signal(str)        # message_id (str)
    vote_updated          = Signal(dict)       # {option_idx: vote_count}
    poll_error            = Signal(str)        # error message

    # Discord text commands routed to Spotify
    _SPOTIFY_CMDS: Tuple[str, ...] = (
        "!play", "!pause", "!skip", "!stop",
        "!search", "!queue", "!volume", "!next",
    )

    def __init__(self, token: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._token = token
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None    # discord.Client, set in _run_bot
        self._vc = None        # discord.VoiceClient, set when joining VC
        self._sink: Optional[_PCMSink] = None
        self._recording = False
        # Poll state
        self._poll_message_id: Optional[int] = None
        self._poll_channel_id: Optional[int] = None
        self._poll_option_count: int = 0
        self._poll_role_name: str = ""

    # ── Thread entry point ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Called by QThread.started — creates asyncio loop, runs bot."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_bot())
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    # ── Bot lifecycle ──────────────────────────────────────────────────────────

    async def _run_bot(self) -> None:
        if not DISCORD_AVAILABLE:
            self.error.emit(
                "discord.py not installed.\n"
                "Run:  pip install discord.py[voice] PyNaCl"
            )
            return

        intents = discord.Intents.default()   # type: ignore[attr-defined]
        intents.message_content = True
        intents.voice_states = True
        intents.members = True

        self._client = discord.Client(intents=intents)  # type: ignore[attr-defined]

        @self._client.event
        async def on_ready() -> None:
            user = self._client.user
            guilds = self._client.guilds
            guild = guilds[0] if guilds else None
            guild_name = guild.name if guild else "(no guild)"
            self.connected.emit(guild_name, str(user))
            if guild:
                vcs = [(str(ch.id), ch.name) for ch in guild.voice_channels]
                self.channels_updated.emit(vcs)
                tcs = [(str(ch.id), ch.name) for ch in guild.text_channels]
                self.text_channels_updated.emit(tcs)

        @self._client.event
        async def on_voice_state_update(member, before, after) -> None:  # noqa: ANN001
            if self._vc and self._vc.channel:
                names = [m.display_name for m in self._vc.channel.members]
                self.members_updated.emit(names)

        @self._client.event
        async def on_reaction_add(reaction, user) -> None:   # noqa: ANN001
            await self._handle_reaction_change(reaction, user)

        @self._client.event
        async def on_reaction_remove(reaction, user) -> None:   # noqa: ANN001
            await self._handle_reaction_change(reaction, user)

        @self._client.event
        async def on_message(message) -> None:   # noqa: ANN001
            if message.author == self._client.user:
                return
            content: str = (message.content or "").strip()
            if not content:
                return
            lower = content.lower()
            for cmd in self._SPOTIFY_CMDS:
                if lower.startswith(cmd):
                    action = cmd.lstrip("!")
                    query = content[len(cmd):].strip()
                    self.spotify_command.emit(action, query)
                    return

        try:
            await self._client.start(self._token)
        except Exception as exc:
            # Catch LoginFailure by name to avoid needing discord imported at
            # module level for type checking.
            if "LoginFailure" in type(exc).__name__:
                self.error.emit(
                    "Discord: Invalid bot token.\n"
                    "Check DISCORD_BOT_TOKEN in variables.env."
                )
            else:
                self.error.emit(f"Discord error: {exc}")
        finally:
            if self._client and not self._client.is_closed():
                await self._client.close()
            self.disconnected.emit("Bot stopped")

    # ── Qt-thread-callable actions ─────────────────────────────────────────────

    def stop(self) -> None:
        if self._loop and self._client:
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)

    def list_text_channels(self) -> None:
        """Request the current guild's text channels — emits text_channels_updated."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._list_text_channels(), self._loop
            )

    def post_poll(
        self, channel_id: int, options: List[Tuple[str, str]], role_name: str
    ) -> None:
        """Post a scheduling poll. options = [(date_label, time_label), ...]."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._post_poll(channel_id, options, role_name), self._loop
            )

    def refresh_votes(self) -> None:
        """Manually re-tally poll reactions and emit vote_updated."""
        if self._loop and self._poll_message_id:
            asyncio.run_coroutine_threadsafe(self._refresh_votes(), self._loop)

    def close_poll(self) -> None:
        """Clear poll state (does not delete the Discord message)."""
        self._poll_message_id = None
        self._poll_channel_id = None
        self._poll_option_count = 0
        self._poll_role_name = ""

    def post_message(self, channel_id: int, content: str) -> None:
        """Post a plain text message to a text channel."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._post_message(channel_id, content), self._loop
            )

    # ── Async helpers: scheduling poll ────────────────────────────────────────

    async def _list_text_channels(self) -> None:
        if not self._client:
            return
        guilds = self._client.guilds
        guild = guilds[0] if guilds else None
        if guild:
            tcs = [(str(ch.id), ch.name) for ch in guild.text_channels]
            self.text_channels_updated.emit(tcs)

    async def _post_poll(
        self, channel_id: int, options: List[Tuple[str, str]], role_name: str
    ) -> None:
        if not self._client:
            self.poll_error.emit("Discord bot is not connected.")
            return
        try:
            channel = self._client.get_channel(channel_id)
            if channel is None:
                self.poll_error.emit(f"Text channel {channel_id} not found.")
                return

            lines = ["📅 **Vote for the next session!**", "React with your availability:\n"]
            for i, (date_lbl, time_lbl) in enumerate(options):
                lines.append(f"{POLL_EMOJIS[i]}  **{date_lbl}** at {time_lbl}")
            lines.append("")
            if role_name:
                lines.append(f"_Only members with the @{role_name} role may vote._")
            lines.append("_Poll closes when the GM selects a date._")

            message = await channel.send("\n".join(lines))

            # Pre-add the emoji reactions so players can just click them
            for i in range(len(options)):
                await message.add_reaction(POLL_EMOJIS[i])

            self._poll_message_id   = message.id
            self._poll_channel_id   = channel_id
            self._poll_option_count = len(options)
            self._poll_role_name    = role_name

            self.poll_sent.emit(str(message.id))
            # Emit initial zero-count votes
            self.vote_updated.emit({i: 0 for i in range(len(options))})

        except Exception as exc:
            self.poll_error.emit(f"Poll error: {exc}")

    async def _handle_reaction_change(self, reaction, user) -> None:
        """Filter and re-tally whenever a reaction is added or removed."""
        if getattr(user, "bot", False):
            return
        if self._poll_message_id is None:
            return
        if reaction.message.id != self._poll_message_id:
            return
        await self._refresh_votes()

    async def _refresh_votes(self) -> None:
        """Re-fetch the poll message and count valid votes per option."""
        if not self._poll_message_id or not self._poll_channel_id:
            return
        if not self._client:
            return
        try:
            channel = self._client.get_channel(self._poll_channel_id)
            if channel is None:
                return
            message = await channel.fetch_message(self._poll_message_id)
            votes: Dict[int, int] = {i: 0 for i in range(self._poll_option_count)}

            for reaction in message.reactions:
                emoji_str = str(reaction.emoji)
                if emoji_str not in POLL_EMOJIS:
                    continue
                opt_idx = POLL_EMOJIS.index(emoji_str)
                if opt_idx >= self._poll_option_count:
                    continue
                async for voter in reaction.users():
                    if getattr(voter, "bot", False):
                        continue
                    if self._poll_role_name:
                        member = channel.guild.get_member(voter.id)
                        if member is None:
                            continue
                        role_names_lower = {r.name.lower() for r in member.roles}
                        if self._poll_role_name.lower() not in role_names_lower:
                            continue
                    votes[opt_idx] += 1

            self.vote_updated.emit(votes)
        except Exception:
            pass   # vote refresh failure is non-critical

    async def _post_message(self, channel_id: int, content: str) -> None:
        if not self._client:
            return
        try:
            channel = self._client.get_channel(channel_id)
            if channel is not None:
                await channel.send(content)
        except Exception as exc:
            self.error.emit(f"Message send error: {exc}")

    def join_voice_channel(self, channel_id: int) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._join_vc(channel_id), self._loop
            )

    def start_recording(self) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._start_rec(), self._loop)

    def stop_recording(self) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._stop_rec(), self._loop)

    # ── Async helpers ──────────────────────────────────────────────────────────

    async def _join_vc(self, channel_id: int) -> None:
        if not self._client:
            return
        guilds = self._client.guilds
        guild = guilds[0] if guilds else None
        if not guild:
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            self.error.emit(f"Voice channel {channel_id} not found.")
            return
        if not isinstance(channel, discord.VoiceChannel):  # type: ignore[attr-defined]
            self.error.emit("Selected channel is not a voice channel.")
            return

        try:
            if self._vc and self._vc.is_connected():
                await self._vc.move_to(channel)
            else:
                self._vc = await channel.connect()
            names = [m.display_name for m in channel.members]
            self.members_updated.emit(names)
        except Exception as exc:
            self.error.emit(f"Could not join voice channel: {exc}")

    async def _start_rec(self) -> None:
        if not self._vc or not self._vc.is_connected():
            self.error.emit("Join a voice channel before recording.")
            return
        if self._recording:
            return

        self._recording = True
        self._sink = _PCMSink(on_chunk_ready=self._on_audio_chunk)

        # discord.py 2.x: VoiceClient.listen(AudioSink)
        try:
            self._vc.listen(self._sink)
        except AttributeError:
            self.error.emit(
                "Voice receive unavailable in this discord.py build.\n"
                "Try:  pip install py-cord[voice]  instead of discord.py."
            )
            self._recording = False
            self._sink = None
        except Exception as exc:
            self.error.emit(f"Could not start recording: {exc}")
            self._recording = False
            self._sink = None

    async def _stop_rec(self) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._vc:
            try:
                self._vc.stop_listening()
            except Exception:
                pass
        if self._sink:
            self._sink.cleanup()   # flushes final audio chunk
            self._sink = None

    # ── Audio → Whisper → signals ──────────────────────────────────────────────

    def _on_audio_chunk(self, wav_path: Path) -> None:
        """Called from the PCMSink (Discord audio thread)."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._transcribe_chunk(wav_path), self._loop
            )

    async def _transcribe_chunk(self, wav_path: Path) -> None:
        """Run Whisper transcription (blocking) in a thread-pool, then emit."""
        try:
            from pantheon.messor.audio_session import transcribe_audio  # local import

            transcript = await asyncio.get_event_loop().run_in_executor(
                None, transcribe_audio, wav_path
            )
            text: str = (transcript.text or "").strip()

            if text and text != "(transcription not yet implemented)":
                ts = datetime.now().strftime("%H:%M:%S")
                self.transcript_ready.emit(ts, text)

                # Extract wake-word commands and emit them separately
                try:
                    from pantheon.convector.transcript_parser import (
                        extract_voice_commands_from_transcript_text,
                    )
                    for cmd in extract_voice_commands_from_transcript_text(text):
                        self.command_detected.emit(cmd.type, cmd.text)
                except Exception:
                    pass   # command extraction errors don't break transcription

        except Exception as exc:
            self.error.emit(f"Transcription error: {exc}")
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  Discord Panel  (QDockWidget)
# ══════════════════════════════════════════════════════════════════════════════

class DiscordPanel(QDockWidget):
    """
    Dockable Discord integration panel.

    Signals:
        status_message(msg)       — forwarded to main-window status bar
        spotify_command(act, q)   — forwarded to SpotifyPanel
    """

    status_message: Signal = Signal(str)
    spotify_command: Signal = Signal(str, str)

    # ── Scheduler-facing signals ──────────────────────────────────────────────
    # Forwarded from _DiscordWorker so SchedulerPanel never touches the worker.
    text_channels_available: Signal = Signal(list)   # [(ch_id_str, ch_name), ...]
    poll_sent_ok:            Signal = Signal(str)    # message_id as str
    vote_updated:            Signal = Signal(dict)   # {option_idx: vote_count}
    poll_error_sig:          Signal = Signal(str)    # human-readable error

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("🎙  Discord", parent)
        self.setObjectName("DiscordPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)   # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |      # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config = config
        self._run_command = run_command

        self._worker: Optional[_DiscordWorker] = None
        self._thread: Optional[QThread] = None
        self._transcript_lines: List[str] = []
        self._recording = False
        self._record_start: Optional[float] = None

        self._settings = QSettings("ProjectCeres", "GMAssistant")

        self._build_ui()
        self._load_token_from_env()

        # Tick every second to update recording duration display
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._update_rec_display)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── Token + connect row ───────────────────────────────────────────
        token_row = QHBoxLayout()

        token_lbl = QLabel("Token:")
        token_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        token_row.addWidget(token_lbl)

        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)   # type: ignore[attr-defined]
        self._token_input.setPlaceholderText(
            "DISCORD_BOT_TOKEN  (auto-loaded from variables.env)"
        )
        self._token_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        token_row.addWidget(self._token_input)

        self._connect_btn = QPushButton("🔌 Connect")
        self._connect_btn.setProperty("class", "accent")
        self._connect_btn.setToolTip("Connect bot to Discord")
        self._connect_btn.clicked.connect(self._on_connect)
        token_row.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("✕")
        self._disconnect_btn.setFixedWidth(28)
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.setToolTip("Disconnect bot")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        token_row.addWidget(self._disconnect_btn)

        layout.addLayout(token_row)

        # ── Connection status label ───────────────────────────────────────
        self._status_lbl = QLabel("● Disconnected")
        self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        # ── Visual separator ──────────────────────────────────────────────
        layout.addWidget(self._make_sep())

        # ── Voice channel selector ────────────────────────────────────────
        vc_row = QHBoxLayout()

        vc_lbl = QLabel("Voice Channel:")
        vc_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        vc_row.addWidget(vc_lbl)

        self._vc_combo = QComboBox()
        self._vc_combo.setPlaceholderText("— connect first —")
        self._vc_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        vc_row.addWidget(self._vc_combo)

        self._join_btn = QPushButton("Join")
        self._join_btn.setEnabled(False)
        self._join_btn.setToolTip("Join selected voice channel")
        self._join_btn.clicked.connect(self._on_join_vc)
        vc_row.addWidget(self._join_btn)

        layout.addLayout(vc_row)

        # ── Members label ─────────────────────────────────────────────────
        self._members_lbl = QLabel("👥  —")
        self._members_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._members_lbl.setWordWrap(True)
        layout.addWidget(self._members_lbl)

        # ── Visual separator ──────────────────────────────────────────────
        layout.addWidget(self._make_sep())

        # ── Recording controls ────────────────────────────────────────────
        rec_row = QHBoxLayout()
        rec_row.setSpacing(4)

        self._record_btn = QPushButton("🔴 Record Session")
        self._record_btn.setProperty("class", "accent")
        self._record_btn.setEnabled(False)
        self._record_btn.setToolTip(
            "Start continuous session recording.\n"
            "Audio is sent to OpenAI Whisper every 30 s for live transcription.\n"
            "Veras / Chroma wake-word commands are extracted automatically."
        )
        self._record_btn.clicked.connect(self._on_start_recording)
        rec_row.addWidget(self._record_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setToolTip("Stop recording")
        self._stop_btn.clicked.connect(self._on_stop_recording)
        rec_row.addWidget(self._stop_btn)

        self._save_btn = QPushButton("💾 Save Transcript")
        self._save_btn.setEnabled(False)
        self._save_btn.setToolTip("Save full transcript to current Obsidian vault")
        self._save_btn.clicked.connect(self._on_save_transcript)
        rec_row.addWidget(self._save_btn)

        layout.addLayout(rec_row)

        # ── Recording status (duration + word count) ──────────────────────
        self._rec_status_lbl = QLabel("⏱  Not recording")
        self._rec_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        layout.addWidget(self._rec_status_lbl)

        # ── Live transcript header ────────────────────────────────────────
        ts_header = QHBoxLayout()

        ts_lbl = QLabel("📜  Live Transcript")
        ts_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        ts_header.addWidget(ts_lbl)
        ts_header.addStretch()

        clear_btn = QPushButton("🗑 Clear")
        clear_btn.setFixedWidth(68)
        clear_btn.setToolTip("Clear transcript display (does not delete saved files)")
        clear_btn.clicked.connect(self._clear_transcript)
        ts_header.addWidget(clear_btn)

        layout.addLayout(ts_header)

        # ── Transcript display ────────────────────────────────────────────
        self._transcript_view = QTextEdit()
        self._transcript_view.setReadOnly(True)
        self._transcript_view.setAcceptRichText(True)
        self._transcript_view.setStyleSheet(
            f"background: {PANEL}; color: {TEXT};"
            f"font-family: Consolas, 'Fira Code', monospace;"
            f"font-size: 11px; border: 1px solid {BORDER};"
        )
        self._transcript_view.setMinimumHeight(140)
        layout.addWidget(self._transcript_view)

        # ── Visual separator ──────────────────────────────────────────────
        layout.addWidget(self._make_sep())

        # ── Spotify quick controls ────────────────────────────────────────
        spotify_lbl = QLabel("🎵  Spotify")
        spotify_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        layout.addWidget(spotify_lbl)

        spotify_row = QHBoxLayout()
        spotify_row.setSpacing(3)

        self._spotify_search = QLineEdit()
        self._spotify_search.setPlaceholderText("Search track / artist…")
        self._spotify_search.setToolTip(
            "Type a track or artist name and press Enter (or 🔍) to play.\n"
            "Discord text commands: !play, !pause, !skip, !stop, !search"
        )
        self._spotify_search.returnPressed.connect(self._on_spotify_search)
        spotify_row.addWidget(self._spotify_search)

        for icon, action, tip in (
            ("▶", "play",  "Play / resume"),
            ("⏸", "pause", "Pause playback"),
            ("⏭", "skip",  "Skip to next track"),
        ):
            btn = QPushButton(icon)
            btn.setFixedWidth(32)
            btn.setToolTip(tip)
            btn.clicked.connect(
                lambda _checked, a=action: self.spotify_command.emit(a, "")
            )
            spotify_row.addWidget(btn)

        search_btn = QPushButton("🔍")
        search_btn.setFixedWidth(32)
        search_btn.setToolTip("Search and play")
        search_btn.clicked.connect(self._on_spotify_search)
        spotify_row.addWidget(search_btn)

        layout.addLayout(spotify_row)

        self.setWidget(outer)

    @staticmethod
    def _make_sep() -> QLabel:
        """One-pixel horizontal rule for visual grouping."""
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER};")
        return sep

    # ── Token loading ──────────────────────────────────────────────────────────

    def _load_token_from_env(self) -> None:
        """Pre-fill the token field from DISCORD_BOT_TOKEN env var or variables.env."""
        token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

        if not token:
            for candidate in (Path("variables.env"), Path("../variables.env")):
                if candidate.exists():
                    for line in candidate.read_text(encoding="utf-8").splitlines():
                        stripped = line.strip()
                        if stripped.startswith("DISCORD_BOT_TOKEN="):
                            token = stripped.split("=", 1)[1].strip()
                            break
                if token:
                    break

        if token:
            self._token_input.setText(token)
            self._status_lbl.setText(
                "Token loaded from variables.env — click 🔌 Connect"
            )

    # ── Bot connection ─────────────────────────────────────────────────────────

    def _on_connect(self) -> None:
        token = self._token_input.text().strip()
        if not token:
            QMessageBox.warning(
                self,
                "No Token",
                "Enter a Discord bot token, or add\n\n"
                "  DISCORD_BOT_TOKEN=<token>\n\n"
                "to variables.env and restart.",
            )
            return

        if not DISCORD_AVAILABLE:
            QMessageBox.critical(
                self,
                "discord.py Not Installed",
                "Install the Discord library:\n\n"
                "  pip install discord.py[voice] PyNaCl\n\n"
                "Then restart the app.",
            )
            return

        self._connect_btn.setEnabled(False)
        self._status_lbl.setText("⟳  Connecting…")
        self._status_lbl.setStyleSheet(f"color: {WARNING}; font-size: 10px;")

        # Create worker + thread
        self._thread = QThread(self)
        self._worker = _DiscordWorker(token)
        self._worker.moveToThread(self._thread)

        # Wire signals
        self._thread.started.connect(self._worker.run)
        self._worker.connected.connect(self._on_bot_connected)
        self._worker.disconnected.connect(self._on_bot_disconnected)
        self._worker.error.connect(self._on_bot_error)
        self._worker.channels_updated.connect(self._on_channels_updated)
        self._worker.members_updated.connect(self._on_members_updated)
        self._worker.transcript_ready.connect(self._on_transcript_ready)
        self._worker.command_detected.connect(self._on_command_detected)
        self._worker.spotify_command.connect(
            lambda a, q: self.spotify_command.emit(a, q)
        )

        # Scheduler signal forwarding
        self._worker.text_channels_updated.connect(self.text_channels_available)
        self._worker.poll_sent.connect(self.poll_sent_ok)
        self._worker.vote_updated.connect(self.vote_updated)
        self._worker.poll_error.connect(self.poll_error_sig)

        self._thread.start()

    def _on_disconnect(self) -> None:
        if self._worker:
            self._worker.stop()

    # ── Bot event slots ────────────────────────────────────────────────────────

    def _on_bot_connected(self, guild: str, user_tag: str) -> None:
        self._status_lbl.setText(f"● Connected  ·  {guild}  ·  {user_tag}")
        self._status_lbl.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        self._join_btn.setEnabled(True)
        self.status_message.emit(f"Discord: connected to {guild}")

    def _on_bot_disconnected(self, reason: str) -> None:
        self._status_lbl.setText(f"● Disconnected  ·  {reason}")
        self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._join_btn.setEnabled(False)
        self._record_btn.setEnabled(False)
        self._members_lbl.setText("👥  —")
        if self._thread:
            self._thread.quit()
        self.status_message.emit("Discord: disconnected")

    def _on_bot_error(self, message: str) -> None:
        self._status_lbl.setText(f"✗  {message[:120]}")
        self._status_lbl.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self.status_message.emit(f"Discord error: {message[:60]}")

    # ── Voice-channel slots ────────────────────────────────────────────────────

    def _on_channels_updated(self, channels: list) -> None:
        self._vc_combo.blockSignals(True)
        self._vc_combo.clear()
        for ch_id, ch_name in channels:
            self._vc_combo.addItem(ch_name, userData=int(ch_id))
        self._vc_combo.blockSignals(False)

        # Restore last-used channel if it's still in the list
        last_channel = self._settings.value("discord/last_channel", "", type=str)
        if last_channel:
            idx = self._vc_combo.findText(last_channel)
            if idx >= 0:
                self._vc_combo.setCurrentIndex(idx)

    def _on_join_vc(self) -> None:
        channel_id = self._vc_combo.currentData()
        if channel_id is not None and self._worker:
            ch_name = self._vc_combo.currentText()
            self._worker.join_voice_channel(int(channel_id))
            self._record_btn.setEnabled(True)
            self._settings.setValue("discord/last_channel", ch_name)
            self.status_message.emit(f"Discord: joining #{ch_name}")

    def _on_members_updated(self, names: list) -> None:
        self._members_lbl.setText(
            "👥  " + "  ·  ".join(names) if names else "👥  (empty channel)"
        )

    # ── Recording slots ────────────────────────────────────────────────────────

    def _on_start_recording(self) -> None:
        if not self._worker:
            return
        self._recording = True
        self._record_start = time.monotonic()
        self._rec_timer.start()
        self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._rec_status_lbl.setText("🔴 Recording  00:00:00  ·  0 words")
        self._rec_status_lbl.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
        self._worker.start_recording()
        self.status_message.emit("Discord: session recording started")

    def _on_stop_recording(self) -> None:
        if self._worker:
            self._worker.stop_recording()
        self._recording = False
        self._rec_timer.stop()
        self._record_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._save_btn.setEnabled(bool(self._transcript_lines))
        self._rec_status_lbl.setText("⏹  Recording stopped")
        self._rec_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self.status_message.emit("Discord: recording stopped")

    def _update_rec_display(self) -> None:
        """Refresh recording duration + word count every second."""
        if not self._recording or self._record_start is None:
            return
        elapsed = int(time.monotonic() - self._record_start)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        words = sum(len(line.split()) for line in self._transcript_lines)
        self._rec_status_lbl.setText(
            f"🔴 Recording  {h:02d}:{m:02d}:{s:02d}  ·  ~{words:,} words"
        )

    # ── Transcript slots ───────────────────────────────────────────────────────

    def _on_transcript_ready(self, timestamp: str, text: str) -> None:
        line = f"[{timestamp}] {text}"
        self._transcript_lines.append(line)
        self._transcript_view.append(line)
        self._save_btn.setEnabled(True)

    def _on_command_detected(self, cmd_type: str, raw_text: str) -> None:
        """Highlight wake-word commands in accent colour."""
        display = f"[⚡ {cmd_type.upper()}] {raw_text[:100]}"
        html = (
            f'<span style="color:{ACCENT}; font-weight:bold;">'
            f'{display}'
            f'</span>'
        )
        self._transcript_view.append(html)
        self.status_message.emit(f"Discord voice cmd: {cmd_type}")

    def _clear_transcript(self) -> None:
        self._transcript_lines.clear()
        self._transcript_view.clear()
        self._save_btn.setEnabled(False)

    # ── Save transcript ────────────────────────────────────────────────────────

    def _on_save_transcript(self) -> None:
        if not self._transcript_lines:
            QMessageBox.information(self, "Nothing to Save", "Transcript is empty.")
            return

        vault_path = self._get_vault_path()
        if vault_path is None:
            return

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        dest_dir = vault_path / "Sessions" / "Transcripts"
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path = dest_dir / f"Discord_Transcript_{ts}.md"

        word_count = sum(len(ln.split()) for ln in self._transcript_lines)
        md_lines: List[str] = [
            f"# Discord Session Transcript — {ts}",
            "",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d')}  ",
            f"**Lines:** {len(self._transcript_lines)}  ",
            f"**Words (approx):** {word_count:,}  ",
            "",
            "---",
            "",
        ]
        md_lines.extend(self._transcript_lines)
        md_lines.append("")

        try:
            out_path.write_text("\n".join(md_lines), encoding="utf-8")
            try:
                display_path = str(out_path.relative_to(vault_path))
            except ValueError:
                display_path = str(out_path)
            self.status_message.emit(f"Transcript saved: {out_path.name}")
            QMessageBox.information(
                self,
                "Transcript Saved",
                f"Saved to vault:\n{display_path}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", str(exc))

    def _get_vault_path(self) -> Optional[Path]:
        if (
            self._config
            and getattr(self._config, "current_vault", None)
            and self._config.current_vault in (getattr(self._config, "vaults", None) or {})
        ):
            return Path(self._config.vaults[self._config.current_vault])
        QMessageBox.warning(
            self,
            "No Vault Selected",
            "Select an Obsidian vault in the Vault / Notes panel first.",
        )
        return None

    # ── Spotify ────────────────────────────────────────────────────────────────

    def _on_spotify_search(self) -> None:
        query = self._spotify_search.text().strip()
        if query:
            self.spotify_command.emit("play", query)
            self._spotify_search.clear()

    # ── Scheduler public API ───────────────────────────────────────────────────

    def request_text_channels(self) -> None:
        """Ask the worker to emit the current guild's text channels."""
        if self._worker:
            self._worker.list_text_channels()

    def send_poll(
        self,
        channel_id: int,
        options: List[Tuple[str, str]],
        role_name: str,
    ) -> None:
        """Post a scheduling poll to *channel_id*. options = [(date, time), ...]."""
        if self._worker:
            self._worker.post_poll(channel_id, options, role_name)

    def close_poll(self) -> None:
        """Clear the active poll (no Discord message is deleted)."""
        if self._worker:
            self._worker.close_poll()

    def post_message_to_channel(self, channel_id: int, content: str) -> None:
        """Send a plain text message to a text channel."""
        if self._worker:
            self._worker.post_message(channel_id, content)

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:   # type: ignore[override]
        """Gracefully stop the bot and recording when the panel is closed."""
        if self._recording and self._worker:
            self._worker.stop_recording()
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)   # up to 3 s for clean asyncio shutdown
        super().closeEvent(event)
