"""
Audio visualiser panel for Project Ceres — GM Assistant UI.

20-bar spectrum display driven by numpy FFT on pygame mixer output.
"""

from __future__ import annotations

import time
from typing import Optional

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QComboBox, QLabel, QSizePolicy,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal as Signal
    from PyQt5.QtGui import QPainter, QColor, QBrush
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QComboBox, QLabel, QSizePolicy,
    )
    from PySide6.QtCore import Qt, QThread, Signal  # type: ignore
    from PySide6.QtGui import QPainter, QColor, QBrush  # type: ignore

from ui.theme import ACCENT, BG, PANEL, SURFACE, TEXT, MUTED, BORDER

_THEMES: dict[str, list[str]] = {
    "Classic Green":  ["#00ff41", "#00cc33", "#009922"],
    "Winamp Blue":    ["#4fc3f7", "#0288d1", "#01579b"],
    "Fire":           ["#ff6f00", "#e53935", "#b71c1c"],
    "Purple Haze":    ["#ce93d8", "#9c27b0", "#6a1b9a"],
    "Monochrome":     ["#e0e0e0", "#9e9e9e", "#424242"],
}
_DEFAULT_THEME = "Classic Green"


class _CaptureWorker(QThread):
    """
    Worker thread: samples pygame mixer output via get_raw(),
    computes FFT, emits `bars_ready` with a list of NUM_BARS normalised floats.
    """

    bars_ready = Signal(list)

    NUM_BARS = 20

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._active = False

    def run(self) -> None:
        self._active = True
        while self._active:
            self.bars_ready.emit(self._capture())
            time.sleep(0.04)  # ~25 fps

    def stop(self) -> None:
        self._active = False
        self.wait(2000)

    def _capture(self) -> list[float]:
        if not _PYGAME_AVAILABLE or not _NUMPY_AVAILABLE:
            return [0.0] * self.NUM_BARS
        if not hasattr(pygame.mixer, "get_raw"):
            return [0.0] * self.NUM_BARS
        try:
            raw = pygame.mixer.get_raw()
            if not raw:
                return [0.0] * self.NUM_BARS
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if samples.size == 0:
                return [0.0] * self.NUM_BARS
            init = pygame.mixer.get_init()
            if init and init[2] == 2:
                samples = samples[::2]
            n = min(len(samples), 1024)
            window = np.hanning(n)
            chunk = samples[:n] * window
            spectrum = np.abs(np.fft.rfft(chunk))
            n_bins = len(spectrum)
            if n_bins < 3:
                return [0.0] * self.NUM_BARS
            hi_max = max(n_bins - 1, 2)
            log_idx = np.logspace(
                np.log10(1), np.log10(hi_max), self.NUM_BARS + 1
            ).astype(int)
            bars: list[float] = []
            for i in range(self.NUM_BARS):
                lo = log_idx[i]
                hi = max(log_idx[i + 1], lo + 1)
                bars.append(float(np.max(spectrum[lo:hi])))
            peak = max(bars) if max(bars) > 0 else 1.0
            return [min(b / peak, 1.0) for b in bars]
        except Exception:
            return [0.0] * self.NUM_BARS


