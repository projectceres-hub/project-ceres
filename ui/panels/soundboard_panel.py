"""
Soundboard panel for Project Ceres — GM Assistant UI.

Lets the GM load, organise, and trigger sound effects and ambient tracks
for scene-setting.  Audio playback uses pygame.mixer if available, with a
graceful fallback to Windows winsound for simple .wav files.

Layout
------
  ┌─ 🔊 SOUNDBOARD ──────────────────────────────┐
  │  [ 🎵 Sounds ]  [ 🎬 Scenes ]                │
  ├──────────────────────────────────────────────│
  │  ... tab content ...                         │
  ├──────────────────────────────────────────────│
  │ Now playing: Forest Night.mp3                │
  └──────────────────────────────────────────────┘

Audio support
-------------
Install pygame for full MP3/OGG/WAV support:
    pip install pygame
Without it, WAV files still work via winsound (Windows only).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    _QT_BINDING = "PyQt5"
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QPushButton, QLabel, QSlider, QFileDialog, QScrollArea,
        QGroupBox, QSizePolicy, QMessageBox, QTabWidget, QListWidget, QListView,
        QListWidgetItem, QInputDialog, QSplitter, QFrame, QDial,
    )
    from PyQt5.QtCore import Qt, QTimer, QSettings, QSize, QUrl, pyqtSignal as Signal, pyqtSlot as Slot
    from PyQt5.QtGui import QFont
except ImportError:
    _QT_BINDING = "PySide6"
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QPushButton, QLabel, QSlider, QFileDialog, QScrollArea,
        QGroupBox, QSizePolicy, QMessageBox, QTabWidget, QListWidget, QListView,
        QListWidgetItem, QInputDialog, QSplitter, QFrame, QDial,
    )
    from PySide6.QtCore import Qt, QTimer, QSettings, QSize, QUrl, Signal, Slot  # type: ignore
    from PySide6.QtGui import QFont  # type: ignore

from ui.theme import ACCENT, ACCENT2, BG, BORDER, MUTED, TEXT, PANEL, SURFACE, SUCCESS, ERROR

_QT_MEDIA_OK = False
_QT_MEDIA_API = ""
try:
    if _QT_BINDING == "PyQt5":
        from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
        _QT_MEDIA_API = "qt5"
    else:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # type: ignore
        _QT_MEDIA_API = "qt6"
    _QT_MEDIA_OK = True
except Exception:
    pass

# ── Audio backend detection ────────────────────────────────────────────────────
_PYGAME_OK = False
try:
    import pygame
    pygame.mixer.init()
    pygame.mixer.set_num_channels(32)   # allow up to 32 simultaneous sounds
    _PYGAME_OK = True
except Exception:
    pass

_WINSOUND_OK = False
if sys.platform == "win32":
    try:
        import winsound  # type: ignore
        _WINSOUND_OK = True
    except ImportError:
        pass

_AUDIO_AVAILABLE = _PYGAME_OK or _WINSOUND_OK or _QT_MEDIA_OK

# File types we can play
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
if not _PYGAME_OK and not _QT_MEDIA_OK:
    # winsound only handles .wav
    AUDIO_EXTENSIONS = {".wav"}

# Subfolder names → emoji labels for auto-categorisation
CATEGORY_ICONS: Dict[str, str] = {
    "ambience":  "🌿",
    "ambient":   "🌿",
    "combat":    "⚔",
    "battle":    "⚔",
    "music":     "🎵",
    "stingers":  "🎺",
    "effects":   "💥",
    "sfx":       "💥",
    "voice":     "🎙",
    "misc":      "🔊",
}

# Number of buttons per row inside a category group
BUTTONS_PER_ROW = 3
ELEMENT_PLAY_ICON = "\u25b6"
ELEMENT_PAUSE_ICON = "\u23f8"


def _icon_for_category(name: str) -> str:
    return CATEGORY_ICONS.get(name.lower(), "🔊")


def _stem_label(path: Path, max_len: int = 14) -> str:
    """Short display label from a file stem."""
    stem = path.stem.replace("_", " ").replace("-", " ").title()
    return stem if len(stem) <= max_len else stem[:max_len - 1] + "…"


# ── Scene data structures ──────────────────────────────────────────────────────

@dataclass
class SceneSlot:
    path: str
    volume: int = 70    # 0–100
    loop: bool = True


@dataclass
class Scene:
    name: str
    slots: List[SceneSlot] = field(default_factory=list)


# ── Sound button ───────────────────────────────────────────────────────────────

class SoundButton(QPushButton):
    """A single sound-trigger button carrying its audio path."""

    def __init__(self, path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(_stem_label(path), parent)
        self.audio_path = path
        self.setToolTip(str(path))
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


# ── Main panel ─────────────────────────────────────────────────────────────────

class SoundboardPanel(QDockWidget):
    """
    Dockable soundboard panel.

    Signals:
        status_message(msg) — forwarded to main window status bar
    """

    status_message: Signal = Signal(str)
    volume_changed: Signal = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None, config: Optional[object] = None) -> None:
        super().__init__("🔊  Soundboard", parent)
        self.setObjectName("SoundboardPanel")
        self.setWindowTitle("Audio Console")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable    |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable  |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # ── Sounds tab state ──
        self._sound_folder: Optional[Path] = None
        self._now_playing: Optional[str] = None
        self._playing_element_key: Optional[str] = None
        self._paused_element_key: Optional[str] = None
        self._volume: float = 0.8  # 0.0 – 1.0

        # ── Scenes tab state ──
        self._scenes: List[Scene] = []
        self._current_scene_idx: int = -1
        self._active_channels: Dict[int, object] = {}   # slot_idx → pygame.mixer.Channel
        self._active_sounds: Dict[int, object] = {}     # slot_idx → pygame.mixer.Sound

        # ── UI widget refs (set in _build_* methods) ──
        self._scene_list_widget: Optional[QListWidget] = None
        self._slot_scroll_layout: Optional[QVBoxLayout] = None
        self._soundset_list_widget: Optional[QListWidget] = None
        self._elements_grid_layout: Optional[QGridLayout] = None
        self._scene_tabs: Optional[QTabWidget] = None
        self._campaign_scene_panel: Optional[QDockWidget] = None
        self._campaign_scene_layout: Optional[QVBoxLayout] = None
        self._element_volume_sliders: Dict[str, QSlider] = {}
        self._element_volume_knobs: Dict[str, QDial] = {}
        self._element_play_buttons: Dict[str, QPushButton] = {}
        self._element_label_buttons: Dict[str, QPushButton] = {}
        self._element_volume_by_path: Dict[str, int] = {}
        self._sound_categories: Dict[str, List[Path]] = {}
        self._selected_soundset_name: str = ""
        self._qt_media_players: List[object] = []
        self._qt_audio_outputs: List[object] = []

        self._settings = QSettings("ProjectCeres", "GMAssistant")
        self._config = config

        self._build_ui()
        self._show_no_folder_hint()
        self._restore_state()   # auto-reload last folder + volume + scenes

        if not _AUDIO_AVAILABLE:
            self._now_playing_label.setText(
                "⚠  No audio backend.  Run: pip install pygame"
            )
            self._now_playing_label.setStyleSheet(f"color: {ERROR};")

    # ══════════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(5)

        header = QHBoxLayout()
        title = QLabel("CERES AUDIO")
        title.setProperty("class", "section-header")
        header.addWidget(title, 1)

        load_btn = QPushButton("Load Folder")
        load_btn.setToolTip("Load a folder of audio files as your soundboard")
        load_btn.clicked.connect(self._load_folder)
        header.addWidget(load_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Remove all loaded sounds")
        clear_btn.clicked.connect(self._clear_board)
        header.addWidget(clear_btn)

        stop_btn = QPushButton("Stop All")
        stop_btn.setProperty("class", "accent")
        stop_btn.setToolTip("Stop all currently playing audio")
        stop_btn.clicked.connect(self._stop_all)
        header.addWidget(stop_btn)

        vol_lbl = QLabel("Vol:")
        vol_lbl.setProperty("class", "muted")
        header.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(int(self._volume * 100))
        self._vol_slider.setFixedWidth(90)
        self._vol_slider.setToolTip("Master volume")
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        header.addWidget(self._vol_slider)
        outer_layout.addLayout(header)

        self._console_splitter = QSplitter(Qt.Orientation.Vertical)  # type: ignore[attr-defined]
        self._console_splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {BORDER}; height: 3px; }}"
        )
        self._console_splitter.addWidget(self._build_soundset_pane())
        self._console_splitter.addWidget(self._build_elements_pane())
        self._console_splitter.addWidget(self._build_scene_pane())
        self._console_splitter_default_sizes = [90, 170, 420]
        for index in range(3):
            self._console_splitter.setStretchFactor(index, 1)
        self._console_splitter.setStretchFactor(0, 0)
        self._console_splitter.setStretchFactor(1, 0)
        self._console_splitter.setStretchFactor(2, 1)
        self._console_splitter.setSizes(self._console_splitter_default_sizes)
        outer_layout.addWidget(self._console_splitter, 1)

        now_row = QHBoxLayout()
        self._now_playing_label = QLabel("-- idle --")
        self._now_playing_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        now_row.addWidget(self._now_playing_label, 1)
        outer_layout.addLayout(now_row)

        self.setWidget(outer)

    def _build_soundset_pane(self) -> QWidget:
        pane = QFrame()
        pane.setProperty("class", "winamp-panel-frame")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        hdr = QLabel("Soundsets")
        hdr.setProperty("class", "section-header")
        layout.addWidget(hdr)

        self._soundset_list_widget = QListWidget()
        self._soundset_list_widget.setFlow(QListView.Flow.LeftToRight)
        self._soundset_list_widget.setWrapping(False)
        self._soundset_list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self._soundset_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # type: ignore[attr-defined]
        self._soundset_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        self._soundset_list_widget.setFixedHeight(42)
        self._soundset_list_widget.setStyleSheet(
            f"QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; }}"
            f"QListWidget::item {{ color: {MUTED}; padding: 5px 14px; }}"
            f"QListWidget::item:selected {{ background: {SURFACE}; color: {TEXT}; }}"
        )
        self._soundset_list_widget.currentItemChanged.connect(self._on_soundset_selected)
        layout.addWidget(self._soundset_list_widget, 1)
        return pane

    def _build_elements_pane(self) -> QWidget:
        pane = QFrame()
        pane.setProperty("class", "winamp-panel-frame")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        hdr = QLabel("Elements")
        hdr.setProperty("class", "section-header")
        layout.addWidget(hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # type: ignore[attr-defined]
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        self._scroll.setStyleSheet(f"background: {BG}; border: none;")

        self._board_widget = QWidget()
        self._elements_grid_layout = QGridLayout(self._board_widget)
        self._elements_grid_layout.setContentsMargins(6, 6, 6, 6)
        self._elements_grid_layout.setSpacing(8)
        self._scroll.setWidget(self._board_widget)
        layout.addWidget(self._scroll, 1)
        return pane

    def _build_scene_pane(self) -> QWidget:
        pane = QFrame()
        pane.setProperty("class", "winamp-panel-frame")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self._scene_tabs = QTabWidget()
        campaign = QWidget()
        self._campaign_scene_layout = QVBoxLayout(campaign)
        self._campaign_scene_layout.setContentsMargins(0, 0, 0, 0)
        waiting = QLabel("Campaign scenes will appear here once audio modules are ready.")
        waiting.setWordWrap(True)
        waiting.setProperty("class", "muted")
        self._campaign_scene_layout.addWidget(waiting)
        self._campaign_scene_layout.addStretch()

        self._scene_tabs.addTab(self._build_scenes_tab(), "Sound Scenes")
        self._scene_tabs.addTab(campaign, "Campaign Scenes")
        layout.addWidget(self._scene_tabs, 1)
        return pane

    def _build_sounds_tab(self) -> QWidget:
        """Build the Sounds tab — existing folder/button behaviour."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        # ── Top toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        load_btn = QPushButton("📁 Load Folder")
        load_btn.setToolTip("Load a folder of audio files as your soundboard")
        load_btn.clicked.connect(self._load_folder)
        toolbar.addWidget(load_btn)

        clear_btn = QPushButton("🗑 Clear")
        clear_btn.setToolTip("Remove all loaded sounds")
        clear_btn.clicked.connect(self._clear_board)
        toolbar.addWidget(clear_btn)

        stop_btn = QPushButton("■ Stop All")
        stop_btn.setProperty("class", "accent")
        stop_btn.setToolTip("Stop all currently playing audio")
        stop_btn.clicked.connect(self._stop_all)
        toolbar.addWidget(stop_btn)

        toolbar.addStretch()

        vol_lbl = QLabel("Vol:")
        vol_lbl.setStyleSheet(f"color: {MUTED};")
        toolbar.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(int(self._volume * 100))
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.setToolTip("Master volume")
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        toolbar.addWidget(self._vol_slider)

        layout.addLayout(toolbar)

        # ── Scroll area for sound buttons ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        self._scroll.setStyleSheet(f"background: {PANEL}; border: none;")

        self._board_widget = QWidget()
        self._board_layout = QVBoxLayout(self._board_widget)
        self._board_layout.setContentsMargins(4, 4, 4, 4)
        self._board_layout.setSpacing(6)
        self._board_layout.addStretch()

        self._scroll.setWidget(self._board_widget)
        layout.addWidget(self._scroll)

        return w

    def _build_scenes_tab(self) -> QWidget:
        """Build the Scenes tab — named scene collections with multi-channel playback."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        if not _PYGAME_OK:
            lbl = QLabel(
                "⚠  Install pygame for scene support:\n"
                "    pip install pygame"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
            lbl.setStyleSheet(f"color: {ERROR}; padding: 20px;")
            layout.addWidget(lbl)
            return w

        # ── Top action bar ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        new_btn = QPushButton("＋ New Scene")
        new_btn.setToolTip("Create a new named scene")
        new_btn.clicked.connect(self._add_scene)
        self._style_btn(new_btn)
        top_bar.addWidget(new_btn)

        play_btn = QPushButton("▶ Play Scene")
        play_btn.setToolTip("Start all slots in the selected scene simultaneously")
        play_btn.clicked.connect(self._play_scene)
        self._style_btn(play_btn)
        top_bar.addWidget(play_btn)

        stop_btn = QPushButton("■ Stop Scene")
        stop_btn.setToolTip("Stop all playing scene channels")
        stop_btn.clicked.connect(self._stop_scene)
        self._style_btn(stop_btn)
        top_bar.addWidget(stop_btn)

        top_bar.addStretch()
        layout.addLayout(top_bar)

        # ── Horizontal splitter: scene list (left) | slot editor (right) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER}; width: 2px; }}")

        # ── Left pane: scene list ──
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        scenes_hdr = QLabel("Scenes")
        scenes_hdr.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px; padding: 2px 4px;"
        )
        left_layout.addWidget(scenes_hdr)

        self._scene_list_widget = QListWidget()
        self._scene_list_widget.setStyleSheet(
            f"QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 3px; }}"
            f"QListWidget::item {{ padding: 2px; border: none; }}"
            f"QListWidget::item:selected {{ background: {ACCENT}; }}"
            f"QListWidget::item:hover:!selected {{ background: {SURFACE}; }}"
        )
        self._scene_list_widget.currentRowChanged.connect(self._on_scene_selected)
        left_layout.addWidget(self._scene_list_widget, 1)
        splitter.addWidget(left_widget)

        # ── Right pane: slot editor ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        slots_hdr = QLabel("Sounds")
        slots_hdr.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px; padding: 2px 4px;"
        )
        right_layout.addWidget(slots_hdr)

        slot_scroll = QScrollArea()
        slot_scroll.setWidgetResizable(True)
        slot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        slot_scroll.setStyleSheet(
            f"background: {PANEL}; border: 1px solid {BORDER}; border-radius: 3px;"
        )

        self._slot_scroll_widget = QWidget()
        self._slot_scroll_layout = QVBoxLayout(self._slot_scroll_widget)
        self._slot_scroll_layout.setContentsMargins(4, 4, 4, 4)
        self._slot_scroll_layout.setSpacing(6)
        self._slot_scroll_layout.addStretch()

        slot_scroll.setWidget(self._slot_scroll_widget)
        right_layout.addWidget(slot_scroll, 1)

        add_slot_btn = QPushButton("＋ Add Sound to Scene")
        add_slot_btn.setToolTip("Pick an audio file to add as a new slot")
        add_slot_btn.clicked.connect(self._add_slot_to_scene)
        self._style_btn(add_slot_btn)
        right_layout.addWidget(add_slot_btn)

        splitter.addWidget(right_widget)
        self._sound_scene_splitter = splitter
        self._sound_scene_splitter_default_sizes = [300, 300]
        self._sound_scene_splitter.setSizes(self._sound_scene_splitter_default_sizes)

        layout.addWidget(splitter, 1)
        return w

    # ══════════════════════════════════════════════════════════════════════════
    # State persistence
    # ══════════════════════════════════════════════════════════════════════════

    def _restore_state(self) -> None:
        """Reload the last-used sound folder, volume, and scenes from QSettings."""
        # Volume — restore before folder so the slider is correct
        saved_vol = self._settings.value("soundboard/volume", 80, type=int)
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(saved_vol)
        self._volume = saved_vol / 100.0
        self._vol_slider.blockSignals(False)

        # Folder — auto-load if it still exists on disk
        saved_folder = self._settings.value("soundboard/folder", "", type=str)
        if saved_folder:
            folder_path = Path(saved_folder)
            if folder_path.exists():
                self._sound_folder = folder_path
                self._rebuild_board()
                self.status_message.emit(
                    f"Soundboard: restored {folder_path.name}"
                )
            else:
                self._settings.remove("soundboard/folder")
        elif self._configured_sound_folders():
            self._rebuild_board()

        # Scenes
        self._load_scenes()
        self._refresh_scene_list()

    # ══════════════════════════════════════════════════════════════════════════
    # Sounds tab — loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Soundboard Folder",
            str(self._sound_folder or Path.home()),
        )
        if not folder:
            return
        self._sound_folder = Path(folder)
        self._settings.setValue("soundboard/folder", str(self._sound_folder))
        self._rebuild_board()
        self.status_message.emit(f"Soundboard: {self._sound_folder.name}")

    def _clear_board(self) -> None:
        self._stop_all()
        self._sound_folder = None
        self._settings.remove("soundboard/folder")
        self._playing_element_key = None
        self._paused_element_key = None
        self._sound_categories.clear()
        self._selected_soundset_name = ""
        if self._elements_grid_layout is not None:
            self._clear_layout(self._elements_grid_layout)
        self._element_volume_sliders.clear()
        self._element_volume_knobs.clear()
        self._element_play_buttons.clear()
        self._element_label_buttons.clear()
        if self._soundset_list_widget is not None:
            self._soundset_list_widget.clear()
        self._show_no_folder_hint()

    def reload_configured_folders(self) -> None:
        """Reload Preferences-managed sound folders alongside any explicit folder."""
        self._rebuild_board()

    def _configured_sound_folders(self) -> List[Path]:
        folders = getattr(self._config, "soundboard_folders", []) if self._config is not None else []
        paths: List[Path] = []
        for folder in folders:
            try:
                path = Path(folder)
            except TypeError:
                continue
            if path.exists() and path.is_dir():
                paths.append(path)
        return paths

    def _sound_roots(self) -> List[Path]:
        roots: List[Path] = []
        if self._sound_folder is not None:
            roots.append(self._sound_folder)
        roots.extend(self._configured_sound_folders())
        unique_roots: List[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve())
            if key not in seen:
                seen.add(key)
                unique_roots.append(root)
        return unique_roots

    def _rebuild_board(self) -> None:
        """Scan folder and rebuild soundset list plus Winamp element tiles."""
        self._stop_all()
        if self._elements_grid_layout is None:
            return

        self._clear_layout(self._elements_grid_layout)
        self._element_volume_sliders.clear()
        self._element_volume_knobs.clear()
        self._element_play_buttons.clear()
        self._element_label_buttons.clear()
        self._sound_categories.clear()
        if self._soundset_list_widget is not None:
            self._soundset_list_widget.blockSignals(True)
            self._soundset_list_widget.clear()

        roots = self._sound_roots()
        if not roots:
            if self._soundset_list_widget is not None:
                self._soundset_list_widget.blockSignals(False)
            self._show_no_folder_hint()
            return

        categories: Dict[str, List[Path]] = {}
        for root in roots:
            for entry in sorted(root.rglob("*")):
                if entry.is_file() and self._is_audio_file(entry):
                    try:
                        rel = entry.relative_to(root)
                        cat = rel.parts[0] if len(rel.parts) > 1 else "General"
                    except ValueError:
                        cat = "General"
                    categories.setdefault(cat, []).append(entry)
        self._sound_categories = categories

        if not categories:
            if self._soundset_list_widget is not None:
                self._soundset_list_widget.blockSignals(False)
            hint = QLabel(f"No audio files found.\nSupported: {', '.join(sorted(AUDIO_EXTENSIONS))}")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
            hint.setStyleSheet(f"color: {MUTED};")
            self._elements_grid_layout.addWidget(hint, 0, 0)
            return

        if self._soundset_list_widget is not None:
            for cat_name in sorted(categories):
                item = QListWidgetItem(f"{_icon_for_category(cat_name)}  {cat_name}")
                item.setData(Qt.ItemDataRole.UserRole, cat_name)  # type: ignore[attr-defined]
                self._soundset_list_widget.addItem(item)

            selected_row = 0
            if self._selected_soundset_name in categories:
                selected_row = sorted(categories).index(self._selected_soundset_name)
            self._selected_soundset_name = sorted(categories)[selected_row]
            self._soundset_list_widget.setCurrentRow(selected_row)
            self._soundset_list_widget.blockSignals(False)

        self._render_selected_soundset()

    def _is_audio_file(self, path: Path) -> bool:
        return (
            path.suffix.lower() in AUDIO_EXTENSIONS
            and not path.name.startswith("._")
            and not path.name.startswith(".")
        )

    def _on_soundset_selected(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        if current is None:
            return
        category = current.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        self._selected_soundset_name = str(category or current.text()).strip()
        self._render_selected_soundset()

    def _render_selected_soundset(self) -> None:
        if self._elements_grid_layout is None:
            return

        self._clear_layout(self._elements_grid_layout)
        self._element_volume_sliders.clear()
        self._element_volume_knobs.clear()
        self._element_play_buttons.clear()
        self._element_label_buttons.clear()

        files = self._sound_categories.get(self._selected_soundset_name, [])
        for tile_index, path in enumerate(sorted(files, key=lambda p: p.stem.lower())):
            tile = self._make_element_tile(path)
            self._elements_grid_layout.addWidget(tile, 0, tile_index)

    def _show_no_folder_hint(self) -> None:
        hint = QLabel('Click "Load Folder" to load your sounds.')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        hint.setStyleSheet(f"color: {MUTED}; padding: 20px;")
        if self._elements_grid_layout is not None:
            self._clear_layout(self._elements_grid_layout)
            self._elements_grid_layout.addWidget(hint, 0, 0)

    def _make_element_tile(self, path: Path) -> QFrame:
        key = str(path)
        saved_volume = self._settings.value(f"soundboard/elements/{key}/volume", 80, type=int)
        self._element_volume_by_path[key] = saved_volume

        tile = QFrame()
        tile.setProperty("class", "winamp-panel-frame")
        tile.setMinimumSize(104, 150)
        tile.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 1px; }}"
        )

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        controls = QHBoxLayout()
        controls.setSpacing(6)

        knob_col = QVBoxLayout()
        knob_col.setSpacing(4)

        play_btn = QPushButton(ELEMENT_PLAY_ICON)
        play_btn.setFixedSize(26, 22)
        play_btn.setToolTip(f"Play {path.name}")
        self._style_element_play_btn(play_btn)
        play_btn.clicked.connect(lambda checked, p=path: self._toggle_element_playback(p))
        knob_col.addWidget(play_btn, 0, Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]

        knob = QDial()
        knob.setFixedSize(52, 52)
        knob.setRange(0, 100)
        knob.setValue(saved_volume)
        knob.setWrapping(False)
        knob.setNotchesVisible(False)
        knob.setStyleSheet(
            "QDial {"
            " border-radius: 26px;"
            f" border: 2px solid {BORDER};"
            " background: qradialgradient(cx:0.35, cy:0.3, radius:0.8,"
            f" stop:0 {MUTED}, stop:0.45 {SURFACE}, stop:1 #050608);"
            f" border-top-color: {MUTED}; border-left-color: {MUTED};"
            "}"
        )
        knob.setToolTip("Element volume")
        knob_col.addWidget(knob, 0, Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        controls.addLayout(knob_col)

        fader = QSlider(Qt.Orientation.Vertical)  # type: ignore[attr-defined]
        fader.setRange(0, 100)
        fader.setValue(saved_volume)
        fader.setFixedHeight(82)
        fader.setToolTip("Element volume")
        self._style_vertical_fader(fader)
        fader.valueChanged.connect(lambda value, k=key: self._on_element_volume_changed(k, value))
        fader.valueChanged.connect(lambda value, dial=knob: self._sync_element_knob(dial, value))
        knob.valueChanged.connect(lambda value, slider=fader: self._sync_element_fader(slider, value))
        controls.addWidget(fader, 0, Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]

        layout.addLayout(controls)

        label_btn = QPushButton(_stem_label(path, 16))
        label_btn.setToolTip(str(path))
        label_btn.setFixedHeight(24)
        self._style_element_label_btn(label_btn)
        label_btn.clicked.connect(lambda checked, p=path: self._play(p))
        layout.addWidget(label_btn)

        pct = QLabel(f"{saved_volume}%")
        pct.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        pct.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        fader.valueChanged.connect(lambda value, label=pct: label.setText(f"{value}%"))
        layout.addWidget(pct)

        self._element_volume_sliders[key] = fader
        self._element_volume_knobs[key] = knob
        self._element_play_buttons[key] = play_btn
        self._element_label_buttons[key] = label_btn
        self._sync_element_button_state(key)
        return tile

    def _toggle_element_playback(self, path: Path) -> None:
        key = str(path)
        if self._playing_element_key == key and self._paused_element_key != key:
            self._pause_current_element()
            return
        if self._playing_element_key == key and self._paused_element_key == key:
            self._resume_current_element()
            return
        self._play(path)

    def _pause_current_element(self) -> None:
        key = self._playing_element_key
        if key is None:
            return
        if _PYGAME_OK:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
        elif _WINSOUND_OK:
            try:
                import winsound  # type: ignore
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        for player in self._qt_media_players:
            try:
                player.pause()
            except Exception:
                pass
        self._paused_element_key = key
        self._sync_element_button_state(key)
        self._now_playing_label.setText(f"Paused: {Path(key).name}")
        self._now_playing_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self.status_message.emit(f"Paused: {Path(key).name}")

    def _resume_current_element(self) -> None:
        key = self._paused_element_key
        if key is None:
            return
        if _PYGAME_OK:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
        else:
            for player in self._qt_media_players:
                try:
                    player.play()
                except Exception:
                    pass
        self._paused_element_key = None
        self._sync_element_button_state(key)
        self._now_playing = Path(key).name
        self._now_playing_label.setText(f"▶  {Path(key).name}")
        self._now_playing_label.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
        self.status_message.emit(f"Playing: {Path(key).name}")

    def _sync_element_button_state(self, key: str) -> None:
        button = self._element_play_buttons.get(key)
        if button is None:
            return
        is_playing = self._playing_element_key == key and self._paused_element_key != key
        button.setText(ELEMENT_PAUSE_ICON if is_playing else ELEMENT_PLAY_ICON)
        button.setToolTip(
            f"Pause {Path(key).name}" if is_playing else f"Play {Path(key).name}"
        )

    def _sync_all_element_button_states(self) -> None:
        for key in self._element_play_buttons:
            self._sync_element_button_state(key)

    def _on_element_volume_changed(self, key: str, value: int) -> None:
        self._element_volume_by_path[key] = value
        self._settings.setValue(f"soundboard/elements/{key}/volume", value)
        self._update_current_element_volume(key)

    def _sync_element_knob(self, knob: QDial, value: int) -> None:
        if knob.value() == value:
            return
        knob.blockSignals(True)
        knob.setValue(value)
        knob.blockSignals(False)

    def _sync_element_fader(self, fader: QSlider, value: int) -> None:
        if fader.value() == value:
            return
        fader.blockSignals(True)
        fader.setValue(value)
        fader.blockSignals(False)
        fader.valueChanged.emit(value)

    def _update_current_element_volume(self, key: str) -> None:
        path_name = Path(key).name
        if self._now_playing != path_name:
            return
        effective_volume = self._effective_element_volume(Path(key))
        if _PYGAME_OK:
            try:
                pygame.mixer.music.set_volume(effective_volume)
            except Exception:
                pass
        for player in self._qt_media_players:
            try:
                if _QT_MEDIA_API == "qt5" and hasattr(player, "setVolume"):
                    player.setVolume(int(effective_volume * 100))
                elif _QT_MEDIA_API == "qt6" and hasattr(player, "audioOutput"):
                    output = player.audioOutput()
                    if output is not None:
                        output.setVolume(effective_volume)
            except Exception:
                pass

    def _effective_element_volume(self, path: Path) -> float:
        element_volume = self._element_volume_by_path.get(str(path), 100) / 100.0
        return max(0.0, min(1.0, self._volume * element_volume))

    def _current_element_key(self) -> Optional[str]:
        if self._playing_element_key is not None:
            return self._playing_element_key
        if not self._now_playing:
            return None
        for key in self._element_volume_by_path:
            if Path(key).name == self._now_playing:
                return key
        return None

    def _style_element_play_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {BG}; color: {ACCENT};"
            f" border: 1px solid {ACCENT}; border-radius: 1px;"
            " font-weight: bold; padding: 0;"
            f" box-shadow: 0 0 4px {ACCENT}; }}"
            f"QPushButton:hover {{ color: {ACCENT2}; border-color: {ACCENT2}; }}"
            f"QPushButton:pressed {{ background: {SURFACE}; color: {ACCENT2}; }}"
        )

    def _style_element_label_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {BG}; color: {TEXT};"
            f" border: 1px solid {BORDER}; border-radius: 1px; padding: 2px;"
            " font-size: 10px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ color: {ACCENT2}; }}"
        )

    def _style_vertical_fader(self, slider: QSlider) -> None:
        slider.setStyleSheet(
            "QSlider::groove:vertical { background: #020302; width: 5px;"
            f" border: 1px solid #05060a; border-right-color: {BORDER};"
            f" border-bottom-color: {BORDER}; border-radius: 1px; }}"
            "QSlider::handle:vertical { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 #fff3a3, stop:0.45 {ACCENT2}, stop:1 #806713);"
            " width: 14px; height: 10px; margin: 0 -5px; border: 1px solid #05060a;"
            " border-radius: 1px; }"
            "QSlider::sub-page:vertical { background: transparent; border-radius: 1px; }"
            f"QSlider::add-page:vertical {{ background: {ACCENT2}; border-radius: 1px; }}"
        )

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            child_layout = item.layout()
            if child is not None:
                child.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def configure_campaign_scenes(self, panel_refs: Dict[str, object], config: object) -> QDockWidget:
        from ui.panels.master_scene_panel import MasterScenePanel

        if self._campaign_scene_layout is None:
            raise RuntimeError("Campaign scene pane has not been built")

        self._clear_layout(self._campaign_scene_layout)
        panel = MasterScenePanel(panel_refs, config, self)
        panel.setWindowTitle("Campaign Scenes")
        panel.status_message.connect(self.status_message.emit)
        self._campaign_scene_panel = panel
        self._campaign_scene_layout.addWidget(panel)
        return panel

    def campaign_scene_handler(self) -> Optional[QDockWidget]:
        return self._campaign_scene_panel

    # ══════════════════════════════════════════════════════════════════════════
    # Sounds tab — playback
    # ══════════════════════════════════════════════════════════════════════════

    def _play(self, path: Path) -> None:
        """Play a sound file using the best available backend."""
        if not _AUDIO_AVAILABLE:
            QMessageBox.warning(
                self, "No Audio Backend",
                "Install pygame for audio support:\n    pip install pygame"
            )
            return

        try:
            if _PYGAME_OK:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(str(path))
                element_volume = self._element_volume_by_path.get(str(path), 100) / 100.0
                pygame.mixer.music.set_volume(self._volume * element_volume)
                pygame.mixer.music.play()
            elif _WINSOUND_OK and path.suffix.lower() == ".wav":
                import winsound  # type: ignore
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif not self._play_with_qt_media(path):
                raise RuntimeError("No supported audio backend for this file")

            previous_key = self._playing_element_key
            self._playing_element_key = str(path)
            self._paused_element_key = None
            if previous_key and previous_key != self._playing_element_key:
                self._sync_element_button_state(previous_key)
            self._sync_element_button_state(self._playing_element_key)
            self._now_playing = path.name
            self._now_playing_label.setText(f"▶  {path.name}")
            self._now_playing_label.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
            self.status_message.emit(f"Playing: {path.name}")
        except Exception as e:
            if path.suffix.lower() in {".mp3", ".wav", ".ogg", ".flac", ".m4a"} and self._play_with_qt_media(path):
                previous_key = self._playing_element_key
                self._playing_element_key = str(path)
                self._paused_element_key = None
                if previous_key and previous_key != self._playing_element_key:
                    self._sync_element_button_state(previous_key)
                self._sync_element_button_state(self._playing_element_key)
                self._now_playing = path.name
                self._now_playing_label.setText(f"▶  {path.name}")
                self._now_playing_label.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
                self.status_message.emit(f"Playing: {path.name}")
                return
            self._now_playing_label.setText(f"Error: {path.name}")
            self._now_playing_label.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
            self.status_message.emit(
                f"Soundboard: {path.name} could not be played; unsupported or corrupt audio file."
            )

    def _play_with_qt_media(self, path: Path) -> bool:
        """Fallback for MP3 files pygame rejects but the OS media stack can play."""
        if not _QT_MEDIA_OK:
            return False
        try:
            if _QT_MEDIA_API == "qt5":
                player = QMediaPlayer(self)
                player.setMedia(QMediaContent(QUrl.fromLocalFile(str(path))))  # type: ignore[name-defined]
                player.setVolume(int(self._effective_element_volume(path) * 100))
            else:
                player = QMediaPlayer(self)
                audio_output = QAudioOutput(self)  # type: ignore[name-defined]
                audio_output.setVolume(self._effective_element_volume(path))
                player.setAudioOutput(audio_output)
                player.setSource(QUrl.fromLocalFile(str(path)))
                self._qt_audio_outputs.append(audio_output)
            if hasattr(player, "errorOccurred"):
                player.errorOccurred.connect(  # type: ignore[attr-defined]
                    lambda _error, p=path: self._on_qt_media_error(p)
                )
            elif hasattr(player, "error"):
                player.error.connect(  # type: ignore[attr-defined]
                    lambda _error, p=path: self._on_qt_media_error(p)
                )
            self._qt_media_players.append(player)
            player.play()
            return True
        except Exception:
            return False

    def _on_qt_media_error(self, path: Path) -> None:
        if self._now_playing != path.name:
            return
        key = str(path)
        if self._playing_element_key == key:
            self._playing_element_key = None
            self._paused_element_key = None
            self._sync_element_button_state(key)
        self._now_playing_label.setText(f"Error: {path.name}")
        self._now_playing_label.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
        self.status_message.emit(
            f"Soundboard: {path.name} could not be played; unsupported or corrupt audio file."
        )

    def _stop_all(self) -> None:
        if _PYGAME_OK:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.stop()
            except Exception:
                pass
        for player in self._qt_media_players:
            try:
                player.stop()
            except Exception:
                pass
        self._qt_media_players.clear()
        self._qt_audio_outputs.clear()
        self._now_playing = None
        self._playing_element_key = None
        self._paused_element_key = None
        self._sync_all_element_button_states()
        self._now_playing_label.setText("— idle —")
        self._now_playing_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")

    def _on_volume_changed(self, value: int) -> None:
        self._volume = value / 100.0
        self._settings.setValue("soundboard/volume", value)
        current_key = self._current_element_key()
        if _PYGAME_OK:
            try:
                if current_key is not None:
                    pygame.mixer.music.set_volume(self._effective_element_volume(Path(current_key)))
                else:
                    pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass
        if current_key is not None:
            self._update_current_element_volume(current_key)
        self.volume_changed.emit(value)

    def get_volume(self) -> int:
        """Return the current master volume (0–100)."""
        return self._vol_slider.value()

    @Slot(int)
    def set_volume(self, value: int) -> None:
        """Set master volume without triggering a volume_changed echo.

        Args:
            value: Volume level 0–100 sent by the Mixer panel.
        """
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(value)
        self._vol_slider.blockSignals(False)
        self._volume = value / 100.0
        self._settings.setValue("soundboard/volume", value)
        current_key = self._current_element_key()
        if _PYGAME_OK:
            try:
                if current_key is not None:
                    pygame.mixer.music.set_volume(self._effective_element_volume(Path(current_key)))
                else:
                    pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass
        if current_key is not None:
            self._update_current_element_volume(current_key)

    def set_eq_bands(self, enabled: bool, bands: list) -> None:
        """
        Apply EQ to all currently-loaded scene `Sound` objects.

        Uses pygame.sndarray to read PCM data as a numpy array,
        applies the 10-band EQ via equalizer_panel.apply_eq, and
        writes the filtered data back. When disabled, reloads from file paths.

        Args:
            enabled: If False, reload sounds from their original paths to restore flat audio.
            bands:   List of 10 dB gain floats matching BAND_FREQS in equalizer_panel.
        """
        if not _PYGAME_OK:
            return
        try:
            import numpy as np
            import pygame.sndarray as sndarray
        except ImportError:
            self.status_message.emit("EQ: numpy/pygame.sndarray not available")
            return

        try:
            from ui.panels.equalizer_panel import apply_eq
        except ImportError:
            return

        freq = 44100
        try:
            if pygame.mixer.get_init():
                freq = pygame.mixer.get_init()[0]
        except Exception:
            pass

        for slot_idx, sound in list(getattr(self, "_active_sounds", {}).items()):
            try:
                scene = (
                    self._scenes[self._current_scene_idx]
                    if 0 <= self._current_scene_idx < len(self._scenes)
                    else None
                )
                path: Optional[Path] = None
                if scene is not None and 0 <= slot_idx < len(scene.slots):
                    path = Path(scene.slots[slot_idx].path)

                if not enabled:
                    if path and path.exists():
                        new_sound = pygame.mixer.Sound(str(path))
                        self._active_sounds[slot_idx] = new_sound
                    continue

                arr = sndarray.array(sound)
                arr_f = arr.astype(np.float32) / 32768.0
                arr_f = apply_eq(arr_f, freq, bands)
                arr_out = np.clip(arr_f * 32767.0, -32768, 32767).astype(np.int16)
                new_sound = sndarray.make_sound(arr_out)
                self._active_sounds[slot_idx] = new_sound
            except Exception as exc:
                self.status_message.emit(f"EQ: soundboard error — {exc}")
                break
        self.status_message.emit(
            "EQ applied to Soundboard" if enabled else "EQ removed from Soundboard"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Scenes tab — UI refresh
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_scene_list(self) -> None:
        """Rebuild the left-pane scene list widget."""
        if self._scene_list_widget is None:
            return

        self._scene_list_widget.blockSignals(True)
        self._scene_list_widget.clear()

        for i, scene in enumerate(self._scenes):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 38))

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 2, 4, 2)
            row_layout.setSpacing(4)

            name_lbl = QLabel(scene.name)
            name_lbl.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
            name_lbl.setToolTip(scene.name)
            row_layout.addWidget(name_lbl, 1)

            rename_btn = QPushButton("✎")
            rename_btn.setFixedSize(22, 22)
            rename_btn.setToolTip("Rename scene")
            rename_btn.clicked.connect(lambda checked, idx=i: self._rename_scene(idx))
            self._style_small_btn(rename_btn)
            row_layout.addWidget(rename_btn)

            del_btn = QPushButton("🗑")
            del_btn.setFixedSize(22, 22)
            del_btn.setToolTip("Delete scene")
            del_btn.clicked.connect(lambda checked, idx=i: self._delete_scene(idx))
            self._style_small_btn(del_btn)
            row_layout.addWidget(del_btn)

            self._scene_list_widget.addItem(item)
            self._scene_list_widget.setItemWidget(item, row)

        self._scene_list_widget.blockSignals(False)

        # Restore selection
        if 0 <= self._current_scene_idx < self._scene_list_widget.count():
            self._scene_list_widget.setCurrentRow(self._current_scene_idx)

    def _refresh_slot_list(self) -> None:
        """Rebuild the right-pane slot editor for the selected scene."""
        if self._slot_scroll_layout is None:
            return

        self._clear_layout(self._slot_scroll_layout)

        if self._current_scene_idx < 0 or self._current_scene_idx >= len(self._scenes):
            hint = QLabel("Select a scene to view its slots.")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
            hint.setStyleSheet(f"color: {MUTED}; padding: 20px;")
            self._slot_scroll_layout.addWidget(hint)
            self._slot_scroll_layout.addStretch()
            return

        scene = self._scenes[self._current_scene_idx]

        if not scene.slots:
            hint = QLabel('No sounds yet.\nClick "＋ Add Sound to Scene".')
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
            hint.setStyleSheet(f"color: {MUTED}; padding: 16px;")
            self._slot_scroll_layout.addWidget(hint)
        else:
            for i, slot in enumerate(scene.slots):
                frame = self._make_slot_widget(i, slot)
                self._slot_scroll_layout.addWidget(frame)

        self._slot_scroll_layout.addStretch()

    def _make_slot_widget(self, slot_idx: int, slot: SceneSlot) -> QFrame:
        """Build the UI widget for a single scene slot."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {BORDER};"
            f"  border-radius: 4px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)

        # ── Header: filename + remove button ──
        header = QHBoxLayout()
        fname = Path(slot.path).name
        short_name = fname if len(fname) <= 32 else fname[:31] + "…"
        name_lbl = QLabel(f"🔊 {short_name}")
        name_lbl.setStyleSheet(f"color: {TEXT}; font-size: 10px; font-weight: bold;")
        name_lbl.setToolTip(slot.path)
        header.addWidget(name_lbl, 1)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setToolTip("Remove this slot")
        remove_btn.clicked.connect(lambda checked, idx=slot_idx: self._remove_slot(idx))
        self._style_small_btn(remove_btn)
        header.addWidget(remove_btn)
        layout.addLayout(header)

        # ── Volume row ──
        vol_row = QHBoxLayout()
        vol_lbl = QLabel("Vol:")
        vol_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        vol_lbl.setFixedWidth(24)
        vol_row.addWidget(vol_lbl)

        vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        vol_slider.setRange(0, 100)
        vol_slider.setValue(slot.volume)
        vol_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background: {BORDER}; height: 4px; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ background: {ACCENT}; width: 12px; height: 12px;"
            f"  margin: -4px 0; border-radius: 6px; }}"
        )
        vol_row.addWidget(vol_slider, 1)

        pct_lbl = QLabel(f"{slot.volume}%")
        pct_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        pct_lbl.setFixedWidth(32)
        vol_row.addWidget(pct_lbl)

        # Wire volume slider
        vol_slider.valueChanged.connect(lambda v, lbl=pct_lbl: lbl.setText(f"{v}%"))
        vol_slider.valueChanged.connect(
            lambda v, idx=slot_idx: self._on_slot_volume_changed(idx, v)
        )

        # ── Loop button ──
        loop_btn = QPushButton("🔁 loop")
        loop_btn.setCheckable(True)
        loop_btn.setChecked(slot.loop)
        loop_btn.setFixedHeight(22)
        loop_btn.setToolTip("Toggle looping for this slot")
        self._style_loop_btn(loop_btn, slot.loop)
        loop_btn.toggled.connect(lambda checked, btn=loop_btn: self._style_loop_btn(btn, checked))
        loop_btn.toggled.connect(
            lambda checked, idx=slot_idx: self._on_slot_loop_changed(idx, checked)
        )
        vol_row.addWidget(loop_btn)

        layout.addLayout(vol_row)

        # ── Play / Stop buttons ──
        btn_row = QHBoxLayout()

        play_btn = QPushButton("▶ Play")
        play_btn.setFixedHeight(24)
        play_btn.setToolTip("Play this slot independently")
        play_btn.clicked.connect(lambda checked, idx=slot_idx: self._play_slot(idx))
        self._style_btn(play_btn)
        btn_row.addWidget(play_btn)

        stop_btn = QPushButton("■ Stop")
        stop_btn.setFixedHeight(24)
        stop_btn.setToolTip("Stop this slot")
        stop_btn.clicked.connect(lambda checked, idx=slot_idx: self._stop_slot(idx))
        self._style_btn(stop_btn)
        btn_row.addWidget(stop_btn)

        layout.addLayout(btn_row)

        return frame

    # ══════════════════════════════════════════════════════════════════════════
    # Scenes tab — event handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_scene_selected(self, row: int) -> None:
        self._current_scene_idx = row
        self._refresh_slot_list()

    def _add_scene(self) -> None:
        name, ok = QInputDialog.getText(self, "New Scene", "Scene name:")
        if ok and name.strip():
            self._scenes.append(Scene(name=name.strip()))
            self._current_scene_idx = len(self._scenes) - 1
            self._save_scenes()
            self._refresh_scene_list()
            self._refresh_slot_list()
            self.status_message.emit(f"Scene created: {name.strip()}")

    def _delete_scene(self, idx: int) -> None:
        if not (0 <= idx < len(self._scenes)):
            return
        name = self._scenes[idx].name
        self._stop_scene()
        del self._scenes[idx]
        # Clamp the current selection
        if self._current_scene_idx >= len(self._scenes):
            self._current_scene_idx = len(self._scenes) - 1
        self._save_scenes()
        self._refresh_scene_list()
        self._refresh_slot_list()
        self.status_message.emit(f"Scene deleted: {name}")

    def _rename_scene(self, idx: int) -> None:
        if not (0 <= idx < len(self._scenes)):
            return
        old_name = self._scenes[idx].name
        name, ok = QInputDialog.getText(
            self, "Rename Scene", "New name:", text=old_name
        )
        if ok and name.strip():
            self._scenes[idx].name = name.strip()
            self._save_scenes()
            self._refresh_scene_list()
            self.status_message.emit(f"Scene renamed: {name.strip()}")

    def _add_slot_to_scene(self) -> None:
        if self._current_scene_idx < 0 or self._current_scene_idx >= len(self._scenes):
            QMessageBox.information(
                self, "No Scene Selected",
                "Please select or create a scene first."
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Sound to Scene", "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.m4a);;All Files (*)"
        )
        if path:
            slot = SceneSlot(path=path, volume=70, loop=True)
            self._scenes[self._current_scene_idx].slots.append(slot)
            self._save_scenes()
            self._refresh_slot_list()
            self.status_message.emit(f"Added slot: {Path(path).name}")

    def _remove_slot(self, slot_idx: int) -> None:
        if self._current_scene_idx < 0:
            return
        scene = self._scenes[self._current_scene_idx]
        if not (0 <= slot_idx < len(scene.slots)):
            return
        self._stop_slot(slot_idx)
        del scene.slots[slot_idx]
        self._save_scenes()
        self._refresh_slot_list()

    def _on_slot_volume_changed(self, slot_idx: int, value: int) -> None:
        if self._current_scene_idx < 0:
            return
        scene = self._scenes[self._current_scene_idx]
        if not (0 <= slot_idx < len(scene.slots)):
            return
        scene.slots[slot_idx].volume = value
        # Update channel volume in real time if playing
        ch = self._active_channels.get(slot_idx)
        if ch is not None and _PYGAME_OK:
            try:
                effective_vol = (value / 100.0) * self._volume
                ch.set_volume(effective_vol)
            except Exception:
                pass
        self._save_scenes()

    def _on_slot_loop_changed(self, slot_idx: int, loop: bool) -> None:
        if self._current_scene_idx < 0:
            return
        scene = self._scenes[self._current_scene_idx]
        if not (0 <= slot_idx < len(scene.slots)):
            return
        scene.slots[slot_idx].loop = loop
        # If currently playing, restart with new loop setting
        if slot_idx in self._active_channels:
            self._play_slot(slot_idx)
        self._save_scenes()

    # ══════════════════════════════════════════════════════════════════════════
    # Scenes tab — playback
    # ══════════════════════════════════════════════════════════════════════════

    def _play_scene(self) -> None:
        """Start all slots in the selected scene simultaneously."""
        if self._current_scene_idx < 0 or self._current_scene_idx >= len(self._scenes):
            self.status_message.emit("No scene selected.")
            return
        if not _PYGAME_OK:
            return
        self._stop_scene()
        scene = self._scenes[self._current_scene_idx]
        count = sum(1 for i in range(len(scene.slots)) if self._play_slot(i))
        self.status_message.emit(
            f"Scene '{scene.name}' playing — {count}/{len(scene.slots)} slots active."
        )

    def _play_slot(self, slot_idx: int) -> bool:
        """Play a single slot independently. Returns True on success."""
        if not _PYGAME_OK:
            return False
        if self._current_scene_idx < 0:
            return False
        scene = self._scenes[self._current_scene_idx]
        if not (0 <= slot_idx < len(scene.slots)):
            return False

        slot = scene.slots[slot_idx]
        path = Path(slot.path)
        if not path.exists():
            self.status_message.emit(f"File not found: {path.name}")
            return False

        # Stop any existing channel for this slot before restarting
        self._stop_slot(slot_idx)

        try:
            sound = pygame.mixer.Sound(str(path))
            channel = pygame.mixer.find_channel(True)   # True = force a free channel
            if channel is None:
                self.status_message.emit("No free audio channel available.")
                return False

            effective_vol = (slot.volume / 100.0) * self._volume
            channel.set_volume(effective_vol)
            loops = -1 if slot.loop else 0
            channel.play(sound, loops=loops)

            self._active_sounds[slot_idx] = sound
            self._active_channels[slot_idx] = channel
            return True
        except Exception as e:
            self.status_message.emit(f"Error playing {path.name}: {e}")
            return False

    def _stop_slot(self, slot_idx: int) -> None:
        """Stop a single slot's channel."""
        ch = self._active_channels.pop(slot_idx, None)
        self._active_sounds.pop(slot_idx, None)
        if ch is not None:
            try:
                ch.stop()
            except Exception:
                pass

    def _stop_scene(self) -> None:
        """Stop all active scene channels."""
        self._stop_all_scene_channels()

    def _stop_all_scene_channels(self) -> None:
        """Stop every playing scene channel and clear tracking dicts."""
        for slot_idx in list(self._active_channels.keys()):
            self._stop_slot(slot_idx)
        self._active_channels.clear()
        self._active_sounds.clear()

    def handle_command(self, action: str, query: str = "") -> None:
        """Route Discord / master-scene commands to named Soundboard scenes."""
        action = action.lower().strip()
        if action == "play_scene" and query.strip():
            q = query.strip().lower()
            for i, sc in enumerate(self._scenes):
                if sc.name.strip().lower() == q:
                    self._current_scene_idx = i
                    if self._scene_list_widget is not None:
                        self._scene_list_widget.setCurrentRow(i)
                    self._refresh_slot_list()
                    self._play_scene()
                    return
            self.status_message.emit(f"Soundboard: no scene named {query!r}")
        elif action == "stop":
            self._stop_scene()

    # ══════════════════════════════════════════════════════════════════════════
    # Scenes tab — persistence
    # ══════════════════════════════════════════════════════════════════════════

    def _save_scenes(self) -> None:
        """Persist all scenes to QSettings as a JSON string."""
        data = [
            {
                "name": scene.name,
                "slots": [
                    {"path": s.path, "volume": s.volume, "loop": s.loop}
                    for s in scene.slots
                ],
            }
            for scene in self._scenes
        ]
        self._settings.setValue("soundboard/scenes", json.dumps(data))

    def _load_scenes(self) -> None:
        """Restore scenes from QSettings."""
        raw = self._settings.value("soundboard/scenes", "", type=str)
        if not raw:
            return
        try:
            data = json.loads(raw)
            self._scenes = []
            for sd in data:
                slots = [SceneSlot(**slot_d) for slot_d in sd.get("slots", [])]
                self._scenes.append(Scene(name=sd["name"], slots=slots))
        except Exception as e:
            self.status_message.emit(f"Failed to load scenes: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Style helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _style_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; font-size: 10px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )

    def _style_small_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {MUTED}; font-size: 9px;"
            f"  border: 1px solid {BORDER}; border-radius: 3px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )

    def _style_loop_btn(self, btn: QPushButton, active: bool) -> None:
        color = ACCENT2 if active else MUTED
        border = ACCENT2 if active else BORDER
        background = PANEL if active else SURFACE
        btn.setStyleSheet(
            f"QPushButton {{ background: {background}; color: {color}; font-size: 9px;"
            f"  border: 1px solid {border}; border-radius: 3px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )
