"""
PDF importer dialog for Project Ceres.

Small modal launcher for the existing PDF command pipeline. It converts one
PDF with ``pdf2md`` or a folder with ``pdfbatch`` and displays command output.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable, Optional

try:
    from PyQt5.QtWidgets import (
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QPlainTextEdit,
        QVBoxLayout,
        QWidget,
    )
    from PyQt5.QtCore import Qt, pyqtSignal as Signal
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QPlainTextEdit,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt, Signal  # type: ignore

from ui.theme import ACCENT, BG, BORDER, MUTED, PANEL, SURFACE, TEXT

_MAPS_DIR = Path(__file__).resolve().parents[2] / "core" / "maps"


def _quote_arg(value: str) -> str:
    """Quote a command argument for the existing shlex-based command parser."""
    return '"' + value.replace('"', '\\"') + '"'


class PDFImporterDialog(QDialog):
    """Modal PDF import launcher backed by ``pdf2md`` and ``pdfbatch``."""

    status_message: Signal = Signal(str)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._run_command = run_command

        self.setWindowTitle("PDF Importer")
        self.resize(640, 460)
        self.setStyleSheet(f"QDialog {{ background: {BG}; color: {TEXT}; }}")

        self._build_ui()
        self._on_mode_changed()
        self._update_run_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("PDF Importer")
        title.setStyleSheet(f"color: {ACCENT}; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("Convert a PDF or folder of PDFs into the current vault's Converted folder.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]
        form.setSpacing(8)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Single PDF", "Folder"])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._mode_combo.setStyleSheet(self._field_style())
        form.addRow("Mode:", self._mode_combo)

        path_widget = QWidget()
        path_row = QHBoxLayout(path_widget)
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(6)
        self._path_edit = QLineEdit()
        self._path_edit.setStyleSheet(self._field_style())
        self._path_edit.textChanged.connect(self._update_run_state)
        path_row.addWidget(self._path_edit, 1)

        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.setStyleSheet(self._button_style())
        self._browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._browse_btn)
        form.addRow("Input:", path_widget)

        self._map_combo = QComboBox()
        self._map_combo.setStyleSheet(self._field_style())
        self._populate_map_combo()
        form.addRow("Map:", self._map_combo)

        layout.addLayout(form)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Command output will appear here.")
        self._output.setStyleSheet(
            f"background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER}; "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        layout.addWidget(self._output, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._button_style())
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)

        self._run_btn = QPushButton("Import")
        self._run_btn.setStyleSheet(self._accent_button_style())
        self._run_btn.clicked.connect(self._run_import)
        buttons.addWidget(self._run_btn)
        layout.addLayout(buttons)

    def _on_mode_changed(self) -> None:
        if self._mode_combo.currentText() == "Folder":
            self._path_edit.setPlaceholderText("Choose a folder containing PDFs")
        else:
            self._path_edit.setPlaceholderText("Choose a PDF file")
        self._update_run_state()

    def _browse(self) -> None:
        if self._mode_combo.currentText() == "Folder":
            selected = QFileDialog.getExistingDirectory(
                self,
                "Choose PDF Folder",
                self._path_edit.text().strip(),
            )
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Choose PDF",
                self._path_edit.text().strip(),
                "PDF files (*.pdf)",
            )
        if selected:
            self._path_edit.setText(selected)

    def _update_run_state(self) -> None:
        if hasattr(self, "_run_btn"):
            self._run_btn.setEnabled(bool(self._path_edit.text().strip()))

    def _run_import(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            return

        command = "pdfbatch" if self._mode_combo.currentText() == "Folder" else "pdf2md"
        args = _quote_arg(path)
        map_path = str(self._map_combo.currentData() or "").strip()
        if map_path:
            args += f" --map {_quote_arg(map_path)}"

        self._output.clear()
        self._output.appendPlainText(f"> {command} {args}")

        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                self._run_command(command, args, self._config)
        except SystemExit:
            pass
        except Exception as exc:
            captured.write(f"Error: {exc}\n")

        output = captured.getvalue().strip()
        if output:
            self._output.appendPlainText(output)

        self.status_message.emit(f"Ran {command}")

    def _populate_map_combo(self) -> None:
        maps = sorted(_MAPS_DIR.glob("*.yaml"))
        for map_file in maps:
            self._map_combo.addItem(map_file.name, str(map_file))

        default_index = self._map_combo.findText("dnd5e.yaml")
        if default_index >= 0:
            self._map_combo.setCurrentIndex(default_index)

    @staticmethod
    def _field_style() -> str:
        return (
            f"background: {SURFACE}; color: {TEXT}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 8px;"
        )

    @staticmethod
    def _button_style() -> str:
        return (
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 12px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )

    @staticmethod
    def _accent_button_style() -> str:
        return (
            f"QPushButton {{ background: {ACCENT}; color: white; font-weight: bold; "
            "border: none; border-radius: 4px; padding: 7px 18px; }}"
            "QPushButton:disabled { background: #555; color: #aaa; }"
        )
