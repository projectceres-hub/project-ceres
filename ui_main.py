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
    print(
        "\n[GM Assistant] Could not find PyQt5 or PySide6.\n"
        "Install one with:\n"
        "    pip install PyQt5\n"
        "  or\n"
        "    pip install PySide6\n",
        file=sys.stderr,
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
    app = QApplication.instance() or QApplication(sys.argv)

    # High-DPI support
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)  # type: ignore[attr-defined]
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)     # type: ignore[attr-defined]
    except AttributeError:
        pass  # PySide6 / newer Qt handles this automatically

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
    app = _make_app()

    # ── Backend initialisation ─────────────────────────────────────────────────
    # initialize_application() loads vaults, settings, Obsidian sync, etc.
    # It sets config.input_provider = prompt_input (CLI version).
    # We immediately replace it with the Qt dialog version BEFORE commands
    # are registered, so every lambda in register_all_commands() picks up
    # the Qt version through the config reference.
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
