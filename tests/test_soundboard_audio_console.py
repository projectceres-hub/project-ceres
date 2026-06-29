import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QSizePolicy, QSlider

from core.config import Config
from ui.panels.master_scene_panel import MasterScenePanel
from ui.panels.soundboard_panel import Scene, SceneSlot, SoundboardPanel


class _SceneTarget:
    def __init__(self) -> None:
        self.commands: list[tuple[str, str]] = []
        self.volumes: list[int] = []

    def handle_command(self, action: str, query: str = "") -> None:
        self.commands.append((action, query))

    def set_volume(self, value: int) -> None:
        self.volumes.append(value)


class _VolumeOnlyTarget:
    def __init__(self) -> None:
        self.volumes: list[int] = []

    def set_volume(self, value: int) -> None:
        self.volumes.append(value)


class SoundboardAudioConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([sys.argv[0]])

    def test_soundboard_builds_three_pane_audio_console(self) -> None:
        panel = SoundboardPanel()
        try:
            self.assertEqual(panel.windowTitle(), "Audio Console")
            self.assertIsNotNone(panel._soundset_list_widget)
            self.assertIsNotNone(panel._elements_grid_layout)
            self.assertIsNotNone(panel._scene_tabs)
            self.assertEqual(panel._scene_tabs.tabText(0), "Sound Scenes")
            self.assertEqual(panel._scene_tabs.tabText(1), "Campaign Scenes")
            self.assertEqual(panel._console_splitter_default_sizes, [240, 240, 240])
            self.assertEqual(panel._sound_scene_splitter_default_sizes, [300, 300])
            self.assertEqual(panel._sound_scene_splitter.sizes(), [320, 320])
            self.assertTrue(
                any(
                    label.text() == "Sounds"
                    for label in panel._scene_tabs.widget(0).findChildren(QLabel)
                )
            )
            self.assertFalse(
                any(
                    label.text() == "Slots"
                    for label in panel._scene_tabs.widget(0).findChildren(QLabel)
                )
            )
        finally:
            panel.close()

    def test_element_tiles_have_vertical_faders_and_two_play_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combat = folder / "combat"
            combat.mkdir()
            sound_path = combat / "sword-hit.wav"
            sound_path.write_bytes(b"not a real wav")

            panel = SoundboardPanel()
            played: list[Path] = []
            try:
                panel._sound_folder = folder
                panel._rebuild_board()

                key = str(sound_path)
                self.assertIn(key, panel._element_volume_sliders)
                self.assertEqual(
                    panel._element_volume_sliders[key].orientation(),
                    Qt.Orientation.Vertical,
                )

                with patch.object(panel, "_play", lambda path: played.append(path)):
                    panel._element_play_buttons[key].click()
                    panel._element_label_buttons[key].click()

                self.assertEqual(played, [sound_path, sound_path])
            finally:
                panel.close()

    def test_configure_campaign_scenes_embeds_campaign_scene_surface(self) -> None:
        panel = SoundboardPanel()
        config = Config(vaults={"TestVault": "GMAssistantVault"}, current_vault="TestVault")
        try:
            panel.configure_campaign_scenes({"soundboard": panel}, config)

            self.assertIsNotNone(panel._campaign_scene_panel)
            self.assertEqual(panel._campaign_scene_panel.windowTitle(), "Campaign Scenes")
            self.assertIs(panel.campaign_scene_handler(), panel._campaign_scene_panel)
        finally:
            panel.close()

    def test_campaign_scene_controls_start_with_idle_status_and_volume(self) -> None:
        panel = MasterScenePanel({}, Config())
        try:
            self.assertEqual(panel._currently_playing_label.text(), "Currently: Nothing playing")
            self.assertEqual(panel._pause_btn.text(), "Pause")
            self.assertFalse(panel._pause_btn.isEnabled())
            self.assertEqual(panel._volume_slider.minimum(), 0)
            self.assertEqual(panel._volume_slider.maximum(), 100)
            self.assertEqual(panel._volume_slider.value(), 80)
        finally:
            panel.close()

    def test_campaign_scene_layout_keeps_controls_compact_above_expanding_grid(self) -> None:
        panel = MasterScenePanel({}, Config())
        try:
            self.assertEqual(panel._toolbar_frame.maximumHeight(), 42)
            self.assertLessEqual(panel._toolbar_frame.minimumSizeHint().width(), 520)
            self.assertEqual(
                panel._toolbar_frame.sizePolicy().verticalPolicy(),
                QSizePolicy.Policy.Fixed,
            )
            self.assertEqual(
                panel._grid_frame.sizePolicy().verticalPolicy(),
                QSizePolicy.Policy.Expanding,
            )
            self.assertEqual(panel.widget().layout().stretch(1), 1)
        finally:
            panel.close()

    def test_campaign_scene_panel_fits_narrow_audio_console_width(self) -> None:
        panel = MasterScenePanel({}, Config())
        try:
            panel.resize(520, 650)
            panel.show()
            self.app.processEvents()

            self.assertLessEqual(panel.width(), 520)
            self.assertLessEqual(panel._toolbar_frame.width(), panel.width())
            for button in panel._slot_buttons:
                self.assertLessEqual(button.geometry().right(), panel._grid_frame.width())
        finally:
            panel.close()

    def test_campaign_scene_controls_pause_and_volume_active_targets(self) -> None:
        spotify = _SceneTarget()
        soundboard = _SceneTarget()
        volume_only = _VolumeOnlyTarget()
        panel = MasterScenePanel(
            {
                "spotify": spotify,
                "soundboard": soundboard,
                "syrinscape": volume_only,
            },
            Config(),
        )
        try:
            panel._scenes[0]["name"] = "Dungeon Ambush"
            panel._scenes[0]["spotify_playlist_id"] = "spotify:playlist:123"
            panel._scenes[0]["soundboard_scene"] = "Battle"

            with patch("ui.panels.master_scene_panel.load_workspace_state") as load_state, patch(
                "ui.panels.master_scene_panel.save_workspace_state"
            ):
                load_state.return_value = type("State", (), {"current_scene": ""})()
                panel._play_scene(0)

            self.assertEqual(
                panel._currently_playing_label.text(),
                "Currently: Dungeon Ambush",
            )
            self.assertTrue(panel._pause_btn.isEnabled())

            panel._pause_btn.click()

            self.assertIn(("pause", ""), spotify.commands)
            self.assertIn(("pause", ""), soundboard.commands)
            self.assertEqual(panel._currently_playing_label.text(), "Paused: Dungeon Ambush")

            panel._volume_slider.setValue(55)

            self.assertIn(55, spotify.volumes)
            self.assertIn(55, soundboard.volumes)
            self.assertIn(55, volume_only.volumes)
        finally:
            panel.close()

    def test_saved_sound_scene_slots_build_loop_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sound_path = Path(tmp) / "rain.wav"
            sound_path.write_bytes(b"not a real wav")

            panel = SoundboardPanel()
            try:
                panel._scenes = [
                    Scene(
                        name="Storm",
                        slots=[SceneSlot(path=str(sound_path), volume=55, loop=True)],
                    )
                ]
                panel._current_scene_idx = 0

                panel._refresh_slot_list()

                loop_buttons = [
                    button
                    for button in panel.findChildren(QPushButton)
                    if "loop" in button.text().lower()
                ]
                self.assertTrue(loop_buttons)
            finally:
                panel.close()
