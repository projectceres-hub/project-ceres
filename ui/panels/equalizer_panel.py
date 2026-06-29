"""
Equalizer panel for Project Ceres — GM Assistant UI.

10-band graphic EQ (32 Hz – 16 kHz, ±12 dB per band).
Applies to pygame-backed audio sources (Soundboard, Local Music).
Streaming services (Spotify, Tidal, Syrinscape, YouTube via yt-dlp) are
not routed through this panel.

DSP engine: scipy.signal IIR peaking filters, second-order sections.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QSlider, QComboBox, QCheckBox,
        QSizePolicy, QFrame,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal as Signal
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QSlider, QComboBox, QCheckBox,
        QSizePolicy, QFrame,
    )
    from PySide6.QtCore import Qt, QTimer, Signal  # type: ignore

from ui.theme import ACCENT, ACCENT2, BG, PANEL, SURFACE, TEXT, MUTED, BORDER

# ── Band centre frequencies ────────────────────────────────────────────────────
BAND_FREQS: Tuple[int, ...] = (32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
BAND_LABELS: Tuple[str, ...] = ("32", "64", "125", "250", "500", "1K", "2K", "4K", "8K", "16K")
DB_RANGE = 12      # ± dB
SLIDER_STEPS = 240    # maps to ±12 dB in 0.1 dB steps

# ── Built-in presets ───────────────────────────────────────────────────────────
PRESETS: Dict[str, List[float]] = {
    "Flat":         [0.0] * 10,
    "Bass Boost":   [8.0, 6.0, 4.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "Treble Boost": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 4.0, 6.0, 8.0],
    "Vocal":        [-2.0, -1.0, 1.0, 4.0, 5.0, 5.0, 4.0, 2.0, 0.0, -1.0],
    "Rock":         [4.0, 3.0, 1.0, 0.0, -1.0, 0.0, 1.0, 3.0, 4.0, 4.0],
    "Classical":    [4.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, -1.0, -2.0, -3.0],
    "Gaming":       [3.0, 2.0, 1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0],
}


# ── DSP helper ────────────────────────────────────────────────────────────────

def _make_peaking_sos(
    centre_hz: float,
    gain_db: float,
    q: float,
    sample_rate: int,
) -> Optional[object]:
    """
    Return a 2nd-order peaking-EQ IIR filter as SOS array.
    Returns None if scipy is unavailable or gain is ~0.
    """
    if abs(gain_db) < 0.05:
        return None
    try:
        import numpy as np
        w0 = 2.0 * np.pi * centre_hz / sample_rate
        A = 10 ** (gain_db / 40.0)
        alpha = np.sin(w0) / (2.0 * q)
        b0 = 1.0 + alpha * A
        b1 = -2.0 * np.cos(w0)
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * np.cos(w0)
        a2 = 1.0 - alpha / A
        sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
        return sos
    except ImportError:
        return None


def apply_eq(
    samples: "np.ndarray",
    sample_rate: int,
    bands_db: List[float],
    q: float = 1.41,
) -> "np.ndarray":
    """
    Apply 10-band peaking EQ to a numpy float32 audio array (mono or stereo).

    Args:
        samples:     float32 numpy array, shape (N,) or (N, channels), normalized ~ -1..1
        sample_rate: audio sample rate in Hz
        bands_db:    list of 10 gain values in dB, one per BAND_FREQS
        q:           Q-factor for each filter (default √2 ≈ 1.41)

    Returns:
        Filtered float32 numpy array (same shape).
        If numpy/scipy are unavailable, returns samples unchanged.
    """
    try:
        import numpy as np
        from scipy.signal import sosfilt
    except ImportError:
        return samples

    out = samples.astype(np.float32)
    for freq, gain in zip(BAND_FREQS, bands_db):
        sos = _make_peaking_sos(freq, gain, q, sample_rate)
        if sos is None:
            continue
        if out.ndim == 1:
            out = sosfilt(sos, out).astype(np.float32)
        else:
            for ch in range(out.shape[1]):
                out[:, ch] = sosfilt(sos, out[:, ch]).astype(np.float32)
    return out


# ── Panel ─────────────────────────────────────────────────────────────────────

class EqualizerPanel(QDockWidget):
    """
    10-band graphic equalizer dock panel.

    Signals:
        eq_changed(enabled, bands)  — emitted whenever the user moves a slider,
                                      toggles on/off, or applies a preset.
                                      Connect in MainWindow → source panels.
        status_message(str)         — forwarded to the main-window status bar.
    """

    eq_changed = Signal(bool, list)
    status_message = Signal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__("Equalizer", parent)
        self._config = config

        self.setObjectName("EqualizerPanel")
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

        self._sliders: List[QSlider] = []
        self._db_labels: List[QLabel] = []
        self._build_ui()
        self._load_from_config()
        # After MainWindow wires eq_changed, push persisted state to panels
        QTimer.singleShot(0, self._emit)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Top bar: On/Off + Preset ──────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        self._enable_cb = QCheckBox("EQ On")
        self._enable_cb.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        self._enable_cb.toggled.connect(self._on_toggle)
        top.addWidget(self._enable_cb)

        top.addStretch(1)

        preset_lbl = QLabel("Preset:")
        preset_lbl.setStyleSheet(f"color: {ACCENT2};")
        top.addWidget(preset_lbl)

        self._preset_combo = QComboBox()
        self._preset_combo.addItems(list(PRESETS.keys()) + ["Custom"])
        self._preset_combo.setFixedWidth(110)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        top.addWidget(self._preset_combo)

        reset_btn = QPushButton("Reset")
        reset_btn.setFixedWidth(52)
        reset_btn.clicked.connect(self._on_reset)
        top.addWidget(reset_btn)

        root.addLayout(top)

        # ── Band sliders ──────────────────────────────────────────────────────
        bands_frame = QFrame()
        bands_frame.setStyleSheet(
            f"QFrame {{ background: #020302; border: 1px solid #05060a; "
            f"border-right-color: {BORDER}; border-bottom-color: {BORDER}; "
            f"border-radius: 1px; padding: 4px; }}"
        )
        bands_layout = QHBoxLayout(bands_frame)
        bands_layout.setContentsMargins(4, 4, 4, 4)
        bands_layout.setSpacing(4)

        for i, freq_label in enumerate(BAND_LABELS):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.setAlignment(Qt.AlignHCenter)

            # dB readout
            db_lbl = QLabel("0.0")
            db_lbl.setAlignment(Qt.AlignCenter)
            db_lbl.setStyleSheet(f"color: {ACCENT2}; font-size: 9px;")
            db_lbl.setFixedWidth(32)
            col.addWidget(db_lbl)
            self._db_labels.append(db_lbl)

            # Vertical slider: range 0→SLIDER_STEPS, centre = SLIDER_STEPS//2
            slider = QSlider(Qt.Vertical)
            slider.setRange(0, SLIDER_STEPS)
            slider.setValue(SLIDER_STEPS // 2)
            slider.setFixedHeight(120)
            slider.setFixedWidth(20)
            slider.setProperty("band_index", i)
            slider.valueChanged.connect(self._on_slider_moved)
            col.addWidget(slider, alignment=Qt.AlignHCenter)
            self._sliders.append(slider)

            # Hz label
            hz_lbl = QLabel(freq_label)
            hz_lbl.setAlignment(Qt.AlignCenter)
            hz_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 9px;")
            hz_lbl.setFixedWidth(32)
            col.addWidget(hz_lbl)

            bands_layout.addLayout(col)

        root.addWidget(bands_frame)

        # ── Scope note ────────────────────────────────────────────────────────
        note = QLabel(
            "Applies to: Soundboard · Local Music\n"
            "Not available: Spotify · Tidal · YouTube · Syrinscape"
        )
        note.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        note.setAlignment(Qt.AlignCenter)
        root.addWidget(note)

        self.setWidget(container)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _slider_to_db(self, value: int) -> float:
        """Map slider integer (0 → SLIDER_STEPS) to dB (-12 → +12)."""
        return round((value - SLIDER_STEPS / 2) / (SLIDER_STEPS / 2) * DB_RANGE, 1)

    def _db_to_slider(self, db: float) -> int:
        return int((db / DB_RANGE + 1.0) * SLIDER_STEPS / 2)

    def get_bands(self) -> List[float]:
        return [self._slider_to_db(s.value()) for s in self._sliders]

    def is_enabled(self) -> bool:
        return self._enable_cb.isChecked()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_slider_moved(self, _value: int) -> None:
        idx = self.sender().property("band_index")  # type: ignore[union-attr]
        if idx is None:
            return
        db = self._slider_to_db(self._sliders[idx].value())
        self._db_labels[idx].setText(f"{db:+.1f}" if db != 0 else "0.0")
        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentText("Custom")
        self._preset_combo.blockSignals(False)
        self._emit()

    def _on_toggle(self, _checked: bool) -> None:
        self._emit()

    def _on_preset_changed(self, name: str) -> None:
        if name == "Custom" or name not in PRESETS:
            return
        bands = PRESETS[name]
        for i, (slider, db) in enumerate(zip(self._sliders, bands)):
            slider.blockSignals(True)
            slider.setValue(self._db_to_slider(db))
            self._db_labels[i].setText(f"{db:+.1f}" if db != 0 else "0.0")
            slider.blockSignals(False)
        self._emit()
        self.status_message.emit(f"EQ preset: {name}")

    def _on_reset(self) -> None:
        self._preset_combo.setCurrentText("Flat")

    def _emit(self) -> None:
        """Persist to config and broadcast eq_changed."""
        enabled = self.is_enabled()
        bands = self.get_bands()
        self._config.eq_enabled = enabled
        self._config.eq_bands = bands
        self._config.eq_preset = self._preset_combo.currentText()
        self._config.save_settings()
        self.eq_changed.emit(enabled, bands)

    def _load_from_config(self) -> None:
        """Restore from persisted config on startup."""
        bands = list(getattr(self._config, "eq_bands", [0.0] * 10))
        while len(bands) < 10:
            bands.append(0.0)
        bands = bands[:10]
        preset = str(getattr(self._config, "eq_preset", "Flat"))
        enabled = bool(getattr(self._config, "eq_enabled", False))

        for i, (slider, db) in enumerate(zip(self._sliders, bands)):
            slider.blockSignals(True)
            slider.setValue(self._db_to_slider(db))
            self._db_labels[i].setText(f"{db:+.1f}" if db != 0 else "0.0")
            slider.blockSignals(False)

        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentText(preset if preset in PRESETS else "Custom")
        self._preset_combo.blockSignals(False)

        self._enable_cb.blockSignals(True)
        self._enable_cb.setChecked(enabled)
        self._enable_cb.blockSignals(False)
