"""
YouTube panel for Project Ceres — GM Assistant UI.

Lets the GM search YouTube and stream audio via yt-dlp + pygame.mixer.
Provides scene quick-launch slots, playlist browsing (OAuth2), and
Mixer integration (volume_changed signal + set_volume slot).

Features
--------
  • API-key auth — YOUTUBE_API_KEY loaded from variables.env
  • Search tab — YouTube Data API v3 search.list (up to 20 results)
  • Now Playing tab — thumbnail, title, channel, progress bar, transport controls
  • My Playlists tab — OAuth2 sign-in, up to 50 user playlists
  • Scenes tab — 8 named quick-launch slots (persist to youtube_scenes.json)
  • Volume slider — updates pygame.mixer.music volume, emits volume_changed

Requirements (optional — panel degrades gracefully if missing)
------------
    pip install google-api-python-client google-auth-oauthlib yt-dlp

variables.env keys
------------------
    YOUTUBE_API_KEY=<your-data-api-v3-key>
    YOUTUBE_CLIENT_SECRETS_FILE=client_secrets.json  # optional, for playlists
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
        QPushButton, QLabel, QLineEdit, QSlider,
        QListWidget, QListWidgetItem, QTabWidget, QGridLayout,
        QSizePolicy, QMenu, QMessageBox, QProgressBar, QInputDialog,
    )
    from PyQt5.QtCore import (
        Qt, QThread, QObject, QTimer, QSize,
        pyqtSignal as Signal, pyqtSlot as Slot,
    )
    from PyQt5.QtGui import QPixmap, QIcon
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider,
        QListWidget, QListWidgetItem, QTabWidget, QGridLayout,
        QSizePolicy, QMenu, QMessageBox, QProgressBar, QInputDialog,
    )
    from PySide6.QtCore import Qt, QThread, QObject, QTimer, QSize, Signal, Slot  # type: ignore
    from PySide6.QtGui import QPixmap, QIcon  # type: ignore

from ui.theme import (
    ACCENT, ACCENT2, BG, BORDER, ERROR, MUTED,
    PANEL, SUCCESS, SURFACE, TEXT, WARNING,
)
from pantheon.vervactor.workspace import load_scene_data, save_scene_data

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    import yt_dlp as _yt_dlp
    _YTDLP_AVAILABLE = True
except ImportError:
    _yt_dlp = None  # type: ignore[assignment]
    _YTDLP_AVAILABLE = False

try:
    from googleapiclient.discovery import build as _yt_build
    _GOOGLE_API_AVAILABLE = True
except ImportError:
    _yt_build = None  # type: ignore[assignment]
    _GOOGLE_API_AVAILABLE = False

try:
    import pygame as _pygame
    _PYGAME_OK = True
except ImportError:
    _pygame = None  # type: ignore[assignment]
    _PYGAME_OK = False

# ── Constants ──────────────────────────────────────────────────────────────────

THUMB_W        = 120
THUMB_H        = 90
PROGRESS_TICK_MS = 1000   # progress bar update interval (ms)

SCENE_SLOTS: List[Tuple[str, str]] = [
    ("⚔  Combat",  "combat"),
    ("🌿  Ambient", "ambient"),
    ("🍺  Tavern",  "tavern"),
    ("🗺  Travel",  "travel"),
    ("💀  Dungeon", "dungeon"),
    ("⚡  Chase",   "chase"),
    ("🌙  Rest",    "rest"),
    ("👹  Boss",    "boss"),
]

_PROJECT_ROOT     = Path(__file__).resolve().parent.parent.parent
SCENE_CONFIG_PATH = _PROJECT_ROOT / "youtube_scenes.json"
TOKEN_PATH        = _PROJECT_ROOT / ".youtube_token.json"


# ── Helper functions ───────────────────────────────────────────────────────────

def _fmt_seconds(s: int) -> str:
    """Format an integer number of seconds as m:ss or h:mm:ss.

    Args:
        s: Duration in seconds.

    Returns:
        Human-readable duration string like '4:37' or '1:02:14'.
    """
    h   = s // 3600
    m   = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _parse_iso_duration(iso: str) -> str:
    """Convert an ISO 8601 duration string (e.g. PT4M37S) to mm:ss.

    Args:
        iso: ISO 8601 duration string from the YouTube Data API.

    Returns:
        Human-readable duration like '4:37', or empty string on failure.
    """
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return ""
    h, mn, sec = (int(x or 0) for x in m.groups())
    return _fmt_seconds(h * 3600 + mn * 60 + sec)


# ── Audio playback thread ──────────────────────────────────────────────────────

class _YTAudioThread(QThread):
    """
    Extract audio URL via yt-dlp and start playback via pygame.mixer.music.

    Signals
    -------
    playback_started(title, channel, duration_s, thumbnail_url)
    playback_error(message)
    """

    playback_started = Signal(str, str, int, str)   # title, channel, duration_s, thumb_url
    playback_error   = Signal(str)

    def __init__(
        self, url_or_query: str, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._url_or_query = url_or_query

    def run(self) -> None:
        """Extract audio URL and begin pygame playback."""
        if not _YTDLP_AVAILABLE:
            self.playback_error.emit("yt-dlp not installed.\nRun:  pip install yt-dlp")
            return
        if not _PYGAME_OK:
            self.playback_error.emit("pygame not installed.\nRun:  pip install pygame")
            return

        ydl_opts = {
            "format":      "bestaudio",
            "quiet":       True,
            "no_warnings": True,
            "noplaylist":  True,
            "extract_flat": False,
        }
        try:
            with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self._url_or_query, download=False)
        except Exception as exc:
            self.playback_error.emit(f"yt-dlp error: {exc}")
            return

        if info is None:
            self.playback_error.emit("yt-dlp returned no info for that URL")
            return

        # Handle playlists or single-video results
        entry = info
        if "entries" in info:
            entries = list(info["entries"])
            if not entries:
                self.playback_error.emit("No playable entries found in result")
                return
            entry = entries[0]

        # Prefer the direct URL; fall back to scanning formats
        audio_url = entry.get("url", "")
        if not audio_url:
            for fmt in (entry.get("formats") or []):
                if fmt.get("acodec") != "none" and fmt.get("url"):
                    audio_url = fmt["url"]
                    break

        if not audio_url:
            self.playback_error.emit("Could not extract a playable audio stream URL")
            return

        title      = entry.get("title", "Unknown")
        channel    = entry.get("uploader") or entry.get("channel") or ""
        duration_s = int(entry.get("duration") or 0)
        thumb_url  = ""
        for thumb in reversed(entry.get("thumbnails") or []):
            if thumb.get("url"):
                thumb_url = thumb["url"]
                break

        try:
            if not _pygame.mixer.get_init():
                _pygame.mixer.init()
            _pygame.mixer.music.load(audio_url)
            _pygame.mixer.music.play()
        except Exception as exc:
            self.playback_error.emit(f"pygame playback error: {exc}")
            return

        self.playback_started.emit(title, channel, duration_s, thumb_url)


# ── Search / playlists worker ──────────────────────────────────────────────────

class _SearchWorker(QObject):
    """
    YouTube Data API v3 calls that run in a background QThread.

    Signals
    -------
    results_ready(list)  — search results or playlist list
    search_error(str)    — error message
    """

    results_ready = Signal(list)
    search_error  = Signal(str)

    @Slot(str, str)
    def do_search(self, api_key: str, query: str) -> None:
        """Run a YouTube search and emit results_ready or search_error.

        Args:
            api_key: YouTube Data API v3 key.
            query:   Search query string.
        """
        if not _GOOGLE_API_AVAILABLE:
            self.search_error.emit(
                "google-api-python-client not installed.\n"
                "Run:  pip install google-api-python-client"
            )
            return
        try:
            service = _yt_build("youtube", "v3", developerKey=api_key)
            resp = service.search().list(
                q=query,
                part="snippet",
                type="video",
                maxResults=20,
                fields="items(id/videoId,snippet(title,channelTitle))",
            ).execute()
        except Exception as exc:
            self.search_error.emit(f"YouTube API error: {exc}")
            return

        video_ids = [item["id"]["videoId"] for item in resp.get("items", [])]
        durations: Dict[str, str] = {}
        if video_ids:
            try:
                details = service.videos().list(
                    id=",".join(video_ids),
                    part="contentDetails",
                    fields="items(id,contentDetails/duration)",
                ).execute()
                for item in details.get("items", []):
                    raw = item.get("contentDetails", {}).get("duration", "")
                    durations[item["id"]] = _parse_iso_duration(raw) if raw else ""
            except Exception:
                pass  # duration is non-critical

        results = []
        for item in resp.get("items", []):
            vid_id  = item["id"]["videoId"]
            snippet = item.get("snippet", {})
            results.append({
                "video_id": vid_id,
                "title":    snippet.get("title", ""),
                "channel":  snippet.get("channelTitle", ""),
                "duration": durations.get(vid_id, ""),
                "url":      f"https://www.youtube.com/watch?v={vid_id}",
            })
        self.results_ready.emit(results)

    @Slot(str)
    def do_load_playlists(self, access_token: str) -> None:
        """Fetch up to 50 user playlists using an OAuth2 access token.

        Args:
            access_token: Valid YouTube OAuth2 access token.
        """
        if not _GOOGLE_API_AVAILABLE:
            self.search_error.emit(
                "google-api-python-client not installed.\n"
                "Run:  pip install google-api-python-client"
            )
            return
        try:
            import google.oauth2.credentials as _creds
            cred = _creds.Credentials(token=access_token)
            service = _yt_build("youtube", "v3", credentials=cred)
            resp = service.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50,
            ).execute()
        except Exception as exc:
            self.search_error.emit(f"Playlists fetch error: {exc}")
            return

        playlists = []
        for item in resp.get("items", []):
            snippet = item.get("snippet", {})
            playlists.append({
                "playlist_id": item["id"],
                "title":       snippet.get("title", ""),
                "channel":     snippet.get("channelTitle", ""),
            })
        self.results_ready.emit(playlists)


# ── Main panel ─────────────────────────────────────────────────────────────────

class YouTubePanel(QDockWidget):
    """
    Dockable YouTube audio panel for Project Ceres.

    Uses yt-dlp to stream audio from YouTube URLs into pygame.mixer.music.
    Provides search (YouTube Data API v3), playlist browsing (OAuth2),
    and 8 scene quick-launch slots.

    Signals
    -------
    status_message(str)     — forwarded to the main window status bar
    volume_changed(int)     — emitted when the volume slider changes (0–100)

    Public slots
    ------------
    set_volume(int)         — set volume 0–100 from Mixer panel
    handle_command(str,str) — voice/chat command dispatch
    """

    status_message: Signal = Signal(str)
    volume_changed: Signal = Signal(int)

    # Internal cross-thread signal for thread-safe thumbnail updates
    _thumb_loaded  = Signal(bytes)

    # Signals routed to the search worker
    _sig_search    = Signal(str, str)   # api_key, query
    _sig_playlists = Signal(str)        # access_token

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("YouTube", parent)
        self.setObjectName("YouTubePanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)       # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |          # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config      = config
        self._run_command = run_command

        # State
        self._api_key            = ""
        self._connected          = False
        self._access_token       = ""
        self._search_results: List[Dict] = []
        self._playlists: List[Dict]      = []
        self._current_title      = ""
        self._current_channel    = ""
        self._current_duration   = 0    # seconds
        self._elapsed_s          = 0
        self._autoplay_on_results = False

        # Scene config: slot_key → {"url": str, "title": str} | None
        self._scene_config: Dict[str, Optional[Dict]] = {
            key: None for _, key in SCENE_SLOTS
        }
        self._scene_buttons: Dict[str, QPushButton] = {}

        # Active playback thread (keep reference to prevent GC)
        self._audio_thread: Optional[_YTAudioThread] = None

        self._load_scene_config()
        self._build_ui()
        self._setup_worker()

        # Auto-connect if API key is present in env
        key = self._load_api_key()
        if key:
            self._set_connected(key)

    # ── Env loading ────────────────────────────────────────────────────────────

    def _load_api_key(self) -> str:
        """Load YOUTUBE_API_KEY from environment or variables.env.

        Returns:
            The API key string, or empty string if not found.
        """
        key = os.environ.get("YOUTUBE_API_KEY", "")
        if not key:
            here = Path(__file__).resolve().parent
            for _ in range(6):
                env_path = here / "variables.env"
                if env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, v = line.partition("=")
                        if k.strip() == "YOUTUBE_API_KEY":
                            key = v.strip()
                            break
                    break
                here = here.parent
        return key

    def _load_client_secrets_path(self) -> str:
        """Load YOUTUBE_CLIENT_SECRETS_FILE from environment or variables.env.

        Returns:
            Path string, or empty string if not set.
        """
        val = os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "")
        if not val:
            here = Path(__file__).resolve().parent
            for _ in range(6):
                env_path = here / "variables.env"
                if env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, v = line.partition("=")
                        if k.strip() == "YOUTUBE_CLIENT_SECRETS_FILE":
                            val = v.strip()
                            break
                    break
                here = here.parent
        return val

    # ── Scene config persistence ────────────────────────────────────────────────

    def _load_scene_config(self) -> None:
        try:
            data = load_scene_data(self._config, "youtube", SCENE_CONFIG_PATH, {})
            if isinstance(data, dict):
                for _, key in SCENE_SLOTS:
                    if key in data:
                        self._scene_config[key] = data[key]
        except Exception:
            pass

    def _save_scene_config(self) -> None:
        try:
            save_scene_data(self._config, "youtube", SCENE_CONFIG_PATH, self._scene_config)
        except Exception:
            pass

    # ── Worker thread setup ────────────────────────────────────────────────────

    def _setup_worker(self) -> None:
        self._search_thread = QThread(self)
        self._search_worker = _SearchWorker()
        self._search_worker.moveToThread(self._search_thread)

        self._search_worker.results_ready.connect(self._on_results_ready)
        self._search_worker.search_error.connect(self._on_search_error)
        self._search_thread.finished.connect(self._search_worker.deleteLater)

        self._sig_search.connect(self._search_worker.do_search)
        self._sig_playlists.connect(self._search_worker.do_load_playlists)

        # Thread-safe thumbnail update
        self._thumb_loaded.connect(self._on_thumb_loaded)

        self._search_thread.start()

        # Progress bar tick timer
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(PROGRESS_TICK_MS)
        self._progress_timer.timeout.connect(self._on_progress_tick)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer  = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── Header: status dot + label + Disconnect + Connect ─────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(5)

        self._dot_label = QLabel("●")
        self._dot_label.setFixedWidth(16)
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        hdr.addWidget(self._dot_label)

        self._status_label = QLabel("○ Not connected")
        self._status_label.setStyleSheet(f"color: {MUTED};")
        hdr.addWidget(self._status_label, 1)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setFixedWidth(90)
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        hdr.addWidget(self._disconnect_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setProperty("class", "accent")
        self._connect_btn.setFixedWidth(74)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        hdr.addWidget(self._connect_btn)

        layout.addLayout(hdr)

        # ── Missing-dependency hint ────────────────────────────────────────────
        missing = []
        if not _YTDLP_AVAILABLE:
            missing.append("yt-dlp")
        if not _GOOGLE_API_AVAILABLE:
            missing.append("google-api-python-client")
        if not _PYGAME_OK:
            missing.append("pygame")
        if missing:
            warn = QLabel(
                f"⚠  Missing: {', '.join(missing)}\n"
                f"Run:  pip install {' '.join(missing)}"
            )
            warn.setStyleSheet(
                f"color: {WARNING}; font-size: 9px; padding: 5px;"
                f"border: 1px solid {WARNING}; border-radius: 3px;"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_now_playing_tab(), "🎬 Now Playing")
        self._tabs.addTab(self._build_search_tab(),      "🔍 Search")
        self._tabs.addTab(self._build_playlists_tab(),   "📚 My Playlists")
        self._tabs.addTab(self._build_scenes_tab(),      "🎬 Scenes")
        layout.addWidget(self._tabs, 1)

        # ── Footer: volume ─────────────────────────────────────────────────────
        vol_row = QHBoxLayout()
        vol_row.setSpacing(5)

        vol_lbl = QLabel("🔊")
        vol_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        vol_lbl.setFixedWidth(18)
        vol_row.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.valueChanged.connect(self._on_vol_changed)
        vol_row.addWidget(self._vol_slider, 1)

        self._vol_val_label = QLabel("80")
        self._vol_val_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._vol_val_label.setFixedWidth(24)
        vol_row.addWidget(self._vol_val_label)

        layout.addLayout(vol_row)
        self.setWidget(outer)

    # ── Now Playing tab ────────────────────────────────────────────────────────

    def _build_now_playing_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        # Thumbnail + metadata
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(THUMB_W, THUMB_H)
        self._thumb_label.setStyleSheet(
            f"background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 3px;"
        )
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        self._thumb_label.setText("🎬")
        meta_row.addWidget(self._thumb_label)

        meta_text = QVBoxLayout()
        meta_text.setSpacing(4)

        self._np_title_label = QLabel("Nothing playing")
        self._np_title_label.setStyleSheet(
            f"color: {TEXT}; font-weight: bold; font-size: 10px;"
        )
        self._np_title_label.setWordWrap(True)
        meta_text.addWidget(self._np_title_label)

        self._np_channel_label = QLabel("")
        self._np_channel_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        meta_text.addWidget(self._np_channel_label)

        self._np_source_label = QLabel("")
        self._np_source_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        meta_text.addWidget(self._np_source_label)

        meta_text.addStretch()
        meta_row.addLayout(meta_text, 1)
        v.addLayout(meta_row)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        v.addWidget(self._progress_bar)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        v.addWidget(self._time_label)

        # Transport controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        ctrl_row.addStretch()

        self._prev_btn = QPushButton("⏮")
        self._prev_btn.setFixedWidth(36)
        self._prev_btn.setToolTip("Restart current track")
        self._prev_btn.clicked.connect(self._on_rewind)
        ctrl_row.addWidget(self._prev_btn)

        self._play_pause_btn = QPushButton("▶")
        self._play_pause_btn.setFixedWidth(36)
        self._play_pause_btn.setProperty("class", "accent")
        self._play_pause_btn.clicked.connect(self._on_play_pause)
        ctrl_row.addWidget(self._play_pause_btn)

        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setFixedWidth(36)
        self._stop_btn.setToolTip("Stop playback")
        self._stop_btn.clicked.connect(self._on_stop)
        ctrl_row.addWidget(self._stop_btn)

        self._next_btn = QPushButton("⏭")
        self._next_btn.setFixedWidth(36)
        self._next_btn.setToolTip("Next in search results")
        self._next_btn.clicked.connect(self._on_next)
        ctrl_row.addWidget(self._next_btn)

        ctrl_row.addStretch()
        v.addLayout(ctrl_row)
        v.addStretch()

        return w

    # ── Search tab ─────────────────────────────────────────────────────────────

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.setSpacing(5)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search YouTube…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.returnPressed.connect(self._on_search_clicked)
        search_row.addWidget(self._search_edit, 1)

        self._search_btn = QPushButton("🔍 Search")
        self._search_btn.setFixedWidth(84)
        self._search_btn.clicked.connect(self._on_search_clicked)
        search_row.addWidget(self._search_btn)

        v.addLayout(search_row)

        self._result_list = QListWidget()
        self._result_list.setAlternatingRowColors(True)
        self._result_list.setToolTip("Double-click to play")
        self._result_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        v.addWidget(self._result_list, 1)

        play_row = QHBoxLayout()
        play_row.addStretch()
        self._play_selected_btn = QPushButton("▶ Play Selected")
        self._play_selected_btn.clicked.connect(self._on_play_selected)
        play_row.addWidget(self._play_selected_btn)
        v.addLayout(play_row)

        return w

    # ── My Playlists tab ───────────────────────────────────────────────────────

    def _build_playlists_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self._oauth_widget = QWidget()
        oauth_v = QVBoxLayout(self._oauth_widget)
        oauth_v.setContentsMargins(0, 0, 0, 0)
        oauth_v.setSpacing(8)

        self._signin_label = QLabel(
            "Sign in with Google to browse your YouTube playlists.\n\n"
            "Requires YOUTUBE_CLIENT_SECRETS_FILE set in variables.env."
        )
        self._signin_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._signin_label.setWordWrap(True)
        oauth_v.addWidget(self._signin_label)

        self._signin_btn = QPushButton("Sign in with Google")
        self._signin_btn.setProperty("class", "accent")
        self._signin_btn.clicked.connect(self._on_signin)
        oauth_v.addWidget(self._signin_btn)
        oauth_v.addStretch()

        v.addWidget(self._oauth_widget)

        self._playlist_list = QListWidget()
        self._playlist_list.setAlternatingRowColors(True)
        self._playlist_list.setToolTip("Double-click to play first video in playlist")
        self._playlist_list.itemDoubleClicked.connect(self._on_playlist_double_clicked)
        self._playlist_list.hide()
        v.addWidget(self._playlist_list, 1)

        return w

    # ── Scenes tab ─────────────────────────────────────────────────────────────

    def _build_scenes_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        scene_lbl = QLabel("Scene Quick-Launch")
        scene_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        v.addWidget(scene_lbl)

        hint = QLabel("Left-click: play  ·  Right-click: assign or clear")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        v.addWidget(hint)

        grid_w  = QWidget()
        grid    = QGridLayout(grid_w)
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (label, key) in enumerate(SCENE_SLOTS):
            btn = QPushButton(label)
            btn.setMinimumHeight(44)
            btn.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu  # type: ignore[attr-defined]
            )
            btn.customContextMenuRequested.connect(
                lambda pos, k=key, b=btn: self._on_scene_context_menu(b, k, pos)
            )
            btn.clicked.connect(lambda checked, k=key: self._on_scene_clicked(k))
            self._scene_buttons[key] = btn
            self._update_scene_btn_style(key)
            grid.addWidget(btn, i // 2, i % 2)

        v.addWidget(grid_w)
        v.addStretch()

        return w

    # ── Scene button helpers ───────────────────────────────────────────────────

    def _scene_tooltip(self, key: str) -> str:
        assigned = self._scene_config.get(key)
        if assigned:
            return (
                f"▶ {assigned.get('title', key)}\n"
                "Right-click to reassign or clear"
            )
        return "No video assigned\nRight-click to assign a video to this slot"

    def _update_scene_btn_style(self, key: str) -> None:
        btn = self._scene_buttons.get(key)
        if btn is None:
            return
        assigned  = self._scene_config.get(key)
        label_txt = next((lbl for lbl, k in SCENE_SLOTS if k == key), key)
        if assigned:
            title = assigned.get("title", "")
            sub   = f"\n{title}" if title else ""
            btn.setText(f"{label_txt}{sub}")
            btn.setStyleSheet(
                f"QPushButton {{ background: {ACCENT2}; color: {TEXT};"
                f" border: 1px solid {ACCENT}; border-radius: 3px;"
                f" text-align: center; padding: 4px; }}"
                f"QPushButton:hover {{ background: {ACCENT}; }}"
            )
        else:
            btn.setText(label_txt)
            btn.setStyleSheet("")
        btn.setToolTip(self._scene_tooltip(key))

    # ── Connection management ──────────────────────────────────────────────────

    def _set_connected(self, api_key: str) -> None:
        """Mark connected and update the header UI.

        Args:
            api_key: The validated YouTube API key.
        """
        self._api_key   = api_key
        self._connected = True
        self._dot_label.setStyleSheet(f"color: {SUCCESS}; font-size: 14px;")
        self._status_label.setText("● API Key Loaded")
        self._status_label.setStyleSheet(f"color: {SUCCESS};")
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        self.status_message.emit("YouTube: API key loaded")

    def _on_connect_clicked(self) -> None:
        key, ok = QInputDialog.getText(
            self,
            "YouTube API Key",
            "Paste your YouTube Data API v3 key:",
            QLineEdit.EchoMode.Normal,
            self._api_key,
        )
        if ok and key.strip():
            self._set_connected(key.strip())

    def _on_disconnect(self) -> None:
        self._api_key   = ""
        self._connected = False
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        self._status_label.setText("○ Not connected")
        self._status_label.setStyleSheet(f"color: {MUTED};")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self.status_message.emit("YouTube: disconnected")

    # ── Search ─────────────────────────────────────────────────────────────────

    def _on_search_clicked(self) -> None:
        query = self._search_edit.text().strip()
        if not query:
            return
        if not self._api_key:
            self.status_message.emit("YouTube: no API key — use Connect to add one")
            return
        if not _GOOGLE_API_AVAILABLE:
            self.status_message.emit(
                "YouTube: google-api-python-client not installed — "
                "run: pip install google-api-python-client"
            )
            return
        self._search_btn.setEnabled(False)
        self._search_btn.setText("Searching…")
        self.status_message.emit(f"YouTube: searching for '{query}'…")
        self._sig_search.emit(self._api_key, query)

    def _on_results_ready(self, results: list) -> None:
        """Handle results from the search worker (both video search and playlists).

        Args:
            results: List of result dicts. Video results have 'video_id';
                     playlist results have 'playlist_id'.
        """
        self._search_btn.setEnabled(True)
        self._search_btn.setText("🔍 Search")

        if not results:
            self.status_message.emit("YouTube: no results found")
            return

        if "video_id" in results[0]:
            # Video search results
            self._search_results = results
            self._result_list.clear()
            for item in results:
                dur   = f"  [{item['duration']}]" if item.get("duration") else ""
                label = f"{item['title']}  ·  {item['channel']}{dur}"
                lw    = QListWidgetItem(label)
                lw.setData(Qt.ItemDataRole.UserRole,     item["url"])    # type: ignore[attr-defined]
                lw.setData(Qt.ItemDataRole.UserRole + 1, item["title"])  # type: ignore[attr-defined]
                self._result_list.addItem(lw)
            self.status_message.emit(f"YouTube: {len(results)} results")
            self._tabs.setCurrentIndex(1)

            if self._autoplay_on_results:
                self._autoplay_on_results = False
                self._play_url(results[0]["url"], results[0]["title"])
                self._result_list.setCurrentRow(0)
        else:
            # Playlist results
            self._playlists = results
            self._playlist_list.clear()
            for pl in results:
                lw = QListWidgetItem(pl.get("title", ""))
                lw.setData(Qt.ItemDataRole.UserRole, pl.get("playlist_id", ""))  # type: ignore[attr-defined]
                self._playlist_list.addItem(lw)
            if results:
                self._oauth_widget.hide()
                self._playlist_list.show()
            self.status_message.emit(f"YouTube: {len(results)} playlists loaded")

    def _on_search_error(self, msg: str) -> None:
        self._search_btn.setEnabled(True)
        self._search_btn.setText("🔍 Search")
        self.status_message.emit(f"YouTube error: {msg}")

    # ── Playback ───────────────────────────────────────────────────────────────

    def _play_url(self, url: str, title: str = "") -> None:
        """Start playback of a YouTube URL.

        Args:
            url:   Full YouTube watch URL or query string for yt-dlp.
            title: Optional pre-known title used in status messages.
        """
        if not _YTDLP_AVAILABLE:
            self.status_message.emit("YouTube: yt-dlp not installed — run: pip install yt-dlp")
            return
        if not _PYGAME_OK:
            self.status_message.emit("YouTube: pygame not installed — run: pip install pygame")
            return

        # Clean up any previous playback thread
        if self._audio_thread and self._audio_thread.isRunning():
            self._audio_thread.quit()
            self._audio_thread.wait(1000)

        self._progress_timer.stop()
        self._elapsed_s = 0
        self._play_pause_btn.setText("▶")
        self.status_message.emit(f"YouTube: loading '{title or url}'…")

        self._audio_thread = _YTAudioThread(url, self)
        self._audio_thread.playback_started.connect(self._on_playback_started)
        self._audio_thread.playback_error.connect(self._on_playback_error)
        self._audio_thread.start()

    def _on_playback_started(
        self, title: str, channel: str, duration_s: int, thumb_url: str
    ) -> None:
        self._current_title    = title
        self._current_channel  = channel
        self._current_duration = duration_s
        self._elapsed_s        = 0

        self._np_title_label.setText(title)
        self._np_channel_label.setText(channel)
        dur_str = _fmt_seconds(duration_s) if duration_s else ""
        self._np_source_label.setText(f"YouTube · {dur_str}" if dur_str else "YouTube")

        self._progress_bar.setValue(0)
        self._time_label.setText(f"0:00 / {dur_str}" if dur_str else "0:00")
        self._play_pause_btn.setText("⏸")
        self._progress_timer.start()
        self.status_message.emit(f"YouTube: ▶ {title}")
        self._tabs.setCurrentIndex(0)

        # Reset thumbnail placeholder while we fetch
        self._thumb_label.setText("🎬")
        self._thumb_label.setPixmap(QPixmap())

        if thumb_url:
            threading.Thread(
                target=self._fetch_thumbnail,
                args=(thumb_url,),
                daemon=True,
            ).start()

        if _PYGAME_OK:
            try:
                _pygame.mixer.music.set_volume(self._vol_slider.value() / 100)
            except Exception:
                pass

    def _on_playback_error(self, msg: str) -> None:
        self.status_message.emit(f"YouTube error: {msg}")

    def _fetch_thumbnail(self, url: str) -> None:
        """Fetch thumbnail bytes and emit signal to update UI on main thread."""
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read()
            self._thumb_loaded.emit(bytes(data))
        except Exception:
            pass

    def _on_thumb_loaded(self, data: bytes) -> None:
        """Apply fetched thumbnail bytes to the Now Playing thumbnail label."""
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    THUMB_W, THUMB_H,
                    Qt.AspectRatioMode.KeepAspectRatio,            # type: ignore[attr-defined]
                    Qt.TransformationMode.SmoothTransformation,    # type: ignore[attr-defined]
                )
                self._thumb_label.setText("")
                self._thumb_label.setPixmap(pixmap)
        except Exception:
            pass

    def _on_progress_tick(self) -> None:
        if not _PYGAME_OK:
            return
        try:
            busy = _pygame.mixer.music.get_busy()
        except Exception:
            return

        if not busy:
            self._progress_timer.stop()
            self._play_pause_btn.setText("▶")
            return

        pos_ms = _pygame.mixer.music.get_pos()
        self._elapsed_s = pos_ms // 1000 if pos_ms >= 0 else self._elapsed_s + 1

        if self._current_duration > 0:
            pct = min(100, int(self._elapsed_s * 100 / self._current_duration))
            self._progress_bar.setValue(pct)
            dur_str = _fmt_seconds(self._current_duration)
            ela_str = _fmt_seconds(self._elapsed_s)
            self._time_label.setText(f"{ela_str} / {dur_str}")

    # ── Transport controls ─────────────────────────────────────────────────────

    def _on_play_pause(self) -> None:
        if not _PYGAME_OK:
            return
        try:
            if _pygame.mixer.music.get_busy():
                _pygame.mixer.music.pause()
                self._play_pause_btn.setText("▶")
                self._progress_timer.stop()
            else:
                _pygame.mixer.music.unpause()
                self._play_pause_btn.setText("⏸")
                self._progress_timer.start()
        except Exception:
            pass

    def _on_stop(self) -> None:
        if not _PYGAME_OK:
            return
        try:
            _pygame.mixer.music.stop()
        except Exception:
            pass
        self._progress_timer.stop()
        self._play_pause_btn.setText("▶")
        self._progress_bar.setValue(0)
        self._time_label.setText("0:00 / 0:00")
        self.status_message.emit("YouTube: ⏹ stopped")

    def _on_rewind(self) -> None:
        if not _PYGAME_OK:
            return
        try:
            _pygame.mixer.music.rewind()
            self._elapsed_s = 0
            self._progress_bar.setValue(0)
        except Exception:
            pass

    def _on_next(self) -> None:
        """Advance to the next item in the current search results list."""
        if not self._search_results:
            return
        cur = self._result_list.currentRow()
        nxt = (cur + 1) % len(self._search_results)
        self._result_list.setCurrentRow(nxt)
        item = self._result_list.item(nxt)
        if item:
            url   = item.data(Qt.ItemDataRole.UserRole)      # type: ignore[attr-defined]
            title = item.data(Qt.ItemDataRole.UserRole + 1)  # type: ignore[attr-defined]
            self._play_url(url, title)

    # ── Result list interaction ────────────────────────────────────────────────

    def _on_result_double_clicked(self, item: QListWidgetItem) -> None:
        url   = item.data(Qt.ItemDataRole.UserRole)      # type: ignore[attr-defined]
        title = item.data(Qt.ItemDataRole.UserRole + 1)  # type: ignore[attr-defined]
        if url:
            self._play_url(url, title)

    def _on_play_selected(self) -> None:
        items = self._result_list.selectedItems()
        if items:
            self._on_result_double_clicked(items[0])

    # ── My Playlists ───────────────────────────────────────────────────────────

    def _on_signin(self) -> None:
        secrets_path = self._load_client_secrets_path()
        if not secrets_path:
            QMessageBox.information(
                self,
                "Client Secrets Required",
                "Set YOUTUBE_CLIENT_SECRETS_FILE in variables.env:\n\n"
                "  YOUTUBE_CLIENT_SECRETS_FILE=client_secrets.json\n\n"
                "Get a client_secrets.json from:\n"
                "https://console.cloud.google.com/apis/credentials",
            )
            return
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            import google.oauth2.credentials as _oauth_creds

            # Reuse a previously saved token if still valid
            if TOKEN_PATH.exists():
                cred_data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
                cred = _oauth_creds.Credentials.from_authorized_user_info(cred_data)
                if cred and cred.valid:
                    self._access_token = cred.token
                    self._sig_playlists.emit(self._access_token)
                    return

            scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
            flow   = InstalledAppFlow.from_client_secrets_file(secrets_path, scopes)
            cred   = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(cred.to_json(), encoding="utf-8")
            self._access_token = cred.token
            self._sig_playlists.emit(self._access_token)
        except ImportError:
            QMessageBox.warning(
                self,
                "Missing Dependency",
                "google-auth-oauthlib is required for playlist sign-in.\n\n"
                "Run:  pip install google-auth-oauthlib",
            )
        except Exception as exc:
            self.status_message.emit(f"YouTube OAuth error: {exc}")

    def _on_playlist_double_clicked(self, item: QListWidgetItem) -> None:
        """Play the first video of the selected playlist.

        Args:
            item: The double-clicked playlist list item.
        """
        playlist_id = item.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if not playlist_id:
            return
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        self._play_url(url, item.text())

    # ── Scene interaction ──────────────────────────────────────────────────────

    def _on_scene_clicked(self, key: str) -> None:
        assigned = self._scene_config.get(key)
        if assigned and assigned.get("url"):
            self._play_url(assigned["url"], assigned.get("title", key))
            self.status_message.emit(
                f"YouTube scene: ▶ {assigned.get('title', key)}"
            )
        else:
            QMessageBox.information(
                self,
                "No Video Assigned",
                f"The «{key}» scene slot has no video assigned yet.\n\n"
                "Search for a video then right-click this slot to assign it.",
            )

    def _on_scene_context_menu(
        self, btn: QPushButton, key: str, pos
    ) -> None:
        menu     = QMenu(self)
        assigned = self._scene_config.get(key)

        if assigned and assigned.get("url"):
            play_act = menu.addAction(
                f"▶  Play: {assigned.get('title', key)}"
            )
            play_act.triggered.connect(lambda: self._on_scene_clicked(key))
            menu.addSeparator()

        assign_act = menu.addAction("📌  Assign selected video")
        assign_act.triggered.connect(lambda: self._assign_selected_video(key))

        url_act = menu.addAction("🔗  Assign by URL…")
        url_act.triggered.connect(lambda: self._assign_by_url(key))

        if assigned:
            menu.addSeparator()
            clear_act = menu.addAction("✕  Clear assignment")
            clear_act.triggered.connect(lambda: self._clear_scene(key))

        menu.exec(btn.mapToGlobal(pos))

    def _assign_selected_video(self, key: str) -> None:
        """Assign the currently selected search result to a scene slot.

        Args:
            key: Scene slot key.
        """
        items = self._result_list.selectedItems()
        if not items:
            QMessageBox.information(
                self,
                "No Video Selected",
                "Please search for a video and select it in the Search tab first.",
            )
            return
        item  = items[0]
        url   = item.data(Qt.ItemDataRole.UserRole)      # type: ignore[attr-defined]
        title = item.data(Qt.ItemDataRole.UserRole + 1)  # type: ignore[attr-defined]
        self._scene_config[key] = {"url": url, "title": title}
        self._save_scene_config()
        self._update_scene_btn_style(key)
        self.status_message.emit(f"YouTube: assigned '{title}' to {key} scene")

    def _assign_by_url(self, key: str) -> None:
        """Open a dialog to paste a URL and assign it to a scene slot.

        Args:
            key: Scene slot key.
        """
        url, ok = QInputDialog.getText(
            self, "Assign by URL", "Paste a YouTube video URL:",
        )
        if not ok or not url.strip():
            return
        title, ok2 = QInputDialog.getText(
            self, "Scene Label", "Short label for this scene slot:",
        )
        self._scene_config[key] = {
            "url":   url.strip(),
            "title": title.strip() if (ok2 and title.strip()) else url.strip(),
        }
        self._save_scene_config()
        self._update_scene_btn_style(key)
        self.status_message.emit(f"YouTube: assigned URL to {key} scene")

    def _clear_scene(self, key: str) -> None:
        self._scene_config[key] = None
        self._save_scene_config()
        self._update_scene_btn_style(key)
        self.status_message.emit(f"YouTube: cleared {key} scene")

    # ── Volume ─────────────────────────────────────────────────────────────────

    def _on_vol_changed(self, value: int) -> None:
        self._vol_val_label.setText(str(value))
        self.volume_changed.emit(value)
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.set_volume(value / 100)
            except Exception:
                pass

    def get_volume(self) -> int:
        """Return the current volume slider value (0–100).

        Returns:
            Volume 0–100.
        """
        return self._vol_slider.value()

    @Slot(int)
    def set_volume(self, vol: int) -> None:
        """Set volume from the Mixer panel without emitting a volume_changed echo.

        Args:
            vol: Volume level 0–100.
        """
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(vol)
        self._vol_val_label.setText(str(vol))
        self._vol_slider.blockSignals(False)
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.set_volume(vol / 100)
            except Exception:
                pass

    def get_np_state(self) -> dict:
        """Return current playback state for the Now Playing panel."""
        try:
            import pygame

            playing = bool(pygame.mixer.get_init() and pygame.mixer.music.get_busy())
        except Exception:
            playing = False
        title = getattr(self, "_current_title", "")
        subtitle = getattr(self, "_current_channel", "")
        dur = getattr(self, "_current_duration", 0)  # seconds
        elapsed = 0
        try:
            import pygame as _pg

            if _pg.mixer.get_init():
                pos_ms = _pg.mixer.music.get_pos()
                if pos_ms >= 0:
                    elapsed = int(pos_ms / 1000)
        except Exception:
            pass
        pct = int(elapsed * 100 / dur) if dur > 0 else (-1 if not playing else 0)
        return {
            "playing": playing,
            "paused": False,
            "title": title,
            "subtitle": subtitle,
            "progress_pct": pct,
            "can_pause": False,
            "can_next": False,
            "can_prev": False,
            "can_stop": True,
        }

    # ── Voice command handler ──────────────────────────────────────────────────

    @Slot(str, str)
    def handle_command(self, action: str, query: str) -> None:
        """Handle a voice/chat command dispatched from Discord or ChatAgent.

        Args:
            action: "play" | "pause" | "stop" | "search"
            query:  Search string for play/search; ignored for pause/stop.
        """
        action = action.lower().strip()
        self.status_message.emit(f"YouTube ← command: {action!r}  query={query!r}")

        if action == "stop":
            self._on_stop()

        elif action == "pause":
            self._on_play_pause()

        elif action in ("play", "search"):
            if not self._api_key:
                self.status_message.emit("YouTube: no API key configured")
                return
            if not _GOOGLE_API_AVAILABLE:
                self.status_message.emit(
                    "YouTube: google-api-python-client not installed — "
                    "run: pip install google-api-python-client"
                )
                return
            if not query.strip():
                self.status_message.emit("YouTube: no search query provided")
                return
            self._search_edit.setText(query.strip())
            self._sig_search.emit(self._api_key, query.strip())
            self.status_message.emit(f"YouTube ← playing '{query}'…")

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop background threads and pygame cleanly before destruction."""
        self._progress_timer.stop()
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.stop()
            except Exception:
                pass
        if self._audio_thread and self._audio_thread.isRunning():
            self._audio_thread.quit()
            self._audio_thread.wait(2000)
        if hasattr(self, "_search_thread") and self._search_thread.isRunning():
            try:
                self._sig_search.disconnect(self._search_worker.do_search)
            except Exception:
                pass
            try:
                self._sig_playlists.disconnect(self._search_worker.do_load_playlists)
            except Exception:
                pass
            self._search_thread.quit()
            self._search_thread.wait(2000)
        super().closeEvent(event)
