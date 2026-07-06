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
        QSlider,
        QFrame,
        QStyle,
        QStyleOption,
    )
    from PyQt5.QtCore import Qt, QTimer, QRect, pyqtSignal as Signal
    from PyQt5.QtGui import QPainter, QPixmap
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
        QSlider,
        QFrame,
        QStyle,
        QStyleOption,
    )
    from PySide6.QtCore import Qt, QTimer, QRect, Signal  # type: ignore
    from PySide6.QtGui import QPainter, QPixmap  # type: ignore

from ui.theme import ACCENT, ACCENT2, CHROME_LITE, CHROME_MID, SHADOW
from pantheon.vervactor.workspace import (
    AudioSourceAdapter,
    AudioSourceState,
    PanelAudioSourceAdapter,
)

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_POLL_MS = 2_000  # refresh cadence


# ─────────────────────────────────────────────────────────────────────────────


class _MarqueeLabel(QLabel):
    """
    LCD label that bounce-scrolls text too wide for the well, like classic
    Winamp: hold, crawl left until the tail is visible, hold, crawl back.
    Styling (colors, well, bevel) still comes from the lcd/lcd-dim QSS classes.
    """

    _TICK_MS = 50       # timer cadence
    _STEP_PX = 1        # pixels per tick (≈20 px/s)
    _HOLD_TICKS = 24    # ≈1.2 s pause at each end
    _PAD_X = 6          # matches lcd QSS horizontal padding

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self._offset = 0
        self._phase = "hold_front"
        self._hold = self._HOLD_TICKS
        self._timer = QTimer(self)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)
        # Long titles must not force the dock wider — we scroll instead.
        self.setMinimumWidth(60)

    # ── Text / geometry ────────────────────────────────────────────────────

    def setText(self, text: str) -> None:  # type: ignore[override]
        if text == self._full_text:
            return  # same track polled again — don't restart the crawl
        self._full_text = text
        self._reset_scroll()
        super().setText(text)
        self._update_timer()

    def _text_width(self) -> int:
        fm = self.fontMetrics()
        try:
            return fm.horizontalAdvance(self._full_text)
        except AttributeError:  # very old Qt bindings
            return fm.width(self._full_text)  # type: ignore[attr-defined]

    def _max_offset(self) -> int:
        avail = max(0, self.width() - 2 * self._PAD_X)
        return max(0, self._text_width() - avail)

    def _reset_scroll(self) -> None:
        self._offset = 0
        self._phase = "hold_front"
        self._hold = self._HOLD_TICKS

    def _update_timer(self) -> None:
        if self._max_offset() > 0:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            if self._offset:
                self._offset = 0
                self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._reset_scroll()
        self._update_timer()

    # ── Animation ──────────────────────────────────────────────────────────

    def _tick(self) -> None:
        max_off = self._max_offset()
        if max_off <= 0:
            self._update_timer()
            return
        if self._phase in ("hold_front", "hold_back"):
            self._hold -= 1
            if self._hold <= 0:
                self._phase = "forward" if self._phase == "hold_front" else "back"
            return
        if self._phase == "forward":
            self._offset = min(max_off, self._offset + self._STEP_PX)
            if self._offset >= max_off:
                self._phase = "hold_back"
                self._hold = self._HOLD_TICKS
        else:  # back
            self._offset = max(0, self._offset - self._STEP_PX)
            if self._offset <= 0:
                self._phase = "hold_front"
                self._hold = self._HOLD_TICKS
        self.update()

    # ── Painting ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        if self._max_offset() <= 0:
            super().paintEvent(event)  # fits — let QLabel/QSS paint normally
            return
        painter = QPainter(self)
        # Draw the QSS background/bevel of the lcd well first
        opt = QStyleOption()
        opt.initFrom(self)
        self.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_Widget, opt, painter, self  # type: ignore[attr-defined]
        )
        clip = self.rect().adjusted(self._PAD_X, 0, -self._PAD_X, 0)
        painter.setClipRect(clip)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        text_rect = QRect(
            clip.x() - self._offset,
            clip.y(),
            self._text_width() + 2,
            clip.height(),
        )
        painter.drawText(
            text_rect,
            int(
                Qt.AlignmentFlag.AlignVCenter  # type: ignore[attr-defined]
                | Qt.AlignmentFlag.AlignLeft
            ),
            self._full_text,
        )


