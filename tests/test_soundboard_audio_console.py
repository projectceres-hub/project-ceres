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
from PyQt5.QtWidgets import QApplication, QLabel, QListView, QPushButton, QComboBox, QDial, QSizePolicy, QSlider

from core.config import Config
from ui.panels.master_scene_panel import MasterScenePanel, _SceneEditDialog
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


class _PanelWithSceneConfig:
    def __init__(self, scene_config: dict) -> None:
        self._scene_config = scene_config


class _PanelWithScenes:
    def __init__(self, scenes: list) -> None:
        self._scenes = scenes


class SoundboardAudioConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Run from a temp directory so any incidental Config.save_settings()
        # can never overwrite the real repo-root settings.json.
        cls._original_cwd = os.getcwd()
        cls._tmpdir = tempfile.TemporaryDirectory()
        os.chdir(cls._tmpdir.name)
        try:
            cls.app = QApplication.instance() or QApplication([sys.argv[0]])
        except BaseException:
            os.chdir(cls._original_cwd)
            cls._tmpdir.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        os.chdir(cls._original_cwd)
        try:
            cls._tmpdir.cleanup()
        except OSError:
            pass

    def test_soundboard_stacks_horizontal_soundset_and_element_bars_above_scenes(self) -> None:
        panel = SoundboardPanel()
        try:
            self.assertEqual(panel.windowTitle(), "Audio Console")
            self.assertIsNotNone(panel._soundset_list_widget)
            self.assertIsNotNone(panel._elements_grid_layout)
            self.assertIsNotNone(panel._scene_tabs)
            self.assertEqual(
                panel._console_splitter.orientation(),
                Qt.Orientation.Vertical,
            )
            self.assertEqual(panel._console_splitter_default_sizes, [90, 170, 420])
            self.assertEqual(
                panel._soundset_list_widget.flow(),
                QListView.Flow.LeftToRight,
            )
            self.assertEqual(
                panel._soundset_list_widget.horizontalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAsNeeded,
            )
            self.assertEqual(panel._scene_tabs.tabText(0), "Sound Scenes")
            self.assertEqual(panel._scene_tabs.tabText(1), "Campaign Scenes")
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

    def test_element_tiles_have_vertical_faders_two_play_targets_and_flow_horizontally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combat = folder / "combat"
            combat.mkdir()
            sound_path = combat / "sword-hit.wav"
            sound_path.write_bytes(b"not a real wav")
            second_sound_path = combat / "shield-block.wav"
            second_sound_path.write_bytes(b"not a real wav")

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
                self.assertIn(str(second_sound_path), panel._element_volume_sliders)
                first_position = panel._elements_grid_layout.getItemPosition(0)
                second_position = panel._elements_grid_layout.getItemPosition(1)
                self.assertEqual(first_position[:2], (0, 0))
                self.assertEqual(second_position[:2], (0, 1))

                with patch.object(panel, "_play", lambda path: played.append(path)):
                    panel._element_play_buttons[key].click()
                    panel._element_label_buttons[key].click()

                self.assertEqual(played, [sound_path, sound_path])
            finally:
                panel.close()

    def test_selecting_soundset_filters_elements_to_that_soundset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combat = folder / "combat"
            ambience = folder / "ambience"
            combat.mkdir()
            ambience.mkdir()
            combat_sound = combat / "sword-hit.wav"
            combat_sound.write_bytes(b"not a real wav")
            ambience_sound = ambience / "rain.wav"
            ambience_sound.write_bytes(b"not a real wav")

            panel = SoundboardPanel()
            try:
                panel._sound_folder = folder
                panel._rebuild_board()

                self.assertIn(str(ambience_sound), panel._element_play_buttons)
                self.assertNotIn(str(combat_sound), panel._element_play_buttons)

                combat_row = [
                    i
                    for i in range(panel._soundset_list_widget.count())
                    if panel._soundset_list_widget.item(i).data(Qt.ItemDataRole.UserRole) == "combat"
                ][0]
                panel._soundset_list_widget.setCurrentRow(combat_row)
                self.app.processEvents()

                self.assertIn(str(combat_sound), panel._element_play_buttons)
                self.assertNotIn(str(ambience_sound), panel._element_play_buttons)
            finally:
                panel.close()

    def test_dot_resource_fork_audio_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combat = folder / "combat"
            combat.mkdir()
            valid_sound = combat / "sword-hit.wav"
            valid_sound.write_bytes(b"not a real wav")
            resource_fork = combat / "._sword-hit.wav"
            resource_fork.write_bytes(b"not a real wav")

            panel = SoundboardPanel()
            try:
                panel._sound_folder = folder
                panel._rebuild_board()

                self.assertIn(str(valid_sound), panel._element_play_buttons)
                self.assertNotIn(str(resource_fork), panel._element_play_buttons)
            finally:
                panel.close()

    def test_element_knob_controls_saved_volume_and_fader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combat = folder / "combat"
            combat.mkdir()
            sound_path = combat / "sword-hit.wav"
            sound_path.write_bytes(b"not a real wav")

            panel = SoundboardPanel()
            try:
                panel._sound_folder = folder
                panel._rebuild_board()

                key = str(sound_path)
                knob = panel._element_volume_knobs[key]
                self.assertIsInstance(knob, QDial)

                knob.setValue(35)

                self.assertEqual(panel._element_volume_by_path[key], 35)
                self.assertEqual(panel._element_volume_sliders[key].value(), 35)
            finally:
                panel.close()

    def test_element_play_button_toggles_to_pause_current_sound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combat = folder / "combat"
            combat.mkdir()
            sound_path = combat / "sword-hit.wav"
            sound_path.write_bytes(b"not a real wav")

            panel = SoundboardPanel()
            try:
                panel._sound_folder = folder
                panel._rebuild_board()

                key = str(sound_path)
                button = panel._element_play_buttons[key]

                with patch("ui.panels.soundboard_panel.pygame.mixer.music.load"), patch(
                    "ui.panels.soundboard_panel.pygame.mixer.music.play"
                ) as play, patch(
                    "ui.panels.soundboard_panel.pygame.mixer.music.pause"
                ) as pause, patch(
                    "ui.panels.soundboard_panel.pygame.mixer.music.unpause"
                ) as unpause:
                    button.click()

                    play.assert_called_once()
                    self.assertEqual(button.text(), "\u23f8")
                    self.assertEqual(panel._playing_element_key, key)

                    button.click()

                    pause.assert_called_once()
                    self.assertEqual(button.text(), "\u25b6")
                    self.assertEqual(panel._paused_element_key, key)

                    button.click()

                    unpause.assert_called_once()
                    self.assertEqual(button.text(), "\u23f8")
                    self.assertEqual(panel._playing_element_key, key)
                    self.assertIsNone(panel._paused_element_key)
            finally:
                panel.close()

    def test_configured_soundboard_folder_loads_nested_audio_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            boss = folder / "combat" / "boss"
            boss.mkdir(parents=True)
            sound_path = boss / "roar.mp3"
            sound_path.write_bytes(b"not a real mp3")

            config = Config(soundboard_folders=[str(folder)])
            panel = SoundboardPanel(config=config)
            try:
                self.assertIn(sound_path, panel._sound_categories["combat"])
            finally:
                panel.close()

    def test_reloading_configured_folders_keeps_loaded_folder_and_adds_new_nested_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            loaded_folder = base / "loaded"
            loaded_folder.mkdir()
            configured_folder = base / "configured"
            nested = configured_folder / "ambience" / "forest"
            nested.mkdir(parents=True)
            configured_sound = nested / "night.wav"
            configured_sound.write_bytes(b"not a real wav")

            config = Config(soundboard_folders=[])
            panel = SoundboardPanel(config=config)
            try:
                panel._sound_folder = loaded_folder
                config.soundboard_folders = [str(configured_folder)]

                panel.reload_configured_folders()

                self.assertIn(str(configured_sound), panel._element_play_buttons)
            finally:
                panel.close()

    def test_corrupt_audio_playback_shows_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sound_path = Path(tmp) / "broken.mp3"
            sound_path.write_bytes(b"not a real mp3")

            panel = SoundboardPanel()
            statuses: list[str] = []
            panel.status_message.connect(statuses.append)
            try:
                with patch(
                    "ui.panels.soundboard_panel.pygame.mixer.music.load",
                    side_effect=Exception("music_dmp3: corrupt mp3 file (bad stream)."),
                ), patch.object(panel, "_play_with_qt_media", return_value=False):
                    panel._play(sound_path)

                self.assertEqual(panel._now_playing_label.text(), "Error: broken.mp3")
                self.assertIn(
                    "Soundboard: broken.mp3 could not be played; unsupported or corrupt audio file.",
                    statuses,
                )
            finally:
                panel.close()

    def test_mp3_rejected_by_pygame_uses_qt_media_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sound_path = Path(tmp) / "works-elsewhere.mp3"
            sound_path.write_bytes(b"mp3 bytes pygame dislikes")

            panel = SoundboardPanel()
            statuses: list[str] = []
            panel.status_message.connect(statuses.append)
            try:
                with patch(
                    "ui.panels.soundboard_panel.pygame.mixer.music.load",
                    side_effect=Exception("music_dmp3: corrupt mp3 file (bad stream)."),
                ), patch.object(panel, "_play_with_qt_media", return_value=True) as fallback:
                    panel._play(sound_path)

                fallback.assert_called_once_with(sound_path)
                self.assertEqual(panel._now_playing_label.text(), "▶  works-elsewhere.mp3")
                self.assertIn("Playing: works-elsewhere.mp3", statuses)
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

    def test_campaign_scene_editor_uses_existing_scene_pickers(self) -> None:
        dialog = _SceneEditDialog(
            {
                "name": "Boss",
                "spotify_playlist_id": "",
                "syrinscape_mood": "",
                "soundboard_scene": "",
                "youtube_scene": "",
                "tidal_scene": "",
                "local_music_scene": "",
                "plex_jellyfin_track": "",
            },
            panel_refs={
                "spotify": _PanelWithSceneConfig(
                    {"combat": {"name": "Boss Fight", "uri": "spotify:playlist:boss"}}
                ),
                "syrinscape": _PanelWithSceneConfig(
                    {
                        "tavern": {
                            "soundset_name": "Taverns",
                            "mood_name": "Busy Tavern",
                            "mood_id": 12,
                        }
                    }
                ),
                "soundboard": _PanelWithScenes([Scene(name="Sword Storm")]),
                "youtube": _PanelWithSceneConfig(
                    {"rain": {"title": "Rain Loop", "url": "https://youtu.be/rain"}}
                ),
                "tidal": _PanelWithSceneConfig(
                    {"rest": {"name": "Long Rest Playlist"}}
                ),
                "local_music": _PanelWithScenes(
                    [type("LocalScene", (), {"name": "Dungeon Crawl", "path": "song.mp3"})()]
                ),
                "plex_jellyfin": _PanelWithScenes(
                    [{"track": {"title": "Cinematic Sting"}}]
                ),
            },
        )
        try:
            for widget_name in (
                "_spotify_edit",
                "_syrin_edit",
                "_sb_edit",
                "_yt_edit",
                "_tidal_edit",
                "_local_edit",
                "_plex_edit",
            ):
                self.assertIsInstance(getattr(dialog, widget_name), QComboBox)

            spotify_values = [
                dialog._spotify_edit.itemData(i)
                for i in range(dialog._spotify_edit.count())
            ]
            self.assertIn("spotify:playlist:boss", spotify_values)

            soundboard_values = [
                dialog._sb_edit.itemData(i)
                for i in range(dialog._sb_edit.count())
            ]
            self.assertIn("Sword Storm", soundboard_values)

            dialog._spotify_edit.setCurrentIndex(
                dialog._spotify_edit.findData("spotify:playlist:boss")
            )
            dialog._sb_edit.setCurrentIndex(dialog._sb_edit.findData("Sword Storm"))

            edited = dialog.get_scene()

            self.assertEqual(edited["spotify_playlist_id"], "spotify:playlist:boss")
            self.assertEqual(edited["soundboard_scene"], "Sword Storm")
        finally:
            dialog.close()

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
