"""
Syrinscape panel for Project Ceres — GM Assistant UI.

Controls Syrinscape Online Player via its REST API, providing soundset
browsing, mood playback, configurable scene quick-launch slots, and a
master volume control.

Features
--------
  • Token-based auth — SYRINSCAPE_AUTH_TOKEN loaded from variables.env
  • Soundsets tab — browse all user soundsets, click to load moods
  • Moods tab — filter + play moods for the selected soundset
  • Scenes tab — 8 named quick-launch slots (persist to syrinscape_scenes.json)
  • Stop All — POST /stop-all/ from the header bar
  • Now Playing label — updates on every successful mood play
  • Worker thread — all HTTP calls run off the main thread via QThread

API base: https://syrinscape.com/online/frontend-api/
Auth:     Authorization: Token <SYRINSCAPE_AUTH_TOKEN>

Requirements
------------
    pip install requests   # standard; likely already installed

variables.env key
-----------------
    SYRINSCAPE_AUTH_TOKEN=<token-from-syrinscape.com/account/auth-token/>
"""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider,
        QListWidget, QListWidgetItem, QTabWidget, QGridLayout,
        QSizePolicy, QMenu, QMessageBox,
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
        QSizePolicy, QMenu, QMessageBox,
    )
    from PySide6.QtCore import Qt, QThread, QObject, QTimer, QSize, Signal, Slot  # type: ignore
    from PySide6.QtGui import QPixmap, QIcon  # type: ignore

from ui.theme import (
    ACCENT, ACCENT2, BG, BORDER, ERROR, MUTED,
    PANEL, SUCCESS, SURFACE, TEXT, WARNING,
)

# ── Optional dependency ────────────────────────────────────────────────────────

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    _requests = None  # type: ignore[assignment]
    REQUESTS_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────

BASE_URL  = "https://syrinscape.com/online/frontend-api/"
THUMB_SIZE = 32   # soundset artwork thumbnail px

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

_PROJECT_ROOT      = Path(__file__).resolve().parent.parent.parent
SCENE_CONFIG_PATH  = _PROJECT_ROOT / "syrinscape_scenes.json"

VOL_DEBOUNCE_MS    = 400


# ── Background worker ──────────────────────────────────────────────────────────

