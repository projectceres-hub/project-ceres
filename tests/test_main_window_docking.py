import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-software-rasterizer")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PyQt5.QtWidgets import QApplication, QDockWidget, QMainWindow
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

    def test_default_dock_policy_allows_split_drops_without_user_tab_drops(self) -> None:
        window = self._build_window()
        try:
            options = window.dockOptions()

            self.assertTrue(options & QMainWindow.DockOption.AllowNestedDocks)
            self.assertFalse(options & QMainWindow.DockOption.AllowTabbedDocks)
            self.assertFalse(options & QMainWindow.DockOption.ForceTabbedDocks)
        finally:
            window.close()

    def test_stale_saved_dock_state_is_not_restored(self) -> None:
        self.assertEqual(MainWindow.LAYOUT_STATE_VERSION, 7)
        self.assertFalse(_should_restore_dock_state(b"old-state", True, 6, 7))
        self.assertFalse(_should_restore_dock_state(b"old-state", False, 7, 7))
        self.assertFalse(_should_restore_dock_state(None, True, 7, 7))
        self.assertTrue(_should_restore_dock_state(b"current-state", True, 7, 7))

    def test_left_tools_are_real_movable_docks(self) -> None:
        window = self._build_window()
        try:
            left_docks = [
                window._chat_dock,
                window._vault_panel,
                window._mixer_panel,
                window._eq_panel,
            ]
            for dock in left_docks:
                self.assertEqual(
                    window.dockWidgetArea(dock),
                    Qt.DockWidgetArea.LeftDockWidgetArea,
                )
                self.assertTrue(
                    dock.features() & QDockWidget.DockWidgetFeature.DockWidgetMovable
                )
                self.assertTrue(
                    dock.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable
                )
                self.assertEqual(
                    dock.allowedAreas(),
                    Qt.DockWidgetArea.AllDockWidgetAreas,
                )
        finally:
            window.close()

    def test_left_dock_columns_keep_readable_minimum_sizes(self) -> None:
        window = self._build_window()
        try:
            self.assertGreaterEqual(window.minimumHeight(), 900)
            self.assertGreaterEqual(window._chat_dock.minimumHeight(), 350)
            self.assertGreaterEqual(window._chat_panel.minimumHeight(), 320)
            self.assertGreaterEqual(window._vault_panel.minimumHeight(), 260)
            self.assertGreaterEqual(window._vault_panel.widget().minimumHeight(), 230)
            self.assertGreaterEqual(window._mixer_panel.minimumHeight(), 220)
            self.assertLessEqual(window._mixer_panel.minimumWidth(), 420)
            self.assertGreaterEqual(window._eq_panel.minimumHeight(), 220)
            self.assertLessEqual(window._eq_panel.maximumHeight(), 260)
        finally:
            window.close()

    def test_left_tool_toggle_actions_show_and_hide_docks(self) -> None:
        window = self._build_window()
        try:
            window.show()
            self.app.processEvents()

            action = window._mixer_panel.toggleViewAction()
            self.assertTrue(action.isCheckable())
            self.assertTrue(window._mixer_panel.isVisible())

            action.trigger()
            self.app.processEvents()

            self.assertFalse(window._mixer_panel.isVisible())

            action.trigger()
            self.app.processEvents()

            self.assertTrue(window._mixer_panel.isVisible())
        finally:
            window.close()

    def test_default_left_layout_uses_two_resizable_tool_columns(self) -> None:
        window = self._build_window()
        try:
            window.resize(1400, 900)
            window.show()
            self.app.processEvents()

            chat = window._chat_dock.geometry()
            vault = window._vault_panel.geometry()
            mixer = window._mixer_panel.geometry()
            eq = window._eq_panel.geometry()

            self.assertEqual(vault.x(), chat.x())
            self.assertLessEqual(abs(vault.width() - chat.width()), 4)
            self.assertEqual(eq.x(), mixer.x())
            self.assertLessEqual(abs(eq.width() - mixer.width()), 4)
            self.assertGreater(mixer.x(), chat.x())
            self.assertLessEqual(vault.right() - mixer.x(), 12)
            self.assertLessEqual(mixer.height(), 260)
            self.assertLessEqual(eq.height(), 260)
        finally:
            window.close()

    def test_right_side_docks_remain_tabified(self) -> None:
        window = self._build_window()
        try:
            self.assertIn(
                window._spotify_panel,
                window.tabifiedDockWidgets(window._discord_panel),
            )
            self.assertIn(
                window._soundboard_panel,
                window.tabifiedDockWidgets(window._spotify_panel),
            )
            self.assertEqual(
                window.dockWidgetArea(window._discord_panel),
                Qt.DockWidgetArea.RightDockWidgetArea,
            )
            self.assertEqual(
                window.dockWidgetArea(window._mixer_panel),
                Qt.DockWidgetArea.LeftDockWidgetArea,
            )
        finally:
            window.close()

    def test_campaign_scenes_are_embedded_in_audio_console(self) -> None:
        window = self._build_window()
        try:
            self.assertEqual(window._soundboard_panel.windowTitle(), "Audio Console")
            self.assertIs(
                window._master_scene_panel,
                window._soundboard_panel.campaign_scene_handler(),
            )
            self.assertEqual(window._master_scene_panel.windowTitle(), "Campaign Scenes")
            self.assertNotIn(
                window._master_scene_panel,
                window.tabifiedDockWidgets(window._plex_jellyfin_panel),
            )

            view_menu = next(
                action.menu()
                for action in window.menuBar().actions()
                if action.text().replace("&", "") == "View"
            )
            view_action_texts = [action.text() for action in view_menu.actions()]
            self.assertIn("Audio Console", view_action_texts)
            self.assertNotIn("Master Scenes", view_action_texts)
        finally:
            window.close()

    def test_modules_menu_keeps_browser_label_when_default_page_title_changes(self) -> None:
        window = self._build_window()
        try:
            window._browser_panel._on_title_changed("D&D Beyond")

            modules_menu = next(
                action.menu()
                for action in window.menuBar().actions()
                if action.text().replace("&", "") == "Modules"
            )
            module_action_texts = [action.text() for action in modules_menu.actions()]

            self.assertIn("Browser", module_action_texts)
            self.assertNotIn("D&D Beyond", module_action_texts)
            self.assertEqual(window._browser_panel._bookmarks[0], ("D&D Beyond", "https://www.dndbeyond.com"))
        finally:
            window.close()

    def test_reset_layout_keeps_equalizer_out_of_right_tabs(self) -> None:
        window = self._build_window()
        try:
            window._reset_layout()

            self.assertNotIn(
                window._eq_panel,
                window.tabifiedDockWidgets(window._now_playing_panel),
            )
            self.assertNotIn(
                window._now_playing_panel,
                window.tabifiedDockWidgets(window._eq_panel),
            )
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