class _SpectrumWidget(QWidget):
    """Canvas — paints bar spectrum with peak-hold dots."""

    PEAK_HOLD_FRAMES = 20

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bars: list[float] = [0.0] * 20
        self._peak: list[float] = [0.0] * 20
        self._peak_ctr: list[int] = [0] * 20
        self._colors: list[str] = _THEMES[_DEFAULT_THEME]
        self.setMinimumHeight(80)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,  # type: ignore[attr-defined]
            QSizePolicy.Policy.Expanding,
        )
        self.setStyleSheet(f"background: {BG};")

    def set_bars(self, bars: list[float]) -> None:
        for i, val in enumerate(bars):
            if i >= len(self._peak):
                break
            if val > self._peak[i]:
                self._peak[i] = val
                self._peak_ctr[i] = self.PEAK_HOLD_FRAMES
            else:
                if self._peak_ctr[i] > 0:
                    self._peak_ctr[i] -= 1
                else:
                    self._peak[i] = max(self._peak[i] - 0.02, val)
        self._bars = list(bars[:20]) if bars else [0.0] * 20
        self.update()

    def set_theme(self, colors: list[str]) -> None:
        self._colors = colors
        self.update()

    def clear(self) -> None:
        self._bars = [0.0] * len(self._bars)
        self._peak = [0.0] * len(self._peak)
        self._peak_ctr = [0] * len(self._peak_ctr)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        w, h = self.width(), self.height()
        n = len(self._bars)
        gap = max(1, w // (n * 6))
        bar_w = max(2, (w - gap * (n + 1)) // n)

        top_c = QColor(self._colors[0])
        mid_c = QColor(self._colors[1])
        bot_c = QColor(self._colors[2])
        peak_c = QColor(self._colors[0])
        peak_c.setAlpha(200)

        painter.fillRect(0, 0, w, h, QColor(BG))

        for i, val in enumerate(self._bars):
            x = gap + i * (bar_w + gap)
            bar_h = max(2, int(val * (h - 4)))
            y = h - bar_h
            seg = max(1, bar_h // 3)

            painter.fillRect(x, y, bar_w, seg, QBrush(top_c))
            painter.fillRect(x, y + seg, bar_w, seg, QBrush(mid_c))
            painter.fillRect(x, y + seg * 2, bar_w, bar_h - seg * 2, QBrush(bot_c))

            if self._peak[i] > 0.01:
                py = h - int(self._peak[i] * (h - 4)) - 2
                painter.fillRect(x, py, bar_w, 2, QBrush(peak_c))

        painter.end()


class VisualiserPanel(QDockWidget):
    """Winamp-style 20-bar spectrum visualiser dock panel."""

    status_message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Visualiser", parent)
        self.setObjectName("VisualiserPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable  # type: ignore[attr-defined]
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._running = False
        self._worker: Optional[_CaptureWorker] = None

        root = QWidget()
        root.setStyleSheet(f"background: {BG};")
        self.setWidget(root)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        self._toggle_btn = QPushButton("▶ Start")
        self._toggle_btn.setFixedWidth(72)
        self._toggle_btn.clicked.connect(self._toggle)
        self._style_btn(self._toggle_btn)

        theme_lbl = QLabel("Theme:")
        theme_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")

        self._theme_combo = QComboBox()
        for name in _THEMES:
            self._theme_combo.addItem(name)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self._theme_combo.setStyleSheet(
            f"QComboBox {{ background: {SURFACE}; color: {TEXT}; "
            f"border: 1px solid {BORDER}; border-radius: 3px; padding: 2px 6px; }}"
        )

        missing = []
        if not _PYGAME_AVAILABLE:
            missing.append("pygame")
        if not _NUMPY_AVAILABLE:
            missing.append("numpy")
        self._status_lbl = QLabel(
            f"{', '.join(missing)} not installed" if missing else "Idle"
        )
        self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")

        bar.addWidget(self._toggle_btn)
        bar.addWidget(theme_lbl)
        bar.addWidget(self._theme_combo)
        bar.addStretch()
        bar.addWidget(self._status_lbl)
        lay.addLayout(bar)

        self._spectrum = _SpectrumWidget()
        lay.addWidget(self._spectrum, stretch=1)

        note = QLabel(
            "Visualises pygame mixer output  (Soundboard · Local Music · YouTube)"
        )
        note.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        note.setAlignment(Qt.AlignCenter)
        lay.addWidget(note)

    def handle_command(self, action: str, query: str = "") -> None:
        if action == "start" and not self._running:
            self._toggle()
        elif action == "stop" and self._running:
            self._toggle()

    def _toggle(self) -> None:
        if self._running:
            self._stop_worker()
            self._toggle_btn.setText("▶ Start")
            self._status_lbl.setText("Stopped")
            self._spectrum.clear()
        else:
            if not _PYGAME_AVAILABLE:
                self._status_lbl.setText("pygame not installed")
                return
            if not _NUMPY_AVAILABLE:
                self._status_lbl.setText("numpy not installed")
                return
            if not hasattr(pygame.mixer, "get_raw"):
                self._status_lbl.setText("pygame ≥ 2.0 required (get_raw missing)")
                return
            if not pygame.mixer.get_init():
                self._status_lbl.setText("pygame mixer not initialised — play audio first")
                return
            self._start_worker()
            self._toggle_btn.setText("⏹ Stop")
            self._status_lbl.setText("Running")

    def _start_worker(self) -> None:
        self._worker = _CaptureWorker(self)
        self._worker.bars_ready.connect(self._on_bars)
        self._worker.start()
        self._running = True

    def _stop_worker(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._running = False

    def _on_bars(self, bars: list[float]) -> None:
        self._spectrum.set_bars(bars)

    def _on_theme_changed(self, name: str) -> None:
        self._spectrum.set_theme(_THEMES.get(name, _THEMES[_DEFAULT_THEME]))

    def _style_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_worker()
        super().closeEvent(event)
