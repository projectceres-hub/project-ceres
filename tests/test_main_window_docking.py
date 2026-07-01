import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-software-rasterizer")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PyQt5.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow
from PyQt5.QtCore import Qt, QSettings

from core.config import Config

import ui.panels.browser_panel as browser_panel
from ui.panels.spotify_panel import (
    SPOTIFY_LOOPBACK_REDIRECT_URI,
    _SpotifyWorker,
    _normalize_loopback_redirect_uri,
    _should_auto_connect_spotify,
)

browser_panel._WEBENGINE_OK = False

from ui.main_window import MainWindow, _should_restore_dock_state


class MainWindowDockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([sys.argv[0]])
        # Keep PyQt wrappers alive; rapid MainWindow GC can abort during dock teardown.
        cls._windows = []

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.quit()

    def _build_window(self, restore_panel_visibility: bool = False) -> MainWindow:
        config = Config(vaults={"TestVault": "GMAssistantVault"}, current_vault="TestVault")

        restore_panel_patch = (
            patch.object(MainWindow, "_restore_panel_visibility", lambda self: None)
            if not restore_panel_visibility
            else patch.object(MainWindow, "_restore_panel_visibility", MainWindow._restore_panel_visibility)
        )
        with patch.object(MainWindow, "_restore_geometry", lambda self: None), restore_panel_patch:
            window = MainWindow(config, lambda _command: "")
            self._windows.append(window)
            return window

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

    def test_spotify_loopback_redirect_uses_local_http_callback(self) -> None:
        self.assertEqual(
            _normalize_loopback_redirect_uri("https://localhost:8888/callback"),
            SPOTIFY_LOOPBACK_REDIRECT_URI,
        )
        self.assertEqual(
            _normalize_loopback_redirect_uri("http://localhost:7777/callback"),
            "http://127.0.0.1:7777/callback",
        )
        self.assertNotIn("localhost", SPOTIFY_LOOPBACK_REDIRECT_URI)

    def test_spotify_auto_connect_requires_existing_token_cache(self) -> None:
        self.assertFalse(
            _should_auto_connect_spotify("client", "secret", "missing-cache-file")
        )

    def test_spotify_play_track_targets_available_connect_device(self) -> None:
        class FakeSpotify:
            def __init__(self) -> None:
                self.devices_called = False
                self.transfers = []
                self.play_calls = []

            def devices(self) -> dict:
                self.devices_called = True
                return {
                    "devices": [
                        {
                            "id": "device-1",
                            "name": "Gaming PC",
                            "type": "Computer",
                            "is_active": False,
                            "is_restricted": False,
                        }
                    ]
                }

            def transfer_playback(self, device_id: str, force_play: bool = False) -> None:
                self.transfers.append((device_id, force_play))

            def start_playback(self, **kwargs) -> None:
                self.play_calls.append(kwargs)

        fake = FakeSpotify()
        worker = _SpotifyWorker()
        worker._sp = fake

        worker.do_play_track("spotify:track:abc")

        self.assertTrue(fake.devices_called)
        self.assertEqual(fake.transfers, [("device-1", False)])
        self.assertEqual(
            fake.play_calls,
            [{"device_id": "device-1", "uris": ["spotify:track:abc"]}],
        )

    def test_spotify_resume_reports_guidance_when_no_connect_device_exists(self) -> None:
        class FakeSpotify:
            def devices(self) -> dict:
                return {"devices": []}

            def start_playback(self, **_kwargs) -> None:
                raise AssertionError("start_playback should not run without a device")

        worker = _SpotifyWorker()
        worker._sp = FakeSpotify()
        errors = []
        worker.error.connect(errors.append)

        worker.do_resume()

        self.assertTrue(errors)
        self.assertIn("Open Spotify", errors[-1])
        self.assertIn("Connect device", errors[-1])

    def test_panel_visibility_restores_even_when_window_state_is_skipped(self) -> None:
        settings = QSettings("ProjectCeres", "GMAssistant")
        keys = ["geometry", "windowState", "layoutStateVersion", "panelVisibility"]
        old_values = {key: settings.value(key) for key in keys}
        try:
            for key in keys:
                settings.remove(key)
            settings.setValue(
                "panelVisibility",
                '{"Audio Console": false, "Mixer": false, "Console": true}',
            )
            settings.sync()

            window = self._build_window(restore_panel_visibility=True)
            try:
                window.show()
                self.app.processEvents()

                self.assertFalse(window._soundboard_panel.toggleViewAction().isChecked())
                self.assertFalse(window._mixer_panel.toggleViewAction().isChecked())
                self.assertTrue(window._console_panel.toggleViewAction().isChecked())
            finally:
                window.close()
                self.app.processEvents()
        finally:
            for key in keys:
                settings.remove(key)
            for key, value in old_values.items():
                if value is not None:
                    settings.setValue(key, value)
            settings.sync()

    def test_all_hidden_panel_visibility_snapshot_is_ignored(self) -> None:
        settings = QSettings("ProjectCeres", "GMAssistant")
        keys = ["geometry", "windowState", "layoutStateVersion", "panelVisibility"]
        old_values = {key: settings.value(key) for key in keys}
        try:
            for key in keys:
                settings.remove(key)
            settings.setValue(
                "panelVisibility",
                '{"AudioConsole": false, "Mixer": false, "Console": false}',
            )
            settings.sync()

            window = self._build_window(restore_panel_visibility=True)
            try:
                window.show()
                self.app.processEvents()

                self.assertTrue(window._soundboard_panel.toggleViewAction().isChecked())
                self.assertTrue(window._mixer_panel.toggleViewAction().isChecked())
            finally:
                window.close()
                self.app.processEvents()
        finally:
            for key in keys:
                settings.remove(key)
            for key, value in old_values.items():
                if value is not None:
                    settings.setValue(key, value)
            settings.sync()

    def test_central_workspace_prompts_to_open_a_module(self) -> None:
        window = self._build_window()
        try:
            labels = window.centralWidget().findChildren(QLabel)
            self.assertTrue(
                any(label.text() == "Open a module to get started" for label in labels)
            )
        finally:
            window.close()

    def test_all_hidden_panel_visibility_snapshot_is_not_saved(self) -> None:
        settings = QSettings("ProjectCeres", "GMAssistant")
        old_value = settings.value("panelVisibility")
        try:
            settings.setValue("panelVisibility", '{"AudioConsole": true}')
            window = self._build_window()
            try:
                for dock in window._dock_visibility_panels().values():
                    dock.hide()

                window._save_panel_visibility(settings)

                self.assertEqual(
                    settings.value("panelVisibility", "", type=str),
                    '{"AudioConsole": true}',
                )
            finally:
                window.close()
        finally:
            settings.remove("panelVisibility")
            if old_value is not None:
                settings.setValue("panelVisibility", old_value)
            settings.sync()

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

    def test_central_workspace_does_not_create_gap_between_dock_columns(self) -> None:
        window = self._build_window()
        try:
            window.resize(1400, 900)
            window.show()
            self.app.processEvents()

            self.assertLessEqual(window.centralWidget().width(), 1)
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
            self.assertNotIn("Campaign Scenes", window._TAB_ICONS)
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
