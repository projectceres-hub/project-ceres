"""
Local Music panel for Project Ceres — GM Assistant UI.

Plays local audio files (MP3, FLAC, OGG, WAV, M4A) via pygame.mixer.music.
Reads ID3 / Vorbis / FLAC tags via mutagen for rich metadata.

Features
--------
  • Folder selector — recursive scan of any folder for audio files
  • Library tree — Artist → Album → Track (double-click to play)
  • Now Playing — album art, track info, progress bar, transport controls
  • Queue — flat list of tracks in play order with prev/next navigation
  • Scene slots — 8 named slots; assign a track or folder to each (2×4 grid)
  • Discord text commands — !localplay <query>, !localstop, !localpause, !localnext
  • Wake-word: "play [track] locally", "local play [track]", "stop local music"
  • Mixer integration — volume_changed / set_volume / get_volume

Requirements (optional — panel shows an install hint if missing)
------------
    pip install mutagen pygame
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QSlider, QProgressBar,
        QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QGridLayout, QSizePolicy, QMenu, QMessageBox,
        QInputDialog, QFileDialog, QApplication,
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
        QTabWidget, QGridLayout, QSizePolicy, QMenu, QMessageBox,
        QInputDialog, QFileDialog, QApplication,
    )
    from PySide6.QtCore import Qt, QThread, QObject, QTimer, QSize, Signal, Slot  # type: ignore
    from PySide6.QtGui import QPixmap, QIcon, QFont  # type: ignore

from ui.theme import (
    ACCENT, ACCENT2, BG, BORDER, ERROR, MUTED,
    PANEL, SUCCESS, SURFACE, TEXT, WARNING,
)

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    import mutagen
    import mutagen.mp3
    import mutagen.flac
    import mutagen.mp4
    import mutagen.ogg
    import mutagen.id3
    _MUTAGEN_OK = True
except ImportError:
    mutagen = None  # type: ignore[assignment]
    _MUTAGEN_OK = False

try:
    import pygame as _pygame
    _PYGAME_OK = True
except ImportError:
    _pygame = None  # type: ignore[assignment]
    _PYGAME_OK = False

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_EXTS: frozenset[str] = frozenset(
    {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".wma"}
)

ALBUM_ART_SIZE   = 80
PROGRESS_TICK_MS = 1_000    # progress bar update interval (ms)
POLL_TICK_MS     = 2_000    # auto-advance poll interval (ms)

SCENE_LABELS: List[Tuple[str, str]] = [
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
SCENE_CONFIG_PATH = _PROJECT_ROOT / "local_music_scenes.json"

_PLACEHOLDER_ART_CSS = f"background: {SURFACE}; border: 1px solid {BORDER};"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class _TrackInfo:
    """Metadata for a single audio file."""

    path:       Path
    title:      str
    artist:     str
    album:      str
    duration_s: int
    art_bytes:  Optional[bytes] = field(default=None, repr=False)

    @property
    def display_duration(self) -> str:
        """Human-readable mm:ss or h:mm:ss duration string."""
        s = self.duration_s
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"


@dataclass
class _SceneSlot:
    """A named quick-launch scene slot."""

    name:      str          # Display label (e.g. "Combat")
    path:      str = ""     # File or folder path assigned to this slot
    slot_type: str = ""     # "track" | "folder" | ""


# ── Library scanner ────────────────────────────────────────────────────────────

class _LibraryScanner(QThread):
    """
    Recursively scans a folder for audio files and reads tags via mutagen.

    Runs in a background QThread so the UI stays responsive during scanning.

    Signals
    -------
    scan_progress(count, filename)  — emitted every 10 files during scan
    scan_complete(tracks)           — emitted when scan finishes
    """

    scan_progress = Signal(int, str)   # count, current filename
    scan_complete = Signal(list)       # List[_TrackInfo]

    def __init__(self, folder: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._folder = folder

    def run(self) -> None:
        """Walk folder recursively, read tags, emit results."""
        tracks: List[_TrackInfo] = []
        folder_path = Path(self._folder)

        all_files: List[Path] = [
            p for p in folder_path.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        ]
        all_files.sort(key=lambda p: (p.parent.name.lower(), p.name.lower()))

        for idx, file_path in enumerate(all_files):
            if idx % 10 == 0:
                self.scan_progress.emit(idx, file_path.name)

            track = _read_tags(file_path)
            if track is not None:
                tracks.append(track)

        self.scan_complete.emit(tracks)


def _read_tags(path: Path) -> Optional[_TrackInfo]:
    """
    Read ID3 / Vorbis / MP4 tags from an audio file via mutagen.

    Falls back to deriving title/artist/album from the directory structure
    when mutagen is unavailable or the file has no embedded tags.

    Args:
        path: Absolute path to the audio file.

    Returns:
        _TrackInfo on success, None if the file cannot be read at all.
    """
    title      = path.stem
    artist     = "Unknown Artist"
    album      = path.parent.name
    duration_s = 0
    art_bytes: Optional[bytes] = None

    if _MUTAGEN_OK:
        try:
            audio = mutagen.File(path, easy=False)  # type: ignore[attr-defined]
            if audio is None:
                return _TrackInfo(path, title, artist, album, duration_s)

            # Duration
            if hasattr(audio, "info") and hasattr(audio.info, "length"):
                duration_s = int(audio.info.length)

            ext = path.suffix.lower()

            if ext == ".mp3":
                from mutagen.id3 import ID3NoHeaderError  # type: ignore
                tags = audio.tags
                if tags:
                    title  = str(tags.get("TIT2", title))
                    artist = str(tags.get("TPE1", artist))
                    album  = str(tags.get("TALB", album))
                    # Album art — APIC frame
                    for key in tags.keys():
                        if key.startswith("APIC"):
                            art_bytes = tags[key].data
                            break

            elif ext == ".flac":
                if audio.get("title"):
                    title = audio["title"][0]
                if audio.get("artist"):
                    artist = audio["artist"][0]
                if audio.get("album"):
                    album = audio["album"][0]
                if audio.pictures:
                    art_bytes = audio.pictures[0].data

            elif ext in (".m4a", ".aac"):
                tags = audio.tags or {}
                if tags.get("\xa9nam"):
                    title = tags["\xa9nam"][0]
                if tags.get("\xa9ART"):
                    artist = tags["\xa9ART"][0]
                if tags.get("\xa9alb"):
                    album = tags["\xa9alb"][0]
                if tags.get("covr"):
                    art_bytes = bytes(tags["covr"][0])

            else:
                # OGG / Vorbis / Opus — EasyTag style
                easy = mutagen.File(path, easy=True)  # type: ignore[attr-defined]
                if easy:
                    if easy.get("title"):
                        title = easy["title"][0]
                    if easy.get("artist"):
                        artist = easy["artist"][0]
                    if easy.get("album"):
                        album = easy["album"][0]

        except Exception:
            pass  # graceful fallback to filename-derived data

    return _TrackInfo(path, title, artist, album, duration_s, art_bytes)


def _fuzzy_match(query: str, tracks: List[_TrackInfo]) -> Optional[_TrackInfo]:
    """
    Find the best matching track for a voice/text query.

    Scoring: exact title match (100) > title contains (50+) > artist contains (20).

    Args:
        query:  The search string from a voice command or text command.
        tracks: The library to search.

    Returns:
        The best-matching _TrackInfo, or None if no tracks match at all.
    """
    if not tracks:
        return None

    q = query.lower().strip()
    scored: List[Tuple[float, _TrackInfo]] = []

    for track in tracks:
        t = track.title.lower()
        a = track.artist.lower()
        score: float = 0.0

        if t == q:
            score = 100.0
        elif q in t:
            score = 50.0 + (len(q) / max(len(t), 1)) * 30.0
        elif q in a:
            score = 20.0

        if score > 0:
            scored.append((score, track))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


# ── Main panel ─────────────────────────────────────────────────────────────────

class LocalMusicPanel(QDockWidget):
    """
    Dockable local music player panel.

    Scans a user-selected folder for audio files, displays them in a
    tree by Artist → Album → Track, and streams them via pygame.mixer.music.

    Signals
    -------
    status_message(str)    — forwarded to main-window status bar
    volume_changed(int)    — emitted when the volume slider moves (0–100)
    """

    status_message: Signal = Signal(str)
    volume_changed:  Signal = Signal(int)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Local Music", parent)
        self.setObjectName("LocalMusicPanel")
        self.setMinimumWidth(280)

        self._config      = config
        self._run_command = run_command

        # ── Library / playback state ──────────────────────────────────────────
        self._library:      List[_TrackInfo]    = []
        self._queue:        List[_TrackInfo]    = []
        self._queue_pos:    int                 = -1
        self._current:      Optional[_TrackInfo] = None
        self._is_playing:   bool                = False
        self._is_paused:    bool                = False
        self._play_start_s: float               = 0.0   # epoch time when playback started
        self._paused_pos_s: float               = 0.0   # seconds elapsed when paused
        self._scanner:      Optional[_LibraryScanner] = None
        self._volume:       int                 = 80

        # ── Scene slots ────────────────────────────────────────────────────────
        self._scenes: List[_SceneSlot] = [
            _SceneSlot(name=label) for label, _ in SCENE_LABELS
        ]
        self._scene_btns: List[QPushButton] = []
        self._load_scenes()

        # ── Build UI ──────────────────────────────────────────────────────────
        self._build_ui()
        self._init_pygame()

        # ── Timers ────────────────────────────────────────────────────────────
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(PROGRESS_TICK_MS)
        self._progress_timer.timeout.connect(self._on_progress_tick)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_TICK_MS)
        self._poll_timer.timeout.connect(self._on_poll_tick)
        self._poll_timer.start()

    # ── pygame init ────────────────────────────────────────────────────────────

    def _init_pygame(self) -> None:
        """Initialise pygame.mixer if available and not already initialised."""
        if not _PYGAME_OK:
            return
        try:
            if not _pygame.mixer.get_init():
                _pygame.mixer.init()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        """Build the full panel UI."""
        root = QWidget()
        root.setStyleSheet(f"background: {PANEL};")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        if not _PYGAME_OK or not _MUTAGEN_OK:
            self._build_missing_deps_notice(layout)
        else:
            self._tabs = QTabWidget()
            self._tabs.setStyleSheet(f"""
                QTabWidget::pane {{ border: 1px solid {BORDER}; background: {PANEL}; }}
                QTabBar::tab {{
                    background: {SURFACE}; color: {MUTED}; padding: 4px 10px;
                    border: 1px solid {BORDER};
                }}
                QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; }}
            """)
            self._tabs.addTab(self._build_library_tab(),    "📁 Library")
            self._tabs.addTab(self._build_now_playing_tab(), "🎵 Now Playing")
            self._tabs.addTab(self._build_queue_tab(),       "📋 Queue")
            self._tabs.addTab(self._build_scenes_tab(),      "🎬 Scenes")
            layout.addWidget(self._tabs)

        self.setWidget(root)

    def _build_missing_deps_notice(self, layout: QVBoxLayout) -> None:
        """Show an install hint when pygame or mutagen are absent."""
        missing = []
        if not _PYGAME_OK:
            missing.append("pygame")
        if not _MUTAGEN_OK:
            missing.append("mutagen")
        msg = QLabel(
            f"Missing: {', '.join(missing)}\n\n"
            f"pip install {' '.join(missing)}"
        )
        msg.setStyleSheet(f"color: {WARNING}; padding: 12px;")
        msg.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        msg.setWordWrap(True)
        layout.addWidget(msg)

    # ── Library tab ────────────────────────────────────────────────────────────

    def _build_library_tab(self) -> QWidget:
        """Build the library tab: folder picker + search bar + track tree."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        # Folder row
        folder_row = QHBoxLayout()
        self._folder_btn = QPushButton("📁 Open Folder")
        self._folder_btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
            f" padding: 4px 8px; }} QPushButton:hover {{ background: {ACCENT}; color: #000; }}"
        )
        self._folder_btn.clicked.connect(self._open_folder)
        self._folder_label = QLabel("No folder selected")
        self._folder_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._folder_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # type: ignore[attr-defined]
        self._rescan_btn = QPushButton("🔄")
        self._rescan_btn.setFixedWidth(30)
        self._rescan_btn.setToolTip("Rescan folder")
        self._rescan_btn.setStyleSheet(self._folder_btn.styleSheet())
        self._rescan_btn.clicked.connect(self._rescan)
        folder_row.addWidget(self._folder_btn)
        folder_row.addWidget(self._folder_label, 1)
        folder_row.addWidget(self._rescan_btn)
        v.addLayout(folder_row)

        # Search bar
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("🔍 Filter tracks…")
        self._search_bar.setStyleSheet(
            f"background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 3px 6px;"
        )
        self._search_bar.textChanged.connect(self._filter_library)
        v.addWidget(self._search_bar)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Title / Artist", "Album", "Duration"])
        self._tree.header().setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}"
            f"QTreeWidget::item:selected {{ background: {ACCENT}; color: #000; }}"
        )
        self._tree.setColumnWidth(0, 180)
        self._tree.setColumnWidth(1, 110)
        self._tree.setColumnWidth(2, 55)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        v.addWidget(self._tree)

        # Status + play button
        bottom_row = QHBoxLayout()
        self._lib_status = QLabel("No tracks loaded")
        self._lib_status.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        play_sel_btn = QPushButton("▶ Play Selected")
        play_sel_btn.setStyleSheet(self._folder_btn.styleSheet())
        play_sel_btn.clicked.connect(self._play_selected)
        bottom_row.addWidget(self._lib_status, 1)
        bottom_row.addWidget(play_sel_btn)
        v.addLayout(bottom_row)

        return w

    # ── Now Playing tab ────────────────────────────────────────────────────────

    def _build_now_playing_tab(self) -> QWidget:
        """Build the Now Playing tab: art, info, progress, transport, volume."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # Album art
        art_row = QHBoxLayout()
        art_row.addStretch()
        self._art_label = QLabel()
        self._art_label.setFixedSize(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        self._art_label.setStyleSheet(_PLACEHOLDER_ART_CSS)
        self._art_label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self._art_label.setText("🎵")
        art_row.addWidget(self._art_label)
        art_row.addStretch()
        v.addLayout(art_row)

        # Track info
        self._title_label = QLabel("Not playing")
        self._title_label.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; font-weight: bold;"
        )
        self._title_label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self._title_label.setWordWrap(True)
        v.addWidget(self._title_label)

        self._artist_label = QLabel("")
        self._artist_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self._artist_label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        v.addWidget(self._artist_label)

        self._album_label = QLabel("")
        self._album_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._album_label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        v.addWidget(self._album_label)

        # Progress
        prog_row = QHBoxLayout()
        self._elapsed_label = QLabel("0:00")
        self._elapsed_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {SURFACE}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}"
        )
        self._duration_label = QLabel("0:00")
        self._duration_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        prog_row.addWidget(self._elapsed_label)
        prog_row.addWidget(self._progress_bar, 1)
        prog_row.addWidget(self._duration_label)
        v.addLayout(prog_row)

        # Transport controls
        transport_row = QHBoxLayout()
        transport_row.addStretch()
        btn_style = (
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
            f" padding: 6px 12px; font-size: 16px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {ACCENT}; color: #000; }}"
            f"QPushButton:disabled {{ color: {MUTED}; }}"
        )
        self._prev_btn = QPushButton("⏮")
        self._play_pause_btn = QPushButton("▶")
        self._stop_btn = QPushButton("⏹")
        self._next_btn = QPushButton("⏭")
        for btn in (self._prev_btn, self._play_pause_btn, self._stop_btn, self._next_btn):
            btn.setStyleSheet(btn_style)
            btn.setFixedWidth(44)
            transport_row.addWidget(btn)
        transport_row.addStretch()
        self._prev_btn.clicked.connect(self._prev_track)
        self._play_pause_btn.clicked.connect(self._play_pause)
        self._stop_btn.clicked.connect(self._stop)
        self._next_btn.clicked.connect(self._next_track)
        v.addLayout(transport_row)

        # Volume
        vol_row = QHBoxLayout()
        vol_lbl = QLabel("🔊")
        vol_lbl.setStyleSheet(f"color: {MUTED};")
        self._vol_slider = QSlider(Qt.Horizontal)  # type: ignore[attr-defined]
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(self._volume)
        self._vol_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 4px; background: {SURFACE}; }}"
            f"QSlider::handle:horizontal {{ width: 12px; height: 12px; background: {ACCENT};"
            f" border-radius: 6px; margin: -4px 0; }}"
            f"QSlider::sub-page:horizontal {{ background: {ACCENT}; }}"
        )
        self._vol_label = QLabel(f"{self._volume}")
        self._vol_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._vol_label.setFixedWidth(28)
        self._vol_slider.valueChanged.connect(self._on_vol_changed)
        vol_row.addWidget(vol_lbl)
        vol_row.addWidget(self._vol_slider, 1)
        vol_row.addWidget(self._vol_label)
        v.addLayout(vol_row)

        v.addStretch()
        return w

    # ── Queue tab ──────────────────────────────────────────────────────────────

    def _build_queue_tab(self) -> QWidget:
        """Build the Queue tab: ordered list of tracks for current playback."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        btn_style = (
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
            f" padding: 4px 8px; }} QPushButton:hover {{ background: {ACCENT}; color: #000; }}"
        )

        top_row = QHBoxLayout()
        shuffle_btn = QPushButton("🔀 Shuffle")
        shuffle_btn.setStyleSheet(btn_style)
        shuffle_btn.clicked.connect(self._shuffle_queue)
        clear_btn = QPushButton("🗑 Clear")
        clear_btn.setStyleSheet(btn_style)
        clear_btn.clicked.connect(self._clear_queue)
        top_row.addWidget(shuffle_btn)
        top_row.addStretch()
        top_row.addWidget(clear_btn)
        v.addLayout(top_row)

        self._queue_list = QListWidget()
        self._queue_list.setStyleSheet(
            f"QListWidget {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT}; color: #000; }}"
        )
        self._queue_list.itemDoubleClicked.connect(self._on_queue_double_clicked)
        v.addWidget(self._queue_list)

        self._queue_status = QLabel("Queue empty")
        self._queue_status.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        v.addWidget(self._queue_status)

        return w

    # ── Scenes tab ─────────────────────────────────────────────────────────────

    def _build_scenes_tab(self) -> QWidget:
        """Build the Scenes tab: 8 named quick-launch slots in a 2×4 grid."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        info = QLabel("Left-click to play · Right-click to assign/rename/clear")
        info.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        info.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        v.addWidget(info)

        grid = QGridLayout()
        grid.setSpacing(6)

        for idx, (label, _key) in enumerate(SCENE_LABELS):
            btn = QPushButton(label)
            btn.setMinimumHeight(52)
            btn.setCheckable(False)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)  # type: ignore[attr-defined]
            btn.customContextMenuRequested.connect(
                lambda _pos, i=idx: self._on_scene_context(i)
            )
            btn.clicked.connect(lambda _checked, i=idx: self._play_scene(i))
            self._refresh_scene_btn(btn, idx)
            self._scene_btns.append(btn)
            grid.addWidget(btn, idx // 2, idx % 2)

        v.addLayout(grid)
        v.addStretch()
        return w

    # ═══════════════════════════════════════════════════════════════════════════
    # Library — scanning & display
    # ═══════════════════════════════════════════════════════════════════════════

    def _open_folder(self) -> None:
        """Open a folder picker dialog and start scanning the selected folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly,  # type: ignore[attr-defined]
        )
        if folder:
            self._scan_folder(folder)

    def _rescan(self) -> None:
        """Re-scan the currently selected folder."""
        current = self._folder_label.text()
        if current and current != "No folder selected":
            self._scan_folder(current)

    def _scan_folder(self, folder: str) -> None:
        """Start a background scan of *folder*."""
        self._folder_label.setText(folder)
        self._lib_status.setText("Scanning…")
        self._tree.clear()
        self._library.clear()

        if self._scanner and self._scanner.isRunning():
            self._scanner.quit()
            self._scanner.wait()

        self._scanner = _LibraryScanner(folder, self)
        self._scanner.scan_progress.connect(self._on_scan_progress)
        self._scanner.scan_complete.connect(self._on_scan_complete)
        self._scanner.start()

    @Slot(int, str)
    def _on_scan_progress(self, count: int, filename: str) -> None:
        self._lib_status.setText(f"Scanning… {count} found — {filename}")

    @Slot(list)
    def _on_scan_complete(self, tracks: list) -> None:
        """Populate the library tree with scanned tracks."""
        self._library = tracks
        self._queue   = list(tracks)
        self._queue_pos = -1
        self._populate_tree(tracks)
        self._update_queue_list()
        count = len(tracks)
        self._lib_status.setText(f"{count} track{'s' if count != 1 else ''} loaded")
        self.status_message.emit(f"Local Music: {count} tracks loaded")

    def _populate_tree(self, tracks: List[_TrackInfo]) -> None:
        """Build Artist → Album → Track tree from *tracks*."""
        self._tree.clear()
        # Group: artist → album → list of tracks
        grouped: Dict[str, Dict[str, List[_TrackInfo]]] = {}
        for t in tracks:
            grouped.setdefault(t.artist, {}).setdefault(t.album, []).append(t)

        for artist in sorted(grouped.keys(), key=str.lower):
            artist_item = QTreeWidgetItem([artist])
            artist_item.setForeground(0, _qcolor(ACCENT))
            artist_item.setFont(0, _bold_font())
            for album in sorted(grouped[artist].keys(), key=str.lower):
                album_item = QTreeWidgetItem([album])
                album_item.setForeground(0, _qcolor(TEXT))
                for track in grouped[artist][album]:
                    track_item = QTreeWidgetItem(
                        [track.title, track.album, track.display_duration]
                    )
                    track_item.setForeground(0, _qcolor(TEXT))
                    track_item.setForeground(1, _qcolor(MUTED))
                    track_item.setForeground(2, _qcolor(MUTED))
                    track_item.setData(0, Qt.UserRole, track)  # type: ignore[attr-defined]
                    album_item.addChild(track_item)
                artist_item.addChild(album_item)
            self._tree.addTopLevelItem(artist_item)

    def _filter_library(self, text: str) -> None:
        """Show/hide tree items based on the search bar text."""
        q = text.lower().strip()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):         # artist
            artist_item = root.child(i)
            artist_visible = False
            for j in range(artist_item.childCount()):  # album
                album_item = artist_item.child(j)
                album_visible = False
                for k in range(album_item.childCount()):  # track
                    track_item = album_item.child(k)
                    track: Optional[_TrackInfo] = track_item.data(0, Qt.UserRole)  # type: ignore[attr-defined]
                    visible = (
                        not q or
                        (track and (
                            q in track.title.lower() or
                            q in track.artist.lower() or
                            q in track.album.lower()
                        ))
                    )
                    track_item.setHidden(not visible)
                    if visible:
                        album_visible = True
                album_item.setHidden(not album_visible)
                if album_visible:
                    artist_visible = True
            artist_item.setHidden(not artist_visible)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        """Play a track when its tree row is double-clicked."""
        track: Optional[_TrackInfo] = item.data(0, Qt.UserRole)  # type: ignore[attr-defined]
        if track:
            self._start_from_track(track)

    def _play_selected(self) -> None:
        """Play the currently selected tree item if it is a track."""
        selected = self._tree.currentItem()
        if selected:
            self._on_tree_double_clicked(selected, 0)

    # ═══════════════════════════════════════════════════════════════════════════
    # Queue
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_from_track(self, track: _TrackInfo) -> None:
        """Set the queue to the library order starting from *track*, then play."""
        if track in self._library:
            idx = self._library.index(track)
        else:
            idx = 0
        # Queue is the full library starting from this track, wrapping around
        self._queue     = self._library[idx:] + self._library[:idx]
        self._queue_pos = 0
        self._play_track(self._queue[0])
        self._update_queue_list()

    def _update_queue_list(self) -> None:
        """Refresh the Queue tab list widget."""
        self._queue_list.clear()
        for i, t in enumerate(self._queue):
            marker = "▶  " if i == self._queue_pos else "   "
            item = QListWidgetItem(f"{marker}{t.title}  —  {t.artist}")
            item.setForeground(_qcolor(ACCENT if i == self._queue_pos else TEXT))
            item.setData(Qt.UserRole, i)  # type: ignore[attr-defined]
            self._queue_list.addItem(item)
        total = len(self._queue)
        pos   = self._queue_pos + 1 if self._queue_pos >= 0 else 0
        self._queue_status.setText(
            f"Track {pos} of {total}" if total else "Queue empty"
        )

    def _on_queue_double_clicked(self, item: QListWidgetItem) -> None:
        """Jump to and play the double-clicked queue entry."""
        idx: int = item.data(Qt.UserRole)  # type: ignore[attr-defined]
        if 0 <= idx < len(self._queue):
            self._queue_pos = idx
            self._play_track(self._queue[idx])
            self._update_queue_list()

    def _shuffle_queue(self) -> None:
        """Shuffle the play queue (keeps current position at the front)."""
        import random
        if not self._queue:
            return
        current = self._queue[self._queue_pos] if self._queue_pos >= 0 else None
        random.shuffle(self._queue)
        if current and current in self._queue:
            self._queue.remove(current)
            self._queue.insert(0, current)
            self._queue_pos = 0
        self._update_queue_list()
        self.status_message.emit("Local Music: queue shuffled")

    def _clear_queue(self) -> None:
        """Clear the queue and stop playback."""
        self._stop()
        self._queue     = []
        self._queue_pos = -1
        self._update_queue_list()

    # ═══════════════════════════════════════════════════════════════════════════
    # Playback
    # ═══════════════════════════════════════════════════════════════════════════

    def _play_track(self, track: _TrackInfo) -> None:
        """Start playing *track* via pygame.mixer.music."""
        if not _PYGAME_OK:
            self.status_message.emit("pygame not installed — cannot play audio")
            return
        try:
            if not _pygame.mixer.get_init():
                _pygame.mixer.init()
            _pygame.mixer.music.load(str(track.path))
            _pygame.mixer.music.set_volume(self._volume / 100.0)
            _pygame.mixer.music.play()
        except Exception as exc:
            self.status_message.emit(f"Local Music: playback error — {exc}")
            return

        import time
        self._current       = track
        self._is_playing    = True
        self._is_paused     = False
        self._play_start_s  = time.time()
        self._paused_pos_s  = 0.0

        self._update_now_playing()
        self._update_queue_list()
        self._play_pause_btn.setText("⏸")
        self._progress_timer.start()
        self.status_message.emit(f"Local Music: {track.title} — {track.artist}")

    def _play_pause(self) -> None:
        """Toggle play/pause for the current track."""
        if not _PYGAME_OK:
            return
        if not self._is_playing and not self._is_paused:
            # Nothing loaded — play first in queue
            if self._queue:
                self._queue_pos = max(self._queue_pos, 0)
                self._play_track(self._queue[self._queue_pos])
            return

        import time
        if self._is_paused:
            _pygame.mixer.music.unpause()
            self._is_paused    = False
            self._is_playing   = True
            # Adjust start time to account for the pause gap
            self._play_start_s = time.time() - self._paused_pos_s
            self._play_pause_btn.setText("⏸")
            self._progress_timer.start()
        else:
            _pygame.mixer.music.pause()
            self._paused_pos_s = time.time() - self._play_start_s
            self._is_paused    = True
            self._is_playing   = False
            self._play_pause_btn.setText("▶")
            self._progress_timer.stop()

    def _stop(self) -> None:
        """Stop playback and reset the progress display."""
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.stop()
            except Exception:
                pass
        self._is_playing  = False
        self._is_paused   = False
        self._play_pause_btn.setText("▶")
        self._progress_bar.setValue(0)
        self._elapsed_label.setText("0:00")
        self._progress_timer.stop()
        self.status_message.emit("Local Music: stopped")

    def _next_track(self) -> None:
        """Advance to the next track in the queue."""
        if not self._queue:
            return
        self._queue_pos = (self._queue_pos + 1) % len(self._queue)
        self._play_track(self._queue[self._queue_pos])

    def _prev_track(self) -> None:
        """Go back to the previous track in the queue."""
        if not self._queue:
            return
        self._queue_pos = (self._queue_pos - 1) % len(self._queue)
        self._play_track(self._queue[self._queue_pos])

    def _play_by_search(self, query: str) -> None:
        """Find the best matching track in the library and play it.

        Args:
            query: Search string from a voice or text command.
        """
        match = _fuzzy_match(query, self._library)
        if match:
            self._start_from_track(match)
            self._tabs.setCurrentIndex(1)  # switch to Now Playing
        else:
            self.status_message.emit(f"Local Music: no match for '{query}'")

    # ═══════════════════════════════════════════════════════════════════════════
    # Now Playing display
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_now_playing(self) -> None:
        """Refresh the Now Playing tab labels and album art."""
        if not self._current:
            return
        t = self._current
        self._title_label.setText(t.title)
        self._artist_label.setText(t.artist)
        self._album_label.setText(t.album)
        self._duration_label.setText(t.display_duration)
        self._progress_bar.setValue(0)
        self._elapsed_label.setText("0:00")

        # Album art
        if t.art_bytes:
            pix = QPixmap()
            pix.loadFromData(t.art_bytes)
            if not pix.isNull():
                pix = pix.scaled(
                    ALBUM_ART_SIZE, ALBUM_ART_SIZE,
                    Qt.KeepAspectRatio,           # type: ignore[attr-defined]
                    Qt.SmoothTransformation,   # type: ignore[attr-defined]
                )
                self._art_label.setPixmap(pix)
                self._art_label.setText("")
                return

        # Placeholder
        self._art_label.clear()
        self._art_label.setText("🎵")
        self._art_label.setStyleSheet(_PLACEHOLDER_ART_CSS)

    @Slot()
    def _on_progress_tick(self) -> None:
        """Update the progress bar every second while playing."""
        if not self._is_playing or not self._current:
            return
        import time
        elapsed = int(time.time() - self._play_start_s)
        total   = self._current.duration_s

        h, rem = divmod(elapsed, 3600)
        m, s   = divmod(rem, 60)
        self._elapsed_label.setText(
            f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        )
        if total > 0:
            self._progress_bar.setValue(min(100, int(elapsed / total * 100)))

    @Slot()
    def _on_poll_tick(self) -> None:
        """Poll pygame to auto-advance to the next track when one ends."""
        if not _PYGAME_OK:
            return
        if self._is_playing and not self._is_paused:
            try:
                if not _pygame.mixer.music.get_busy():
                    self._next_track()
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # Scenes
    # ═══════════════════════════════════════════════════════════════════════════

    def _play_scene(self, idx: int) -> None:
        """Play the track or folder assigned to scene slot *idx*."""
        slot = self._scenes[idx]
        if not slot.path:
            self.status_message.emit(
                f"Local Music: scene '{slot.name}' has nothing assigned"
            )
            return
        p = Path(slot.path)
        if slot.slot_type == "folder" and p.is_dir():
            # Scan and play the folder inline (non-blocking — use scanned library if same path)
            tracks = [
                _read_tags(f)
                for f in sorted(p.rglob("*"))
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
            ]
            tracks = [t for t in tracks if t is not None]
            if tracks:
                self._queue     = tracks  # type: ignore[assignment]
                self._queue_pos = 0
                self._play_track(self._queue[0])
                self._update_queue_list()
        elif slot.slot_type == "track" and p.is_file():
            track = _read_tags(p)
            if track:
                self._queue     = [track]
                self._queue_pos = 0
                self._play_track(track)
                self._update_queue_list()

    def _on_scene_context(self, idx: int) -> None:
        """Show right-click context menu for a scene slot."""
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}"
            f"QMenu::item:selected {{ background: {ACCENT}; color: #000; }}"
        )
        menu.addAction("🎵 Assign Track…").triggered.connect(
            lambda: self._assign_track(idx)
        )
        menu.addAction("📁 Assign Folder…").triggered.connect(
            lambda: self._assign_folder(idx)
        )
        menu.addSeparator()
        menu.addAction("✎ Rename Slot…").triggered.connect(
            lambda: self._rename_slot(idx)
        )
        menu.addAction("✕ Clear").triggered.connect(
            lambda: self._clear_slot(idx)
        )
        menu.exec(self._scene_btns[idx].mapToGlobal(
            self._scene_btns[idx].rect().center()
        ))

    def _assign_track(self, idx: int) -> None:
        """Open a file picker and assign the selected track to slot *idx*."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio File", str(Path.home()),
            "Audio Files (*.mp3 *.flac *.ogg *.wav *.m4a *.aac *.opus)"
        )
        if path:
            self._scenes[idx].path      = path
            self._scenes[idx].slot_type = "track"
            self._refresh_scene_btn(self._scene_btns[idx], idx)
            self._save_scenes()

    def _assign_folder(self, idx: int) -> None:
        """Open a folder picker and assign it to slot *idx*."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder", str(Path.home()),
            QFileDialog.ShowDirsOnly,  # type: ignore[attr-defined]
        )
        if folder:
            self._scenes[idx].path      = folder
            self._scenes[idx].slot_type = "folder"
            self._refresh_scene_btn(self._scene_btns[idx], idx)
            self._save_scenes()

    def _rename_slot(self, idx: int) -> None:
        """Prompt the user for a new name for scene slot *idx*."""
        name, ok = QInputDialog.getText(
            self, "Rename Scene", "Slot name:", text=self._scenes[idx].name
        )
        if ok and name.strip():
            self._scenes[idx].name = name.strip()
            self._refresh_scene_btn(self._scene_btns[idx], idx)
            self._save_scenes()

    def _clear_slot(self, idx: int) -> None:
        """Remove the assignment from scene slot *idx* and reset its label."""
        self._scenes[idx].path      = ""
        self._scenes[idx].slot_type = ""
        self._refresh_scene_btn(self._scene_btns[idx], idx)
        self._save_scenes()

    def _refresh_scene_btn(self, btn: QPushButton, idx: int) -> None:
        """Update a scene button's text and style to reflect its current state."""
        slot = self._scenes[idx]
        assigned = bool(slot.path)
        sub = ""
        if slot.path:
            p = Path(slot.path)
            sub = f"\n{p.name[:22]}{'…' if len(p.name) > 22 else ''}"
        btn.setText(f"{slot.name}{sub}")
        btn.setStyleSheet(
            f"QPushButton {{ background: {'#2a3a2a' if assigned else SURFACE};"
            f" color: {TEXT}; border: 1px solid {ACCENT if assigned else BORDER};"
            f" padding: 4px; font-size: 11px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {ACCENT}; color: #000; }}"
        )

    def _save_scenes(self) -> None:
        """Persist scene slots to *local_music_scenes.json*."""
        data = [
            {"name": s.name, "path": s.path, "type": s.slot_type}
            for s in self._scenes
        ]
        try:
            SCENE_CONFIG_PATH.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load_scenes(self) -> None:
        """Load scene slots from *local_music_scenes.json* if it exists."""
        if not SCENE_CONFIG_PATH.exists():
            return
        try:
            data = json.loads(SCENE_CONFIG_PATH.read_text())
            for i, entry in enumerate(data[:len(self._scenes)]):
                self._scenes[i].name      = entry.get("name", self._scenes[i].name)
                self._scenes[i].path      = entry.get("path", "")
                self._scenes[i].slot_type = entry.get("type", "")
        except (OSError, json.JSONDecodeError):
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # Volume — Mixer interface
    # ═══════════════════════════════════════════════════════════════════════════

    def get_volume(self) -> int:
        """Return the current volume level (0–100).

        Returns:
            Integer volume in the range 0–100.
        """
        return self._volume

    @Slot(int)
    def set_volume(self, value: int) -> None:
        """Set the volume to *value* (0–100) and update pygame.

        Args:
            value: New volume level clamped to 0–100.
        """
        value = max(0, min(100, value))
        self._volume = value
        if hasattr(self, "_vol_slider"):
            self._vol_slider.blockSignals(True)
            self._vol_slider.setValue(value)
            self._vol_slider.blockSignals(False)
        if hasattr(self, "_vol_label"):
            self._vol_label.setText(str(value))
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.set_volume(value / 100.0)
            except Exception:
                pass

    def _on_vol_changed(self, value: int) -> None:
        """Handle the panel's own volume slider movement."""
        self._volume = value
        self._vol_label.setText(str(value))
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.set_volume(value / 100.0)
            except Exception:
                pass
        self.volume_changed.emit(value)

    # ═══════════════════════════════════════════════════════════════════════════
    # Discord voice command handler
    # ═══════════════════════════════════════════════════════════════════════════

    @Slot(str, str)
    def handle_command(self, action: str, query: str) -> None:
        """
        Handle a voice or text command forwarded from the Discord panel.

        Supported actions (all case-insensitive)
        -----------------------------------------
        play     — search library for *query* and play the best match;
                   if *query* is empty, resume/toggle playback
        pause    — pause / resume
        stop     — stop playback
        next     — advance to next track in queue
        search   — alias for play

        Args:
            action: The command verb (play/pause/stop/next/search).
            query:  Optional search string for play/search actions.
        """
        action = action.lower().strip()
        if action in ("play", "search"):
            if query.strip():
                self._play_by_search(query.strip())
            else:
                self._play_pause()
        elif action == "pause":
            self._play_pause()
        elif action == "stop":
            self._stop()
        elif action == "next":
            self._next_track()

    # ═══════════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop playback and timers on close to avoid dangling threads."""
        self._progress_timer.stop()
        self._poll_timer.stop()
        if _PYGAME_OK:
            try:
                _pygame.mixer.music.stop()
            except Exception:
                pass
        if self._scanner and self._scanner.isRunning():
            self._scanner.quit()
            self._scanner.wait()
        super().closeEvent(event)


# ── Qt helpers ─────────────────────────────────────────────────────────────────

def _qcolor(hex_str: str):
    """Return a QColor from a hex string — used for tree item foregrounds."""
    try:
        from PyQt5.QtGui import QColor
    except ImportError:
        from PySide6.QtGui import QColor  # type: ignore
    return QColor(hex_str)


def _bold_font() -> QFont:
    """Return a bold QFont for tree artist rows."""
    f = QFont()
    f.setBold(True)
    return f
