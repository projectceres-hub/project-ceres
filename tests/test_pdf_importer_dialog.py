import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

try:
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from PySide6.QtWidgets import QApplication  # type: ignore

from ui.dialogs.pdf_importer_dialog import PDFImporterDialog


class PDFImporterDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_single_pdf_runs_pdf2md_and_captures_output(self) -> None:
        calls = []

        def run_command(name, args, config):
            calls.append((name, args, config))
            print("converted one pdf")

        config = object()
        dialog = PDFImporterDialog(config, run_command)
        dialog._mode_combo.setCurrentText("Single PDF")
        dialog._path_edit.setText(r"C:\Vault\Books\Rules.pdf")
        dialog._map_combo.setCurrentText("dnd5e.yaml")

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            dialog._run_import()

        expected_map = str(Path.cwd() / "core" / "maps" / "dnd5e.yaml")
        self.assertEqual(calls, [("pdf2md", rf'"C:\Vault\Books\Rules.pdf" --map "{expected_map}"', config)])
        self.assertIn("converted one pdf", dialog._output.toPlainText())

    def test_map_dropdown_is_populated_from_core_maps(self) -> None:
        dialog = PDFImporterDialog(object(), lambda *_args: None)

        labels = [dialog._map_combo.itemText(i) for i in range(dialog._map_combo.count())]

        self.assertIn("dnd5e.yaml", labels)
        self.assertIn("generic.yaml", labels)
        self.assertEqual(dialog._map_combo.currentText(), "dnd5e.yaml")

    def test_folder_mode_runs_pdfbatch(self) -> None:
        calls = []

        def run_command(name, args, config):
            calls.append((name, args, config))

        config = object()
        dialog = PDFImporterDialog(config, run_command)
        dialog._mode_combo.setCurrentText("Folder")
        dialog._path_edit.setText(r"C:\Vault\PDF Queue")

        dialog._run_import()

        expected_map = str(Path.cwd() / "core" / "maps" / "dnd5e.yaml")
        self.assertEqual(calls, [("pdfbatch", rf'"C:\Vault\PDF Queue" --map "{expected_map}"', config)])


if __name__ == "__main__":
    unittest.main()
