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
        from PyQt5.QtCore import Qt, QSettings
    except ImportError:
        from PySide6.QtWidgets import QApplication  # type: ignore
        from PySide6.QtCore import Qt, QSettings  # type: ignore

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
    settings = QSettings("ProjectCeres", "GMAssistant")
    isolated_setting_keys = [
        "geometry",
        "windowState",
        "layoutStateVersion",
        "panelVisibility",
    ]
    saved_settings = {key: settings.value(key) for key in isolated_setting_keys}
    for key in isolated_setting_keys:
        settings.remove(key)
    settings.sync()
    window = None
    try:
        window = MainWindow(config, run_command)

        menu_titles = [action.text().replace("&", "") for action in window.menuBar().actions()]
        expected_order = ["File", "Tools", "View", "Modules", "Help"]
        if menu_titles[:5] != expected_order:
            raise AssertionError(f"Unexpected menu order: {menu_titles[:5]}")

        tools_menu = next(
            (action.menu() for action in window.menuBar().actions() if action.text().replace("&", "") == "Tools"),
            None,
        )
        if tools_menu is None:
            raise AssertionError("Tools menu missing")

        tool_actions = [action.text().replace("&", "") for action in tools_menu.actions()]
        if "PDF Importer..." not in tool_actions:
            raise AssertionError(f"PDF Importer action missing from Tools menu: {tool_actions}")

        left_docks = [
            window._chat_dock,
            window._vault_panel,
            window._mixer_panel,
            window._eq_panel,
        ]
        for dock in left_docks:
            if window.dockWidgetArea(dock) != Qt.DockWidgetArea.LeftDockWidgetArea:
                raise AssertionError(f"{dock.objectName()} is not in the left dock area")

        if window._spotify_panel not in window.tabifiedDockWidgets(window._discord_panel):
            raise AssertionError("Spotify is no longer tabified with Discord")
        if window._soundboard_panel not in window.tabifiedDockWidgets(window._spotify_panel):
            raise AssertionError("Soundboard is no longer in the right-side media tab group")

        print("GUI constructor smoke OK.")
        print(f"Registered commands: {len(config.commands)}")
        print(f"Window title: {window.windowTitle()}")
    finally:
        if window is not None:
            window.close()
        for key in isolated_setting_keys:
            settings.remove(key)
        for key, value in saved_settings.items():
            if value is not None:
                settings.setValue(key, value)
        settings.sync()
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
