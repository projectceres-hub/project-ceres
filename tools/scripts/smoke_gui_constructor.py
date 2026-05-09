"""Smoke-test the Project Ceres GUI constructor without showing the window.

This is intentionally narrower than ``python ui_main.py``. It catches Python
import, command-registration, and MainWindow wiring errors while avoiding the
native Qt/WebEngine edge cases that can crash Windows headless runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_headless_env() -> None:
    """Set process env before importing Qt, WebEngine, or pygame."""
    os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --disable-software-rasterizer",
    )
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def main() -> int:
    _set_headless_env()

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        from PySide6.QtWidgets import QApplication  # type: ignore

    from assistant import initialize_application, register_all_commands, run_command

    # Import the module directly and force the friendly fallback widget. Creating
    # QWebEngineView under Windows headless/minimal/offscreen platforms can crash
    # in native Qt before Python can raise an exception.
    import ui.panels.browser_panel as browser_panel

    browser_panel._WEBENGINE_OK = False

    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([sys.argv[0]])
    config, gpt_client, scheduler, scheduler_context, history_manager = (
        initialize_application()
    )
    register_all_commands(
        config,
        gpt_client,
        scheduler,
        scheduler_context,
        history_manager,
    )
    window = MainWindow(config, run_command)

    print("GUI constructor smoke OK.")
    print(f"Registered commands: {len(config.commands)}")
    print(f"Window title: {window.windowTitle()}")

    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
