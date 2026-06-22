import tempfile
import unittest
from pathlib import Path

from core.config import Config
from pantheon.messor.fgu_import import import_campaign_entities


def _write_campaign(root: Path, name: str = "Ceres Test Campaign") -> Path:
    campaign = root / name
    campaign.mkdir()
    (campaign / "db.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<root release="8.1|CoreRPG:7">
  <npcdata>
    <id-00001>
      <name>Clockwork Sentry</name>
      <hp>12</hp>
      <ac>15</ac>
      <attacks>Slam</attacks>
    </id-00001>
  </npcdata>
</root>
""",
        encoding="utf-8",
    )
    return campaign


def _config_for(vault: Path) -> Config:
    return Config(vaults={"TestVault": str(vault)}, current_vault="TestVault")


class FGUImportTests(unittest.TestCase):
    def test_import_without_overwrite_preserves_existing_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign = _write_campaign(root)
            vault = root / "vault"
            config = _config_for(vault)

            created, errors = import_campaign_entities(campaign, config, ("npc",))
            self.assertEqual(created, 1)
            self.assertEqual(errors, [])

            note = vault / "Campaigns" / campaign.name / "NPCs" / "Clockwork Sentry.md"
            note.write_text("user edited content", encoding="utf-8")

            created, errors = import_campaign_entities(campaign, config, ("npc",))

            self.assertEqual(created, 0)
            self.assertEqual(note.read_text(encoding="utf-8"), "user edited content")
            self.assertTrue(any("Skipped existing note" in err for err in errors))

    def test_import_with_overwrite_replaces_existing_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign = _write_campaign(root)
            vault = root / "vault"
            config = _config_for(vault)
            note = vault / "Campaigns" / campaign.name / "NPCs" / "Clockwork Sentry.md"
            note.parent.mkdir(parents=True)
            note.write_text("old content", encoding="utf-8")

            created, errors = import_campaign_entities(
                campaign,
                config,
                ("npc",),
                overwrite=True,
            )

            self.assertEqual(created, 1)
            self.assertEqual(errors, [])
            text = note.read_text(encoding="utf-8")
            self.assertIn("fgu_entity: true", text)
            self.assertIn("Clockwork Sentry", text)
            self.assertNotEqual(text, "old content")

    def test_import_reports_progress_for_each_notespec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign = _write_campaign(root)
            vault = root / "vault"
            config = _config_for(vault)
            progress = []

            created, errors = import_campaign_entities(
                campaign,
                config,
                ("npc",),
                progress_callback=lambda current, total, label: progress.append(
                    (current, total, label)
                ),
            )

            self.assertEqual(created, 1)
            self.assertEqual(errors, [])
            self.assertEqual(progress, [(1, 1, "Clockwork Sentry")])


if __name__ == "__main__":
    unittest.main()
