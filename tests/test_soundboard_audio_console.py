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
from PyQt5.QtWidgets import QApplication, QPushButton, QSlider

from core.config import Config
from ui.panels.soundboard_panel import Scene, SceneSlot, SoundboardPanel


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
            self.assertEqual(panel._scene_tabs.tabText(0), "Campaign Scenes")
            self.assertEqual(panel._scene_tabs.tabText(1), "Sound Scenes")
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
