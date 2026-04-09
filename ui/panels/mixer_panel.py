"""
Volume Mixer Panel for Project Ceres — GM Assistant UI.

A central dockable mixer that shows one volume channel per audio-producing
panel, letting the GM control all audio levels from one place.  The mixer
owns no audio itself — it is a pure control layer that reads state from other
panels and writes back via their set_volume() slots.

Architecture
------------
  main_window calls mixer_panel.register_source(name, panel) for each audio
  panel after all panels are created.  The mixer stores references and wires
  signals bidirectionally so its sliders stay in sync with each panel's own
  volume control.

Effective volume formula
------------------------
  effective = round((channel_vol / 100) * (master_vol / 100) * 100)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from pathlib import Path

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QSlider, QScrollArea, QFrame,
        QSizePolicy,
    )
    from PyQt5.QtCore import Qt, QSize, QSettings, pyqtSignal as Signal, pyqtSlot as Slot
    from PyQt5.QtGui import QFont, QIcon, QPixmap
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QSlider, QScrollArea, QFrame,
        QSizePolicy,
    )
    from PySide6.QtCore import Qt, QSize, QSettings, Signal, Slot  # type: ignore
    from PySide6.QtGui import QFont, QIcon, QPixmap  # type: ignore

from ui.theme import ACCENT, BG, BORDER, MUTED, TEXT, PANEL, SURFACE, ERROR

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


@dataclass
class _ChannelState:
    """Holds per-channel UI references and runtime state."""

    name: str
    panel: object          # source panel (duck-typed — must have set_volume)
    slider: QSlider
    value_label: QLabel
    mute_btn: QPushButton
    row_widget: Optional[QWidget] = None
    icon_file: str = ""
    pre_mute_vol: int = 80
    muted: bool = False


class MixerPanel(QDockWidget):
    """
    Dockable volume mixer panel.

    Shows one channel row per registered audio source.  A MASTER row at the
    bottom applies a multiplier to all sources simultaneously.  Channel rows
    are created dynamically by register_source() — no audio sources are
    hardcoded here.

    Signals:
        status_message(str) — forwarded to the main window status bar
    """

    status_message: Signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("🎚  MIXER", parent)
        self.setObjectName("MixerPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._channels: Dict[str, _ChannelState] = {}
        self._settings = QSettings("ProjectCeres", "GMAssistant")

        # Re-entrant loop guard: True while the mixer is pushing a value to a
        # source panel so we ignore the resulting volume_changed echo.
        self._updating_from_source: bool = False

        self._master_muted: bool = False
        self._master_pre_mute: int = 100

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(4)

        # ── Top bar: title + Reset All ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        title_lbl = QLabel("Volume Mixer")
        title_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        top_bar.addWidget(title_lbl, 1)

        reset_btn = QPushButton("Reset All")
        reset_btn.setFixedHeight(22)
        reset_btn.setToolTip("Set all channels to 80, master to 100, unmute all")
        reset_btn.clicked.connect(self._reset_all)
        reset_btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {MUTED}; font-size: 9px;"
            f"  border: 1px solid {BORDER}; border-radius: 3px; padding: 1px 8px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )
        top_bar.addWidget(reset_btn)
        outer_layout.addLayout(top_bar)

        # ── Scroll area for dynamic channel rows ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        scroll.setStyleSheet(f"background: {PANEL}; border: none;")

        self._channels_widget = QWidget()
        self._channels_layout = QVBoxLayout(self._channels_widget)
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.setSpacing(2)
        self._channels_layout.addStretch()

        scroll.setWidget(self._channels_widget)
        outer_layout.addWidget(scroll, 1)

        # ── Visual separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)  # type: ignore[attr-defined]
        sep.setStyleSheet(f"color: {BORDER};")
        outer_layout.addWidget(sep)

        # ── Master row (always at the bottom) ──
        outer_layout.addWidget(self._build_master_row())

        self.setWidget(outer)

    def _build_master_row(self) -> QWidget:
        """Build the always-present MASTER row."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {BORDER};"
            f"  border-radius: 3px; }}"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)

        master_lbl = QLabel("MASTER")
        master_lbl.setFixedWidth(90)
        master_lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 10px;"
        )
        row.addWidget(master_lbl)

        self._master_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._master_slider.setRange(0, 100)
        self._master_slider.setValue(100)
        self._master_slider.setToolTip("Master volume — scales all channel outputs")
        self._master_slider.valueChanged.connect(self._on_master_changed)
        _apply_slider_style(self._master_slider)
        row.addWidget(self._master_slider, 1)

        self._master_val_label = QLabel("100")
        self._master_val_label.setFixedWidth(28)
        self._master_val_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter  # type: ignore[attr-defined]
        )
        self._master_val_label.setStyleSheet(f"color: {TEXT}; font-size: 10px;")
        row.addWidget(self._master_val_label)

        self._master_mute_btn = QPushButton("🔊")
        self._master_mute_btn.setFixedSize(28, 24)
        self._master_mute_btn.setToolTip("Mute / unmute all channels")
        self._master_mute_btn.clicked.connect(self._on_master_mute_clicked)
        _apply_mute_btn_style(self._master_mute_btn, muted=False)
        row.addWidget(self._master_mute_btn)

        return frame

    def _build_channel_row(self, state: _ChannelState) -> QWidget:
        """Build a single source channel row widget from a _ChannelState."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border: 1px solid {BORDER};"
            f"  border-radius: 3px; }}"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)

        if state.icon_file:
            icon_path = _ASSETS / state.icon_file
            if icon_path.exists():
                icon_lbl = QLabel()
                pm = QPixmap(str(icon_path)).scaled(
                    16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon_lbl.setPixmap(pm)
                icon_lbl.setFixedSize(16, 16)
                icon_lbl.setStyleSheet("background: transparent; border: none;")
                row.addWidget(icon_lbl)

        name_lbl = QLabel(state.name)
        name_lbl.setFixedWidth(74 if state.icon_file else 90)
        name_lbl.setStyleSheet(f"color: {TEXT}; font-size: 10px;")
        name_lbl.setToolTip(state.name)
        row.addWidget(name_lbl)

        _apply_slider_style(state.slider)
        row.addWidget(state.slider, 1)

        state.value_label.setFixedWidth(28)
        state.value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter  # type: ignore[attr-defined]
        )
        state.value_label.setStyleSheet(f"color: {TEXT}; font-size: 10px;")
        row.addWidget(state.value_label)

        state.mute_btn.setFixedSize(28, 24)
        _apply_mute_btn_style(state.mute_btn, muted=state.muted)
        row.addWidget(state.mute_btn)

        return frame

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════

    def register_source(self, name: str, panel: object, icon_file: str = "") -> None:
        """
        Register an audio source panel and add its channel row.

        Args:
            name:      Display label for the row (e.g. "Soundboard").
            panel:     Source panel — must expose get_volume() -> int,
                       set_volume(int) slot, and volume_changed Signal(int).
            icon_file: Optional filename in ui/assets/ for a brand icon.
        """
        key = name

        saved_vol = self._settings.value(f"mixer/{key}/volume", 80, type=int)
        saved_muted = self._settings.value(f"mixer/{key}/muted", False, type=bool)

        slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        slider.setRange(0, 100)
        slider.setValue(saved_vol)
        slider.setToolTip(name)

        val_label = QLabel(str(saved_vol))
        mute_btn = QPushButton("🔇" if saved_muted else "🔊")

        state = _ChannelState(
            name=name,
            panel=panel,
            slider=slider,
            value_label=val_label,
            mute_btn=mute_btn,
            icon_file=icon_file,
            pre_mute_vol=saved_vol,
            muted=saved_muted,
        )
        self._channels[key] = state

        slider.valueChanged.connect(
            lambda v, k=key: self._on_channel_slider_moved(k, v)
        )
        mute_btn.clicked.connect(lambda checked, k=key: self._on_mute_clicked(k))

        if hasattr(panel, "volume_changed"):
            panel.volume_changed.connect(  # type: ignore[attr-defined]
                lambda v, k=key: self._on_source_volume_changed(k, v)
            )

        row_widget = self._build_channel_row(state)
        state.row_widget = row_widget
        count = self._channels_layout.count()
        self._channels_layout.insertWidget(count - 1, row_widget)

        # Track panel on/off state — hide mixer row when panel is disabled
        # via the Modules/View menu or closed with the X button.
        # toggleViewAction().toggled only fires for true enable/disable, not tab switches.
        if isinstance(panel, QDockWidget):
            panel.toggleViewAction().toggled.connect(
                lambda checked, k=key: self._on_source_visibility_changed(k, checked)
            )
            if not panel.toggleViewAction().isChecked():
                row_widget.hide()

        self._send_effective_volume(key)

    # ══════════════════════════════════════════════════════════════════════════
    # Channel event handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_channel_slider_moved(self, key: str, value: int) -> None:
        state = self._channels.get(key)
        if state is None:
            return
        state.value_label.setText(str(value))
        if not state.muted:
            state.pre_mute_vol = value
        self._settings.setValue(f"mixer/{key}/volume", value)
        self._send_effective_volume(key)

    def _on_mute_clicked(self, key: str) -> None:
        state = self._channels.get(key)
        if state is None:
            return
        state.muted = not state.muted
        self._settings.setValue(f"mixer/{key}/muted", state.muted)

        if state.muted:
            state.pre_mute_vol = state.slider.value()
        else:
            # Restore the pre-mute slider position without re-triggering the handler.
            state.slider.blockSignals(True)
            state.slider.setValue(state.pre_mute_vol)
            state.value_label.setText(str(state.pre_mute_vol))
            state.slider.blockSignals(False)

        _apply_mute_btn_style(state.mute_btn, state.muted)
        self._send_effective_volume(key)

    def _on_master_changed(self, value: int) -> None:
        self._master_val_label.setText(str(value))
        if not self._master_muted:
            self._master_pre_mute = value
        # Re-compute effective volume for every registered source.
        for key in self._channels:
            self._send_effective_volume(key)

    def _on_master_mute_clicked(self) -> None:
        self._master_muted = not self._master_muted
        if self._master_muted:
            self._master_pre_mute = self._master_slider.value()
        else:
            self._master_slider.blockSignals(True)
            self._master_slider.setValue(self._master_pre_mute)
            self._master_val_label.setText(str(self._master_pre_mute))
            self._master_slider.blockSignals(False)

        _apply_mute_btn_style(self._master_mute_btn, self._master_muted)
        for key in self._channels:
            self._send_effective_volume(key)

    def _on_source_visibility_changed(self, key: str, visible: bool) -> None:
        """Show/hide the mixer row when a source panel is toggled on/off."""
        state = self._channels.get(key)
        if state is None or state.row_widget is None:
            return
        state.row_widget.setVisible(visible)

    def _on_source_volume_changed(self, key: str, value: int) -> None:
        """
        Keep the mixer slider in sync when the source's own UI slider changes.

        This is a display-only sync — we do NOT re-apply effective volume here
        because the source panel has already applied the volume itself.
        """
        if self._updating_from_source:
            return
        state = self._channels.get(key)
        if state is None:
            return
        self._updating_from_source = True
        state.slider.blockSignals(True)
        state.slider.setValue(value)
        state.value_label.setText(str(value))
        state.slider.blockSignals(False)
        self._updating_from_source = False

    # ══════════════════════════════════════════════════════════════════════════
    # Effective volume calculation
    # ══════════════════════════════════════════════════════════════════════════

    def _send_effective_volume(self, key: str) -> None:
        """Compute effective volume and push it to the source panel."""
        state = self._channels.get(key)
        if state is None:
            return

        if state.muted:
            vol = 0
        else:
            raw = state.slider.value()
            master = 0 if self._master_muted else self._master_slider.value()
            vol = round((raw / 100) * (master / 100) * 100)

        if hasattr(state.panel, "set_volume"):
            self._updating_from_source = True
            state.panel.set_volume(vol)  # type: ignore[attr-defined]
            self._updating_from_source = False

    # ══════════════════════════════════════════════════════════════════════════
    # Reset All
    # ══════════════════════════════════════════════════════════════════════════

    def _reset_all(self) -> None:
        """Reset all channels to 80, master to 100, unmute everything."""
        self._master_muted = False
        self._master_pre_mute = 100
        self._master_slider.blockSignals(True)
        self._master_slider.setValue(100)
        self._master_val_label.setText("100")
        self._master_slider.blockSignals(False)
        _apply_mute_btn_style(self._master_mute_btn, muted=False)

        for key, state in self._channels.items():
            state.muted = False
            state.pre_mute_vol = 80
            state.slider.blockSignals(True)
            state.slider.setValue(80)
            state.value_label.setText("80")
            state.slider.blockSignals(False)
            _apply_mute_btn_style(state.mute_btn, muted=False)
            self._settings.setValue(f"mixer/{key}/volume", 80)
            self._settings.setValue(f"mixer/{key}/muted", False)
            self._send_effective_volume(key)

        self.status_message.emit("Mixer: all channels reset to 80")


# ── Module-level style helpers (not class methods — avoids self boilerplate) ──

def _apply_slider_style(slider: QSlider) -> None:
    slider.setStyleSheet(
        f"QSlider::groove:horizontal {{ background: {BORDER}; height: 4px;"
        f"  border-radius: 2px; }}"
        f"QSlider::handle:horizontal {{ background: {ACCENT}; width: 12px; height: 12px;"
        f"  margin: -4px 0; border-radius: 6px; }}"
        f"QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}"
    )


def _apply_mute_btn_style(btn: QPushButton, *, muted: bool) -> None:
    if muted:
        btn.setText("🔇")
        btn.setStyleSheet(
            f"QPushButton {{ background: {ERROR}; color: white; font-size: 11px;"
            f"  border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: #cc3333; }}"
        )
    else:
        btn.setText("🔊")
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {MUTED}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 3px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )
