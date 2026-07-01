import os
import sys
import unittest

from ui import theme

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
os.environ.setdefault("QT_OPENGL", "software")


class WinampThemeTest(unittest.TestCase):
    def test_winamp_palette_exports_reference_colors(self):
        self.assertEqual(theme.BG, "#050608")
        self.assertEqual(theme.PANEL, "#11131b")
        self.assertEqual(theme.SURFACE, "#2f3548")
        self.assertEqual(theme.ACCENT, "#00ff3c")
        self.assertEqual(theme.ACCENT2, "#f3d94e")
        self.assertEqual(theme.TEXT, "#00ff3c")
        self.assertEqual(theme.MUTED, "#a8b0c2")
        self.assertEqual(theme.BORDER, "#697084")

    def test_stylesheet_contains_winamp_chrome_markers(self):
        qss = theme.STYLESHEET
        self.assertIn("Winamp classic base", qss)
        self.assertIn("qlineargradient", qss)
        self.assertIn("QSlider::handle:horizontal", qss)
        self.assertIn("QDockWidget::title", qss)
        self.assertIn("border-right-color: #697084", qss)
        self.assertIn("border-bottom-color: #697084", qss)
        self.assertIn('QFrame[class="winamp-panel-frame"]', qss)
        self.assertIn("border-radius: 1px", qss)
        self.assertIn("#f3d94e", qss)

    def test_stylesheet_contains_winamp_media_button_classes(self):
        qss = theme.STYLESHEET
        self.assertIn('QPushButton[class="media-control"]', qss)
        self.assertIn('QPushButton[class="media-control-primary"]', qss)
        media_qss = qss.split('QPushButton[class="media-control"]', 1)[1]
        primary_qss = qss.split('QPushButton[class="media-control-primary"]', 1)[1]
        self.assertIn("#00ff3c", media_qss)
        self.assertIn("#4b5f95", media_qss)
        self.assertIn("#313a54", primary_qss)
        self.assertNotIn("#7cff91", primary_qss.split("QPushButton:disabled", 1)[0])

    def test_spotify_transport_buttons_use_winamp_media_classes(self):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            from PySide6.QtWidgets import QApplication  # type: ignore

        from core.config import Config
        from ui.panels.spotify_panel import SpotifyPanel

        app = QApplication.instance() or QApplication([sys.argv[0]])
        config = Config(vaults={"TestVault": "GMAssistantVault"}, current_vault="TestVault")
        panel = SpotifyPanel(config, lambda _command: "")
        try:
            self.assertEqual(panel._play_btn.property("class"), "media-control-primary")
            self.assertLessEqual(panel._play_btn.height(), 24)
            self.assertLessEqual(panel._play_btn.width(), 34)
            self.assertEqual(panel._prev_btn.text(), "|<")
            self.assertEqual(panel._next_btn.text(), ">|")
            panel._on_playback_updated(
                {
                    "is_playing": True,
                    "progress_ms": 0,
                    "item": {"duration_ms": 1000, "artists": [], "album": {}},
                }
            )
            self.assertEqual(panel._play_btn.text(), "||")
            for button in (
                panel._prev_btn,
                panel._next_btn,
                panel._shuffle_btn,
                panel._repeat_btn,
            ):
                self.assertEqual(button.property("class"), "media-control")
                self.assertLessEqual(button.height(), 24)
                self.assertLessEqual(button.width(), 28)
        finally:
            panel.close()
            app.processEvents()

    def test_spotify_now_playing_art_placeholder_has_no_music_note(self):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            from PySide6.QtWidgets import QApplication  # type: ignore

        from core.config import Config
        from ui.panels.spotify_panel import SpotifyPanel

        app = QApplication.instance() or QApplication([sys.argv[0]])
        config = Config(vaults={"TestVault": "GMAssistantVault"}, current_vault="TestVault")
        panel = SpotifyPanel(config, lambda _command: "")
        try:
            self.assertEqual(panel._art_label.text(), "")

            panel._on_playback_updated({})

            self.assertEqual(panel._art_label.text(), "")
        finally:
            panel.close()
            app.processEvents()


class MixerWinampLayoutTest(unittest.TestCase):
    def test_mixer_uses_vertical_winamp_sliders(self):
        try:
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            from PySide6.QtCore import Qt  # type: ignore
            from PySide6.QtWidgets import QApplication  # type: ignore

        from ui.panels.mixer_panel import MixerPanel

        class Source:
            def __init__(self):
                self.volume = None

            def set_volume(self, value):
                self.volume = value

        app = QApplication.instance() or QApplication([sys.argv[0]])
        panel = MixerPanel()
        panel.register_source("Soundboard", Source())

        self.assertEqual(panel._master_slider.orientation(), Qt.Vertical)
        self.assertEqual(
            panel._channels["Soundboard"].slider.orientation(),
            Qt.Vertical,
        )

    def test_mixer_minimum_size_fits_all_registered_faders(self):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            from PySide6.QtWidgets import QApplication  # type: ignore

        from ui.panels.mixer_panel import MixerPanel

        class Source:
            def set_volume(self, value):
                self.volume = value

        app = QApplication.instance() or QApplication([sys.argv[0]])
        panel = MixerPanel()
        for name in (
            "Soundboard",
            "Syrinscape",
            "Spotify",
            "YouTube",
            "Tidal",
            "Local Music",
            "Plex/Jellyfin",
        ):
            panel.register_source(name, Source(), "music.png")

        self.assertLessEqual(panel.minimumWidth(), 420)
        self.assertGreaterEqual(panel.minimumHeight(), 220)
        self.assertLessEqual(panel.maximumHeight(), 260)
        self.assertGreaterEqual(panel._channels_widget.minimumWidth(), 560)
        self.assertGreaterEqual(panel._channels_widget.minimumHeight(), 160)

    def test_mixer_vertical_slider_fill_rises_from_bottom(self):
        try:
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QApplication, QSlider
        except ImportError:
            from PySide6.QtCore import Qt  # type: ignore
            from PySide6.QtWidgets import QApplication, QSlider  # type: ignore

        from ui.panels.mixer_panel import _apply_slider_style

        app = QApplication.instance() or QApplication([sys.argv[0]])
        slider = QSlider(Qt.Vertical)
        _apply_slider_style(slider)
        qss = slider.styleSheet()

        self.assertIn("QSlider::add-page:vertical", qss)
        self.assertIn("#f3d94e", qss.split("QSlider::add-page:vertical", 1)[1])


class EqualizerWinampLayoutTest(unittest.TestCase):
    def test_equalizer_uses_compact_framed_content(self):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            from PySide6.QtWidgets import QApplication  # type: ignore

        from core.config import Config
        from ui.panels.equalizer_panel import EqualizerPanel

        app = QApplication.instance() or QApplication([sys.argv[0]])
        config = Config(vaults={"TestVault": "GMAssistantVault"}, current_vault="TestVault")
        panel = EqualizerPanel(config)

        self.assertEqual(panel._content_frame.property("class"), "winamp-panel-frame")
        self.assertLessEqual(panel._content_frame.maximumWidth(), 430)
        self.assertLessEqual(panel._content_frame.maximumHeight(), 320)
        self.assertIn("QScrollArea", panel._bands_scroll.styleSheet())
        self.assertIn("#697084", panel._bands_scroll.styleSheet())
