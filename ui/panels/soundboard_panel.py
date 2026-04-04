"""
Soundboard panel for Project Ceres — GM Assistant UI.

Lets the GM load, organise, and trigger sound effects and ambient tracks
for scene-setting.  Audio playback uses pygame.mixer if available, with a
graceful fallback to Windows winsound for simple .wav files.

Layout
------
  ┌─ 🔊 SOUNDBOARD ──────────────────────────────┐
  │ [📁 Load Folder]  [🗑 Clear]   Vol: [====]   │
  ├──────────────────────────────────────────────│
  │ Ambience                                     │
  │  [🌲 Forest Night ] [🌊 Ocean   ] [🔥 Fire  ]│
  │ Combat                                       │
  │  [⚔ Swords       ] [💥 Explosion] [🏹 Arrow ]│
  │ Stingers                                     │
  │  [🎺 Victory      ] [💀 Defeat  ] [🎲 Roll  ]│
  ├──────────────────────────────────────────────│
  │ Now playing: Forest Night.mp3        [■ Stop]│
  └──────────────────────────────────────────────┘

Audio support
-------------
Install pygame for full MP3/OGG/WAV support:
    pip install pygame
Without it, WAV files still work via winsound (Windows only).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QPushButton, QLabel, QSlider, QFileDialog, QScrollArea,
        QGroupBox, QSizePolicy, QMessageBox,
    )
    from PyQt5.QtCore import Qt, QTimer, QSettings, pyqtSignal as Signal
    from PyQt5.QtGui import QFont
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QPushButton, QLabel, QSlider, QFileDialog, QScrollArea,
        QGroupBox, QSizePolicy, QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer, QSettings, Signal  # type: ignore
    from PySide6.QtGui import QFont  # type: ignore

from ui.theme import ACCENT, MUTED, TEXT, PANEL, SURFACE, SUCCESS, ERROR

# ── Audio backend detection ────────────────────────────────────────────────────
_PYGAME_OK = False
try:
    import pygame
    pygame.mixer.init()
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

_AUDIO_AVAILABLE = _PYGAME_OK or _WINSOUND_OK

# File types we can play
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
if not _PYGAME_OK:
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


def _icon_for_category(name: str) -> str:
    return CATEGORY_ICONS.get(name.lower(), "🔊")


def _stem_label(path: Path, max_len: int = 14) -> str:
    """Short display label from a file stem."""
    stem = path.stem.replace("_", " ").replace("-", " ").title()
    return stem if len(stem) <= max_len else stem[:max_len - 1] + "…"


class SoundButton(QPushButton):
    """A single sound-trigger button carrying its audio path."""

    def __init__(self, path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(_stem_label(path), parent)
        self.audio_path = path
        self.setToolTip(str(path))
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class SoundboardPanel(QDockWidget):
    """
    Dockable soundboard panel.

    Signals:
        status_message(msg) — forwarded to main window status bar
    """

    status_message: Signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("🔊  Soundboard", parent)
        self.setObjectName("SoundboardPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable    |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable  |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._sound_folder: Optional[Path] = None
        self._now_playing: Optional[str] = None
        self._volume: float = 0.8  # 0.0 – 1.0

        self._settings = QSettings("ProjectCeres", "GMAssistant")

        self._build_ui()
        self._show_no_folder_hint()
        self._restore_state()   # auto-reload last folder + volume

        if not _AUDIO_AVAILABLE:
            self._now_playing_label.setText(
                "⚠  No audio backend.  Run: pip install pygame"
            )
            self._now_playing_label.setStyleSheet(f"color: {ERROR};")

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(5)

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

        outer_layout.addLayout(toolbar)

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
        outer_layout.addWidget(self._scroll)

        # ── Now-playing bar ──
        now_row = QHBoxLayout()
        self._now_playing_label = QLabel("— idle —")
        self._now_playing_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        now_row.addWidget(self._now_playing_label, 1)
        outer_layout.addLayout(now_row)

        self.setWidget(outer)

    # ── State persistence ──────────────────────────────────────────────────────

    def _restore_state(self) -> None:
        """Reload the last-used sound folder and volume from QSettings."""
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
                # Remove the "no folder" hint that was just added, then rebuild
                self._clear_layout(self._board_layout)
                self._rebuild_board()
                self.status_message.emit(
                    f"Soundboard: restored {folder_path.name}"
                )
            else:
                # Saved path no longer exists — clear the stale entry
                self._settings.remove("soundboard/folder")

    # ── Loading sounds ─────────────────────────────────────────────────────────

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
        self._clear_layout(self._board_layout)
        self._board_layout.addStretch()
        self._show_no_folder_hint()

    def _rebuild_board(self) -> None:
        """Scan folder and rebuild all category groups + sound buttons."""
        self._stop_all()
        self._clear_layout(self._board_layout)

        if self._sound_folder is None or not self._sound_folder.exists():
            self._show_no_folder_hint()
            return

        # Collect files: group by immediate subfolder name, or "General"
        categories: Dict[str, List[Path]] = {}
        for entry in sorted(self._sound_folder.rglob("*")):
            if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                # Category = direct subfolder of sound_folder, else "General"
                try:
                    rel = entry.relative_to(self._sound_folder)
                    cat = rel.parts[0] if len(rel.parts) > 1 else "General"
                except ValueError:
                    cat = "General"
                categories.setdefault(cat, []).append(entry)

        if not categories:
            hint = QLabel(f"No audio files found.\nSupported: {', '.join(sorted(AUDIO_EXTENSIONS))}")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
            hint.setStyleSheet(f"color: {MUTED};")
            self._board_layout.insertWidget(0, hint)
            self._board_layout.addStretch()
            return

        for cat_name in sorted(categories):
            files = categories[cat_name]
            icon = _icon_for_category(cat_name)
            group = QGroupBox(f"{icon}  {cat_name}")
            group.setStyleSheet(
                f"QGroupBox {{ color: {ACCENT}; border: 1px solid #2a2a4a; "
                f"border-radius: 4px; margin-top: 1.2em; padding: 6px; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; "
                f"padding: 0 4px; color: {ACCENT}; font-weight: bold; }}"
            )
            grid = QGridLayout(group)
            grid.setSpacing(4)

            for i, path in enumerate(sorted(files, key=lambda p: p.stem.lower())):
                btn = SoundButton(path)
                btn.clicked.connect(lambda checked, p=path: self._play(p))
                grid.addWidget(btn, i // BUTTONS_PER_ROW, i % BUTTONS_PER_ROW)

            self._board_layout.addWidget(group)

        self._board_layout.addStretch()

    def _show_no_folder_hint(self) -> None:
        hint = QLabel('Click "📁 Load Folder" to load your sounds.')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        hint.setStyleSheet(f"color: {MUTED}; padding: 20px;")
        self._board_layout.insertWidget(0, hint)

    # ── Playback ───────────────────────────────────────────────────────────────

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
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.play()
            elif _WINSOUND_OK and path.suffix.lower() == ".wav":
                import winsound  # type: ignore
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)

            self._now_playing = path.name
            self._now_playing_label.setText(f"▶  {path.name}")
            self._now_playing_label.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
            self.status_message.emit(f"Playing: {path.name}")
        except Exception as e:
            self._now_playing_label.setText(f"Error: {e}")
            self._now_playing_label.setStyleSheet(f"color: {ERROR}; font-size: 10px;")

    def _stop_all(self) -> None:
        if _PYGAME_OK:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.stop()
            except Exception:
                pass
        self._now_playing = None
        self._now_playing_label.setText("— idle —")
        self._now_playing_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")

    def _on_volume_changed(self, value: int) -> None:
        self._volume = value / 100.0
        self._settings.setValue("soundboard/volume", value)
        if _PYGAME_OK:
            try:
                pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _clear_layout(layout) -> None:
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