class _SyrinscapeWorker(QObject):
    """
    All Syrinscape REST calls run in this QObject (moved to a QThread).
    Communicates back to SyrinscapePanel exclusively through Qt signals.
    """

    # ── Outbound signals ───────────────────────────────────────────────────────
    auth_success     = Signal()
    auth_failed      = Signal(str)          # error message
    soundsets_loaded = Signal(list)         # list of soundset dicts
    moods_loaded     = Signal(list)         # list of mood dicts
    mood_played      = Signal(str, str)     # (soundset_name, mood_name)
    stopped_all      = Signal()
    artwork_loaded   = Signal(str, bytes)   # (url, raw_png)
    elements_loaded  = Signal(list)         # list of {"id": int, "name": str}
    error            = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._token   = ""
        self._lock    = threading.Lock()
        self._session: Optional["_requests.Session"] = None  # type: ignore[name-defined]

    # ── Private helpers ────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token {self._token}",
            "Accept":        "application/json",
        }

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[dict]:
        """GET from the API; return parsed JSON or None on error (emits error signal)."""
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests library not installed — run: pip install requests")
            return None
        url = BASE_URL + endpoint
        try:
            with self._lock:
                session = self._session
            if session is None:
                return None
            resp = session.get(url, headers=self._headers(), params=params or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            self.error.emit(f"GET {endpoint}: {exc}")
            return None

    def _post(self, endpoint: str) -> bool:
        """POST to the API; return True on success (emits error signal on failure)."""
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests library not installed — run: pip install requests")
            return False
        url = BASE_URL + endpoint
        try:
            with self._lock:
                session = self._session
            if session is None:
                return False
            resp = session.post(url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return True
        except Exception as exc:
            self.error.emit(f"POST {endpoint}: {exc}")
            return False

    # ── Inbound slots ──────────────────────────────────────────────────────────

    @Slot(str)
    def do_connect(self, token: str) -> None:
        """Validate token by fetching soundsets; emit auth_success or auth_failed."""
        if not REQUESTS_AVAILABLE:
            self.auth_failed.emit(
                "requests library not installed.\nRun:  pip install requests"
            )
            return
        try:
            self._token = token.strip()
            session = _requests.Session()
            resp = session.get(
                BASE_URL + "soundsets/",
                headers={
                    "Authorization": f"Token {self._token}",
                    "Accept":        "application/json",
                },
                params={"format": "json"},
                timeout=12,
            )
            resp.raise_for_status()
            with self._lock:
                self._session = session
            self.auth_success.emit()
            # Populate soundsets immediately after auth
            data = resp.json()
            self._emit_soundsets(data)
        except Exception as exc:
            self._token = ""
            self.auth_failed.emit(str(exc))

    @Slot()
    def do_load_soundsets(self) -> None:
        data = self._get("soundsets/", {"format": "json"})
        if data is not None:
            self._emit_soundsets(data)

    def _emit_soundsets(self, data) -> None:
        items = data if isinstance(data, list) else data.get("results") or []
        soundsets = []
        for s in items:
            entry = {
                "id":      s.get("id"),
                "name":    s.get("name", ""),
                "uuid":    s.get("uuid", s.get("pk", "")),
                "artwork": s.get("artwork", ""),
            }
            soundsets.append(entry)
            # Fetch artwork asynchronously
            if entry["artwork"]:
                self._fetch_artwork(entry["artwork"])
        self.soundsets_loaded.emit(soundsets)

    @Slot(str)
    def do_load_moods(self, soundset_uuid: str) -> None:
        data = self._get("moods/", {"soundset__uuid": soundset_uuid, "format": "json"})
        if data is None:
            return
        items = data if isinstance(data, list) else data.get("results") or []
        moods = []
        for m in items:
            moods.append({
                "id":   m.get("id"),
                "name": m.get("name", ""),
            })
        self.moods_loaded.emit(moods)

    @Slot(int, str, str)
    def do_play_mood(self, mood_id: int, soundset_name: str, mood_name: str) -> None:
        ok = self._post(f"moods/{mood_id}/play/?format=json")
        if ok:
            self.mood_played.emit(soundset_name, mood_name)

    @Slot()
    def do_stop_all(self) -> None:
        ok = self._post("stop-all/?format=json")
        if ok:
            self.stopped_all.emit()

    @Slot()
    def do_disconnect(self) -> None:
        with self._lock:
            self._session = None
        self._token = ""

    @Slot(str)
    def do_load_elements(self, soundset_uuid: str) -> None:
        """Fetch all elements for a soundset; emit elements_loaded with their IDs."""
        data = self._get("elements/", {"soundset__uuid": soundset_uuid, "format": "json"})
        if data is None:
            return
        items = data if isinstance(data, list) else data.get("results") or []
        elements = [
            {"id": e.get("id"), "name": e.get("name", "")}
            for e in items
        ]
        self.elements_loaded.emit(elements)

    @Slot(list, int)
    def do_set_volume_all(self, element_ids: list, volume: int) -> None:
        """POST set-current-volume to every element in element_ids."""
        for eid in element_ids:
            self._post(f"elements/{eid}/set-current-volume/{volume}/?format=json")

    # ── Artwork fetch (internal, non-slot) ─────────────────────────────────────

    def _fetch_artwork(self, url: str) -> None:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read()
            self.artwork_loaded.emit(url, bytes(data))
        except Exception:
            pass  # non-critical


# ── Main panel ─────────────────────────────────────────────────────────────────

class SyrinscapePanel(QDockWidget):
    """
    Dockable Syrinscape Online integration panel.

    Signals
    -------
    status_message(str) — forwarded to the main window status bar

    Public slot
    -----------
    handle_command(action, query) — "play_mood" or "stop" from voice commands
    """

    status_message: Signal = Signal(str)
    volume_changed: Signal = Signal(int)

    # ── Signals routed to the worker (queued, cross-thread) ───────────────────
    _sig_connect         = Signal(str)
    _sig_disconnect      = Signal()
    _sig_load_soundsets  = Signal()
    _sig_load_moods      = Signal(str)
    _sig_play_mood       = Signal(int, str, str)
    _sig_stop_all        = Signal()
    _sig_load_elements   = Signal(str)
    _sig_set_volume_all  = Signal(list, int)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Syrinscape", parent)
        self.setObjectName("SyrinscapePanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)       # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |          # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config      = config
        self._run_command = run_command

        # State
        self._connected         = False
        self._soundsets: List[Dict]  = []      # full list from last fetch
        self._moods: List[Dict]      = []      # moods for selected soundset
        self._filtered_moods: List[Dict] = []  # after search filter
        self._selected_soundset_name  = ""
        self._selected_soundset_uuid  = ""
        self._artwork_cache: Dict[str, QPixmap] = {}
        self._active_element_ids: List[int] = []  # element IDs for current mood's soundset

        # Scene config: slot_key → {"mood_id": int, "mood_name": str, "soundset_name": str} | None
        self._scene_config: Dict[str, Optional[Dict]] = {
            key: None for _, key in SCENE_SLOTS
        }
        self._scene_buttons: Dict[str, QPushButton] = {}

        self._load_scene_config()
        self._build_ui()
        self._setup_worker()

        # Auto-connect if token is present
        token = self._load_token()
        if token:
            QTimer.singleShot(800, lambda: self._do_connect(token))

    # ── Token loading ──────────────────────────────────────────────────────────

    def _load_token(self) -> str:
        """Load SYRINSCAPE_AUTH_TOKEN from environment or variables.env."""
        import os
        token = os.environ.get("SYRINSCAPE_AUTH_TOKEN", "")
        if not token:
            here = Path(__file__).resolve().parent
            for _ in range(6):
                env_path = here / "variables.env"
                if env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, v = line.partition("=")
                        if k.strip() == "SYRINSCAPE_AUTH_TOKEN":
                            token = v.strip()
                            break
                    break
                here = here.parent
        return token

    # ── Scene config persistence ───────────────────────────────────────────────

    def _load_scene_config(self) -> None:
        try:
            if SCENE_CONFIG_PATH.exists():
                data = json.loads(SCENE_CONFIG_PATH.read_text(encoding="utf-8"))
                for _, key in SCENE_SLOTS:
                    if key in data:
                        self._scene_config[key] = data[key]
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
        self._worker = _SyrinscapeWorker()
        self._worker.moveToThread(self._thread)

        # Worker → panel
        self._worker.auth_success.connect(self._on_auth_success)
        self._worker.auth_failed.connect(self._on_auth_failed)
        self._worker.soundsets_loaded.connect(self._on_soundsets_loaded)
        self._worker.moods_loaded.connect(self._on_moods_loaded)
        self._worker.mood_played.connect(self._on_mood_played)
        self._worker.stopped_all.connect(self._on_stopped_all)
        self._worker.artwork_loaded.connect(self._on_artwork_loaded)
        self._worker.elements_loaded.connect(self._on_elements_loaded)
        self._worker.error.connect(self._on_worker_error)

        # Panel → worker (QueuedConnection across thread boundary)
        self._sig_connect.connect(self._worker.do_connect)
        self._sig_disconnect.connect(self._worker.do_disconnect)
        self._sig_load_soundsets.connect(self._worker.do_load_soundsets)
        self._sig_load_moods.connect(self._worker.do_load_moods)
        self._sig_play_mood.connect(self._worker.do_play_mood)
        self._sig_stop_all.connect(self._worker.do_stop_all)
        self._sig_load_elements.connect(self._worker.do_load_elements)
        self._sig_set_volume_all.connect(self._worker.do_set_volume_all)

        self._thread.start()

        # Volume debounce timer (runs on main thread — no API call needed until
        # Syrinscape exposes an active-element list; see HANDOFF.md)
        # Volume debounce timer (main thread)
        self._vol_debounce = QTimer(self)
        self._vol_debounce.setSingleShot(True)
        self._vol_debounce.setInterval(VOL_DEBOUNCE_MS)
        self._vol_debounce.timeout.connect(self._on_vol_debounce_fired)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── Header row: status + token + buttons ──────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(5)

        self._dot_label = QLabel("●")
        self._dot_label.setFixedWidth(16)
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        hdr.addWidget(self._dot_label)

        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet(f"color: {MUTED};")
        hdr.addWidget(self._status_label)

        hdr.addStretch()

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("Auth token…")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setFixedWidth(140)
        self._token_edit.setToolTip(
            "Syrinscape auth token — get yours at "
            "https://syrinscape.com/account/auth-token/"
        )
        token = self._load_token()
        if token:
            self._token_edit.setText(token)
        hdr.addWidget(self._token_edit)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setProperty("class", "accent")
        self._connect_btn.setFixedWidth(84)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        hdr.addWidget(self._connect_btn)

        self._stop_all_btn = QPushButton("⏹ Stop All")
        self._stop_all_btn.setFixedWidth(84)
        self._stop_all_btn.setToolTip("Stop all Syrinscape audio")
        self._stop_all_btn.setEnabled(False)
        self._stop_all_btn.clicked.connect(self._on_stop_all)
        hdr.addWidget(self._stop_all_btn)

        layout.addLayout(hdr)

        # ── Availability hint (shown when requests not installed) ─────────────
        if not REQUESTS_AVAILABLE:
            warn = QLabel(
                "⚠  requests library not installed.\n"
                "Run:  pip install requests"
            )
            warn.setStyleSheet(
                f"color: {WARNING}; font-size: 9px; padding: 5px;"
                f"border: 1px solid {WARNING}; border-radius: 3px;"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # ── Tabs ─────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_soundsets_tab(), "🎵 Soundsets")
        self._tabs.addTab(self._build_moods_tab(),     "🎭 Moods")
        self._tabs.addTab(self._build_scenes_tab(),    "🎬 Scenes")
        layout.addWidget(self._tabs, 1)

        # ── Footer: volume + now playing ─────────────────────────────────────
        footer = QVBoxLayout()
        footer.setSpacing(3)

        vol_row = QHBoxLayout()
        vol_row.setSpacing(5)
        vol_lbl = QLabel("🔊")
        vol_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        vol_lbl.setFixedWidth(18)
        vol_row.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setToolTip("Master volume — applies to all active elements")
        self._vol_slider.setEnabled(False)
        self._vol_slider.valueChanged.connect(self._on_vol_changed)
        vol_row.addWidget(self._vol_slider, 1)

        self._vol_val_label = QLabel("80")
        self._vol_val_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        self._vol_val_label.setFixedWidth(24)
        vol_row.addWidget(self._vol_val_label)

        footer.addLayout(vol_row)

        self._now_playing_label = QLabel("Nothing playing")
        self._now_playing_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 9px; font-style: italic;"
        )
        self._now_playing_label.setWordWrap(True)
        footer.addWidget(self._now_playing_label)
        layout.addLayout(footer)

        self.setWidget(outer)

    # ── Soundsets tab ─────────────────────────────────────────────────────────

    def _build_soundsets_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        hdr_row = QHBoxLayout()
        lbl = QLabel("Soundsets")
        lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 10px;")
        hdr_row.addWidget(lbl, 1)
        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh soundsets")
        refresh_btn.clicked.connect(lambda: self._sig_load_soundsets.emit())
        hdr_row.addWidget(refresh_btn)
        v.addLayout(hdr_row)

        self._soundset_list = QListWidget()
        self._soundset_list.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self._soundset_list.setAlternatingRowColors(True)
        self._soundset_list.setToolTip("Click to load moods for this soundset")
        self._soundset_list.currentItemChanged.connect(self._on_soundset_selected)
        v.addWidget(self._soundset_list, 1)

        hint = QLabel("Click a soundset to browse its moods →")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        v.addWidget(hint)

        return w

    # ── Moods tab ─────────────────────────────────────────────────────────────

    def _build_moods_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self._moods_header_lbl = QLabel("Moods")
        self._moods_header_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        v.addWidget(self._moods_header_lbl)

        self._mood_filter = QLineEdit()
        self._mood_filter.setPlaceholderText("🔍 Filter moods…")
        self._mood_filter.setClearButtonEnabled(True)
        self._mood_filter.textChanged.connect(self._on_mood_filter_changed)
        v.addWidget(self._mood_filter)

        mood_hdr_row = QHBoxLayout()
        results_lbl = QLabel("Results")
        results_lbl.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        mood_hdr_row.addWidget(results_lbl, 1)
        play_btn = QPushButton("▶ Play")
        play_btn.setFixedWidth(58)
        play_btn.setToolTip("Play selected mood")
        play_btn.clicked.connect(self._on_play_selected_mood)
        mood_hdr_row.addWidget(play_btn)
        v.addLayout(mood_hdr_row)

        self._mood_list = QListWidget()
        self._mood_list.setAlternatingRowColors(True)
        self._mood_list.setToolTip("Double-click to play")
        self._mood_list.itemDoubleClicked.connect(self._on_mood_double_clicked)
        v.addWidget(self._mood_list, 1)

        return w

    # ── Scenes tab ────────────────────────────────────────────────────────────

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

        hint = QLabel(
            "Left-click: play  ·  Right-click: assign or clear"
        )
        hint.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        v.addWidget(hint)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
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
            ss  = assigned.get("soundset_name", "")
            mn  = assigned.get("mood_name", "")
            return f"▶ {ss} — {mn}\nRight-click to reassign or clear"
        return "No mood assigned\nRight-click to assign the currently-selected mood"

    def _update_scene_btn_style(self, key: str) -> None:
        btn = self._scene_buttons.get(key)
        if btn is None:
            return
        assigned = self._scene_config.get(key)
        if assigned:
            mn = assigned.get("mood_name", "")
            ss = assigned.get("soundset_name", "")
            # Two-line label: slot name + mood name
            label_text = None
            for lbl, k in SCENE_SLOTS:
                if k == key:
                    label_text = lbl
                    break
            sub = f"\n{ss} — {mn}" if ss and mn else (f"\n{mn}" if mn else "")
            btn.setText(f"{label_text}{sub}")
            btn.setStyleSheet(
                f"QPushButton {{ background: {ACCENT2}; color: {TEXT};"
                f" border: 1px solid {ACCENT}; border-radius: 3px;"
                f" text-align: center; padding: 4px; }}"
                f"QPushButton:hover {{ background: {ACCENT}; }}"
            )
        else:
            for lbl, k in SCENE_SLOTS:
                if k == key:
                    btn.setText(lbl)
                    break
            btn.setStyleSheet("")
        btn.setToolTip(self._scene_tooltip(key))

    # ── Worker signal handlers ─────────────────────────────────────────────────

    def _on_auth_success(self) -> None:
        self._connected = True
        self._dot_label.setStyleSheet(f"color: {SUCCESS}; font-size: 14px;")
        self._status_label.setText("Connected")
        self._connect_btn.setText("Disconnect")
        self._connect_btn.setEnabled(True)
        self._stop_all_btn.setEnabled(True)
        self._vol_slider.setEnabled(True)
        self.status_message.emit("Syrinscape: connected")

    def _on_auth_failed(self, msg: str) -> None:
        self._connected = False
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        self._status_label.setText("Auth failed")
        self._connect_btn.setText("Connect")
        self._connect_btn.setEnabled(True)
        self.status_message.emit(f"Syrinscape auth failed: {msg}")

    def _on_soundsets_loaded(self, soundsets: list) -> None:
        self._soundsets = soundsets
        self._soundset_list.clear()
        for s in soundsets:
            item = QListWidgetItem(s["name"])
            item.setData(Qt.ItemDataRole.UserRole, s["uuid"])                           # type: ignore[attr-defined]
            item.setData(Qt.ItemDataRole.UserRole + 1, s["name"])                       # type: ignore[attr-defined]
            item.setData(Qt.ItemDataRole.UserRole + 2, s.get("artwork", ""))            # type: ignore[attr-defined]
            # Apply cached artwork if already fetched
            art_url = s.get("artwork", "")
            if art_url and art_url in self._artwork_cache:
                item.setIcon(QIcon(self._artwork_cache[art_url]))
            self._soundset_list.addItem(item)
        self.status_message.emit(f"Syrinscape: {len(soundsets)} soundsets loaded")

    def _on_moods_loaded(self, moods: list) -> None:
        self._moods = moods
        self._apply_mood_filter()
        self._moods_header_lbl.setText(
            f"Moods — {self._selected_soundset_name} ({len(moods)})"
        )
        self._tabs.setCurrentIndex(1)   # switch to Moods tab

    def _on_mood_played(self, soundset_name: str, mood_name: str) -> None:
        text = f"▶  {soundset_name} — {mood_name}"
        self._now_playing_label.setText(text)
        self.status_message.emit(f"Syrinscape: {text}")
        if self._selected_soundset_uuid:
            self._sig_load_elements.emit(self._selected_soundset_uuid)

    def _on_stopped_all(self) -> None:
        self._now_playing_label.setText("Nothing playing")
        self.status_message.emit("Syrinscape: ⏹ stopped")

    def _on_artwork_loaded(self, url: str, data: bytes) -> None:
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    THUMB_SIZE, THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,             # type: ignore[attr-defined]
                    Qt.TransformationMode.SmoothTransformation,     # type: ignore[attr-defined]
                )
                self._artwork_cache[url] = pixmap
                # Update any list item that uses this URL
                for i in range(self._soundset_list.count()):
                    item = self._soundset_list.item(i)
                    if item and item.data(Qt.ItemDataRole.UserRole + 2) == url:  # type: ignore[attr-defined]
                        item.setIcon(QIcon(pixmap))
        except Exception:
            pass

    def _on_worker_error(self, msg: str) -> None:
        self.status_message.emit(f"Syrinscape error: {msg}")

    def _on_elements_loaded(self, elements: list) -> None:
        self._active_element_ids = [
            e["id"] for e in elements if e.get("id") is not None
        ]

    # ── User interaction slots ─────────────────────────────────────────────────

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self._disconnect()
            return
        token = self._token_edit.text().strip()
        if not token:
            QMessageBox.warning(
                self, "No Token",
                "Enter your Syrinscape auth token or add it to variables.env:\n\n"
                "  SYRINSCAPE_AUTH_TOKEN=<token>\n\n"
                "Get your token at: https://syrinscape.com/account/auth-token/",
            )
            return
        self._do_connect(token)

    def _do_connect(self, token: str) -> None:
        self._status_label.setText("Connecting…")
        self._dot_label.setStyleSheet(f"color: {WARNING}; font-size: 14px;")
        self._connect_btn.setEnabled(False)
        self._sig_connect.emit(token)

    def _disconnect(self) -> None:
        self._connected = False
        self._sig_disconnect.emit()
        self._dot_label.setStyleSheet(f"color: {ERROR}; font-size: 14px;")
        self._status_label.setText("Disconnected")
        self._connect_btn.setText("Connect")
        self._stop_all_btn.setEnabled(False)
        self._vol_slider.setEnabled(False)
        self._soundset_list.clear()
        self._mood_list.clear()
        self._now_playing_label.setText("Nothing playing")
        self.status_message.emit("Syrinscape: disconnected")

    def _on_stop_all(self) -> None:
        self._sig_stop_all.emit()

    def _on_soundset_selected(
        self, current: Optional[QListWidgetItem], _previous
    ) -> None:
        if current is None:
            return
        uuid = current.data(Qt.ItemDataRole.UserRole)           # type: ignore[attr-defined]
        name = current.data(Qt.ItemDataRole.UserRole + 1)       # type: ignore[attr-defined]
        self._selected_soundset_uuid = uuid or ""
        self._selected_soundset_name = name or ""
        if uuid:
            self._mood_filter.clear()
            self._mood_list.clear()
            self._moods_header_lbl.setText(f"Loading moods for {name}…")
            self._sig_load_moods.emit(uuid)

    def _on_mood_filter_changed(self, text: str) -> None:
        self._apply_mood_filter()

    def _apply_mood_filter(self) -> None:
        f = self._mood_filter.text().strip().lower()
        self._filtered_moods = [
            m for m in self._moods if f in m["name"].lower()
        ] if f else list(self._moods)
        self._mood_list.clear()
        for m in self._filtered_moods:
            item = QListWidgetItem(m["name"])
            item.setData(Qt.ItemDataRole.UserRole, m["id"])   # type: ignore[attr-defined]
            self._mood_list.addItem(item)

    def _on_mood_double_clicked(self, item: QListWidgetItem) -> None:
        self._play_mood_item(item)

    def _on_play_selected_mood(self) -> None:
        selected = self._mood_list.selectedItems()
        if selected:
            self._play_mood_item(selected[0])

    def _play_mood_item(self, item: QListWidgetItem) -> None:
        mood_id = item.data(Qt.ItemDataRole.UserRole)   # type: ignore[attr-defined]
        mood_name = item.text()
        if mood_id is not None:
            self._sig_play_mood.emit(
                mood_id,
                self._selected_soundset_name,
                mood_name,
            )

    # ── Scene interaction ──────────────────────────────────────────────────────

    def _on_scene_clicked(self, key: str) -> None:
        assigned = self._scene_config.get(key)
        if assigned and assigned.get("mood_id") is not None:
            self._sig_play_mood.emit(
                assigned["mood_id"],
                assigned.get("soundset_name", ""),
                assigned.get("mood_name", ""),
            )
            self.status_message.emit(
                f"Syrinscape scene: ▶ {assigned.get('mood_name', key)}"
            )
        else:
            QMessageBox.information(
                self,
                "No Mood Assigned",
                f"The «{key}» scene slot has no mood assigned yet.\n\n"
                "Select a mood in the Moods tab then right-click this slot to assign it.",
            )

    def _on_scene_context_menu(
        self, btn: QPushButton, key: str, pos
    ) -> None:
        menu = QMenu(self)
        assigned = self._scene_config.get(key)

        if assigned and assigned.get("mood_id") is not None:
            play_act = menu.addAction(
                f"▶  Play: {assigned.get('mood_name', key)}"
            )
            play_act.triggered.connect(lambda: self._on_scene_clicked(key))
            menu.addSeparator()

        assign_act = menu.addAction("📌  Assign selected mood")
        assign_act.triggered.connect(lambda: self._assign_selected_mood(key))

        if assigned:
            menu.addSeparator()
            clear_act = menu.addAction("✕  Clear assignment")
            clear_act.triggered.connect(lambda: self._clear_scene(key))

        menu.exec(btn.mapToGlobal(pos))

    def _assign_selected_mood(self, key: str) -> None:
        """Assign the currently-selected mood in the Moods tab to a scene slot."""
        selected = self._mood_list.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "No Mood Selected",
                "Please select a mood in the Moods tab first,\n"
                "then right-click a scene slot to assign it.",
            )
            return
        item    = selected[0]
        mood_id = item.data(Qt.ItemDataRole.UserRole)   # type: ignore[attr-defined]
        mood_name = item.text()
        self._scene_config[key] = {
            "mood_id":      mood_id,
            "mood_name":    mood_name,
            "soundset_name": self._selected_soundset_name,
        }
        self._save_scene_config()
        self._update_scene_btn_style(key)
        self.status_message.emit(
            f"Syrinscape: assigned «{mood_name}» to {key} scene"
        )

    def _clear_scene(self, key: str) -> None:
        self._scene_config[key] = None
        self._save_scene_config()
        self._update_scene_btn_style(key)
        self.status_message.emit(f"Syrinscape: cleared {key} scene")

    # ── Volume ─────────────────────────────────────────────────────────────────

    def _on_vol_changed(self, value: int) -> None:
        self._vol_val_label.setText(str(value))
        self._vol_debounce.start()
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
        self._vol_val_label.setText(str(value))
        self._vol_slider.blockSignals(False)
        # Use the existing debounce path so rapid mixer drags don't spam the API.
        self._vol_debounce.start()

    def _on_vol_debounce_fired(self) -> None:
        vol = self._vol_slider.value()
        if self._active_element_ids:
            self._sig_set_volume_all.emit(list(self._active_element_ids), vol)
            self.status_message.emit(
                f"Syrinscape: volume → {vol} ({len(self._active_element_ids)} elements)"
            )
        else:
            self.status_message.emit(
                f"Syrinscape: volume → {vol} (play a mood first to activate)"
            )

    # ── Voice command handler ─────────────────────────────────────────────────

    @Slot(str, str)
    def handle_command(self, action: str, query: str) -> None:
        """
        Handle a voice/chat command dispatched from DiscordPanel or ChatAgent.

        Actions
        -------
        play_mood — search moods by name (client-side) and play first match
        stop      — POST /stop-all/
        """
        action = action.lower().strip()
        self.status_message.emit(f"Syrinscape ← command: {action!r}  query={query!r}")

        if action == "stop":
            self._sig_stop_all.emit()

        elif action == "play_mood":
            query_lower = query.strip().lower()
            match = next(
                (m for m in self._moods if query_lower in m["name"].lower()),
                None,
            )
            if match:
                self._sig_play_mood.emit(
                    match["id"],
                    self._selected_soundset_name,
                    match["name"],
                )
            else:
                self.status_message.emit(
                    f"Syrinscape: no mood matching '{query}' in current soundset"
                )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop worker thread cleanly before the panel is destroyed."""
        self._vol_debounce.stop()
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._sig_disconnect.emit()
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
