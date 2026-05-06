"""
Tidal panel for Project Ceres — GM Assistant UI.

Streams Tidal music via tidalapi (OAuth2 device-code login) with local
playback through pygame.mixer.music.

Features
--------
  - OAuth2 device-code login via tidalapi — auto-reconnects if tokens saved
  - Now Playing — 80x80 album art, track / artist / album, progress bar
  - Transport — Play/Pause, Stop, Prev, Next (local pygame playback)
  - Search — text query, results list, double-click to play
  - Playlist browser — user's Tidal playlists, double-click to queue
  - Scene quick-launch — 8 configurable slots
  - Discord command slot — handle_command("play"/"pause"/"stop"/"search", query)
  - Mixer integration — volume_changed / set_volume / get_volume

Requirements
------------
    pip install tidalapi

Architecture
------------
  tidalapi has NO remote playback control (unlike Spotify Connect).
  We get the audio stream URL from tidalapi and play it locally with
  pygame.mixer.music — same pattern as the YouTube panel.
"""

from __future__ import annotations

import json
import os
import tempfile
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
    import tidalapi
    _TIDAL_OK = True
except ImportError:
    tidalapi = None  # type: ignore[assignment]
    _TIDAL_OK = False

try:
    import pygame
    _PYGAME_OK = True
except ImportError:
    pygame = None  # type: ignore[assignment]
    _PYGAME_OK = False

# ── Constants ──────────────────────────────────────────────────────────────────

ALBUM_ART_SIZE   = 80
PROGRESS_TICK_MS = 1_000

SCENE_TAGS: List[Tuple[str, str]] = [
    ("\u2694  Combat",   "combat"),
    ("\U0001f33f  Ambient",  "ambient"),
    ("\U0001f37a  Tavern",   "tavern"),
    ("\U0001f5fa  Travel",   "travel"),
    ("\U0001f608  Villain",  "villain"),
    ("\U0001f3c6  Victory",  "victory"),
    ("\U0001f480  Dungeon",  "dungeon"),
    ("\U0001f319  Night",    "night"),
]

_PROJECT_ROOT        = Path(__file__).resolve().parent.parent.parent
_TOKEN_PATH          = _PROJECT_ROOT / ".tidal_token.json"
_SCENE_CONFIG_PATH   = _PROJECT_ROOT / "tidal_scene_playlists.json"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _s_to_str(seconds: int) -> str:
    m, s = divmod(max(seconds, 0), 60)
    return f"{m}:{s:02d}"


# ── Background worker ──────────────────────────────────────────────────────────

