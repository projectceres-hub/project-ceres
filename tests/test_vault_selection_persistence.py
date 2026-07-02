import json
import os
import tempfile
import unittest
from pathlib import Path

from assistant import _wrap_switch
from core.config import Config


class VaultSelectionPersistenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