# ─────────────────────────────────────────────────────────────────────────────


class _SourceRow:
    """Holds the widgets for one registered audio source."""

    def __init__(
        self,
        name: str,
        adapter: AudioSourceAdapter,
        icon_file: str,
        parent_widget: QWidget,
        source_panel: object = None,
    ) -> None:
        self.name = name
        self.adapter = adapter
        self._source_panel = source_panel

        # ── Build row frame — beveled Winamp chrome ─────────────────────────
        self.frame = QFrame(parent_widget)
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)  # type: ignore[attr-defined]
        self.frame.setProperty("class", "winamp-panel-frame")

        outer = QVBoxLayout(self.frame)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(3)

        # Row 1: icon | name | ridge | LCD track info
        row = QHBoxLayout()
        row.setSpacing(6)
        outer.addLayout(row)

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

        # Source name — gold, uppercase, like dock/section titles
        name_lbl = QLabel(name.upper())
        name_lbl.setFixedWidth(76)
        name_lbl.setStyleSheet(
            f"color: {ACCENT2}; font-weight: bold; font-size: 10px; "
            f"letter-spacing: 1px; background: transparent;"
        )
        row.addWidget(name_lbl)

        # Chrome ridge separator
        sep = QFrame()
        sep.setFixedWidth(2)
        sep.setStyleSheet(
            f"background: {CHROME_MID}; border-left: 1px solid {SHADOW}; "
            f"border-right: 1px solid {CHROME_LITE};"
        )
        row.addWidget(sep)

        # Track info — black LCD well, green readout, Winamp bounce-scroll
        self.info_lbl = _MarqueeLabel("— not playing —")
        self.info_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.info_lbl.setProperty("class", "lcd-dim")
        self.info_lbl.setWordWrap(False)
        self._lcd_active = False
        row.addWidget(self.info_lbl)

        # Row 2: transport buttons | seek bar
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(2)
        outer.addLayout(ctrl_row)

        # Control buttons — beveled Winamp media controls
        self.btn_prev = QPushButton("|<")
        self.btn_play = QPushButton("||")  # shows ▶ while paused
        self.btn_next = QPushButton(">|")
        self.btn_stop = QPushButton("■")

        self.btn_play.setProperty("class", "media-control-primary")
        self.btn_play.setFixedSize(30, 20)
        for btn in (self.btn_prev, self.btn_next, self.btn_stop):
            btn.setProperty("class", "media-control")
            btn.setFixedSize(26, 20)
        for btn in (self.btn_prev, self.btn_play, self.btn_next, self.btn_stop):
            ctrl_row.addWidget(btn)

        ctrl_row.addSpacing(6)

        # Progress bar — themed globally (black well, green→gold chunk)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        ctrl_row.addWidget(self.progress, 1)

        # Row 3: volume — gold Winamp slider, wired to the panel's set_volume
        vol_row = QHBoxLayout()
        vol_row.setSpacing(6)
        outer.addLayout(vol_row)

        vol_lbl = QLabel("VOL")
        vol_lbl.setStyleSheet(
            f"color: {ACCENT2}; font-size: 8px; font-weight: bold; "
            f"background: transparent;"
        )
        vol_row.addWidget(vol_lbl)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setToolTip(f"{name} volume")
        supports_vol = hasattr(adapter, "set_volume")
        init_vol = adapter.get_volume() if hasattr(adapter, "get_volume") else -1
        self.vol_slider.setValue(init_vol if init_vol >= 0 else 100)
        self.vol_slider.setEnabled(supports_vol and init_vol >= 0)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self.vol_slider, 1)

        # Start in the idle state; update() re-enables from real state
        for btn in (self.btn_prev, self.btn_play, self.btn_next, self.btn_stop):
            btn.setEnabled(False)

        # Wire control buttons → handle_command
        self.btn_prev.clicked.connect(lambda: self._cmd("previous", ""))
        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_next.clicked.connect(lambda: self._cmd("next", ""))
        self.btn_stop.clicked.connect(lambda: self._cmd("stop", ""))

        # Store last state for play/pause toggle
        self._last_playing = False
        self._last_paused = False
        self._vol_syncing = False

    def source_on(self) -> bool:
        """True when the source's panel is turned on (View/Modules menu)."""
        p = self._source_panel
        if p is None:
            return True
        try:
            if hasattr(p, "toggleViewAction"):
                return bool(p.toggleViewAction().isChecked())
            if hasattr(p, "isHidden"):
                return not p.isHidden()
        except Exception:
            pass
        return True

    def _on_volume_changed(self, value: int) -> None:
        """User moved the row's volume slider → forward to the panel."""
        if self._vol_syncing:
            return
        if hasattr(self.adapter, "set_volume"):
            try:
                self.adapter.set_volume(int(value))
            except Exception:
                pass

    def _sync_volume(self) -> None:
        """Pull the panel's volume into the slider (poll), without echoing back."""
        if self.vol_slider.isSliderDown():
            return  # user is dragging
        if not hasattr(self.adapter, "get_volume"):
            return
        try:
            vol = self.adapter.get_volume()
        except Exception:
            return
        if vol < 0:
            self.vol_slider.setEnabled(False)
            return
        if not self.vol_slider.isEnabled():
            self.vol_slider.setEnabled(True)
        if vol != self.vol_slider.value():
            self._vol_syncing = True
            try:
                self.vol_slider.setValue(vol)
            finally:
                self._vol_syncing = False

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

        # Info label — bright LCD when active, dim green when idle
        if title:
            text = f"{title} — {subtitle}" if subtitle else title
        else:
            text = "— not playing —"
        self.info_lbl.setText(text)
        if bool(title) != self._lcd_active:
            self._lcd_active = bool(title)
            self.info_lbl.setProperty(
                "class", "lcd" if self._lcd_active else "lcd-dim"
            )
            style = self.info_lbl.style()
            style.unpolish(self.info_lbl)
            style.polish(self.info_lbl)

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
            self.btn_play.setText("||")

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

        # Volume slider follows the panel's current volume
        self._sync_volume()


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

        header = QLabel("AUDIO SOURCES")
        header.setProperty("class", "section-header")
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
        row = _SourceRow(
            name, adapter, icon_file, self._rows_widget, source_panel=panel
        )
        # Insert before the trailing stretch
        idx = self._rows_layout.count() - 1
        self._rows_layout.insertWidget(idx, row.frame)
        self._sources.append(row)

        # Only show rows for panels that are turned on; follow the
        # View/Modules-menu toggle live, with the poll as a fallback.
        row.frame.setVisible(row.source_on())
        if hasattr(panel, "toggleViewAction"):
            try:
                panel.toggleViewAction().toggled.connect(  # type: ignore[attr-defined]
                    lambda on, r=row: r.frame.setVisible(bool(on))
                )
            except Exception:
                pass

        # Immediate first paint
        try:
            row.update(adapter.get_state())
        except Exception:
            pass

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        """Called every _POLL_MS ms; refreshes all visible source rows."""
        for src in self._sources:
            on = src.source_on()
            if src.frame.isHidden() == on:
                src.frame.setVisible(on)
            if not on:
                continue
            try:
                src.update(src.adapter.get_state())
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop the poll timer before the dock widget is destroyed."""
        self._timer.stop()
        super().closeEvent(event)
