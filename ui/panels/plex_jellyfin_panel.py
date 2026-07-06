"""
Plex / Jellyfin panel for Project Ceres — GM Assistant UI.

Connects to a self-hosted Plex or Jellyfin media server, browses the music
library, and plays audio locally via pygame.mixer.music.

Features
--------
  - Server-type toggle: Plex or Jellyfin (single panel, shared UI)
  - URL + API-token connection with live status feedback
  - Library tree: Artist → Album → Track (double-click to play)
  - Now Playing: 80×80 art, track/artist/album, progress bar, transport
  - Search tab: text query → results list → double-click to play
  - Scene quick-launch: 8 configurable slots (persist to plex_jellyfin_scenes.json)
  - Mixer integration: volume_changed / set_volume / get_volume
  - handle_command("play"/"pause"/"stop"/"next", query) for Discord wiring

Requirements (optional — panel shows an install hint if missing)
------------
    pip install requests pygame

Architecture
------------
  Plex:     HTTP GET to <host>:32400 with X-Plex-Token header.
  Jellyfin: HTTP GET to <host>:8096 with Authorization: MediaBrowser Token=…
  Both return JSON (Jellyfin) or XML (Plex, parsed manually).
  Audio stream URLs are fetched via requests, then handed to
  pygame.mixer.music — same pattern as the Tidal and YouTube panels.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider, QProgressBar,
        QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QGridLayout, QSizePolicy, QMessageBox, QInputDialog,
        QComboBox, QMenu, QApplication,
    )
    from PyQt5.QtCore import (
        Qt, QThread, QObject, QTimer, QSize,
        pyqtSignal as Signal, pyqtSlot as Slot,
    )
    from PyQt5.QtGui import QPixmap, QIcon, QFont
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider, QProgressBar,
        QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QGridLayout, QSizePolicy, QMessageBox, QInputDialog,
        QComboBox, QMenu, QApplication,
    )
    from PySide6.QtCore import Qt, QThread, QObject, QTimer, QSize, Signal, Slot  # type: ignore
    from PySide6.QtGui import QPixmap, QIcon, QFont  # type: ignore

from ui.theme import (
    ACCENT, ACCENT2, BG, BORDER, ERROR, MUTED,
    PANEL, SUCCESS, SURFACE, TEXT, WARNING,
)
from pantheon.vervactor.workspace import load_scene_data, save_scene_data

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _requests = None  # type: ignore[assignment]
    _REQUESTS_OK = False

try:
    import pygame as _pygame
    _PYGAME_OK = True
except ImportError:
    _pygame = None  # type: ignore[assignment]
    _PYGAME_OK = False

# ── Constants ──────────────────────────────────────────────────────────────────

ALBUM_ART_SIZE   = 80
PROGRESS_TICK_MS = 1_000
PLEX_DEFAULT_PORT    = 32400
JELLYFIN_DEFAULT_PORT = 8096

SERVER_TYPES = ["Plex", "Jellyfin"]

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

_PROJECT_ROOT      = Path(__file__).resolve().parent.parent.parent
_SCENE_CONFIG_PATH = _PROJECT_ROOT / "plex_jellyfin_scenes.json"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_env_key(env_path: str, key: str) -> str:
    """Read a single KEY=VALUE from an env file. Returns '' if not found."""
    try:
        for line in Path(env_path).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                if k.strip() == key:
                    return v.strip()
    except Exception:
        pass
    return ""


def _write_env_key(env_path: str, key: str, value: str) -> None:
    """Write or update a single KEY=VALUE in an env file, preserving all other content."""
    path   = Path(env_path)
    lines  = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found  = False
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.partition("=")[0].strip()
            if k == key:
                result.append(f"{key}={value}")
                found = True
                continue
        result.append(line)
    if not found:
        result.append(f"{key}={value}")
    path.write_text("\n".join(result) + "\n", encoding="utf-8")


def _s_to_str(seconds: int) -> str:
    """Format seconds as M:SS string."""
    m, s = divmod(max(seconds, 0), 60)
    return f"{m}:{s:02d}"


def _ms_to_str(milliseconds: int) -> str:
    """Format milliseconds as M:SS string."""
    return _s_to_str(milliseconds // 1000)


# ── API clients ────────────────────────────────────────────────────────────────

class _PlexClient:
    """Thin HTTP wrapper for the Plex Media Server REST API."""

    def __init__(self, base_url: str, token: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.token    = token
        self.timeout  = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Plex-Token":          self.token,
            "X-Plex-Client-Identifier": "ProjectCeresGMAssistant",
            "Accept":                "application/json",
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> dict:
        url  = self.base_url + path
        resp = _requests.get(url, headers=self._headers(),
                             params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def ping(self) -> bool:
        """Return True if the server is reachable and the token is valid."""
        try:
            self._get("/identity")
            return True
        except Exception:
            return False

    def music_sections(self) -> List[Dict]:
        """Return list of music library sections: {id, title}."""
        data    = self._get("/library/sections")
        entries = data.get("MediaContainer", {}).get("Directory", [])
        return [{"id": e["key"], "title": e["title"]}
                for e in entries if e.get("type") == "artist"]

    def artists(self, section_id: str) -> List[Dict]:
        """Return artists in a section: {id, title}."""
        data   = self._get(f"/library/sections/{section_id}/all",
                           params={"type": "8"})
        items  = data.get("MediaContainer", {}).get("Metadata", [])
        return [{"id": it["ratingKey"], "title": it.get("title", "?")}
                for it in items]

    def albums(self, artist_id: str) -> List[Dict]:
        """Return albums for an artist: {id, title, year}."""
        data  = self._get(f"/library/metadata/{artist_id}/children")
        items = data.get("MediaContainer", {}).get("Metadata", [])
        return [{"id": it["ratingKey"],
                 "title": it.get("title", "?"),
                 "year":  it.get("year", "")}
                for it in items]

    def tracks(self, album_id: str) -> List[Dict]:
        """Return tracks for an album: {id, title, duration_ms, index, stream_key}."""
        data  = self._get(f"/library/metadata/{album_id}/children")
        items = data.get("MediaContainer", {}).get("Metadata", [])
        result = []
        for it in items:
            part  = (it.get("Media") or [{}])[0]
            parts = (part.get("Part") or [{}])[0]
            result.append({
                "id":          it["ratingKey"],
                "title":       it.get("title", "?"),
                "duration_ms": it.get("duration", 0),
                "index":       it.get("index", 0),
                "stream_key":  parts.get("key", ""),
            })
        return result

    def stream_url(self, stream_key: str) -> str:
        """Direct stream URL for a track part key."""
        token_param = urllib.parse.urlencode({"X-Plex-Token": self.token})
        return f"{self.base_url}{stream_key}?download=1&{token_param}"

    def search_tracks(self, query: str) -> List[Dict]:
        """Search for tracks by title: returns same schema as tracks()."""
        data  = self._get("/library/search",
                          params={"query": query, "type": "10"})
        items = data.get("MediaContainer", {}).get("Metadata", [])
        result = []
        for it in items:
            part  = (it.get("Media") or [{}])[0]
            parts = (part.get("Part") or [{}])[0]
            result.append({
                "id":          it["ratingKey"],
                "title":       it.get("title", "?"),
                "artist":      it.get("grandparentTitle", ""),
                "album":       it.get("parentTitle", ""),
                "duration_ms": it.get("duration", 0),
                "stream_key":  parts.get("key", ""),
            })
        return result

    def album_art_url(self, metadata_id: str) -> str:
        """Return a URL for album art (thumb) for a metadata item."""
        token_param = urllib.parse.urlencode({"X-Plex-Token": self.token})
        return f"{self.base_url}/library/metadata/{metadata_id}/thumb?{token_param}"


class _JellyfinClient:
    """Thin HTTP wrapper for the Jellyfin REST API."""

    def __init__(self, base_url: str, token: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.token    = token
        self.timeout  = timeout
        self._user_id: str = ""

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"MediaBrowser Token={self.token}",
            "Accept":        "application/json",
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> dict:
        url  = self.base_url + path
        resp = _requests.get(url, headers=self._headers(),
                             params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def ping(self) -> bool:
        """Return True if server reachable and token valid; also caches user ID."""
        try:
            data = self._get("/Users/Me")
            self._user_id = data.get("Id", "")
            return True
        except Exception:
            return False

    def user_id(self) -> str:
        """Return cached user ID (call ping() first)."""
        return self._user_id

    def artists(self) -> List[Dict]:
        """Return all album artists: {id, title}."""
        data  = self._get("/Artists/AlbumArtists",
                          params={"Recursive": "true", "UserId": self._user_id})
        items = data.get("Items", [])
        return [{"id": it["Id"], "title": it.get("Name", "?")} for it in items]

    def albums(self, artist_id: str) -> List[Dict]:
        """Return albums for an artist: {id, title, year}."""
        data  = self._get("/Items", params={
            "ParentId":           artist_id,
            "IncludeItemTypes":   "MusicAlbum",
            "Recursive":          "true",
            "UserId":             self._user_id,
        })
        items = data.get("Items", [])
        return [{"id":    it["Id"],
                 "title": it.get("Name", "?"),
                 "year":  it.get("ProductionYear", "")}
                for it in items]

    def tracks(self, album_id: str) -> List[Dict]:
        """Return tracks in an album: {id, title, duration_ms, index}."""
        data  = self._get("/Items", params={
            "ParentId":         album_id,
            "IncludeItemTypes": "Audio",
            "Recursive":        "true",
            "UserId":           self._user_id,
        })
        items = data.get("Items", [])
        result = []
        for it in items:
            ticks = it.get("RunTimeTicks", 0) or 0
            result.append({
                "id":          it["Id"],
                "title":       it.get("Name", "?"),
                "duration_ms": ticks // 10_000,
                "index":       it.get("IndexNumber", 0),
            })
        return result

    def stream_url(self, item_id: str) -> str:
        """Direct stream URL for a track."""
        params = urllib.parse.urlencode({
            "UserId":   self._user_id,
            "ApiKey":   self.token,
            "static":   "true",
        })
        return f"{self.base_url}/Audio/{item_id}/universal?{params}"

    def search_tracks(self, query: str) -> List[Dict]:
        """Search for audio items: returns same schema as tracks()."""
        data  = self._get("/Items", params={
            "SearchTerm":       query,
            "IncludeItemTypes": "Audio",
            "Recursive":        "true",
            "UserId":           self._user_id,
        })
        items = data.get("Items", [])
        result = []
        for it in items:
            ticks = it.get("RunTimeTicks", 0) or 0
            result.append({
                "id":          it["Id"],
                "title":       it.get("Name", "?"),
                "artist":      it.get("AlbumArtist", ""),
                "album":       it.get("Album", ""),
                "duration_ms": ticks // 10_000,
            })
        return result

    def album_art_url(self, item_id: str) -> str:
        """Return a URL for primary image of an item."""
        params = urllib.parse.urlencode({"api_key": self.token})
        return f"{self.base_url}/Items/{item_id}/Images/Primary?{params}"


# ── Background workers ─────────────────────────────────────────────────────────

class _LibraryWorker(QThread):
    """
    Fetches library data in a background thread.

    Emits `artists_ready`, `albums_ready`, or `tracks_ready` depending on
    what was requested; emits `error` on failure.
    """

    artists_ready: Signal = Signal(list)       # List[Dict]
    albums_ready:  Signal = Signal(list)       # List[Dict]
    tracks_ready:  Signal = Signal(list)       # List[Dict]
    error:         Signal = Signal(str)

    def __init__(
        self,
        client,                         # _PlexClient | _JellyfinClient
        task: str,                      # "artists" | "albums" | "tracks"
        parent_id: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._client    = client
        self._task      = task
        self._parent_id = parent_id

    def run(self) -> None:  # noqa: D102
        try:
            if self._task == "artists":
                if isinstance(self._client, _PlexClient):
                    sections = self._client.music_sections()
                    if not sections:
                        self.error.emit("No music library section found on this Plex server.")
                        return
                    items = self._client.artists(sections[0]["id"])
                else:
                    items = self._client.artists()
                self.artists_ready.emit(items)

            elif self._task == "albums":
                items = self._client.albums(self._parent_id)
                self.albums_ready.emit(items)

            elif self._task == "tracks":
                items = self._client.tracks(self._parent_id)
                self.tracks_ready.emit(items)

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class _SearchWorker(QThread):
    """Searches for tracks in the background."""

    results_ready: Signal = Signal(list)   # List[Dict]
    error:         Signal = Signal(str)

    def __init__(self, client, query: str, parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._query  = query

    def run(self) -> None:  # noqa: D102
        try:
            results = self._client.search_tracks(self._query)
            self.results_ready.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class _ArtFetcher(QThread):
    """Downloads album art bytes in the background."""

    art_ready: Signal = Signal(bytes)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:  # noqa: D102
        try:
            resp = _requests.get(self._url, timeout=8)
            if resp.ok:
                self.art_ready.emit(resp.content)
        except Exception:  # noqa: BLE001
            pass


# ── Main panel ─────────────────────────────────────────────────────────────────

class PlexJellyfinPanel(QDockWidget):
    """
    Dockable panel for Plex / Jellyfin music streaming.

    Args:
        config:      core.config.Config (for persisting connection settings)
        run_command: assistant.run_command callable (unused internally but
                     kept for constructor symmetry with other panels)
        parent:      Parent QWidget / QMainWindow
    """

    status_message: Signal = Signal(str)
    volume_changed: Signal = Signal(int)   # 0–100, for Mixer

    def __init__(
        self,
        config,
        run_command: Callable,
        parent=None,
    ) -> None:
        super().__init__("Plex / Jellyfin", parent)
        self.setObjectName("PlexJellyfinPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   # type: ignore[attr-defined]
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config      = config
        self._run_command = run_command
        self._client: Optional[object] = None        # _PlexClient | _JellyfinClient
        self._queue:  List[Dict]       = []
        self._queue_pos:  int          = -1
        self._volume:     int          = 80
        self._scenes:     List[Dict]   = self._load_scenes()
        self._current_track: Optional[Dict] = None
        self._duration_ms:   int       = 0
        self._lib_worker:    Optional[_LibraryWorker] = None
        self._search_worker: Optional[_SearchWorker]  = None
        self._art_fetcher:   Optional[_ArtFetcher]    = None
        # Browse state: stack of (level, parent_id, items)
        self._browse_stack: List[Tuple[str, str, List[Dict]]] = []

        if not _PYGAME_OK:
            self._show_missing_dep("pygame")
            return
        if not _REQUESTS_OK:
            self._show_missing_dep("requests")
            return

        self._init_pygame()
        self._build_ui()
        self._load_saved_connection()

    # ── Dependency-missing stub ────────────────────────────────────────────────

    def _show_missing_dep(self, lib: str) -> None:
        root = QWidget()
        root.setStyleSheet(f"background: {BG};")
        self.setWidget(root)
        lay  = QVBoxLayout(root)
        lbl  = QLabel(f"⚠  {lib} is not installed.\n\nRun:  pip install {lib}")
        lbl.setStyleSheet(f"color: {WARNING}; font-size: 12px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        lay.addWidget(lbl)

    # ── pygame init ───────────────────────────────────────────────────────────

    def _init_pygame(self) -> None:
        try:
            if not _pygame.get_init():
                _pygame.init()
            if not _pygame.mixer.get_init():
                _pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        except Exception as exc:
            self.status_message.emit(f"pygame init failed: {exc}")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root.setStyleSheet(f"background: {BG};")
        self.setWidget(root)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # ── Connection bar ─────────────────────────────────────────────────
        conn_row = QHBoxLayout()
        conn_row.setSpacing(4)

        self._server_combo = QComboBox()
        self._server_combo.addItems(SERVER_TYPES)
        self._server_combo.setFixedWidth(84)
        self._server_combo.setStyleSheet(self._combo_style())
        self._server_combo.currentTextChanged.connect(self._on_server_type_changed)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("http://localhost:32400")
        self._url_edit.setStyleSheet(self._input_style())

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("API token / X-Plex-Token")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setStyleSheet(self._input_style())

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(72)
        self._style_btn(self._connect_btn, accent=True)
        self._connect_btn.clicked.connect(self._on_connect)

        self._conn_status = QLabel("●")
        self._conn_status.setStyleSheet(f"color: {MUTED}; font-size: 12px;")

        conn_row.addWidget(self._server_combo)
        conn_row.addWidget(self._url_edit, 3)
        conn_row.addWidget(self._token_edit, 3)
        conn_row.addWidget(self._connect_btn)
        conn_row.addWidget(self._conn_status)
        lay.addLayout(conn_row)

        # ── Tabs ───────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {BORDER}; }}"
            f"QTabBar::tab {{ background: {SURFACE}; color: {MUTED}; padding: 5px 10px; }}"
            f"QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; }}"
        )
        lay.addWidget(self._tabs, stretch=1)

        self._build_library_tab()
        self._build_now_playing_tab()
        self._build_search_tab()
        self._build_scenes_tab()

        # ── Volume / master controls ───────────────────────────────────────
        vol_row = QHBoxLayout()
        vol_row.setSpacing(6)

        vol_lbl = QLabel("Vol:")
        vol_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        vol_row.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(self._volume)
        self._vol_slider.setFixedWidth(100)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self._vol_slider)

        self._vol_label = QLabel(f"{self._volume}%")
        self._vol_label.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
        self._vol_label.setFixedWidth(36)
        vol_row.addWidget(self._vol_label)
        vol_row.addStretch()
        lay.addLayout(vol_row)

        # ── Progress timer ─────────────────────────────────────────────────
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(PROGRESS_TICK_MS)
        self._progress_timer.timeout.connect(self._tick_progress)

    def _build_library_tab(self) -> None:
        """Library tab: Artist → Album → Track tree with back navigation."""
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        nav_row = QHBoxLayout()
        self._back_btn = QPushButton("← Back")
        self._back_btn.setEnabled(False)
        self._style_btn(self._back_btn)
        self._back_btn.clicked.connect(self._browse_back)
        self._browse_label = QLabel("Library")
        self._browse_label.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: bold;")
        nav_row.addWidget(self._back_btn)
        nav_row.addWidget(self._browse_label, stretch=1)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(28)
        self._style_btn(refresh_btn)
        refresh_btn.clicked.connect(self._refresh_library)
        nav_row.addWidget(refresh_btn)
        lay.addLayout(nav_row)

        self._lib_tree = QTreeWidget()
        self._lib_tree.setHeaderHidden(True)
        self._lib_tree.setStyleSheet(
            f"QTreeWidget {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}"
            f"QTreeWidget::item:hover {{ background: {PANEL}; }}"
            f"QTreeWidget::item:selected {{ background: {ACCENT}; color: {BG}; }}"
        )
        self._lib_tree.itemDoubleClicked.connect(self._on_lib_item_double_clicked)
        self._lib_tree.itemExpanded.connect(self._on_lib_item_expanded)
        lay.addWidget(self._lib_tree, stretch=1)

        self._tabs.addTab(w, "Library")

    def _build_now_playing_tab(self) -> None:
        """Now Playing tab: art + info + progress + transport."""
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Art + info row
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        self._art_label = QLabel()
        self._art_label.setFixedSize(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        self._art_label.setStyleSheet(f"background: {SURFACE}; border: 1px solid {BORDER};")
        self._art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        self._art_label.setText("♪")
        info_row.addWidget(self._art_label)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(2)
        self._track_label  = QLabel("—")
        self._artist_label = QLabel("—")
        self._album_label  = QLabel("—")
        self._track_label.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        self._artist_label.setStyleSheet(f"color: {ACCENT}; font-size: 11px;")
        self._album_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        for lbl in (self._track_label, self._artist_label, self._album_label):
            lbl.setWordWrap(True)
        meta_col.addWidget(self._track_label)
        meta_col.addWidget(self._artist_label)
        meta_col.addWidget(self._album_label)
        meta_col.addStretch()
        info_row.addLayout(meta_col, stretch=1)
        lay.addLayout(info_row)

        # Progress bar + time
        prog_row = QHBoxLayout()
        self._elapsed_lbl = QLabel("0:00")
        self._elapsed_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._elapsed_lbl.setFixedWidth(36)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}"
        )

        self._duration_lbl = QLabel("0:00")
        self._duration_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._duration_lbl.setFixedWidth(36)

        prog_row.addWidget(self._elapsed_lbl)
        prog_row.addWidget(self._progress_bar, stretch=1)
        prog_row.addWidget(self._duration_lbl)
        lay.addLayout(prog_row)

        # Transport
        trans_row = QHBoxLayout()
        trans_row.setSpacing(6)
        for label, slot in [
            ("⏮", self._cmd_prev),
            ("⏯", self._cmd_playpause),
            ("⏹", self._cmd_stop),
            ("⏭", self._cmd_next),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(38, 28)
            self._style_btn(btn)
            btn.clicked.connect(slot)
            trans_row.addWidget(btn)
        trans_row.addStretch()

        self._np_status = QLabel("Idle")
        self._np_status.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        trans_row.addWidget(self._np_status)
        lay.addLayout(trans_row)
        lay.addStretch()

        self._tabs.addTab(w, "Now Playing")

    def _build_search_tab(self) -> None:
        """Search tab: query field + results list."""
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search tracks…")
        self._search_edit.setStyleSheet(self._input_style())
        self._search_edit.returnPressed.connect(self._do_search)
        search_row.addWidget(self._search_edit)

        go_btn = QPushButton("Search")
        go_btn.setFixedWidth(60)
        self._style_btn(go_btn)
        go_btn.clicked.connect(self._do_search)
        search_row.addWidget(go_btn)
        lay.addLayout(search_row)

        self._search_status = QLabel("")
        self._search_status.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(self._search_status)

        self._search_list = QListWidget()
        self._search_list.setStyleSheet(
            f"QListWidget {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}"
            f"QListWidget::item:hover {{ background: {PANEL}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT}; color: {BG}; }}"
        )
        self._search_list.itemDoubleClicked.connect(self._on_search_item_play)
        lay.addWidget(self._search_list, stretch=1)

        self._tabs.addTab(w, "Search")

    def _build_scenes_tab(self) -> None:
        """Scenes tab: 8 quick-launch slots in a 2×4 grid."""
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._scene_btns: List[QPushButton] = []

        for idx, (label, tag) in enumerate(SCENE_TAGS):
            btn = QPushButton(label)
            btn.setToolTip(f"Scene slot {idx + 1}: {tag}")
            btn.setFixedHeight(44)
            self._style_btn(btn)
            btn.clicked.connect(lambda checked, i=idx: self._play_scene(i))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # type: ignore[attr-defined]
            btn.customContextMenuRequested.connect(
                lambda pos, i=idx, b=btn: self._scene_context_menu(i, b, pos)
            )
            self._update_scene_btn_label(btn, idx)
            grid.addWidget(btn, idx // 2, idx % 2)
            self._scene_btns.append(btn)

        lay.addLayout(grid)
        lay.addStretch()
        self._tabs.addTab(w, "Scenes")

    # ── Connection ─────────────────────────────────────────────────────────────

    def _on_server_type_changed(self, server_type: str) -> None:
        placeholder = (
            "http://localhost:32400"
            if server_type == "Plex"
            else "http://localhost:8096"
        )
        self._url_edit.setPlaceholderText(placeholder)

    def _on_connect(self) -> None:
        url   = self._url_edit.text().strip()
        token = self._token_edit.text().strip()
        stype = self._server_combo.currentText()

        if not url or not token:
            self._conn_status.setStyleSheet(f"color: {ERROR}; font-size: 12px;")
            self._conn_status.setText("●")
            self.status_message.emit("Plex/Jellyfin: URL and token are required.")
            return

        self._connect_btn.setEnabled(False)
        self._conn_status.setStyleSheet(f"color: {WARNING}; font-size: 12px;")
        self._conn_status.setText("◌")
        self.status_message.emit(f"Connecting to {stype}…")

        def _do_connect() -> None:
            try:
                if stype == "Plex":
                    client = _PlexClient(url, token)
                else:
                    client = _JellyfinClient(url, token)
                ok = client.ping()
            except Exception as exc:
                ok = False
                client = None  # noqa: F841 — will be unused
                _err = str(exc)
            else:
                _err = ""

            if ok:
                self._client = client  # type: ignore[assignment]
                self._save_connection(stype, url, token)
                self._conn_status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
                self._conn_status.setText("●")
                self.status_message.emit(f"{stype} connected.")
                self._refresh_library()
            else:
                self._conn_status.setStyleSheet(f"color: {ERROR}; font-size: 12px;")
                self._conn_status.setText("●")
                msg = _err or "Could not reach server."
                self.status_message.emit(f"{stype} connection failed: {msg}")
            self._connect_btn.setEnabled(True)

        threading.Thread(target=_do_connect, daemon=True).start()

    # ── Library browsing ───────────────────────────────────────────────────────

    def _refresh_library(self) -> None:
        if self._client is None:
            return
        self._lib_tree.clear()
        self._browse_stack.clear()
        self._back_btn.setEnabled(False)
        self._browse_label.setText("Artists")
        self._lib_status("Loading artists…")
        self._start_lib_worker("artists")

    def _start_lib_worker(self, task: str, parent_id: str = "") -> None:
        if self._lib_worker and self._lib_worker.isRunning():
            return
        self._lib_worker = _LibraryWorker(self._client, task, parent_id, self)
        self._lib_worker.artists_ready.connect(self._on_artists)
        self._lib_worker.albums_ready.connect(self._on_albums)
        self._lib_worker.tracks_ready.connect(self._on_tracks)
        self._lib_worker.error.connect(lambda e: self.status_message.emit(f"Library error: {e}"))
        self._lib_worker.start()

    def _on_artists(self, items: List[Dict]) -> None:
        self._lib_tree.clear()
        for it in items:
            node = QTreeWidgetItem(self._lib_tree, [it["title"]])
            node.setData(0, Qt.ItemDataRole.UserRole, {"level": "artist", **it})  # type: ignore[attr-defined]
            node.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator  # type: ignore[attr-defined]
            )
        self._lib_status(f"{len(items)} artists")

    def _on_albums(self, items: List[Dict]) -> None:
        self._lib_tree.clear()
        for it in items:
            year = f" ({it['year']})" if it.get("year") else ""
            node = QTreeWidgetItem(self._lib_tree, [f"{it['title']}{year}"])
            node.setData(0, Qt.ItemDataRole.UserRole, {"level": "album", **it})  # type: ignore[attr-defined]
            node.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator  # type: ignore[attr-defined]
            )
        self._lib_status(f"{len(items)} albums")

    def _on_tracks(self, items: List[Dict]) -> None:
        self._lib_tree.clear()
        for it in items:
            dur = _ms_to_str(it.get("duration_ms", 0))
            idx = it.get("index", 0)
            lbl = f"{idx:02d}. {it['title']}  [{dur}]" if idx else f"{it['title']}  [{dur}]"
            node = QTreeWidgetItem(self._lib_tree, [lbl])
            node.setData(0, Qt.ItemDataRole.UserRole, {"level": "track", **it})  # type: ignore[attr-defined]
        self._lib_status(f"{len(items)} tracks")

    def _on_lib_item_expanded(self, item: QTreeWidgetItem) -> None:
        # Lazy-load stub children (we load on double-click instead)
        item.setChildIndicatorPolicy(
            QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator  # type: ignore[attr-defined]
        )

    def _on_lib_item_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if not data:
            return
        level = data.get("level")
        if level == "artist":
            self._browse_stack.append(("artists", "", []))
            self._browse_label.setText(f"Albums — {data['title']}")
            self._back_btn.setEnabled(True)
            self._start_lib_worker("albums", data["id"])
        elif level == "album":
            self._browse_stack.append(("albums", data.get("_parent_id", ""), []))
            self._browse_label.setText(f"Tracks — {data['title']}")
            self._back_btn.setEnabled(True)
            self._start_lib_worker("tracks", data["id"])
        elif level == "track":
            self._play_track(data)

    def _browse_back(self) -> None:
        if not self._browse_stack:
            return
        prev_level, prev_parent_id, _ = self._browse_stack.pop()
        if prev_level == "artists":
            self._browse_label.setText("Artists")
            self._back_btn.setEnabled(False)
            self._start_lib_worker("artists")
        elif prev_level == "albums":
            self._browse_label.setText("Albums")
            self._back_btn.setEnabled(len(self._browse_stack) > 0)
            self._start_lib_worker("albums", prev_parent_id)

    # ── Playback ───────────────────────────────────────────────────────────────

    def _play_track(self, track: Dict) -> None:
        """Resolve the stream URL and begin pygame playback."""
        if self._client is None:
            return
        self._current_track = track
        self._duration_ms   = track.get("duration_ms", 0)
        self._np_status.setText("Resolving…")
        self.status_message.emit(f"Loading: {track.get('title', '?')}")

        def _stream() -> None:
            try:
                if isinstance(self._client, _PlexClient):
                    key = track.get("stream_key", "")
                    url = self._client.stream_url(key) if key else ""
                else:
                    url = self._client.stream_url(track["id"])

                if not url:
                    self.status_message.emit("Could not resolve stream URL.")
                    self._np_status.setText("Error")
                    return

                _pygame.mixer.music.load(url)
                _pygame.mixer.music.set_volume(self._volume / 100.0)
                _pygame.mixer.music.play()
                self._np_status.setText("Playing")
                self._progress_timer.start()
                self._update_np_labels(track)
                self._fetch_art(track)
            except Exception as exc:
                self.status_message.emit(f"Playback error: {exc}")
                self._np_status.setText("Error")

        threading.Thread(target=_stream, daemon=True).start()
        self._tabs.setCurrentIndex(1)  # switch to Now Playing

    def _update_np_labels(self, track: Dict) -> None:
        self._track_label.setText(track.get("title", "—"))
        self._artist_label.setText(track.get("artist", ""))
        self._album_label.setText(track.get("album", ""))
        dur = _ms_to_str(track.get("duration_ms", 0))
        self._duration_lbl.setText(dur)
        self._elapsed_lbl.setText("0:00")
        self._progress_bar.setValue(0)

    def _fetch_art(self, track: Dict) -> None:
        """Fetch album art asynchronously if possible."""
        if not _REQUESTS_OK or self._client is None:
            return
        try:
            if isinstance(self._client, _PlexClient):
                url = self._client.album_art_url(track["id"])
            else:
                url = self._client.album_art_url(track["id"])
        except Exception:
            return
        self._art_fetcher = _ArtFetcher(url, self)
        self._art_fetcher.art_ready.connect(self._on_art_ready)
        self._art_fetcher.start()

    def _on_art_ready(self, data: bytes) -> None:
        pix = QPixmap()
        if pix.loadFromData(data):
            self._art_label.setPixmap(
                pix.scaled(ALBUM_ART_SIZE, ALBUM_ART_SIZE,
                           Qt.AspectRatioMode.KeepAspectRatio,          # type: ignore[attr-defined]
                           Qt.TransformationMode.SmoothTransformation)   # type: ignore[attr-defined]
            )

    def _tick_progress(self) -> None:
        if not _pygame.mixer.music.get_busy():
            self._progress_timer.stop()
            self._np_status.setText("Stopped")
            return
        pos_ms = _pygame.mixer.music.get_pos()
        if pos_ms < 0:
            return
        self._elapsed_lbl.setText(_ms_to_str(pos_ms))
        if self._duration_ms > 0:
            pct = min(int(pos_ms / self._duration_ms * 1000), 1000)
            self._progress_bar.setValue(pct)

    # ── Transport commands ─────────────────────────────────────────────────────

    def _cmd_playpause(self) -> None:
        if not _PYGAME_OK:
            return
        if _pygame.mixer.music.get_busy():
            _pygame.mixer.music.pause()
            self._np_status.setText("Paused")
            self._progress_timer.stop()
        else:
            _pygame.mixer.music.unpause()
            self._np_status.setText("Playing")
            self._progress_timer.start()

    def _cmd_stop(self) -> None:
        if not _PYGAME_OK:
            return
        _pygame.mixer.music.stop()
        self._progress_timer.stop()
        self._np_status.setText("Stopped")
        self._elapsed_lbl.setText("0:00")
        self._progress_bar.setValue(0)

    def _cmd_next(self) -> None:
        if self._queue and self._queue_pos + 1 < len(self._queue):
            self._queue_pos += 1
            self._play_track(self._queue[self._queue_pos])

    def _cmd_prev(self) -> None:
        if self._queue and self._queue_pos > 0:
            self._queue_pos -= 1
            self._play_track(self._queue[self._queue_pos])

    # ── Search ─────────────────────────────────────────────────────────────────

    def _do_search(self) -> None:
        if self._client is None:
            self.status_message.emit("Plex/Jellyfin: not connected.")
            return
        query = self._search_edit.text().strip()
        if not query:
            return
        self._search_list.clear()
        self._search_status.setText("Searching…")
        self._search_worker = _SearchWorker(self._client, query, self)
        self._search_worker.results_ready.connect(self._on_search_results)
        self._search_worker.error.connect(
            lambda e: self._search_status.setText(f"Error: {e}")
        )
        self._search_worker.start()

    def _on_search_results(self, results: List[Dict]) -> None:
        self._search_list.clear()
        self._search_status.setText(f"{len(results)} result(s)")
        for it in results:
            artist = it.get("artist", "")
            album  = it.get("album", "")
            dur    = _ms_to_str(it.get("duration_ms", 0))
            label  = f"{it['title']}  —  {artist}"
            if album:
                label += f"  [{album}]"
            label += f"  {dur}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, it)  # type: ignore[attr-defined]
            self._search_list.addItem(item)

    def _on_search_item_play(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if track:
            self._play_track(track)

    # ── Scenes ─────────────────────────────────────────────────────────────────

    def _play_scene(self, idx: int) -> None:
        if self._client is None:
            self.status_message.emit("Plex/Jellyfin: not connected.")
            return
        scene = self._scenes[idx]
        track = scene.get("track")
        if not track:
            self.status_message.emit(f"Scene {idx + 1} is empty — right-click to assign a track.")
            return
        self._play_track(track)

    def _scene_context_menu(self, idx: int, btn: QPushButton, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}"
            f"QMenu::item:selected {{ background: {ACCENT}; color: {BG}; }}"
        )
        assign = menu.addAction("Assign current track")
        clear  = menu.addAction("Clear slot")
        action = menu.exec(btn.mapToGlobal(pos))
        if action == assign:
            self._assign_scene(idx)
        elif action == clear:
            self._clear_scene(idx)

    def _assign_scene(self, idx: int) -> None:
        track = self._current_track
        if not track:
            self.status_message.emit("Play a track first, then assign it to a scene slot.")
            return
        self._scenes[idx]["track"] = track
        self._save_scenes()
        self._update_scene_btn_label(self._scene_btns[idx], idx)
        self.status_message.emit(f"Scene {idx + 1} assigned: {track.get('title', '?')}")

    def _clear_scene(self, idx: int) -> None:
        self._scenes[idx]["track"] = None
        self._save_scenes()
        self._update_scene_btn_label(self._scene_btns[idx], idx)
        self.status_message.emit(f"Scene {idx + 1} cleared.")

    def _update_scene_btn_label(self, btn: QPushButton, idx: int) -> None:
        label, _tag = SCENE_TAGS[idx]
        track = self._scenes[idx].get("track")
        name  = track.get("title", "?") if track else ""
        btn.setText(f"{label}\n{name[:22]}" if name else label)

    # ── Volume / Mixer integration ─────────────────────────────────────────────

    def _on_volume_changed(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))
        if hasattr(self, "_vol_label"):
            self._vol_label.setText(f"{self._volume}%")
        if _PYGAME_OK and _pygame.mixer.get_init():
            _pygame.mixer.music.set_volume(self._volume / 100.0)
        self.volume_changed.emit(self._volume)

    def set_volume(self, value: int) -> None:
        """Called by MixerPanel."""
        value = max(0, min(100, int(value)))
        if hasattr(self, "_vol_slider"):
            self._vol_slider.setValue(value)
        else:
            self._on_volume_changed(value)

    def get_volume(self) -> int:
        """Called by MixerPanel."""
        return self._volume

    def get_np_state(self) -> Dict:
        """Called by NowPlayingPanel (2-second poll)."""
        if not _PYGAME_OK or self._current_track is None:
            return {
                "title": "",
                "playing": False,
                "paused": False,
                "can_pause": False,
                "can_next": False,
                "can_prev": False,
                "can_stop": False,
            }
        busy = _pygame.mixer.music.get_busy()
        pos  = _pygame.mixer.music.get_pos()
        paused = (not busy) and self._np_status.text() == "Paused"
        has_queue = bool(self._queue)
        return {
            "title":       self._current_track.get("title", ""),
            "artist":      self._current_track.get("artist", ""),
            "album":       self._current_track.get("album", ""),
            "playing":     busy,
            "paused":      paused,
            "position_ms": max(pos, 0),
            "duration_ms": self._duration_ms,
            "art_url":     None,
            "can_pause":   True,
            "can_next":    has_queue and self._queue_pos + 1 < len(self._queue),
            "can_prev":    has_queue and self._queue_pos > 0,
            "can_stop":    True,
        }

    # ── Discord handle_command ─────────────────────────────────────────────────

    def handle_command(self, action: str, query: str = "") -> None:
        """
        Route a Discord / voice command to the panel.

        Actions: "play", "pause", "stop", "next", "search"
        """
        action = action.lower().strip()
        if action == "play":
            if query and self._client:
                self._search_edit.setText(query)
                self._do_search()
            else:
                self._cmd_playpause()
        elif action == "pause":
            self._cmd_playpause()
        elif action == "stop":
            self._cmd_stop()
        elif action == "next":
            self._cmd_next()
        elif action == "previous":
            self._cmd_prev()
        elif action == "search" and query:
            self._search_edit.setText(query)
            self._do_search()
            self._tabs.setCurrentIndex(2)

    # ── Settings persistence ───────────────────────────────────────────────────

    def _save_connection(self, stype: str, url: str, token: str) -> None:
        """
        Persist connection settings through the proper channels:
          - Server type + URL → Config fields → settings.json via save_settings()
          - Token → variables.env as PLEX_JELLYFIN_TOKEN (matches all other services)
        """
        try:
            self._config.plex_jellyfin_server_type = stype
            self._config.plex_jellyfin_url         = url
            self._config.save_settings()
        except Exception:
            pass
        try:
            env_path = getattr(self._config, "env_file", "variables.env")
            _write_env_key(env_path, "PLEX_JELLYFIN_TOKEN", token)
            if token:
                os.environ["PLEX_JELLYFIN_TOKEN"] = token
        except Exception:
            pass

    def _load_saved_connection(self) -> None:
        """
        Restore connection fields from Config (type + URL) and os.environ / variables.env (token).
        """
        stype = getattr(self._config, "plex_jellyfin_server_type", "Jellyfin")
        url   = getattr(self._config, "plex_jellyfin_url", "")
        token = os.environ.get("PLEX_JELLYFIN_TOKEN", "")
        if not token:
            # Fallback: try reading directly from env file in case dotenv hasn't loaded it
            try:
                env_path = getattr(self._config, "env_file", "variables.env")
                token = _read_env_key(env_path, "PLEX_JELLYFIN_TOKEN")
            except Exception:
                pass
        if url or token:
            idx = SERVER_TYPES.index(stype) if stype in SERVER_TYPES else 1
            self._server_combo.setCurrentIndex(idx)
            self._url_edit.setText(url)
            self._token_edit.setText(token)

    # ── Scene persistence ──────────────────────────────────────────────────────

    def _load_scenes(self) -> List[Dict]:
        try:
            scenes = load_scene_data(self._config, "plex_jellyfin", _SCENE_CONFIG_PATH, [])
            if isinstance(scenes, list) and len(scenes) >= len(SCENE_TAGS):
                return scenes[: len(SCENE_TAGS)]
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            pass
        return [{"track": None} for _ in SCENE_TAGS]

    def _save_scenes(self) -> None:
        try:
            save_scene_data(self._config, "plex_jellyfin", _SCENE_CONFIG_PATH, self._scenes)
        except Exception:
            pass

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _lib_status(self, msg: str) -> None:
        self.status_message.emit(f"Plex/Jellyfin library: {msg}")

    def _style_btn(self, btn: QPushButton, accent: bool = False) -> None:
        bg = ACCENT if accent else SURFACE
        fg = BG    if accent else TEXT
        btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {fg}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 8px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT if not accent else fg}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
            f"QPushButton:disabled {{ color: {MUTED}; }}"
        )

    def _input_style(self) -> str:
        return (
            f"QLineEdit {{ background: {SURFACE}; color: {TEXT}; "
            f"border: 1px solid {BORDER}; border-radius: 3px; padding: 3px 6px; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {SURFACE}; color: {TEXT}; "
            f"border: 1px solid {BORDER}; border-radius: 3px; padding: 2px 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; "
            f"selection-background-color: {ACCENT}; }}"
        )
