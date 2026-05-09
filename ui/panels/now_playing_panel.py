"""
Now Playing panel for Project Ceres — GM Assistant UI.

Aggregates live playback state from all registered audio sources into a
single read-at-a-glance view.  Each source row shows:

  [icon]  Source Name  |  Title — Subtitle  |  [progress]  |  [controls]

Controls (pause/resume, prev, next, stop) are enabled only for sources
that declare support via get_np_state()["can_*"] flags.  Volume stays
in the Mixer panel.

Layout
------
  ┌─ NOW PLAYING ────────────────────────────────────────────────────┐
  │ [♫] Spotify  │ Bohemian Rhapsody — Queen   │▓▓▓▓▓░│ ⏮ ▐▐ ⏭ ■  │
  │ [▶] YouTube  │ — not playing —             │       │           ■ │
  │ [~] Tidal    │ — not playing —             │                     │
  │ [♪] Local    │ Misty Mountains — Tolkien   │▓▓░░░░│    ▐▐    ■  │
  │ [🔊]Syrinsc. │ — not connected —           │                     │
  └──────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

try:
    from PyQt5.QtWidgets import (
        QDockWidget,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QProgressBar,
        QScrollArea,
        QSizePolicy,
        QFrame,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal as Signal
    from PyQt5.QtGui import QPixmap
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QProgressBar,
        QScrollArea,
        QSizePolicy,
        QFrame,
    )
    from PySide6.QtCore import Qt, QTimer, Signal  # type: ignore
    from PySide6.QtGui import QPixmap  # type: ignore

from ui.theme import ACCENT, BORDER, MUTED, SURFACE, TEXT
from pantheon.vervactor.workspace import (
    AudioSourceAdapter,
    AudioSourceState,
    PanelAudioSourceAdapter,
)

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_POLL_MS = 2_000  # refresh cadence


# ─────────────────────────────────────────────────────────────────────────────


class _SourceRow:
    """Holds the widgets for one registered audio source."""

    def __init__(
        self,
        name: str,
        adapter: AudioSourceAdapter,
        icon_file: str,
        parent_widget: QWidget,
    ) -> None:
        self.name = name
        self.adapter = adapter

        # ── Build row frame ──────────────────────────────────────────────────
        self.frame = QFrame(parent_widget)
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)  # type: ignore[attr-defined]
        self.frame.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; padding: 2px; }}"
        )

        row = QHBoxLayout(self.frame)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)

        # Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(20, 20)
        icon_path = _ASSETS / icon_file if icon_file else None
        if icon_path and icon_path.exists():
            px = QPixmap(str(icon_path)).scaled(
                20,
                20,
                Qt.AspectRatioMode.KeepAspectRatio,  # type: ignore[attr-defined]
                Qt.TransformationMode.SmoothTransformation,  # type: ignore[attr-defined]
            )
            self.icon_lbl.setPixmap(px)
        else:
            self.icon_lbl.setText("♫")
            self.icon_lbl.setStyleSheet(f"color: {ACCENT};")
        row.addWidget(self.icon_lbl)

        # Source name
        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(72)
        name_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 11px;"
        )
        row.addWidget(name_lbl)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)  # type: ignore[attr-defined]
        sep.setStyleSheet(f"color: {BORDER};")
        row.addWidget(sep)

        # Track info
        self.info_lbl = QLabel("— not playing —")
        self.info_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.info_lbl.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
        self.info_lbl.setWordWrap(False)
        row.addWidget(self.info_lbl)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(80)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {BORDER}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}"
        )
        row.addWidget(self.progress)

        # Control buttons — created; visibility set by update()
        btn_style = (
            "QPushButton { background: transparent; color: %s; "
            "border: none; font-size: 14px; padding: 0 2px; }"
            "QPushButton:hover { color: %s; }"
            "QPushButton:disabled { color: %s; }"
        ) % (TEXT, ACCENT, MUTED)

        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▐▐")  # will flip to ▶ when paused
        self.btn_next = QPushButton("⏭")
        self.btn_stop = QPushButton("■")

        for btn in (self.btn_prev, self.btn_play, self.btn_next, self.btn_stop):
            btn.setFixedWidth(24)
            btn.setStyleSheet(btn_style)
            row.addWidget(btn)

        # Wire control buttons → handle_command
        self.btn_prev.clicked.connect(lambda: self._cmd("previous", ""))
        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_next.clicked.connect(lambda: self._cmd("next", ""))
        self.btn_stop.clicked.connect(lambda: self._cmd("stop", ""))

        # Store last state for play/pause toggle
        self._last_playing = False
        self._last_paused = False

    def _cmd(self, action: str, query: str) -> None:
        """Forward a command to the source adapter."""
        a = action.lower().strip()
        name = self.name

        if name == "Spotify":
            if a == "next":
                a = "skip"
            elif a == "resume":
                a = "play"
            elif a == "stop":
                a = "pause"
        elif name == "Tidal":
            if a == "next":
                a = "skip"
            elif a == "resume":
                a = "play"
            elif a == "previous":
                return
        elif name == "YouTube":
            if a == "resume":
                a = "pause"
            elif a in ("next", "previous"):
                return
        elif name == "Local Music":
            if a == "resume":
                a = "pause"
        elif name == "Syrinscape":
            if a != "stop":
                return

        try:
            if a in ("play", "resume"):
                self.adapter.play()
            elif a == "pause":
                self.adapter.pause()
            elif a == "stop":
                self.adapter.stop()
            elif a in ("next", "skip"):
                self.adapter.next()
            elif a == "previous":
                self.adapter.previous()
        except Exception:
            pass

    def _on_play_clicked(self) -> None:
        if self._last_playing:
            self._cmd("pause", "")
        elif self._last_paused:
            self._cmd("resume", "")
        else:
            self._cmd("resume", "")

    def update(self, state: AudioSourceState) -> None:
        """Refresh all widgets from an AudioSourceState."""
        playing = state.playing
        paused = state.paused
        title = state.title
        subtitle = state.subtitle
        pct = state.progress_pct

        self._last_playing = playing
        self._last_paused = paused

        # Info label
        if title:
            text = f"{title} — {subtitle}" if subtitle else title
        else:
            text = "— not playing —"
        self.info_lbl.setText(text)
        self.info_lbl.setStyleSheet(
            f"color: {TEXT if title else MUTED}; font-size: 11px;"
        )

        # Progress bar
        if pct >= 0 and (playing or paused):
            self.progress.setValue(pct)
            self.progress.setVisible(True)
        else:
            self.progress.setValue(0)
            self.progress.setVisible(False)

        # Play / pause button label
        if paused:
            self.btn_play.setText("▶")
        else:
            self.btn_play.setText("▐▐")

        # Enable / disable controls
        can_pause = state.can_pause
        can_next = state.can_next
        can_prev = state.can_prev
        can_stop = state.can_stop
        active = playing or paused

        self.btn_play.setEnabled(can_pause and active)
        self.btn_next.setEnabled(can_next and active)
        self.btn_prev.setEnabled(can_prev and active)
        self.btn_stop.setEnabled(can_stop and active)


# ─────────────────────────────────────────────────────────────────────────────


class NowPlayingPanel(QDockWidget):
    """
    Dockable aggregator panel — shows live playback state for all audio sources.

    Signals:
        status_message(str) — forwarded to the main-window status bar
    """

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Now Playing", parent)
        self._sources: List[_SourceRow] = []

        self.setObjectName("NowPlayingPanel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable  # type: ignore[attr-defined]
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        self._root_layout = QVBoxLayout(container)
        self._root_layout.setContentsMargins(6, 6, 6, 6)
        self._root_layout.setSpacing(4)

        header = QLabel("Audio Sources")
        header.setStyleSheet(
            f"color: {MUTED}; font-size: 10px; font-weight: bold; "
            f"text-transform: uppercase; letter-spacing: 1px;"
        )
        self._root_layout.addWidget(header)

        # Scroll area holds the source rows (can grow if many sources)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)  # type: ignore[attr-defined]
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff  # type: ignore[attr-defined]
        )

        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch(1)

        scroll.setWidget(self._rows_widget)
        self._root_layout.addWidget(scroll)

        self.setWidget(container)

    # ── Registration ──────────────────────────────────────────────────────────

    def register_source(
        self,
        name: str,
        panel: object,
        icon_file: str = "",
    ) -> None:
        """
        Register an audio source panel.

        The panel must implement get_np_state() -> dict and handle_command(action, query).
        Call this from MainWindow after all source panels are constructed.
        """
        adapter = (
            panel
            if isinstance(panel, AudioSourceAdapter)
            else PanelAudioSourceAdapter(name.lower().replace(" ", "_"), name, panel)
        )
        row = _SourceRow(name, adapter, icon_file, self._rows_widget)
        # Insert before the trailing stretch
        idx = self._rows_layout.count() - 1
        self._rows_layout.insertWidget(idx, row.frame)
        self._sources.append(row)

        # Immediate first paint
        try:
            row.update(adapter.get_state())
        except Exception:
            pass

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        """Called every _POLL_MS ms; refreshes all source rows."""
        for src in self._sources:
            try:
                src.update(src.adapter.get_state())
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop polling before the dock widget is destroyed."""
        self._timer.stop()
        super().closeEvent(event)