class _TidalWorker(QObject):
    """All tidalapi + pygame calls run here (on a QThread)."""

    auth_success     = Signal(str)         # display name
    auth_failed      = Signal(str)         # error
    auth_link        = Signal(str)         # device-code URL for user
    playback_started = Signal(str, str, str, int, str)  # title, artist, album, duration_s, art_url
    playback_stopped = Signal()
    playback_error   = Signal(str)
    search_results   = Signal(list)        # list of dicts
    playlists_loaded = Signal(list)        # list of dicts
    artwork_loaded   = Signal(str, bytes)  # url, raw bytes
    track_finished   = Signal()
    error            = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._session: Optional[object] = None
        self._queue: List[object] = []
        self._queue_idx: int = -1
        self._playing: bool = False
        self._paused: bool = False
        self._poll_timer: Optional[QTimer] = None
        self._current_duration_s: int = 0

    # ── Auth ──────────────────────────────────────────────────────────────────

    @Slot()
    def do_connect(self) -> None:
        if not _TIDAL_OK:
            self.auth_failed.emit("tidalapi not installed — pip install tidalapi")
            return
        try:
            session = tidalapi.Session()

            # Try loading saved tokens first
            if _TOKEN_PATH.exists():
                try:
                    data = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
                    session.load_oauth_session(
                        data["token_type"],
                        data["access_token"],
                        data.get("refresh_token", ""),
                        data.get("expiry_time"),
                    )
                    if session.check_login():
                        self._session = session
                        user = session.user
                        name = user.name if user else "Tidal User"
                        self.auth_success.emit(name)
                        self._start_poll_timer()
                        return
                except Exception:
                    pass

            # Device-code OAuth flow
            login, future = session.login_oauth()
            self.auth_link.emit(login.verification_uri_complete)
            future.result()

            if session.check_login():
                self._session = session
                self._save_tokens(session)
                user = session.user
                name = user.name if user else "Tidal User"
                self.auth_success.emit(name)
                self._start_poll_timer()
            else:
                self.auth_failed.emit("Login failed — try again")
        except Exception as exc:
            self.auth_failed.emit(str(exc))

    def _save_tokens(self, session) -> None:
        try:
            data = {
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token or "",
                "expiry_time": str(session.expiry_time) if session.expiry_time else "",
            }
            _TOKEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @Slot()
    def do_disconnect(self) -> None:
        self._stop_playback()
        self._session = None
        if self._poll_timer:
            self._poll_timer.stop()

    def _start_poll_timer(self) -> None:
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._poll_playback_state)
        self._poll_timer.start(1000)

    def _poll_playback_state(self) -> None:
        if self._playing and _PYGAME_OK and not self._paused:
            if not pygame.mixer.music.get_busy():
                self._playing = False
                self.track_finished.emit()

    # ── Search ────────────────────────────────────────────────────────────────

    @Slot(str)
    def do_search(self, query: str) -> None:
        if not self._session:
            self.error.emit("Not connected to Tidal")
            return
        try:
            results = self._session.search(query, models=[tidalapi.media.Track], limit=20)
            tracks = results.get("tracks", []) if isinstance(results, dict) else []
            items = []
            for t in tracks:
                items.append({
                    "id": t.id,
                    "name": t.name,
                    "artist": t.artist.name if t.artist else "Unknown",
                    "album": t.album.name if t.album else "",
                    "duration": t.duration or 0,
                    "_track": t,
                })
            self.search_results.emit(items)
        except Exception as exc:
            self.error.emit(f"Search failed: {exc}")

    # ── Playlists ─────────────────────────────────────────────────────────────

    @Slot()
    def do_load_playlists(self) -> None:
        if not self._session:
            self.error.emit("Not connected to Tidal")
            return
        try:
            user = self._session.user
            if not user:
                self.playlists_loaded.emit([])
                return
            plists = user.playlists() or []
            items = []
            for p in plists:
                items.append({
                    "id": p.id,
                    "name": p.name,
                    "num_tracks": p.num_tracks if hasattr(p, "num_tracks") else 0,
                    "_playlist": p,
                })
            self.playlists_loaded.emit(items)
        except Exception as exc:
            self.error.emit(f"Failed to load playlists: {exc}")

    # ── Playback ──────────────────────────────────────────────────────────────

    @Slot(object)
    def do_play_track(self, track) -> None:
        """Play a single track object from tidalapi."""
        self._queue = [track]
        self._queue_idx = 0
        self._start_track(track)

    @Slot(list)
    def do_play_queue(self, tracks: list) -> None:
        """Play a list of track objects, starting from the first."""
        if not tracks:
            return
        self._queue = list(tracks)
        self._queue_idx = 0
        self._start_track(self._queue[0])

    def _start_track(self, track) -> None:
        if not _PYGAME_OK:
            self.playback_error.emit("pygame not available")
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

            url = track.get_url()
            if not url:
                self.playback_error.emit(f"No stream URL for: {track.name}")
                return

            duration_s = track.duration or 0
            self._current_duration_s = duration_s

            art_url = ""
            try:
                if track.album:
                    art_url = track.album.image(160)
            except Exception:
                pass

            # Download stream to temp file (pygame needs a file or file-like)
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp_path = tmp.name
            tmp.close()

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(tmp_path, "wb") as f:
                    f.write(resp.read())

            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            self._playing = True
            self._paused = False

            artist_name = track.artist.name if track.artist else "Unknown"
            album_name = track.album.name if track.album else ""
            self.playback_started.emit(
                track.name, artist_name, album_name, duration_s, art_url
            )

            # Fetch artwork in background
            if art_url:
                threading.Thread(
                    target=self._fetch_artwork, args=(art_url,), daemon=True
                ).start()

        except Exception as exc:
            self.playback_error.emit(str(exc))

    def _fetch_artwork(self, url: str) -> None:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            self.artwork_loaded.emit(url, data)
        except Exception:
            pass

    def _stop_playback(self) -> None:
        if _PYGAME_OK and pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self._playing = False
        self._paused = False
        self.playback_stopped.emit()

    @Slot()
    def do_stop(self) -> None:
        self._stop_playback()

    @Slot()
    def do_pause(self) -> None:
        if _PYGAME_OK and self._playing and not self._paused:
            pygame.mixer.music.pause()
            self._paused = True

    @Slot()
    def do_resume(self) -> None:
        if _PYGAME_OK and self._paused:
            pygame.mixer.music.unpause()
            self._paused = False
        elif not self._playing and self._queue and self._queue_idx >= 0:
            self._start_track(self._queue[self._queue_idx])

    @Slot()
    def do_next(self) -> None:
        if self._queue and self._queue_idx < len(self._queue) - 1:
            self._queue_idx += 1
            self._start_track(self._queue[self._queue_idx])
        else:
            self._stop_playback()

    @Slot()
    def do_previous(self) -> None:
        if self._queue and self._queue_idx > 0:
            self._queue_idx -= 1
            self._start_track(self._queue[self._queue_idx])

    @Slot(int)
    def do_set_volume(self, value: int) -> None:
        if _PYGAME_OK and pygame.mixer.get_init():
            pygame.mixer.music.set_volume(max(0, min(value, 100)) / 100.0)


