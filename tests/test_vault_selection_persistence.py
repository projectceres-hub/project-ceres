import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-software-rasterizer")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from assistant import _wrap_switch
from core.config import Config
from PyQt5.QtWidgets import QApplication
from pantheon.vervactor.workspace import WorkspaceObjectRef, set_current_object
from ui.panels.vault_notes_panel import VaultNotesPanel


class VaultSelectionPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([sys.argv[0]])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.quit()

    def test_switch_command_persists_selected_vault_for_next_session(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                alpha = Path(tmp) / "Alpha"
                beta = Path(tmp) / "Beta"
                alpha.mkdir()
                beta.mkdir()
                config = Config(
                    vaults={"Alpha": str(alpha), "Beta": str(beta)},
                    current_vault="Alpha",
                )

                _wrap_switch("Beta", config)

                self.assertEqual(config.current_vault, "Beta")
                saved = json.loads(Path("settings.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["current_vault"], "Beta")

                next_session = Config(vaults=config.vaults)
                next_session.load_settings()
                self.assertEqual(next_session.current_vault, "Beta")
            finally:
                os.chdir(original_cwd)

    def test_vault_panel_dropdown_persists_selected_vault_for_next_session(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                alpha = Path(tmp) / "Alpha"
                beta = Path(tmp) / "Beta"
                alpha.mkdir()
                beta.mkdir()
                config = Config(
                    vaults={"Alpha": str(alpha), "Beta": str(beta)},
                    current_vault="Alpha",
                )
                commands = []

                panel = VaultNotesPanel(
                    config,
                    lambda command, args, _config: commands.append((command, args)),
                )
                try:
                    panel._vault_combo.setCurrentIndex(panel._vault_combo.findText("Beta"))
                    self.app.processEvents()

                    self.assertEqual(config.current_vault, "Beta")
                    self.assertEqual(commands, [("switch", "Beta")])
                    saved = json.loads(Path("settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["current_vault"], "Beta")

                    next_session = Config(vaults=config.vaults)
                    next_session.load_settings()
                    self.assertEqual(next_session.current_vault, "Beta")
                finally:
                    panel.close()
            finally:
                os.chdir(original_cwd)

    def test_vault_panel_starts_on_browser_when_vault_has_saved_current_note(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                vault = Path(tmp) / "Beta"
                vault.mkdir()
                note = vault / "First Note.md"
                note.write_text("# First Note\n", encoding="utf-8")
                config = Config(vaults={"Beta": str(vault)}, current_vault="Beta")
                set_current_object(
                    config,
                    WorkspaceObjectRef(
                        kind="note",
                        path=str(note),
                        title="First Note",
                        source="vault_notes",
                    ),
                )

                panel = VaultNotesPanel(config, lambda *_args: None)
                try:
                    self.assertEqual(panel._stack.currentIndex(), 0)
                    self.assertIsNone(panel._current_note_path)
                finally:
                    panel.close()
            finally:
                os.chdir(original_cwd)

    def test_vault_panel_switch_clears_open_note_preview(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                alpha = Path(tmp) / "Alpha"
                beta = Path(tmp) / "Beta"
                alpha.mkdir()
                beta.mkdir()
                note = alpha / "Open Note.md"
                note.write_text("# Open Note\n", encoding="utf-8")
                config = Config(
                    vaults={"Alpha": str(alpha), "Beta": str(beta)},
                    current_vault="Alpha",
                )

                panel = VaultNotesPanel(config, lambda *_args: None)
                try:
                    panel._open_note_viewer(note)
                    self.assertEqual(panel._stack.currentIndex(), 1)
                    self.assertEqual(panel._current_note_path, note)

                    panel._vault_combo.setCurrentIndex(panel._vault_combo.findText("Beta"))
                    self.app.processEvents()

                    self.assertEqual(config.current_vault, "Beta")
                    self.assertEqual(panel._stack.currentIndex(), 0)
                    self.assertIsNone(panel._current_note_path)
                    saved = json.loads(Path("settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["current_vault"], "Beta")
                finally:
                    panel.close()
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
