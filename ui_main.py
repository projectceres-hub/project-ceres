"""
GM Assistant — Project Ceres  |  GUI entry point
================================================

Run this file to launch the graphical interface:

    python ui_main.py

The CLI is still fully intact at assistant.py.  The two entry points share
the same backend (initialize_application / run_command / register_all_commands)
and the same Config dataclass.  The only difference is how user input is
captured:

  CLI  →  config.input_provider = prompt_input   (uses input())
  GUI  →  config.input_provider = qt_input_provider  (uses QInputDialog)

Dependencies
------------
    PyQt5  OR  PySide6  (one must be installed)
    All other deps are the same as assistant.py

Install whichever Qt binding you prefer:
    pip install PyQt5
  or
    pip install PySide6
"""

from __future__ import annotations

import sys
import os
from datetime import datetime
from pathlib import Path

# ── Redirect all stdout/stderr to logs/ui.log ────────────────────────────────
# Creates a fresh log on every launch so the terminal stays clean.
# Chromium console noise, Qt warnings, pygame banners — everything lands here.

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "ui.log"

_log_handle = open(_LOG_FILE, "w", encoding="utf-8", buffering=1)  # line-buffered
_log_handle.write(f"── GM Assistant — launched {datetime.now():%Y-%m-%d %H:%M:%S} ──\n\n")

# Save a copy of the real stderr fd BEFORE dup2 overwrites it, so we can
# still print the one-liner "started" message to the actual terminal.
_terminal_fd = os.dup(2)
_original_stderr = os.fdopen(_terminal_fd, "w", encoding="utf-8", closefd=True)

sys.stdout = _log_handle
sys.stderr = _log_handle

# Redirect OS-level file descriptors so native C++ code (Chromium)
# writes to the log file instead of the real terminal.
os.dup2(_log_handle.fileno(), 1)  # fd 1 = stdout
os.dup2(_log_handle.fileno(), 2)  # fd 2 = stderr

# ── Ensure project root is importable ─────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Qt availability check ──────────────────────────────────────────────────────
def _require_qt() -> str:
    """Return the Qt binding name or exit with a helpful message."""
    for binding in ("PyQt5", "PySide6"):
        try:
            __import__(binding)
            return binding
        except ImportError:
            continue
    _original_stderr.write(
        "\n[GM Assistant] Could not find PyQt5 or PySide6.\n"
        "Install one with:\n"
        "    pip install PyQt5\n"
        "  or\n"
        "    pip install PySide6\n"
    )
    sys.exit(1)


_QT_BINDING = _require_qt()

# ── Qt imports (binding already validated above) ───────────────────────────────
if _QT_BINDING == "PyQt5":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
else:
    from PySide6.QtWidgets import QApplication  # type: ignore
    from PySide6.QtCore import Qt               # type: ignore
    from PySide6.QtGui import QFont             # type: ignore

# ── Internal imports ───────────────────────────────────────────────────────────
from assistant import (
    initialize_application,
    register_all_commands,
    run_command,
)
from ui.main_window import MainWindow
from ui.input_bridge import qt_input_provider
from ui.theme import FONT_SIZE


def _make_app() -> QApplication:
    """Create and configure the QApplication."""
    # High-DPI attributes must be set BEFORE QApplication is constructed
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)  # type: ignore[attr-defined]
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)     # type: ignore[attr-defined]
    except AttributeError:
        pass  # PySide6 / newer Qt handles this automatically

    app = QApplication.instance() or QApplication(sys.argv)

    # Global font
    font = QFont("Consolas")
    if not font.exactMatch():
        font = QFont("Courier New")
    font.setPointSize(FONT_SIZE)
    app.setFont(font)

    app.setApplicationName("GM Assistant")
    app.setOrganizationName("ProjectCeres")
    app.setApplicationVersion("0.1.0")

    return app


def main() -> int:
    _original_stderr.write(
        f"GM Assistant started — logs at {_LOG_FILE}\n"
    )

    app = _make_app()

    # ── Backend initialisation ─────────────────────────────────────────────────
    config, gpt_client, scheduler, scheduler_context, history_manager = (
        initialize_application()
    )

    # Swap CLI input provider → Qt dialog input provider
    config.input_provider = qt_input_provider

    # Wire all command handlers (they now use config.input_provider → Qt)
    register_all_commands(config, gpt_client, scheduler, scheduler_context, history_manager)

    # ── Window ────────────────────────────────────────────────────────────────
    window = MainWindow(config, run_command)
    window.show()

    return app.exec() if hasattr(app, "exec") else app.exec_()  # type: ignore[attr-defined]


if __name__ == "__main__":
    sys.exit(main())
