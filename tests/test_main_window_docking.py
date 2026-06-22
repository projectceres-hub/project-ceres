import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-software-rasterizer")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt

from core.config import Config

import ui.panels.browser_panel as browser_panel

browser_panel._WEBENGINE_OK = False

from ui.main_window import MainWindow, _should_restore_dock_state


class MainWindowDockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([sys.argv[0]])

    def _build_window(self) -> MainWindow:
        config = Config(vaults={"TestVault": "GMAssistantVault"}, current_vault="TestVault")

        with patch.object(MainWindow, "_restore_geometry", lambda self: None):
            return MainWindow(config, lambda _command: "")

    def test_default_dock_policy_allows_split_or_tab_drops_without_forcing_tabs(self) -> None:
        window = self._build_window()
        try:
            options = window.dockOptions()

            self.assertTrue(options & QMainWindow.DockOption.AllowNestedDocks)
            self.assertTrue(options & QMainWindow.DockOption.AllowTabbedDocks)
            self.assertFalse(options & QMainWindow.DockOption.ForceTabbedDocks)
        finally:
            window.close()

    def test_stale_saved_dock_state_is_not_restored(self) -> None:
        self.assertFalse(_should_restore_dock_state(b"old-state", True, 1, 2))
        self.assertFalse(_should_restore_dock_state(b"old-state", False, 2, 2))
        self.assertFalse(_should_restore_dock_state(None, True, 2, 2))
        self.assertTrue(_should_restore_dock_state(b"current-state", True, 2, 2))

    def test_equalizer_starts_as_own_left_column_section_not_right_tab(self) -> None:
        window = self._build_window()
        try:
            self._assert_equalizer_is_left_section(window)

            window._reset_layout()

            self._assert_equalizer_is_left_section(window)
        finally:
            window.close()

    def _assert_equalizer_is_left_section(self, window: MainWindow) -> None:
        self.assertEqual(
            window.dockWidgetArea(window._eq_panel),
            Qt.DockWidgetArea.LeftDockWidgetArea,
        )
        self.assertNotIn(
            window._eq_panel,
            window.tabifiedDockWidgets(window._now_playing_panel),
        )
        self.assertNotIn(
            window._now_playing_panel,
            window.tabifiedDockWidgets(window._eq_panel),
        )


if __name__ == "__main__":
    unittest.main()
