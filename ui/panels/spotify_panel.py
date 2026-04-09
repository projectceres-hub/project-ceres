"""
Spotify panel for Project Ceres — GM Assistant UI.

Full Spotify integration via spotipy (OAuth2 Authorization Code + local callback).

Features
--------
  • OAuth2 via SpotifyOAuth — auto-connects on launch if credentials are present
  • Now Playing — 80×80 album art, track / artist / album, progress bar + clock
  • Playback controls — Play/Pause, Prev, Skip, Shuffle toggle, Repeat cycle, Volume
  • Search — text query, results list, double-click or button to play
  • Playlist browser — user's Spotify playlists, double-click or button to queue
  • Scene quick-launch — 8 configurable slots (right-click to assign a playlist URI)
  • Discord command slot — handle_command("play"/"pause"/"skip"/"search", query)
  • Auto-refresh — QTimer polls Spotify every 5 s; 1 s tick interpolates progress

Requirements
------------
    pip install spotipy

variables.env keys
------------------
    SPOTIFY_CLIENT_ID=<your_client_id>
    SPOTIFY_CLIENT_SECRET=<your_client_secret>
    SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

Create a Spotify Developer app at: https://developer.spotify.com/dashboard
Set the Redirect URI in the app dashboard to: http://localhost:8888/callback

Layout
------
  ┌─ 🎵 SPOTIFY ─────────────────────────────────────────┐
  │ ● Connected · paulius727          [Disconnect]        │
  ├──────────────────────────────────────────────────────│
  │ [ 🎵 Now Playing ]  [ 🔍 Search ]  [ 📚 Library ]    │
  │  ┌───────────────────────────────────────────────┐   │
  │  │ [🖼80]  The Witcher 3 OST                     │   │
  │  │         Marcin Przybyłowicz                   │   │
  │  │         The Witcher 3: Wild Hunt               │   │
  │  │  ████████░░░░░░░░  2:34 / 5:12                │   │
  │  │  [⏮] [▶/⏸] [⏭]   [⇌ Shuffle] [↻ Repeat]    │   │
  │  │  🔊 [════════════════]  80%                   │   │
  │  └───────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider, QProgressBar,
        QListWidget, QListWidgetItem, QTabWidget, QGridLayout,
        QSizePolicy, QMessageBox, QInputDialog, QMenu,
    )
    from PyQt5.QtCore import Qt, QThread, QObject, QTimer, pyqtSignal as Signal, pyqtSlot as Slot
    from PyQt5.QtGui import QPixmap
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider, QProgressBar,
        QListWidget, QListWidgetItem, QTabWidget, QGridLayout,
        QSizePolicy, QMessageBox, QInputDialog, QMenu,
    )
    from PySide6.QtCore import Qt, QThread, QObject, QTimer, Signal, Slot  # type: ignore
    from PySide6.QtGui import QPixmap  # type: ignore

from ui.theme import ACCENT, ACCENT2, BG, BORDER, MUTED, PANEL, SUCCESS, SURFACE, TEXT, WARNING, ERROR

# ── Optional dependency ────────────────────────────────────────────────────────

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    spotipy = None        # type: ignore[assignment]
    SpotifyOAuth = None   # type: ignore[assignment, misc]
    SPOTIPY_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────

SPOTIFY_SCOPE = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative"
)

POLL_INTERVAL_MS  = 5_000   # API poll cadence
PROGRESS_TICK_MS  = 1_000   # local progress interpolation cadence
ALBUM_ART_SIZE    = 80       # pixels

REPEAT_MODES: List[str] = ["off", "context", "track"]

# Eight scene-tag slots shown in the Library tab
SCENE_TAGS: List[Tuple[str, str]] = [
    ("⚔  Combat",   "combat"),
    ("🌿  Ambient",  "ambient"),
    ("🍺  Tavern",   "tavern"),
    ("🗺  Travel",   "travel"),
    ("😈  Villain",  "villain"),
    ("🏆  Victory",  "victory"),
    ("💀  Dungeon",  "dungeon"),
    ("🌙  Night",    "night"),
]

_PROJECT_ROOT      = Path(__file__).resolve().parent.parent.parent
SCENE_CONFIG_PATH  = _PROJECT_ROOT / "scene_playlists.json"
SPOTIFY_CACHE_PATH = str(_PROJECT_ROOT / ".spotipyoauthcache")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ms_to_str(ms: int) -> str:
    """Convert milliseconds to M:SS string."""
    total_s = max(ms, 0) // 1000
    m, s = divmod(total_s, 60)
    return f"{m}:{s:02d}"


def _normalize_spotify_uri(text: str) -> str:
    """Convert a Spotify playlist URL or URI to a spotify:playlist:<id> URI."""
    text = text.strip()
    if text.startswith("spotify:"):
        return text
    # https://open.spotify.com/playlist/4abc123?si=xxx  →  spotify:playlist:4abc123
    if "open.spotify.com" in text:
        try:
            path_part = text.split("open.spotify.com/")[1].split("?")[0]
            parts = path_part.strip("/").split("/")
            if len(parts) >= 2:
                return f"spotify:{parts[0]}:{parts[1]}"
        except Exception:
            pass
    return ""


# ── Background worker ──────────────────────────────────────────────────────────

class _SpotifyWorker(QObject):
    """
    All spotipy API calls run in this QObject (moved to a QThread).
    Communicates with SpotifyPanel exclusively through Qt signals.
    """

    # ── Signals emitted toward SpotifyPanel (main thread) ─────────────────────
    auth_success     = Signal(str)        # display_name
    auth_failed      = Signal(str)        # error message
    playback_updated = Signal(dict)       # current_playback() dict (or {} for nothing)
    search_results   = Signal(list)       # list of track dicts
    playlists_loaded = Signal(list)       # list of playlist dicts
    artwork_loaded   = Signal(str, bytes) # (image_url, raw_bytes)
    command_done     = Signal(str)        # brief status message
    error            = Signal(str)        # error message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._sp: Optional["spotipy.Spotify"] = None
        self._lock = threading.Lock()
        self._last_artwork_url = ""
        self._poll_timer: Optional[QTimer] = None   # created lazily in do_connect

    # ── Inbound slots (invoked via queued connections from main thread) ────────

    @Slot(str, str, str)
    def do_connect(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        if not SPOTIPY_AVAILABLE:
            self.auth_failed.emit(
                "spotipy not installed.\nRun:  pip install spotipy"
            )
            return
        try:
            auth_manager = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=SPOTIFY_SCOPE,
                cache_path=SPOTIFY_CACHE_PATH,
                open_browser=True,
            )
            sp = spotipy.Spotify(auth_manager=auth_manager)
            # Triggers actual auth — may open browser + block for callback
            me = sp.me()
            with self._lock:
                self._sp = sp
            display_name = me.get("display_name") or me.get("id") or "Spotify User"
            self.auth_success.emit(display_name)
            # Start poll timer (now we're in the worker thread)
            if self._poll_timer is None:
                self._poll_timer = QTimer(self)
                self._poll_timer.timeout.connect(self._poll_playback)
            self._poll_timer.start(POLL_INTERVAL_MS)
            # Populate library immediately
            self.do_load_playlists()
            self._poll_playback()
        except Exception as exc:
            self.auth_failed.emit(str(exc))

    @Slot()
    def do_disconnect(self) -> None:
        if self._poll_timer:
            self._poll_timer.stop()
        with self._lock:
            self._sp = None
        self.command_done.emit("Disconnected")

    @Slot(str)
    def do_search(self, query: str) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            results = sp.search(q=query, type="track", limit=20)
            items = (results.get("tracks") or {}).get("items") or []
            tracks = []
            for t in items:
                artists = ", ".join(a["name"] for a in (t.get("artists") or []))
                tracks.append({
                    "name":        t.get("name", ""),
                    "artist":      artists,
                    "album":       (t.get("album") or {}).get("name", ""),
                    "uri":         t.get("uri", ""),
                    "duration_ms": t.get("duration_ms", 0),
                })
            self.search_results.emit(tracks)
        except Exception as exc:
            self.error.emit(f"Search error: {exc}")

    @Slot()
    def do_load_playlists(self) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            results = sp.current_user_playlists(limit=50)
            playlists = []
            for p in (results.get("items") or []):
                playlists.append({
                    "name": p.get("name", ""),
                    "uri":  p.get("uri",  ""),
                    "id":   p.get("id",   ""),
                })
            self.playlists_loaded.emit(playlists)
        except Exception as exc:
            self.error.emit(f"Playlist load error: {exc}")

    @Slot(str)
    def do_play_track(self, uri: str) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.start_playback(uris=[uri])
            self.command_done.emit("▶ Playing")
            QTimer.singleShot(600, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Play error: {exc}")

    @Slot(str)
    def do_play_context(self, context_uri: str) -> None:
        """Play a playlist, album, or artist context URI."""
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.start_playback(context_uri=context_uri)
            self.command_done.emit("▶ Playing playlist")
            QTimer.singleShot(600, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Play context error: {exc}")

    @Slot()
    def do_pause(self) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.pause_playback()
            self.command_done.emit("⏸ Paused")
            QTimer.singleShot(400, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Pause error: {exc}")

    @Slot()
    def do_resume(self) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.start_playback()
            self.command_done.emit("▶ Resumed")
            QTimer.singleShot(400, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Resume error: {exc}")

    @Slot()
    def do_previous(self) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.previous_track()
            self.command_done.emit("⏮ Previous")
            QTimer.singleShot(600, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Previous track error: {exc}")

    @Slot()
    def do_next(self) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.next_track()
            self.command_done.emit("⏭ Next")
            QTimer.singleShot(600, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Next track error: {exc}")

    @Slot(int)
    def do_set_volume(self, volume_percent: int) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.volume(volume_percent)
        except Exception as exc:
            self.error.emit(f"Volume error: {exc}")

    @Slot(bool)
    def do_set_shuffle(self, state: bool) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.shuffle(state)
            self.command_done.emit(f"Shuffle {'on' if state else 'off'}")
            QTimer.singleShot(400, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Shuffle error: {exc}")

    @Slot(str)
    def do_set_repeat(self, mode: str) -> None:
        """mode must be 'off', 'context', or 'track'."""
        sp = self._get_sp()
        if sp is None:
            return
        try:
            sp.repeat(mode)
            self.command_done.emit(f"Repeat: {mode}")
            QTimer.singleShot(400, self._poll_playback)
        except Exception as exc:
            self.error.emit(f"Repeat error: {exc}")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _get_sp(self) -> Optional["spotipy.Spotify"]:
        with self._lock:
            return self._sp

    def _poll_playback(self) -> None:
        sp = self._get_sp()
        if sp is None:
            return
        try:
            pb = sp.current_playback()
            self.playback_updated.emit(pb or {})
            # Fetch album art if the track changed
            if pb:
                track = pb.get("item") or {}
                images = (track.get("album") or {}).get("images") or []
                art_url = images[0]["url"] if images else ""
                if art_url and art_url != self._last_artwork_url:
                    self._last_artwork_url = art_url
                    self._fetch_artwork(art_url)
        except Exception as exc:
            self.error.emit(f"Playback poll error: {exc}")

    def _fetch_artwork(self, url: str) -> None:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read()
            self.artwork_loaded.emit(url, bytes(data))
        except Exception:
            pass  # artwork fetch failure is non-critical


# ── Main panel ─────────────────────────────────────────────────────────────────

class SpotifyPanel(QDockWidget):
    """
    Dockable Spotify integration panel.

    Signals:
        status_message(msg) — forwarded to the main window status bar

    Public slot:
        handle_command(action, query) — called by DiscordPanel.spotify_command signal
    """

    status_message: Signal = Signal(str)
    volume_changed: Signal = Signal(int)

    # ── Signals routed to the worker (queued, cross-thread) ───────────────────
    _sig_connect     = Signal(str, str, str)
    _sig_disconnect  = Signal()
    _sig_search      = Signal(str)
    _sig_load_plists = Signal()
    _sig_play_track  = Signal(str)
    _sig_play_ctx    = Signal(str)
    _sig_pause       = Signal()
    _sig_resume      = Signal()
    _sig_previous    = Signal()
    _sig_next        = Signal()
    _sig_set_vol     = Signal(int)
    _sig_set_shuffle = Signal(bool)
    _sig_set_repeat  = Signal(str)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Spotify", parent)
        self.setObjectName("SpotifyPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable    |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable  |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config      = config
        self._run_command = run_command

        # Playback state (kept in sync by _on_playback_updated)
        self._is_playing          = False
        self._progress_ms         = 0
        self._duration_ms         = 0
        self._shuffle_on          = False
        self._repeat_mode         = "off"
        self._current_context_uri = ""
        self._auto_play_first     = False
        self._artwork_cache: Dict[str, QPixmap] = {}

        # Scene config: tag → {"name": ..., "uri": ...}  or None
        self._scene_config: Dict[str, Optional[Dict]] = {
            tag: None for _, tag in SCENE_TAGS
        }
        self._scene_buttons: Dict[str, QPushButton] = {}

        self._load_scene_config()
        self._build_ui()
        self._setup_worker()

        # Auto-connect on launch if credentials are present
        cid, csec, ruri = self._load_credentials()
        if cid and csec:
            QTimer.singleShot(1200, lambda: self._do_connect(cid, csec, ruri))

    # ── Credentials ───────────────────────────────────────────────────────────

    def _load_credentials(self) -> Tuple[str, str, str]:
        """Load SPOTIFY_* keys from environment variables or variables.env."""
        cid  = os.environ.get("SPOTIFY_CLIENT_ID", "")
        csec = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        ruri = os.environ.get("SPOTIFY_REDIRECT_URI", "")

        if not (cid and csec):
            # Walk up directory tree to find variables.env
            here = Path(__file__).resolve().parent
            for _ in range(6):
                env_path = here / "variables.env"
                if env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip()
                        if k == "SPOTIFY_CLIENT_ID":
                            cid = v
                        elif k == "SPOTIFY_CLIENT_SECRET":
                            csec = v
                        elif k == "SPOTIFY_REDIRECT_URI":
                            ruri = v
                    break
                here = here.parent

        return cid, csec, ruri or "http://localhost:8888/callback"

    # ── Scene config persistence ──────────────────────────────────────────────

    def _load_scene_config(self) -> None:
        try:
            if SCENE_CONFIG_PATH.exists():
                data = json.loads(SCENE_CONFIG_PATH.read_text(encoding="utf-8"))
                for _, tag in SCENE_TAGS:
                    if tag in data:
                        self._scene_config[tag] = data[tag]
        except Exception:
            pass

    def _save_scene_config(self) -> None:
        try:
            SCENE_CONFIG_PATH.write_text(
                json.dumps(self._scene_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Worker thread setup ───────────────────────────────────────────────────

    def _setup_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = _SpotifyWorker()
        self._worker.moveToThread(self._thread)

        # Worker → panel
        self._worker.auth_success.connect(self._on_auth_success)
        self._worker.auth_failed.connect(self._on_auth_failed)
        self._worker.playback_updated.connect(self._on_playback_updated)
        self._worker.search_results.connect(self._on_search_results)
        self._worker.playlists_loaded.connect(self._on_playlists_loaded)
        self._worker.artwork_loaded.connect(self._on_artwork_loaded)
        self._worker.command_done.connect(
            lambda msg: self.status_message.emit(f"Spotify: {msg}")
        )
        self._worker.error.connect(self._on_worker_error)

        # Panel → worker  (these become QueuedConnections because of moveToThread)
        self._sig_connect.connect(self._worker.do_connect)
        self._sig_disconnect.connect(self._worker.do_disconnect)
        self._sig_search.connect(self._worker.do_search)
        self._sig_load_plists.connect(self._worker.do_load_playlists)
        self._sig_play_track.connect(self._worker.do_play_track)
        self._sig_play_ctx.connect(self._worker.do_play_context)
        self._sig_pause.connect(self._worker.do_pause)
        self._sig_resume.connect(self._worker.do_resume)
        self._sig_previous.connect(self._worker.do_previous)
        self._sig_next.connect(self._worker.do_next)
        self._sig_set_vol.connect(self._worker.do_set_volume)
        self._sig_set_shuffle.connect(self._worker.do_set_shuffle)
        self._sig_set_repeat.connect(self._worker.do_set_repeat)

        self._thread.start()

        # Progress interpolation timer runs in the main thread
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(PROGRESS_TICK_MS)
        self._progress_timer.timeout.connect(self._tick_progress)

        # Volume debounce timer
        self._vol_debounce = QTimer(self)
        self._vol_debounce.setSingleShot(True)
        self._vol_debounce.setInterval(400)
        self._vol_debounce.timeout.connect(
            lambda: self._sig_set_vol.emit(self._vol_slider.value())
        )

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── Status row ──────────────────────────────────────────────────────
        status_row = QHBoxLayout()

        self._dot_label = QLabel("●")
        self._dot_label.setFixedWidth(16)
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        status_row.addWidget(self._dot_label)

        self._status_label = QLabel("Not connected")
        self._status_label.setStyleSheet(f"color: {MUTED};")
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        status_row.addWidget(self._status_label, 1)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setProperty("class", "accent")
        self._connect_btn.setFixedWidth(92)
        self._connect_btn.setToolTip(
            "Authenticate with Spotify (opens browser on first use)"
        )
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        status_row.addWidget(self._connect_btn)

        layout.addLayout(status_row)

        # ── Credentials warning (hidden when creds present) ─────────────────
        cid, csec, _ = self._load_credentials()
        if not (cid and csec):
            warn = QLabel(
                "⚠  Add to variables.env:\n"
                "  SPOTIFY_CLIENT_ID=...\n"
                "  SPOTIFY_CLIENT_SECRET=...\n"
                "  SPOTIFY_REDIRECT_URI=http://localhost:8888/callback\n"
                "  (create app at developer.spotify.com/dashboard)"
            )
            warn.setStyleSheet(
                f"color: {WARNING}; font-size: 9px; padding: 5px;"
                f"border: 1px solid {WARNING}; border-radius: 3px;"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # ── Tab widget ───────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_now_playing_tab(), "🎵 Now Playing")
        self._tabs.addTab(self._build_search_tab(),      "🔍 Search")
        self._tabs.addTab(self._build_library_tab(),     "📚 Library")
        layout.addWidget(self._tabs, 1)

        self.setWidget(outer)
        self._set_controls_enabled(False)

    # ── Now Playing tab ───────────────────────────────────────────────────────

    def _build_now_playing_tab(self) -> QWidget:
        w = QWidget()
        vlay = QVBoxLayout(w)
        vlay.setContentsMargins(6, 8, 6, 6)
        vlay.setSpacing(8)

        # Track info row: album art (left) + text (right)
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        self._art_label = QLabel("🎵")
        self._art_label.setFixedSize(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        self._art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        self._art_label.setStyleSheet(
            f"background: {SURFACE}; border: 1px solid {BORDER};"
            f"border-radius: 4px; font-size: 28px; color: {MUTED};"
        )
        info_row.addWidget(self._art_label)

        txt_col = QVBoxLayout()
        txt_col.setSpacing(3)

        self._track_label = QLabel("— not playing —")
        self._track_label.setStyleSheet(
            f"color: {TEXT}; font-weight: bold; font-size: 11px;"
        )
        self._track_label.setWordWrap(True)

        self._artist_label = QLabel("")
        self._artist_label.setStyleSheet(f"color: {ACCENT}; font-size: 10px;")
        self._artist_label.setWordWrap(True)

        self._album_label = QLabel("")
        self._album_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._album_label.setWordWrap(True)

        txt_col.addWidget(self._track_label)
        txt_col.addWidget(self._artist_label)
        txt_col.addWidget(self._album_label)
        txt_col.addStretch()

        info_row.addLayout(txt_col, 1)
        vlay.addLayout(info_row)

        # Progress bar + time label
        prog_row = QHBoxLayout()
        prog_row.setSpacing(6)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        prog_row.addWidget(self._progress_bar, 1)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._time_label.setFixedWidth(72)
        prog_row.addWidget(self._time_label)

        vlay.addLayout(prog_row)

        # Playback control row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)

        self._prev_btn = QPushButton("⏮")
        self._prev_btn.setFixedSize(34, 30)
        self._prev_btn.setToolTip("Previous track")
        self._prev_btn.clicked.connect(self._on_prev)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(42, 30)
        self._play_btn.setProperty("class", "accent")
        self._play_btn.setToolTip("Play / Pause  (Space)")
        self._play_btn.clicked.connect(self._on_play_pause)

        self._next_btn = QPushButton("⏭")
        self._next_btn.setFixedSize(34, 30)
        self._next_btn.setToolTip("Next track")
        self._next_btn.clicked.connect(self._on_next)

        for b in (self._prev_btn, self._play_btn, self._next_btn):
            ctrl_row.addWidget(b)

        ctrl_row.addSpacing(8)

        self._shuffle_btn = QPushButton("⇌")
        self._shuffle_btn.setFixedSize(34, 30)
        self._shuffle_btn.setCheckable(True)
        self._shuffle_btn.setToolTip("Toggle shuffle")
        self._shuffle_btn.clicked.connect(self._on_shuffle)

        self._repeat_btn = QPushButton("↻")
        self._repeat_btn.setFixedSize(34, 30)
        self._repeat_btn.setToolTip("Cycle repeat: off → playlist → track")
        self._repeat_btn.clicked.connect(self._on_repeat)

        ctrl_row.addWidget(self._shuffle_btn)
        ctrl_row.addWidget(self._repeat_btn)
        ctrl_row.addStretch()

        vlay.addLayout(ctrl_row)

        # Volume row
        vol_row = QHBoxLayout()
        vol_row.setSpacing(6)

        vol_lbl = QLabel("🔊")
        vol_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        vol_lbl.setFixedWidth(18)
        vol_row.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setToolTip("Volume")
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self._vol_slider, 1)

        self._vol_label = QLabel("80%")
        self._vol_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._vol_label.setFixedWidth(30)
        vol_row.addWidget(self._vol_label)

        vlay.addLayout(vol_row)
        vlay.addStretch()

        return w

    # ── Search tab ────────────────────────────────────────────────────────────

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        vlay = QVBoxLayout(w)
        vlay.setContentsMargins(6, 8, 6, 6)
        vlay.setSpacing(6)

        search_row = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Track, artist, or album…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input, 1)

        search_go = QPushButton("Search")
        search_go.setFixedWidth(58)
        search_go.clicked.connect(self._on_search)
        search_row.addWidget(search_go)

        vlay.addLayout(search_row)

        results_hdr = QHBoxLayout()
        results_lbl = QLabel("Results")
        results_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        results_hdr.addWidget(results_lbl, 1)

        play_sel_btn = QPushButton("▶ Play")
        play_sel_btn.setFixedWidth(52)
        play_sel_btn.setToolTip("Play selected result")
        play_sel_btn.clicked.connect(self._on_play_selected_result)
        results_hdr.addWidget(play_sel_btn)

        vlay.addLayout(results_hdr)

        self._search_results = QListWidget()
        self._search_results.setAlternatingRowColors(True)
        self._search_results.setToolTip("Double-click to play")
        self._search_results.itemDoubleClicked.connect(
            self._on_result_double_clicked
        )
        vlay.addWidget(self._search_results, 1)

        return w

    # ── Library tab ───────────────────────────────────────────────────────────

    def _build_library_tab(self) -> QWidget:
        w = QWidget()
        vlay = QVBoxLayout(w)
        vlay.setContentsMargins(6, 8, 6, 6)
        vlay.setSpacing(6)

        # ── Playlist browser ─────────────────────────────────────────────────
        plist_hdr = QHBoxLayout()
        plist_lbl = QLabel("Your Playlists")
        plist_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        plist_hdr.addWidget(plist_lbl, 1)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh playlists")
        refresh_btn.clicked.connect(lambda: self._sig_load_plists.emit())
        plist_hdr.addWidget(refresh_btn)

        play_plist_btn = QPushButton("▶ Play")
        play_plist_btn.setFixedWidth(52)
        play_plist_btn.setToolTip("Play selected playlist")
        play_plist_btn.clicked.connect(self._on_play_selected_playlist)
        plist_hdr.addWidget(play_plist_btn)

        vlay.addLayout(plist_hdr)

        self._playlist_list = QListWidget()
        self._playlist_list.setAlternatingRowColors(True)
        self._playlist_list.setMaximumHeight(130)
        self._playlist_list.setToolTip("Double-click to play playlist")
        self._playlist_list.itemDoubleClicked.connect(
            self._on_playlist_double_clicked
        )
        vlay.addWidget(self._playlist_list)

        # ── Separator ────────────────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER};")
        vlay.addWidget(sep)

        # ── Scene quick-launch ────────────────────────────────────────────────
        scene_lbl = QLabel("Scene Quick-Launch")
        scene_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        vlay.addWidget(scene_lbl)

        scene_hint = QLabel("Click to play  ·  Right-click to assign a playlist")
        scene_hint.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        vlay.addWidget(scene_hint)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (label, tag) in enumerate(SCENE_TAGS):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu  # type: ignore[attr-defined]
            )
            btn.customContextMenuRequested.connect(
                lambda pos, t=tag, b=btn: self._on_scene_context_menu(b, t, pos)
            )
            btn.clicked.connect(lambda checked, t=tag: self._on_scene_clicked(t))
            self._scene_buttons[tag] = btn
            self._update_scene_btn_style(tag)
            btn.setToolTip(self._scene_tooltip(tag))
            grid.addWidget(btn, i // 3, i % 3)

        vlay.addWidget(grid_w)
        vlay.addStretch()

        return w

    # ── Scene button helpers ──────────────────────────────────────────────────

    def _scene_tooltip(self, tag: str) -> str:
        assigned = self._scene_config.get(tag)
        if assigned:
            return f"▶ Play: {assigned.get('name', tag)}\nRight-click to reassign"
        return f"No playlist assigned\nRight-click to assign one"

    def _update_scene_btn_style(self, tag: str) -> None:
        btn = self._scene_buttons.get(tag)
        if btn is None:
            return
        if self._scene_config.get(tag):
            btn.setStyleSheet(
                f"QPushButton {{ background: {ACCENT2}; color: {TEXT};"
                f" border: 1px solid {ACCENT}; border-radius: 3px; }}"
                f"QPushButton:hover {{ background: {ACCENT}; }}"
            )
        else:
            btn.setStyleSheet("")   # fall back to global stylesheet

    # ── Worker signal handlers ────────────────────────────────────────────────

    def _on_auth_success(self, display_name: str) -> None:
        self._dot_label.setStyleSheet(f"color: {SUCCESS}; font-size: 14px;")
        self._status_label.setText(f"Connected · {display_name}")
        self._connect_btn.setText("Disconnect")
        self._connect_btn.setEnabled(True)
        self._set_controls_enabled(True)
        self._progress_timer.start()
        self.status_message.emit(f"Spotify: connected as {display_name}")

    def _on_auth_failed(self, error_msg: str) -> None:
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        self._status_label.setText("Auth failed")
        self._connect_btn.setText("Connect")
        self._connect_btn.setEnabled(True)
        self.status_message.emit(f"Spotify auth failed: {error_msg}")

    def _on_playback_updated(self, state: dict) -> None:
        if not state:
            self._track_label.setText("— not playing —")
            self._artist_label.setText("")
            self._album_label.setText("")
            self._time_label.setText("0:00 / 0:00")
            self._progress_bar.setValue(0)
            self._play_btn.setText("▶")
            self._is_playing = False
            return

        track = state.get("item") or {}
        self._is_playing  = state.get("is_playing", False)
        self._progress_ms = state.get("progress_ms", 0)
        self._duration_ms = track.get("duration_ms", 0)

        # Track context (for "assign current playlist")
        ctx = state.get("context") or {}
        self._current_context_uri = ctx.get("uri", "")

        # Labels
        track_name = track.get("name", "—")
        artists    = ", ".join(a["name"] for a in (track.get("artists") or []))
        album_name = (track.get("album") or {}).get("name", "")

        self._track_label.setText(track_name)
        self._artist_label.setText(artists)
        self._album_label.setText(album_name)

        self._update_progress_display()
        self._play_btn.setText("⏸" if self._is_playing else "▶")

        # Shuffle / Repeat sync
        self._shuffle_on  = state.get("shuffle_state", False)
        self._repeat_mode = state.get("repeat_state", "off")
        self._shuffle_btn.setChecked(self._shuffle_on)
        self._update_repeat_btn()

        # Volume sync from active device
        device = state.get("device") or {}
        vol = device.get("volume_percent")
        if vol is not None:
            self._vol_slider.blockSignals(True)
            self._vol_slider.setValue(vol)
            self._vol_label.setText(f"{vol}%")
            self._vol_slider.blockSignals(False)

    def _on_search_results(self, tracks: list) -> None:
        self._search_results.clear()

        # Auto-play first result if triggered by a Discord "!play <query>" command
        if self._auto_play_first and tracks:
            self._auto_play_first = False
            uri = tracks[0].get("uri", "")
            if uri:
                self._sig_play_track.emit(uri)
            return

        for t in tracks:
            dur  = _ms_to_str(t.get("duration_ms", 0))
            text = f"{t['name']}  ·  {t['artist']}  [{dur}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t.get("uri", ""))  # type: ignore[attr-defined]
            item.setToolTip(f"Album: {t['album']}")
            self._search_results.addItem(item)

        if not tracks:
            self._search_results.addItem("No results found.")

        self._tabs.setCurrentIndex(1)   # switch to Search tab

    def _on_playlists_loaded(self, playlists: list) -> None:
        self._playlist_list.clear()
        for p in playlists:
            item = QListWidgetItem(p["name"])
            item.setData(Qt.ItemDataRole.UserRole, p["uri"])  # type: ignore[attr-defined]
            self._playlist_list.addItem(item)

    def _on_artwork_loaded(self, url: str, data: bytes) -> None:
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    ALBUM_ART_SIZE, ALBUM_ART_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,              # type: ignore[attr-defined]
                    Qt.TransformationMode.SmoothTransformation,      # type: ignore[attr-defined]
                )
                self._artwork_cache[url] = pixmap
                self._art_label.setPixmap(pixmap)
                self._art_label.setStyleSheet(
                    "border: 1px solid #2a2a4a; border-radius: 4px;"
                )
        except Exception:
            pass

    def _on_worker_error(self, error_msg: str) -> None:
        self.status_message.emit(f"Spotify error: {error_msg}")

    # ── User interaction slots ────────────────────────────────────────────────

    def _on_connect_clicked(self) -> None:
        if self._connect_btn.text() == "Disconnect":
            self._disconnect()
            return

        cid, csec, ruri = self._load_credentials()
        if not (cid and csec):
            QMessageBox.warning(
                self, "Spotify Credentials Missing",
                "Add your Spotify app credentials to variables.env:\n\n"
                "  SPOTIFY_CLIENT_ID=<your_client_id>\n"
                "  SPOTIFY_CLIENT_SECRET=<your_client_secret>\n"
                "  SPOTIFY_REDIRECT_URI=http://localhost:8888/callback\n\n"
                "Create a Spotify Developer app at:\n"
                "  https://developer.spotify.com/dashboard\n\n"
                "Add  http://localhost:8888/callback  as a Redirect URI in the app settings.",
            )
            return

        self._do_connect(cid, csec, ruri)

    def _do_connect(self, cid: str, csec: str, ruri: str) -> None:
        self._status_label.setText("Connecting… (check browser)")
        self._dot_label.setStyleSheet(f"color: {WARNING}; font-size: 14px;")
        self._connect_btn.setEnabled(False)
        self._sig_connect.emit(cid, csec, ruri)

    def _disconnect(self) -> None:
        self._progress_timer.stop()
        self._sig_disconnect.emit()
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        self._status_label.setText("Not connected")
        self._connect_btn.setText("Connect")
        self._set_controls_enabled(False)
        # Clear Now Playing display
        self._track_label.setText("— not playing —")
        self._artist_label.setText("")
        self._album_label.setText("")
        self._art_label.clear()
        self._art_label.setText("🎵")
        self._art_label.setStyleSheet(
            f"background: {SURFACE}; border: 1px solid {BORDER};"
            f"border-radius: 4px; font-size: 28px; color: {MUTED};"
        )
        self._progress_bar.setValue(0)
        self._time_label.setText("0:00 / 0:00")

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            return
        self._sig_search.emit(query)
        self.status_message.emit(f"Spotify: searching '{query}'…")

    def _on_result_double_clicked(self, item: QListWidgetItem) -> None:
        uri = item.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if uri:
            self._sig_play_track.emit(uri)

    def _on_play_selected_result(self) -> None:
        selected = self._search_results.selectedItems()
        if not selected:
            return
        uri = selected[0].data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if uri:
            self._sig_play_track.emit(uri)

    def _on_playlist_double_clicked(self, item: QListWidgetItem) -> None:
        uri = item.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if uri:
            self._sig_play_ctx.emit(uri)

    def _on_play_selected_playlist(self) -> None:
        selected = self._playlist_list.selectedItems()
        if not selected:
            return
        uri = selected[0].data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if uri:
            self._sig_play_ctx.emit(uri)

    def _on_play_pause(self) -> None:
        if self._is_playing:
            self._sig_pause.emit()
        else:
            self._sig_resume.emit()

    def _on_prev(self) -> None:
        self._sig_previous.emit()

    def _on_next(self) -> None:
        self._sig_next.emit()

    def _on_shuffle(self, checked: bool) -> None:
        self._sig_set_shuffle.emit(checked)

    def _on_repeat(self) -> None:
        idx = REPEAT_MODES.index(self._repeat_mode) if self._repeat_mode in REPEAT_MODES else 0
        self._repeat_mode = REPEAT_MODES[(idx + 1) % len(REPEAT_MODES)]
        self._update_repeat_btn()
        self._sig_set_repeat.emit(self._repeat_mode)

    def _on_volume_changed(self, value: int) -> None:
        self._vol_label.setText(f"{value}%")
        self._vol_debounce.start()  # restart debounce window
        self.volume_changed.emit(value)

    def get_volume(self) -> int:
        """Return the current volume slider value (0–100)."""
        return self._vol_slider.value()

    @Slot(int)
    def set_volume(self, value: int) -> None:
        """Set volume without triggering a volume_changed echo.

        Args:
            value: Volume level 0–100 sent by the Mixer panel.
        """
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(value)
        self._vol_label.setText(f"{value}%")
        self._vol_slider.blockSignals(False)
        # Push directly to Spotify device — bypass the debounce for responsiveness.
        self._sig_set_vol.emit(value)

    # ── Scene interaction ─────────────────────────────────────────────────────

    def _on_scene_clicked(self, tag: str) -> None:
        assigned = self._scene_config.get(tag)
        if assigned and assigned.get("uri"):
            self._sig_play_ctx.emit(assigned["uri"])
            self.status_message.emit(
                f"Spotify: ▶ {assigned.get('name', tag)}"
            )
        else:
            reply = QMessageBox.question(
                self, "No Playlist Assigned",
                f"The «{tag}» scene slot has no playlist assigned yet.\n\n"
                "Assign one now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._assign_scene_by_uri(tag)

    def _on_scene_context_menu(
        self, btn: QPushButton, tag: str, pos
    ) -> None:
        menu = QMenu(self)

        assigned = self._scene_config.get(tag)
        if assigned and assigned.get("uri"):
            play_act = menu.addAction(f"▶  Play: {assigned.get('name', tag)}")
            play_act.triggered.connect(lambda: self._on_scene_clicked(tag))
            menu.addSeparator()

        assign_current = menu.addAction("📌  Assign currently-playing playlist")
        assign_current.triggered.connect(lambda: self._assign_current_context(tag))

        assign_uri = menu.addAction("🔗  Assign by Spotify URL / URI…")
        assign_uri.triggered.connect(lambda: self._assign_scene_by_uri(tag))

        if assigned:
            menu.addSeparator()
            clear_act = menu.addAction("✕  Clear assignment")
            clear_act.triggered.connect(lambda: self._clear_scene(tag))

        menu.exec(btn.mapToGlobal(pos))

    def _assign_scene_by_uri(self, tag: str) -> None:
        """Prompt user to paste a Spotify playlist URL or URI."""
        text, ok = QInputDialog.getText(
            self,
            f"Assign Playlist — {tag}",
            "Paste Spotify playlist URL or URI:\n"
            "  e.g.  https://open.spotify.com/playlist/4abc123\n"
            "  or    spotify:playlist:4abc123",
        )
        if not ok or not text.strip():
            return

        uri = _normalize_spotify_uri(text.strip())
        if not uri or not uri.startswith("spotify:playlist:"):
            QMessageBox.warning(
                self, "Invalid Playlist",
                "That doesn't look like a valid Spotify playlist URL or URI.\n\n"
                "Make sure you're using a Playlist link, not a track or album.",
            )
            return

        name, ok2 = QInputDialog.getText(
            self,
            "Playlist Name",
            f"Short label for the «{tag}» button tooltip:",
            text=tag.capitalize(),
        )
        if not ok2:
            name = tag.capitalize()

        self._save_scene_assignment(tag, name or tag.capitalize(), uri)

    def _assign_current_context(self, tag: str) -> None:
        """Assign whatever playlist is currently playing to a scene slot."""
        uri = self._current_context_uri
        if not uri or not uri.startswith("spotify:playlist:"):
            QMessageBox.information(
                self, "No Playlist Context",
                "No playlist is currently playing (or Spotify is using a\n"
                "non-playlist context such as an album, artist, or radio).\n\n"
                "Use 'Assign by URL/URI' instead.",
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "Playlist Name",
            f"Short label for the «{tag}» button tooltip:",
            text=tag.capitalize(),
        )
        if not ok:
            name = tag.capitalize()

        self._save_scene_assignment(tag, name or tag.capitalize(), uri)

    def _save_scene_assignment(self, tag: str, name: str, uri: str) -> None:
        self._scene_config[tag] = {"name": name, "uri": uri}
        self._save_scene_config()
        self._update_scene_btn_style(tag)
        btn = self._scene_buttons.get(tag)
        if btn:
            btn.setToolTip(self._scene_tooltip(tag))
        self.status_message.emit(f"Spotify: assigned «{name}» to {tag} scene")

    def _clear_scene(self, tag: str) -> None:
        self._scene_config[tag] = None
        self._save_scene_config()
        self._update_scene_btn_style(tag)
        btn = self._scene_buttons.get(tag)
        if btn:
            btn.setToolTip(self._scene_tooltip(tag))
        self.status_message.emit(f"Spotify: cleared {tag} scene assignment")

    # ── Discord command handler ───────────────────────────────────────────────

    @Slot(str, str)
    def handle_command(self, action: str, query: str) -> None:
        """
        Called by DiscordPanel.spotify_command signal.

        Supported actions
        -----------------
        play   — resume if no query, else search + auto-play first result
        pause  — pause playback
        skip   — skip to next track
        search — run search and show results (no auto-play)
        """
        action = action.lower().strip()
        self.status_message.emit(
            f"Spotify ← Discord: {action!r}  query={query!r}"
        )

        if action == "pause":
            self._sig_pause.emit()

        elif action == "play":
            if query.strip():
                # Search Spotify and auto-play the first hit
                self._auto_play_first = True
                self._sig_search.emit(query.strip())
            else:
                self._sig_resume.emit()

        elif action == "skip":
            self._sig_next.emit()

        elif action == "search":
            if query.strip():
                self._search_input.setText(query.strip())
                self._sig_search.emit(query.strip())
                self._tabs.setCurrentIndex(1)   # switch to Search tab

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._prev_btn,
            self._play_btn,
            self._next_btn,
            self._shuffle_btn,
            self._repeat_btn,
            self._vol_slider,
            self._search_input,
        ):
            widget.setEnabled(enabled)

        for btn in self._scene_buttons.values():
            btn.setEnabled(enabled)

    def _update_repeat_btn(self) -> None:
        icons = {"off": "↻", "context": "↻¹", "track": "↺¹"}
        tips  = {
            "off":     "Repeat: off  (click for playlist)",
            "context": "Repeat: playlist  (click for track)",
            "track":   "Repeat: track  (click to turn off)",
        }
        self._repeat_btn.setText(icons.get(self._repeat_mode, "↻"))
        self._repeat_btn.setToolTip(tips.get(self._repeat_mode, "Repeat"))
        if self._repeat_mode != "off":
            self._repeat_btn.setStyleSheet(
                f"QPushButton {{ color: {ACCENT}; font-weight: bold; }}"
            )
        else:
            self._repeat_btn.setStyleSheet("")

    def _update_progress_display(self) -> None:
        if self._duration_ms > 0:
            frac = min(self._progress_ms / self._duration_ms, 1.0)
            self._progress_bar.setValue(int(frac * 1000))
        else:
            self._progress_bar.setValue(0)
        self._time_label.setText(
            f"{_ms_to_str(self._progress_ms)} / {_ms_to_str(self._duration_ms)}"
        )

    def _tick_progress(self) -> None:
        """Advance the progress bar by 1 s between API polls."""
        if self._is_playing and self._duration_ms > 0:
            self._progress_ms = min(
                self._progress_ms + PROGRESS_TICK_MS, self._duration_ms
            )
            self._update_progress_display()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._progress_timer.stop()
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._sig_disconnect.emit()
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