# ── Main panel ─────────────────────────────────────────────────────────────────

class TidalPanel(QDockWidget):
    """
    Dockable Tidal integration panel.

    Signals:
        status_message(msg) — forwarded to the main window status bar
        volume_changed(int) — sent when the panel's volume slider changes

    Public slot:
        handle_command(action, query) — called by DiscordPanel.tidal_command
    """

    status_message: Signal = Signal(str)
    volume_changed: Signal = Signal(int)

    _sig_connect      = Signal()
    _sig_disconnect   = Signal()
    _sig_search       = Signal(str)
    _sig_load_plists  = Signal()
    _sig_play_track   = Signal(object)
    _sig_play_queue   = Signal(list)
    _sig_stop         = Signal()
    _sig_pause        = Signal()
    _sig_resume       = Signal()
    _sig_next         = Signal()
    _sig_previous     = Signal()
    _sig_set_vol      = Signal(int)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Tidal", parent)
        self.setObjectName("TidalPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config = config
        self._run_command = run_command

        self._is_playing    = False
        self._paused        = False
        self._progress_s    = 0
        self._duration_s    = 0
        self._auto_play_first = False
        self._artwork_cache: Dict[str, QPixmap] = {}
        self._search_track_refs: List[object] = []

        self._scene_config: Dict[str, Optional[Dict]] = {
            tag: None for _, tag in SCENE_TAGS
        }
        self._scene_buttons: Dict[str, QPushButton] = {}

        self._load_scene_config()
        self._build_ui()
        self._setup_worker()

        # Progress interpolation timer
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(PROGRESS_TICK_MS)
        self._progress_timer.timeout.connect(self._tick_progress)

    # ── Scene config persistence ──────────────────────────────────────────────

    def _load_scene_config(self) -> None:
        try:
            if _SCENE_CONFIG_PATH.exists():
                data = json.loads(_SCENE_CONFIG_PATH.read_text(encoding="utf-8"))
                for _, tag in SCENE_TAGS:
                    if tag in data:
                        self._scene_config[tag] = data[tag]
        except Exception:
            pass

    def _save_scene_config(self) -> None:
        try:
            _SCENE_CONFIG_PATH.write_text(
                json.dumps(self._scene_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _setup_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = _TidalWorker()
        self._worker.moveToThread(self._thread)

        self._worker.auth_success.connect(self._on_auth_success)
        self._worker.auth_failed.connect(self._on_auth_failed)
        self._worker.auth_link.connect(self._on_auth_link)
        self._worker.playback_started.connect(self._on_playback_started)
        self._worker.playback_stopped.connect(self._on_playback_stopped)
        self._worker.playback_error.connect(
            lambda msg: self.status_message.emit(f"Tidal: {msg}")
        )
        self._worker.search_results.connect(self._on_search_results)
        self._worker.playlists_loaded.connect(self._on_playlists_loaded)
        self._worker.artwork_loaded.connect(self._on_artwork_loaded)
        self._worker.track_finished.connect(self._on_track_finished)
        self._worker.error.connect(
            lambda msg: self.status_message.emit(f"Tidal error: {msg}")
        )

        self._sig_connect.connect(self._worker.do_connect)
        self._sig_disconnect.connect(self._worker.do_disconnect)
        self._sig_search.connect(self._worker.do_search)
        self._sig_load_plists.connect(self._worker.do_load_playlists)
        self._sig_play_track.connect(self._worker.do_play_track)
        self._sig_play_queue.connect(self._worker.do_play_queue)
        self._sig_stop.connect(self._worker.do_stop)
        self._sig_pause.connect(self._worker.do_pause)
        self._sig_resume.connect(self._worker.do_resume)
        self._sig_next.connect(self._worker.do_next)
        self._sig_previous.connect(self._worker.do_previous)
        self._sig_set_vol.connect(self._worker.do_set_volume)

        self._thread.start()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Status row
        status_row = QHBoxLayout()
        status_row.setSpacing(6)

        self._dot_label = QLabel("\u25cf")
        self._dot_label.setFixedWidth(14)
        self._dot_label.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        status_row.addWidget(self._dot_label)

        self._status_label = QLabel("Not connected")
        self._status_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        status_row.addWidget(self._status_label, 1)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedHeight(24)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        status_row.addWidget(self._connect_btn)

        layout.addLayout(status_row)

        if not _TIDAL_OK:
            warn = QLabel("tidalapi not installed — pip install tidalapi")
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {WARNING}; font-size: 10px; padding: 4px;")
            layout.addWidget(warn)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_now_playing_tab(), "Now Playing")
        self._tabs.addTab(self._build_search_tab(), "Search")
        self._tabs.addTab(self._build_library_tab(), "Library")
        layout.addWidget(self._tabs, 1)

        self.setWidget(outer)
        self._set_controls_enabled(False)

    def _build_now_playing_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Art + info
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        self._art_label = QLabel("\U0001f3b5")
        self._art_label.setFixedSize(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        self._art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._art_label.setStyleSheet(
            f"background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 4px;"
            f"font-size: 28px; color: {MUTED};"
        )
        info_row.addWidget(self._art_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._track_label = QLabel("No track")
        self._track_label.setStyleSheet(f"color: {TEXT}; font-weight: bold; font-size: 11px;")
        self._artist_label = QLabel("")
        self._artist_label.setStyleSheet(f"color: {ACCENT}; font-size: 10px;")
        self._album_label = QLabel("")
        self._album_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        text_col.addWidget(self._track_label)
        text_col.addWidget(self._artist_label)
        text_col.addWidget(self._album_label)
        text_col.addStretch()
        info_row.addLayout(text_col, 1)
        lay.addLayout(info_row)

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        lay.addWidget(self._progress_bar)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        lay.addWidget(self._time_label)

        # Transport
        transport = QHBoxLayout()
        transport.setSpacing(6)
        transport.addStretch()

        self._prev_btn = QPushButton("\u23ee")
        self._prev_btn.setFixedSize(32, 28)
        self._prev_btn.setToolTip("Previous")
        self._prev_btn.clicked.connect(lambda: self._sig_previous.emit())
        transport.addWidget(self._prev_btn)

        self._play_btn = QPushButton("\u25b6")
        self._play_btn.setFixedSize(36, 28)
        self._play_btn.setToolTip("Play / Pause")
        self._play_btn.clicked.connect(self._on_play_pause)
        transport.addWidget(self._play_btn)

        self._stop_btn = QPushButton("\u25a0")
        self._stop_btn.setFixedSize(32, 28)
        self._stop_btn.setToolTip("Stop")
        self._stop_btn.clicked.connect(lambda: self._sig_stop.emit())
        transport.addWidget(self._stop_btn)

        self._next_btn = QPushButton("\u23ed")
        self._next_btn.setFixedSize(32, 28)
        self._next_btn.setToolTip("Next")
        self._next_btn.clicked.connect(lambda: self._sig_next.emit())
        transport.addWidget(self._next_btn)

        transport.addStretch()
        lay.addLayout(transport)

        # Volume
        vol_row = QHBoxLayout()
        vol_row.setSpacing(4)
        vol_lbl = QLabel("\U0001f50a")
        vol_lbl.setFixedWidth(18)
        vol_row.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self._vol_slider, 1)

        self._vol_label = QLabel("80%")
        self._vol_label.setFixedWidth(32)
        self._vol_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        vol_row.addWidget(self._vol_label)
        lay.addLayout(vol_row)

        lay.addStretch()
        return page

    def _build_search_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search Tidal...")
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input, 1)

        search_btn = QPushButton("Search")
        search_btn.setFixedHeight(26)
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)
        lay.addLayout(search_row)

        header = QHBoxLayout()
        header.addWidget(QLabel("Results"))
        play_btn = QPushButton("Play")
        play_btn.setFixedHeight(22)
        play_btn.clicked.connect(self._on_play_selected_search)
        header.addWidget(play_btn)
        lay.addLayout(header)

        self._search_list = QListWidget()
        self._search_list.itemDoubleClicked.connect(
            lambda item: self._on_play_selected_search()
        )
        lay.addWidget(self._search_list, 1)

        return page

    def _build_library_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Playlists
        pl_header = QHBoxLayout()
        pl_header.addWidget(QLabel("Your Playlists"))
        refresh_btn = QPushButton("\u21bb")
        refresh_btn.setFixedSize(24, 22)
        refresh_btn.setToolTip("Refresh playlists")
        refresh_btn.clicked.connect(lambda: self._sig_load_plists.emit())
        pl_header.addWidget(refresh_btn)

        play_pl_btn = QPushButton("Play")
        play_pl_btn.setFixedHeight(22)
        play_pl_btn.clicked.connect(self._on_play_selected_playlist)
        pl_header.addWidget(play_pl_btn)
        lay.addLayout(pl_header)

        self._playlist_list = QListWidget()
        self._playlist_list.setMaximumHeight(130)
        self._playlist_list.itemDoubleClicked.connect(
            lambda item: self._on_play_selected_playlist()
        )
        lay.addWidget(self._playlist_list)

        # Scene quick-launch
        scene_lbl = QLabel("Scene Quick-Launch")
        scene_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 10px;")
        lay.addWidget(scene_lbl)

        hint = QLabel("Right-click a slot to assign a playlist")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        lay.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i, (label, tag) in enumerate(SCENE_TAGS):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setToolTip(self._scene_tooltip(tag))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.clicked.connect(lambda checked, t=tag: self._on_scene_clicked(t))
            btn.customContextMenuRequested.connect(
                lambda pos, t=tag, b=btn: self._on_scene_context(t, b, pos)
            )
            self._scene_buttons[tag] = btn
            grid.addWidget(btn, i // 4, i % 4)
        lay.addLayout(grid)

        lay.addStretch()
        return page

    def _scene_tooltip(self, tag: str) -> str:
        cfg = self._scene_config.get(tag)
        if cfg:
            return f"{tag}: {cfg.get('name', '?')}"
        return f"{tag}: (unassigned — right-click to assign)"

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_connect_clicked(self) -> None:
        if self._connect_btn.text() == "Connect":
            self._status_label.setText("Connecting...")
            self._dot_label.setStyleSheet(f"color: {WARNING}; font-size: 14px;")
            self._connect_btn.setEnabled(False)
            self._sig_connect.emit()
        else:
            self._sig_disconnect.emit()
            self._on_disconnected()

    def _on_auth_success(self, name: str) -> None:
        self._dot_label.setStyleSheet(f"color: {SUCCESS}; font-size: 14px;")
        self._status_label.setText(f"Connected \u00b7 {name}")
        self._connect_btn.setText("Disconnect")
        self._connect_btn.setEnabled(True)
        self._set_controls_enabled(True)
        self.status_message.emit(f"Tidal: connected as {name}")
        self._sig_load_plists.emit()

    def _on_auth_failed(self, msg: str) -> None:
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        self._status_label.setText(f"Failed: {msg}")
        self._connect_btn.setText("Connect")
        self._connect_btn.setEnabled(True)
        self.status_message.emit(f"Tidal auth failed: {msg}")

    def _on_auth_link(self, url: str) -> None:
        self._status_label.setText("Open browser to log in...")
        self.status_message.emit(f"Tidal: open {url} to log in")
        import webbrowser
        webbrowser.open(url)

    def _on_disconnected(self) -> None:
        self._dot_label.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        self._status_label.setText("Not connected")
        self._connect_btn.setText("Connect")
        self._connect_btn.setEnabled(True)
        self._set_controls_enabled(False)
        self._is_playing = False
        self._progress_timer.stop()
        self._track_label.setText("No track")
        self._artist_label.setText("")
        self._album_label.setText("")

    def _on_playback_started(self, title: str, artist: str, album: str,
                              duration_s: int, art_url: str) -> None:
        self._track_label.setText(title)
        self._artist_label.setText(artist)
        self._album_label.setText(album)
        self._duration_s = duration_s
        self._progress_s = 0
        self._is_playing = True
        self._paused = False
        self._play_btn.setText("\u23f8")
        self._update_progress_display()
        self._progress_timer.start()
        self.status_message.emit(f"Tidal: {title} \u2014 {artist}")

    def _on_playback_stopped(self) -> None:
        self._is_playing = False
        self._paused = False
        self._progress_timer.stop()
        self._play_btn.setText("\u25b6")
        self._progress_bar.setValue(0)
        self._time_label.setText("0:00 / 0:00")

    def _on_track_finished(self) -> None:
        self._sig_next.emit()

    def _on_search_results(self, items: list) -> None:
        self._search_list.clear()
        self._search_track_refs = []
        for item in items:
            display = f"{item['name']}  \u2014  {item['artist']}  ({_s_to_str(item['duration'])})"
            self._search_list.addItem(display)
            self._search_track_refs.append(item.get("_track"))

        if self._auto_play_first and items:
            self._auto_play_first = False
            track = items[0].get("_track")
            if track:
                self._sig_play_track.emit(track)

        self.status_message.emit(f"Tidal: {len(items)} results")

    def _on_playlists_loaded(self, items: list) -> None:
        self._playlist_list.clear()
        self._playlist_refs: List[object] = []
        for item in items:
            display = f"{item['name']}  ({item.get('num_tracks', '?')} tracks)"
            self._playlist_list.addItem(display)
            self._playlist_refs.append(item.get("_playlist"))

    def _on_artwork_loaded(self, url: str, data: bytes) -> None:
        pm = QPixmap()
        pm.loadFromData(data)
        if not pm.isNull():
            pm = pm.scaled(
                ALBUM_ART_SIZE, ALBUM_ART_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._art_label.setPixmap(pm)
            self._artwork_cache[url] = pm

    # ── UI event handlers ─────────────────────────────────────────────────────

    def _on_play_pause(self) -> None:
        if self._is_playing and not self._paused:
            self._sig_pause.emit()
            self._paused = True
            self._play_btn.setText("\u25b6")
            self._progress_timer.stop()
        elif self._paused:
            self._sig_resume.emit()
            self._paused = False
            self._play_btn.setText("\u23f8")
            self._progress_timer.start()
        else:
            self._sig_resume.emit()

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if query:
            self._sig_search.emit(query)

    def _on_play_selected_search(self) -> None:
        row = self._search_list.currentRow()
        if 0 <= row < len(self._search_track_refs):
            track = self._search_track_refs[row]
            if track:
                self._sig_play_track.emit(track)

    def _on_play_selected_playlist(self) -> None:
        row = self._playlist_list.currentRow()
        if not hasattr(self, "_playlist_refs"):
            return
        if 0 <= row < len(self._playlist_refs):
            playlist = self._playlist_refs[row]
            if playlist:
                try:
                    tracks = playlist.tracks()
                    if tracks:
                        self._sig_play_queue.emit(tracks)
                except Exception as exc:
                    self.status_message.emit(f"Tidal: failed to load playlist: {exc}")

    def _on_volume_changed(self, value: int) -> None:
        self._vol_label.setText(f"{value}%")
        self._sig_set_vol.emit(value)
        self.volume_changed.emit(value)

    # ── Scene slots ───────────────────────────────────────────────────────────

    def _on_scene_clicked(self, tag: str) -> None:
        cfg = self._scene_config.get(tag)
        if not cfg:
            self.status_message.emit(f"Tidal: {tag} not assigned — right-click to set")
            return
        playlist = cfg.get("_playlist")
        if playlist:
            try:
                tracks = playlist.tracks()
                if tracks:
                    self._sig_play_queue.emit(tracks)
                    self.status_message.emit(f"Tidal: playing {tag} scene")
            except Exception as exc:
                self.status_message.emit(f"Tidal: {exc}")

    def _on_scene_context(self, tag: str, btn: QPushButton, pos) -> None:
        menu = QMenu(self)
        assign_act = menu.addAction("Assign selected playlist")
        clear_act = menu.addAction("Clear assignment")

        action = menu.exec_(btn.mapToGlobal(pos))
        if action == assign_act:
            self._assign_scene(tag)
        elif action == clear_act:
            self._clear_scene(tag)

    def _assign_scene(self, tag: str) -> None:
        row = self._playlist_list.currentRow()
        if not hasattr(self, "_playlist_refs"):
            return
        if 0 <= row < len(self._playlist_refs):
            playlist = self._playlist_refs[row]
            name = self._playlist_list.item(row).text() if self._playlist_list.item(row) else tag
            self._scene_config[tag] = {"name": name, "_playlist": playlist}
            self._save_scene_config()
            btn = self._scene_buttons.get(tag)
            if btn:
                btn.setToolTip(self._scene_tooltip(tag))
            self.status_message.emit(f"Tidal: assigned {name} to {tag}")

    def _clear_scene(self, tag: str) -> None:
        self._scene_config[tag] = None
        self._save_scene_config()
        btn = self._scene_buttons.get(tag)
        if btn:
            btn.setToolTip(self._scene_tooltip(tag))
        self.status_message.emit(f"Tidal: cleared {tag} scene")

    # ── Mixer integration ─────────────────────────────────────────────────────

    @Slot(int)
    def set_volume(self, value: int) -> None:
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(value)
        self._vol_label.setText(f"{value}%")
        self._vol_slider.blockSignals(False)
        self._sig_set_vol.emit(value)

    def get_volume(self) -> int:
        return self._vol_slider.value()

    def get_np_state(self) -> dict:
        """Return current playback state for the Now Playing panel."""
        playing = bool(getattr(self, "_is_playing", False))
        paused = bool(getattr(self, "_paused", False))
        title = self._track_label.text() if hasattr(self, "_track_label") else ""
        subtitle = self._artist_label.text() if hasattr(self, "_artist_label") else ""
        if title == "No track":
            title = ""
        dur = getattr(self, "_duration_s", 0)
        prog = getattr(self, "_progress_s", 0)
        pct = int(prog * 100 / dur) if dur > 0 else (-1 if not (playing or paused) else 0)
        return {
            "playing": playing,
            "paused": paused,
            "title": title,
            "subtitle": subtitle,
            "progress_pct": pct,
            "can_pause": True,
            "can_next": True,
            "can_prev": False,
            "can_stop": True,
        }

    # ── Discord command handler ───────────────────────────────────────────────

    @Slot(str, str)
    def handle_command(self, action: str, query: str) -> None:
        """
        Called by DiscordPanel.tidal_command signal.

        Supported actions: play, pause, stop, search, skip
        """
        action = action.lower().strip()
        self.status_message.emit(f"Tidal \u2190 command: {action!r}  query={query!r}")

        if action == "stop":
            self._sig_stop.emit()
        elif action == "pause":
            self._on_play_pause()
        elif action == "play":
            if query.strip():
                self._auto_play_first = True
                self._search_input.setText(query.strip())
                self._sig_search.emit(query.strip())
            else:
                self._sig_resume.emit()
        elif action == "skip":
            self._sig_next.emit()
        elif action == "search":
            if query.strip():
                self._search_input.setText(query.strip())
                self._sig_search.emit(query.strip())
                self._tabs.setCurrentIndex(1)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._prev_btn, self._play_btn, self._stop_btn, self._next_btn,
            self._vol_slider, self._search_input,
        ):
            widget.setEnabled(enabled)
        for btn in self._scene_buttons.values():
            btn.setEnabled(enabled)

    def _update_progress_display(self) -> None:
        if self._duration_s > 0:
            frac = min(self._progress_s / self._duration_s, 1.0)
            self._progress_bar.setValue(int(frac * 1000))
            self._time_label.setText(
                f"{_s_to_str(self._progress_s)} / {_s_to_str(self._duration_s)}"
            )
        else:
            self._progress_bar.setValue(0)
            self._time_label.setText("0:00 / 0:00")

    def _tick_progress(self) -> None:
        if self._is_playing and not self._paused and self._duration_s > 0:
            self._progress_s = min(self._progress_s + 1, self._duration_s)
            self._update_progress_display()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._progress_timer.stop()
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._sig_disconnect.emit()
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)