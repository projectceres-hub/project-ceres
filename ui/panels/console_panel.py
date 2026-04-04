"""
Console panel for Project Ceres — GM Assistant UI.

A QDockWidget providing a CLI-style command interface within the GUI:
  • Scrollable output log (read-only QPlainTextEdit)
  • Single-line command input with history
  • Dispatches commands through run_command() — same backend as the CLI

Layout
------
  ┌─ CONSOLE ────────────────────────────────────┐
  │ [GM ASSISTANT v0.1]                          │
  │ > switch-vault GMAssistantVault              │
  │ Vault switched to GMAssistantVault           │
  │ > list-notes                                 │
  │ ⋮  (scrollable output)                       │
  ├──────────────────────────────────────────────│
  │ > [command input                      ] [▶]  │
  └──────────────────────────────────────────────┘
"""

from __future__ import annotations

import sys
import io
from typing import Callable, List, Optional

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLineEdit, QPlainTextEdit, QSizePolicy,
    )
    from PyQt5.QtCore import Qt, pyqtSignal as Signal
    from PyQt5.QtGui import QColor, QTextCharFormat, QFont, QKeyEvent
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLineEdit, QPlainTextEdit, QSizePolicy,
    )
    from PySide6.QtCore import Qt, Signal  # type: ignore
    from PySide6.QtGui import QColor, QTextCharFormat, QFont, QKeyEvent  # type: ignore

from ui.theme import ACCENT, TEXT, MUTED, SUCCESS, WARNING, ERROR, BG, PANEL

# Max lines before the output log auto-truncates from the top
_MAX_LINES = 2000


class HistoryLineEdit(QLineEdit):
    """QLineEdit with Up/Down arrow command history."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._history: List[str] = []
        self._history_pos: int = -1

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        if key == Qt.Key.Key_Up:  # type: ignore[attr-defined]
            if self._history:
                self._history_pos = min(self._history_pos + 1, len(self._history) - 1)
                self.setText(self._history[-(self._history_pos + 1)])
            return
        if key == Qt.Key.Key_Down:  # type: ignore[attr-defined]
            if self._history_pos > 0:
                self._history_pos -= 1
                self.setText(self._history[-(self._history_pos + 1)])
            else:
                self._history_pos = -1
                self.clear()
            return
        super().keyPressEvent(event)

    def push_history(self, cmd: str) -> None:
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._history_pos = -1


class ConsolePanel(QDockWidget):
    """
    Dockable console panel with command input and output log.

    Signals:
        status_message(msg) — push text to the main window status bar
    """

    status_message: Signal = Signal(str)

    def __init__(
        self,
        config,                     # core.config.Config
        run_command: Callable,      # assistant.run_command
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("⌨  Console", parent)
        self._config = config
        self._run_command = run_command

        self.setObjectName("ConsolePanel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas  # type: ignore[attr-defined]
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._build_ui()
        self._print_banner()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Output log
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumBlockCount(_MAX_LINES)
        self._output.setWordWrapMode(
            __import__(
                "PyQt5.QtGui" if "PyQt5" in sys.modules else "PySide6.QtGui",
                fromlist=["QTextOption"]
            ).QTextOption.WrapMode.NoWrap
            if False else
            __import__(
                "PyQt5.QtGui" if "PyQt5" in sys.modules else "PySide6.QtGui",
                fromlist=["QTextOption"]
            ).QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
        )
        self._output.setStyleSheet(
            f"background: {BG}; color: {TEXT}; border: 1px solid #2a2a4a;"
        )
        layout.addWidget(self._output)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        prompt_lbl = __import__(
            "PyQt5.QtWidgets" if "PyQt5" in sys.modules else "PySide6.QtWidgets",
            fromlist=["QLabel"]
        ).QLabel(">")
        prompt_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 14px;")
        prompt_lbl.setFixedWidth(14)
        input_row.addWidget(prompt_lbl)

        self._input = HistoryLineEdit()
        self._input.setPlaceholderText("Enter command…  (try: help)")
        self._input.returnPressed.connect(self._execute)
        input_row.addWidget(self._input)

        run_btn = QPushButton("▶")
        run_btn.setFixedWidth(32)
        run_btn.setToolTip("Run command")
        run_btn.setProperty("class", "accent")
        run_btn.clicked.connect(self._execute)
        input_row.addWidget(run_btn)

        layout.addLayout(input_row)
        self.setWidget(container)

    # ── Output helpers ─────────────────────────────────────────────────────────

    def _print_banner(self) -> None:
        self.print_output(
            "╔══════════════════════════════════════╗", color=ACCENT
        )
        self.print_output(
            "║   GM ASSISTANT  ·  Project Ceres     ║", color=ACCENT
        )
        self.print_output(
            "╚══════════════════════════════════════╝", color=ACCENT
        )
        self.print_output(
            "Type 'help' to list commands.", color=MUTED
        )

    def print_output(self, text: str, color: Optional[str] = None) -> None:
        """Append a line of text to the output log, optionally coloured."""
        cursor = self._output.textCursor()
        cursor.movePosition(
            __import__(
                "PyQt5.QtGui" if "PyQt5" in sys.modules else "PySide6.QtGui",
                fromlist=["QTextCursor"]
            ).QTextCursor.MoveOperation.End
        )
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        else:
            fmt.setForeground(QColor(TEXT))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def print_error(self, text: str) -> None:
        self.print_output(f"[ERROR] {text}", color=ERROR)

    def print_success(self, text: str) -> None:
        self.print_output(text, color=SUCCESS)

    def print_warning(self, text: str) -> None:
        self.print_output(text, color=WARNING)

    # ── Command execution ──────────────────────────────────────────────────────

    def _execute(self) -> None:
        raw = self._input.text().strip()
        if not raw:
            return

        self._input.push_history(raw)
        self._input.clear()

        # Echo the command
        self.print_output(f"> {raw}", color=ACCENT)

        # Split into command name + args (first token = command)
        parts = raw.split(None, 1)
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        # Redirect stdout so we can capture the backend's print() output
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured = io.StringIO()
        sys.stdout = captured
        sys.stderr = captured

        try:
            self._run_command(cmd_name, args, self._config)
        except SystemExit:
            pass
        except Exception as exc:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.print_error(str(exc))
            return
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = captured.getvalue()
        if output.strip():
            for line in output.splitlines():
                self.print_output(line)

        self.status_message.emit(f"Ran: {cmd_name}")
