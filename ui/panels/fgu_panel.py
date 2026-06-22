"""
Fantasy Grounds Unity panel for Project Ceres — GM Assistant UI.

Connects to the local FGU installation, reads campaign db.xml files,
and lets the GM browse/import characters, NPCs, and items into Obsidian.

Auto-detects FGU campaigns from:
  %APPDATA%\\SmiteWorks\\Fantasy Grounds\\campaigns\\
  %APPDATA%\\Fantasy Grounds\\campaigns\\
  ~/Documents/Fantasy Grounds/campaigns/

Layout
------
  ┌─ 🐉 FANTASY GROUNDS ─────────────────────────┐
  │ Campaign: [▾ The Lost Mines              ] [⟳]│
  ├──────────────────────────────────────────────│
  │ [🧙 Characters] [👹 NPCs] [🗡 Items]           │
  ├──────────────────────────────────────────────│
  │ 🔍 [filter…                             ]    │
  │ ┌────────────────────────────────────────┐   │
  │ │ Aragorn          Ranger 5  HP:44  AC:16│   │
  │ │ Gandalf          Wizard 20 HP:99  AC:12│   │
  │ └────────────────────────────────────────┘   │
  ├──────────────────────────────────────────────│
  │ [→ Import Selected] [→ Import All] [👁 Preview]│
  └──────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QLineEdit, QFileDialog, QSizePolicy, QCheckBox,
        QMessageBox, QTextEdit, QSplitter, QApplication, QProgressBar,
        QListWidget, QListWidgetItem, QAbstractItemView,
    )
    from PyQt5.QtCore import Qt, QTimer, QSettings, QThread, pyqtSignal as Signal
    from PyQt5.QtGui import QColor, QFont
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QLineEdit, QFileDialog, QSizePolicy, QCheckBox,
        QMessageBox, QTextEdit, QSplitter, QApplication, QProgressBar,
        QListWidget, QListWidgetItem, QAbstractItemView,
    )
    from PySide6.QtCore import Qt, QTimer, QSettings, QThread, Signal  # type: ignore
    from PySide6.QtGui import QColor, QFont  # type: ignore

from ui.theme import ACCENT, MUTED, TEXT, SUCCESS, WARNING, ERROR, PANEL, SURFACE

from pantheon.messor.fgu_character import (
    FGUCampaignParser,
    FGUCharacter, FGUNPC, FGUItem,
    find_campaign_folders,
    scan_campaigns_in_folder,
    import_entity_to_vault,
    character_to_markdown, npc_to_markdown, item_to_markdown,
)
from pantheon.messor import (
    detect_ruleset,
    import_campaign_entities,
    export_entities_to_xml,
    read_fgu_notes_in_vault,
)
from pantheon.vervactor.workspace import WorkspaceObjectRef, set_current_object

# Tab indices
TAB_CHARS = 0
TAB_NPCS  = 1
TAB_ITEMS = 2
TAB_IMPORT = 3
TAB_EXPORT = 4

# TreeWidget column indices
COL_NAME   = 0
COL_DETAIL = 1
COL_HP     = 2
COL_AC     = 3


class _ImportWorker(QThread):
    """Background worker for system-aware FGU entity imports."""

    progress: Signal = Signal(int, int, str)
    finished_import: Signal = Signal(int, list)

    def __init__(
        self,
        campaign_path: Path,
        config,
        entity_types: Tuple[str, ...],
        overwrite: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._campaign_path = campaign_path
        self._config = config
        self._entity_types = entity_types
        self._overwrite = overwrite

    def run(self) -> None:
        def _progress(current: int, total: int, label: str) -> None:
            self.progress.emit(current, total, label)

        try:
            count, errors = import_campaign_entities(
                self._campaign_path,
                self._config,
                entity_types=self._entity_types,
                overwrite=self._overwrite,
                progress_callback=_progress,
            )
            self.finished_import.emit(count, errors)
        except Exception as exc:
            self.finished_import.emit(0, [str(exc)])


class _ExportWorker(QThread):
    """Background worker for scanning and exporting FGU notes."""

    scan_done: Signal = Signal(list)
    export_done: Signal = Signal(int, list)

    def __init__(
        self,
        mode: str,
        vault_path: Optional[Path] = None,
        note_paths: Optional[List[Path]] = None,
        output_path: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._vault_path = vault_path
        self._note_paths = note_paths or []
        self._output_path = output_path

    def run(self) -> None:
        if self._mode == "scan":
            try:
                self.scan_done.emit(read_fgu_notes_in_vault(self._vault_path or Path()))
            except Exception:
                self.scan_done.emit([])
            return

        if self._mode == "export":
            try:
                if self._output_path is None:
                    raise ValueError("No export output path set")
                count, errors = export_entities_to_xml(
                    self._note_paths,
                    self._output_path,
                )
                self.export_done.emit(count, errors)
            except Exception as exc:
                self.export_done.emit(0, [str(exc)])


class FGUPanel(QDockWidget):
    """
    Dockable Fantasy Grounds Unity integration panel.

    Signals:
        status_message(msg) — forwarded to main window status bar
    """

    status_message: Signal = Signal(str)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Fantasy Grounds", parent)
        self.setObjectName("FGUPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable    |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable  |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config = config
        self._run_command = run_command
        self._parser: Optional[FGUCampaignParser] = None
        self._campaigns: Dict[str, Path] = {}
        self._export_path: str = ""
        self._import_worker: Optional[_ImportWorker] = None
        self._export_worker: Optional[_ExportWorker] = None
        self._export_note_data: List[Tuple[Path, Dict[str, object]]] = []
        self._active_import_campaign: Optional[Path] = None
        self._active_export_path: Optional[Path] = None

        self._settings = QSettings("ProjectCeres", "GMAssistant")

        self._build_ui()

        # Auto-detect on a short delay so the window fully opens first
        QTimer.singleShot(500, self._auto_detect_campaigns)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── Campaign selector ──
        cam_row = QHBoxLayout()

        cam_lbl = QLabel("Campaign:")
        cam_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        cam_row.addWidget(cam_lbl)

        self._campaign_combo = QComboBox()
        self._campaign_combo.setPlaceholderText("— detecting FGU… —")
        self._campaign_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._campaign_combo.currentIndexChanged.connect(self._on_campaign_selected)
        cam_row.addWidget(self._campaign_combo)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Re-scan FGU campaign folders")
        refresh_btn.clicked.connect(self._auto_detect_campaigns)
        cam_row.addWidget(refresh_btn)

        browse_btn = QPushButton("📁")
        browse_btn.setFixedWidth(28)
        browse_btn.setToolTip("Browse to campaign folder manually")
        browse_btn.clicked.connect(self._browse_campaign)
        cam_row.addWidget(browse_btn)

        layout.addLayout(cam_row)

        # ── Status label ──
        self._db_status = QLabel("No campaign loaded.")
        self._db_status.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._db_status.setWordWrap(True)
        layout.addWidget(self._db_status)

        # ── Entity tabs ──
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._char_tree  = self._make_tree(["Name", "Class", "HP", "AC"])
        self._npc_tree   = self._make_tree(["Name", "Type / CR", "HP", "AC"])
        self._item_tree  = self._make_tree(["Name", "Type", "Rarity", "Cost"])

        self._tabs.addTab(self._wrap_tab(self._char_tree),  "🧙 Characters")
        self._tabs.addTab(self._wrap_tab(self._npc_tree),   "👹 NPCs")
        self._tabs.addTab(self._wrap_tab(self._item_tree),  "🗡 Items")
        self._tabs.addTab(self._build_import_tab(), "📥 Import")
        self._tabs.addTab(self._build_export_tab(), "📤 Export")

        layout.addWidget(self._tabs)

        # ── Filter ──
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("🔍  Filter…")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._import_sel_btn = QPushButton("→ Import Selected")
        self._import_sel_btn.setProperty("class", "accent")
        self._import_sel_btn.setEnabled(False)
        self._import_sel_btn.setToolTip("Import selected entity to current Obsidian vault")
        self._import_sel_btn.clicked.connect(self._import_selected)
        btn_row.addWidget(self._import_sel_btn)

        self._import_all_btn = QPushButton("→ Import All")
        self._import_all_btn.setEnabled(False)
        self._import_all_btn.setToolTip("Import all entities in the current tab")
        self._import_all_btn.clicked.connect(self._import_all)
        btn_row.addWidget(self._import_all_btn)

        self._preview_btn = QPushButton("👁 Preview")
        self._preview_btn.setEnabled(False)
        self._preview_btn.setToolTip("Preview the markdown that will be created")
        self._preview_btn.clicked.connect(self._preview_selected)
        btn_row.addWidget(self._preview_btn)

        layout.addLayout(btn_row)

        self.setWidget(outer)

    @staticmethod
    def _make_tree(headers) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)  # type: ignore[attr-defined]
        tree.setSortingEnabled(True)
        tree.setColumnWidth(0, 160)
        tree.setColumnWidth(1, 110)
        tree.setColumnWidth(2, 50)
        tree.setColumnWidth(3, 50)
        return tree

    @staticmethod
    def _wrap_tab(tree: QTreeWidget) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.addWidget(tree)
        return w

    def _build_import_tab(self) -> QWidget:
        """Build the campaign import tab UI."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        ruleset_row = QHBoxLayout()
        ruleset_row.addWidget(QLabel("Ruleset:"))
        self._ruleset_lbl = QLabel("Load a campaign first")
        self._ruleset_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        ruleset_row.addWidget(self._ruleset_lbl, 1)
        layout.addLayout(ruleset_row)

        checks_row = QHBoxLayout()
        checks_row.setSpacing(10)
        self._import_npcs_cb = QCheckBox("NPCs")
        self._import_pcs_cb = QCheckBox("PCs")
        self._import_items_cb = QCheckBox("Items")
        self._import_encounters_cb = QCheckBox("Encounters")
        self._import_notes_cb = QCheckBox("Notes")
        for checkbox in (
            self._import_npcs_cb,
            self._import_pcs_cb,
            self._import_items_cb,
            self._import_encounters_cb,
            self._import_notes_cb,
        ):
            checkbox.setChecked(True)
            checkbox.setStyleSheet(f"color: {TEXT};")
            checks_row.addWidget(checkbox)
        checks_row.addStretch(1)
        layout.addLayout(checks_row)

        self._overwrite_cb = QCheckBox("Overwrite existing notes")
        self._overwrite_cb.setStyleSheet(f"color: {TEXT};")
        layout.addWidget(self._overwrite_cb)

        self._import_tab_button = QPushButton("Import Campaign")
        self._import_tab_button.setStyleSheet(
            f"background: {SUCCESS}; color: white; font-weight: bold;"
        )
        self._import_tab_button.clicked.connect(self._on_import_clicked)
        layout.addWidget(self._import_tab_button)

        self._import_progress = QProgressBar()
        self._import_progress.setRange(0, 100)
        self._import_progress.setValue(0)
        self._import_progress.setVisible(False)
        self._import_progress.setStyleSheet(
            f"QProgressBar {{ background: {SURFACE}; color: {TEXT}; "
            f"border: 1px solid {MUTED}; border-radius: 3px; }}"
        )
        layout.addWidget(self._import_progress)

        self._import_log = QTextEdit()
        self._import_log.setReadOnly(True)
        self._import_log.setStyleSheet(
            f"background: {PANEL}; color: {TEXT}; "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        layout.addWidget(self._import_log, 1)
        return tab

    def _build_export_tab(self) -> QWidget:
        """Build the campaign export tab UI."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        scan_row = QHBoxLayout()
        self._export_scan_btn = QPushButton("Scan Vault for FGU Notes")
        self._export_scan_btn.clicked.connect(self._start_export_scan)
        scan_row.addWidget(self._export_scan_btn)
        self._export_scan_lbl = QLabel("")
        self._export_scan_lbl.setStyleSheet(f"color: {MUTED};")
        scan_row.addWidget(self._export_scan_lbl, 1)
        layout.addLayout(scan_row)

        self._export_list = QListWidget()
        self._export_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # type: ignore[attr-defined]
        self._export_list.setMinimumHeight(180)
        self._export_list.setStyleSheet(
            f"background: {SURFACE}; color: {TEXT}; border: 1px solid {MUTED};"
        )
        layout.addWidget(self._export_list, 1)

        btn_row = QHBoxLayout()
        self._export_sel_btn = QPushButton("Export Selected")
        self._export_sel_btn.setEnabled(False)
        self._export_sel_btn.clicked.connect(lambda: self._start_export(True))
        btn_row.addWidget(self._export_sel_btn)

        self._export_all_btn = QPushButton("Export All")
        self._export_all_btn.setEnabled(False)
        self._export_all_btn.clicked.connect(lambda: self._start_export(False))
        btn_row.addWidget(self._export_all_btn)
        layout.addLayout(btn_row)

        self._export_log = QTextEdit()
        self._export_log.setReadOnly(True)
        self._export_log.setStyleSheet(
            f"background: {PANEL}; color: {TEXT}; "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        layout.addWidget(self._export_log)
        return tab

    def _on_choose_export_file(self) -> None:
        """Choose output XML path for export."""
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Export Output",
            self._export_path or "",
            "XML files (*.xml)",
        )
        if not selected:
            return
        self._export_path = selected
        if hasattr(self, "_export_path_edit"):
            self._export_path_edit.setText(selected)

    def _on_import_clicked(self) -> None:
        """Start a background import for selected entity types."""
        campaign_data = self._campaign_combo.currentData()
        if not campaign_data:
            QMessageBox.warning(
                self,
                "No Campaign Selected",
                "Select a campaign before importing.",
            )
            return

        selected_types = []
        if self._import_npcs_cb.isChecked():
            selected_types.append("npc")
        if self._import_pcs_cb.isChecked():
            selected_types.append("pc")
        if self._import_items_cb.isChecked():
            selected_types.append("item")
        if self._import_encounters_cb.isChecked():
            selected_types.append("encounter")
        if self._import_notes_cb.isChecked():
            selected_types.append("note")

        entity_types = tuple(selected_types)
        if not entity_types:
            QMessageBox.warning(
                self,
                "Nothing Selected",
                "Choose at least one entity type to import.",
            )
            return

        if (
            not self._config
            or not self._config.current_vault
            or self._config.current_vault not in (self._config.vaults or {})
        ):
            self._import_log.append("No active vault. Select one in Vault / Notes first.")
            return

        if self._import_worker is not None and self._import_worker.isRunning():
            self._import_log.append("Import already running.")
            return

        campaign_path = Path(campaign_data)
        self._active_import_campaign = campaign_path
        self._import_log.clear()
        self._import_log.append(f"Starting import: {campaign_path.name}")
        self._import_progress.setValue(0)
        self._import_progress.setVisible(True)
        self._import_tab_button.setEnabled(False)

        self._import_worker = _ImportWorker(
            campaign_path,
            self._config,
            entity_types,
            self._overwrite_cb.isChecked(),
            self,
        )
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished_import.connect(self._on_import_finished)
        self._import_worker.start()

    def _on_import_progress(self, current: int, total: int, label: str) -> None:
        """Update import progress UI from the worker thread."""
        if total > 0:
            self._import_progress.setValue(int((current / total) * 100))
        self._import_log.append(f"[{current}/{total}] {label}")
        sb = self._import_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_import_finished(self, count: int, errors: list) -> None:
        """Finish import UI state after the worker exits."""
        self._import_progress.setValue(100)
        self._import_tab_button.setEnabled(True)
        self._import_log.append(f"Imported {count} note(s).")
        if errors:
            self._import_log.append(f"{len(errors)} warning/error(s):")
            for err in errors[:20]:
                self._import_log.append(f"  - {err}")

        campaign_path = self._active_import_campaign
        if campaign_path is not None:
            set_current_object(
                self._config,
                WorkspaceObjectRef(
                    kind="fgu_import",
                    path=str(campaign_path),
                    title=campaign_path.name,
                    source="fgu_panel",
                    metadata={"imported_count": count, "errors": len(errors)},
                ),
            )
        self.status_message.emit(f"FGU import: {count} note(s), {len(errors)} issue(s)")
        self._import_worker = None

    def _on_export_clicked(self) -> None:
        """Compatibility entrypoint: export every scanned note."""
        self._start_export(selected_only=False)

    def _start_export_scan(self) -> None:
        """Scan the active vault for FGU-tagged notes."""
        if (
            not self._config
            or not self._config.current_vault
            or self._config.current_vault not in (self._config.vaults or {})
        ):
            self._export_log.append("No active vault. Select one in Vault / Notes first.")
            return

        if self._export_worker is not None and self._export_worker.isRunning():
            self._export_log.append("Export task already running.")
            return

        vault_path = Path(self._config.vaults[self._config.current_vault])
        self._export_log.clear()
        self._export_log.append(f"Scanning: {vault_path}")
        self._export_scan_lbl.setText("Scanning...")
        self._export_scan_btn.setEnabled(False)
        self._export_sel_btn.setEnabled(False)
        self._export_all_btn.setEnabled(False)
        self._export_list.clear()

        self._export_worker = _ExportWorker("scan", vault_path=vault_path, parent=self)
        self._export_worker.scan_done.connect(self._on_export_scan_done)
        self._export_worker.start()

    def _on_export_scan_done(self, results: list) -> None:
        """Populate the export note list after a scan."""
        self._export_note_data = results
        self._export_list.clear()
        for note_path, fm in results:
            label = (
                f"{fm.get('name', Path(note_path).stem)} "
                f"[{fm.get('fgu_system', '?')} / {fm.get('fgu_record_class', '?')}]"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(note_path))  # type: ignore[attr-defined]
            self._export_list.addItem(item)

        count = len(results)
        self._export_scan_lbl.setText(f"{count} note(s) found")
        self._export_log.append(f"Found {count} FGU note(s).")
        self._export_scan_btn.setEnabled(True)
        self._export_sel_btn.setEnabled(count > 0)
        self._export_all_btn.setEnabled(count > 0)
        self._export_worker = None

    def _start_export(self, selected_only: bool) -> None:
        """Export selected or all scanned FGU notes."""
        if selected_only:
            selected_rows = {
                self._export_list.row(item)
                for item in self._export_list.selectedItems()
            }
            note_paths = [
                path for index, (path, _fm) in enumerate(self._export_note_data)
                if index in selected_rows
            ]
        else:
            note_paths = [path for path, _fm in self._export_note_data]

        if not note_paths:
            self._export_log.append("Nothing to export. Scan and select notes first.")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save FGU Export XML",
            self._export_path or str(Path.home() / "fgu_export.xml"),
            "XML files (*.xml);;All files (*)",
        )
        if not output_path:
            return

        self._export_path = output_path
        self._active_export_path = Path(output_path)
        self._export_log.clear()
        self._export_log.append(f"Exporting {len(note_paths)} note(s) to {output_path}")
        self._export_sel_btn.setEnabled(False)
        self._export_all_btn.setEnabled(False)

        self._export_worker = _ExportWorker(
            "export",
            note_paths=note_paths,
            output_path=Path(output_path),
            parent=self,
        )
        self._export_worker.export_done.connect(self._on_export_done)
        self._export_worker.start()

    def _on_export_done(self, count: int, errors: list) -> None:
        """Finish export UI state after the worker exits."""
        self._export_log.append(f"Exported {count} record(s).")
        if errors:
            self._export_log.append(f"{len(errors)} warning/error(s):")
            for err in errors[:20]:
                self._export_log.append(f"  - {err}")

        self._export_sel_btn.setEnabled(bool(self._export_note_data))
        self._export_all_btn.setEnabled(bool(self._export_note_data))
        if self._active_export_path is not None:
            set_current_object(
                self._config,
                WorkspaceObjectRef(
                    kind="fgu_export",
                    path=str(self._active_export_path),
                    title=self._active_export_path.name,
                    source="fgu_panel",
                    metadata={"exported_count": count, "errors": len(errors)},
                ),
            )
        self.status_message.emit(f"FGU export: {count} record(s), {len(errors)} issue(s)")
        self._export_worker = None

    # ── Campaign detection ─────────────────────────────────────────────────────

    def _auto_detect_campaigns(self) -> None:
        # 1. Standard auto-detect from known AppData/Documents paths
        self._campaigns = find_campaign_folders()

        # 2. Also scan the user's saved campaigns root (if set and different)
        saved_root = getattr(self._config, "fgu_campaigns_root", None)
        if saved_root is not None:
            from pathlib import Path as _Path
            extra = scan_campaigns_in_folder(_Path(saved_root))
            # Merge — saved root takes precedence for same-named campaigns
            self._campaigns.update(extra)

        self._campaign_combo.blockSignals(True)
        self._campaign_combo.clear()

        if self._campaigns:
            for name in sorted(self._campaigns):
                self._campaign_combo.addItem(name, userData=str(self._campaigns[name]))
            source = f" (from {saved_root})" if saved_root and not find_campaign_folders() else ""
            self._db_status.setText(f"Found {len(self._campaigns)} campaign(s){source}.")
            self._db_status.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
        else:
            self._campaign_combo.setPlaceholderText("— FGU not found —")
            self._db_status.setText(
                "FGU campaigns not found.\n"
                "Use 📁 to browse to your campaigns folder, or check that FGU is installed."
            )
            self._db_status.setStyleSheet(f"color: {WARNING}; font-size: 10px;")

        self._campaign_combo.blockSignals(False)

        if self._campaigns:
            # Try to restore the last-used campaign; fall back to index 0
            last = self._settings.value("fgu/last_campaign", "", type=str)
            idx = self._campaign_combo.findText(last) if last else -1
            self._campaign_combo.setCurrentIndex(idx if idx >= 0 else 0)
            # currentIndexChanged may not fire if index didn't change; force load
            self._load_campaign()

    def _browse_campaign(self) -> None:
        # Start from the saved campaigns root if we have one
        start_dir = str(
            getattr(self._config, "fgu_campaigns_root", None) or Path.home()
        )
        folder = QFileDialog.getExistingDirectory(
            self, "Select FGU Campaign or Campaigns Folder", start_dir
        )
        if not folder:
            return

        path = Path(folder)
        found = scan_campaigns_in_folder(path)

        if not found:
            QMessageBox.warning(
                self, "No FGU Campaigns Found",
                f"No db.xml files found in:\n{path}\n\n"
                "Select either a campaign folder (containing db.xml) or\n"
                "a campaigns root folder (containing campaign sub-folders)."
            )
            return

        # If it's a campaigns root (user picked the parent folder) save it
        if not (path / "db.xml").exists() and len(found) > 0:
            if self._config is not None:
                self._config.fgu_campaigns_root = path
                try:
                    self._config.save_settings()
                except Exception:
                    pass
            self._db_status.setText(
                f"Campaigns root saved: {path}\n"
                f"Found {len(found)} campaign(s) — will remember for next launch."
            )
            self._db_status.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")

        # Merge into current campaigns and repopulate combo
        self._campaigns.update(found)
        self._campaign_combo.blockSignals(True)
        for name, camp_path in sorted(found.items()):
            idx = self._campaign_combo.findText(name)
            if idx == -1:
                self._campaign_combo.addItem(name, userData=str(camp_path))
                idx = self._campaign_combo.count() - 1
        self._campaign_combo.blockSignals(False)

        # Select the first newly added campaign
        first_name = next(iter(sorted(found)))
        select_idx = self._campaign_combo.findText(first_name)
        if select_idx >= 0:
            self._campaign_combo.setCurrentIndex(select_idx)
        else:
            self._load_campaign()

    def _on_campaign_selected(self, index: int) -> None:
        if index >= 0:
            self._load_campaign()

    def _load_campaign(self) -> None:
        data = self._campaign_combo.currentData()
        name = self._campaign_combo.currentText()
        if not data:
            return

        campaign_path = Path(data)
        self._parser = FGUCampaignParser(campaign_path)
        self._db_status.setText(f"Loading {name}…")
        self._db_status.setStyleSheet(f"color: {MUTED}; font-size: 10px;")

        ok = self._parser.load()
        if not ok:
            self._db_status.setText(f"Error: {self._parser.error}")
            self._db_status.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
            return

        n_chars = len(self._parser.characters)
        n_npcs  = len(self._parser.npcs)
        n_items = len(self._parser.items)

        self._db_status.setText(
            f"{name}  ·  {n_chars} PC(s)  ·  {n_npcs} NPC(s)  ·  {n_items} item(s)"
        )
        self._db_status.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
        if hasattr(self, "_ruleset_lbl"):
            self._ruleset_lbl.setText(detect_ruleset(campaign_path))
        self._settings.setValue("fgu/last_campaign", name)
        self.status_message.emit(f"FGU: {name} loaded")

        self._populate_trees()
        self._import_sel_btn.setEnabled(True)
        self._import_all_btn.setEnabled(True)
        self._preview_btn.setEnabled(True)

    # ── Tree population ────────────────────────────────────────────────────────

    def _populate_trees(self) -> None:
        if self._parser is None:
            return

        # Characters
        self._char_tree.clear()
        for char in sorted(self._parser.characters.values(), key=lambda c: c.name):
            item = QTreeWidgetItem([
                char.name,
                char.class_string or "—",
                f"{char.hp_current}/{char.hp_max}",
                str(char.ac),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, char.fgu_id)  # type: ignore[attr-defined]
            item.setData(0, Qt.ItemDataRole.UserRole + 1, "char")  # type: ignore[attr-defined]
            self._char_tree.addTopLevelItem(item)

        # NPCs
        self._npc_tree.clear()
        for npc in sorted(self._parser.npcs.values(), key=lambda n: n.name):
            cr_str = f"CR {npc.cr}" if npc.cr else ""
            type_cr = f"{npc.npc_type[:20] if npc.npc_type else '—'}  {cr_str}".strip()
            item = QTreeWidgetItem([
                npc.name,
                type_cr,
                str(npc.hp_max),
                str(npc.ac),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, npc.fgu_id)  # type: ignore[attr-defined]
            item.setData(0, Qt.ItemDataRole.UserRole + 1, "npc")  # type: ignore[attr-defined]
            self._npc_tree.addTopLevelItem(item)

        # Items
        self._item_tree.clear()
        for itm in sorted(self._parser.items.values(), key=lambda i: i.name):
            item = QTreeWidgetItem([
                itm.name,
                itm.item_type or "—",
                itm.rarity or "—",
                itm.cost or "—",
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, itm.fgu_id)  # type: ignore[attr-defined]
            item.setData(0, Qt.ItemDataRole.UserRole + 1, "item")  # type: ignore[attr-defined]
            self._item_tree.addTopLevelItem(item)

        self._apply_filter(self._filter.text())

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        for tree in (self._char_tree, self._npc_tree, self._item_tree):
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                match = not text or any(
                    text in (item.text(col) or "").lower()
                    for col in range(tree.columnCount())
                )
                item.setHidden(not match)

    # ── Current selection helpers ──────────────────────────────────────────────

    def _current_tree(self) -> QTreeWidget:
        tab = self._tabs.currentIndex()
        return {
            TAB_CHARS: self._char_tree,
            TAB_NPCS: self._npc_tree,
            TAB_ITEMS: self._item_tree,
        }.get(tab, self._char_tree)

    def _resolve_entity(self, fgu_id: str, kind: str):
        """Return the parsed entity object from the parser."""
        if self._parser is None:
            return None
        if kind == "char":
            return self._parser.characters.get(fgu_id)
        if kind == "npc":
            return self._parser.npcs.get(fgu_id)
        if kind == "item":
            return self._parser.items.get(fgu_id)
        return None

    def _entity_from_item(self, tree_item: QTreeWidgetItem):
        fgu_id = tree_item.data(0, Qt.ItemDataRole.UserRole)   # type: ignore[attr-defined]
        kind   = tree_item.data(0, Qt.ItemDataRole.UserRole + 1)  # type: ignore[attr-defined]
        return self._resolve_entity(fgu_id, kind)

    # ── Import ─────────────────────────────────────────────────────────────────

    def _get_vault_path(self) -> Optional[Path]:
        if (
            self._config
            and self._config.current_vault
            and self._config.current_vault in (self._config.vaults or {})
        ):
            return Path(self._config.vaults[self._config.current_vault])
        QMessageBox.warning(
            self, "No Vault Selected",
            "Please select an Obsidian vault in the Vault / Notes panel first."
        )
        return None

    def _import_selected(self) -> None:
        vault_path = self._get_vault_path()
        if vault_path is None:
            return

        tree = self._current_tree()
        selected = tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Nothing Selected", "Select one or more entries to import.")
            return

        imported, skipped, errors = 0, 0, []
        for tree_item in selected:
            entity = self._entity_from_item(tree_item)
            if entity is None:
                continue
            try:
                note_path = import_entity_to_vault(entity, vault_path)
                imported += 1
                self.status_message.emit(f"Imported: {note_path.name}")
            except FileExistsError:
                reply = QMessageBox.question(
                    self, "Already Exists",
                    f'"{entity.name}" already exists in vault. Overwrite?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        import_entity_to_vault(entity, vault_path, overwrite=True)
                        imported += 1
                    except Exception as e:
                        errors.append(f"{entity.name}: {e}")
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{entity.name}: {e}")

        msg = f"Imported {imported}"
        if skipped:
            msg += f", skipped {skipped}"
        if errors:
            msg += f", {len(errors)} error(s)"
            QMessageBox.warning(self, "Import Errors", "\n".join(errors))
        self._db_status.setText(msg)
        self.status_message.emit(msg)

    def _import_all(self) -> None:
        vault_path = self._get_vault_path()
        if vault_path is None:
            return
        if self._parser is None:
            return

        tab = self._tabs.currentIndex()
        entities = []
        if tab == TAB_CHARS:
            entities = list(self._parser.characters.values())
        elif tab == TAB_NPCS:
            entities = list(self._parser.npcs.values())
        elif tab == TAB_ITEMS:
            entities = list(self._parser.items.values())

        if not entities:
            QMessageBox.information(self, "Nothing to Import", "No entries loaded in this tab.")
            return

        reply = QMessageBox.question(
            self, "Import All",
            f"Import all {len(entities)} entries to vault?\n"
            f"Existing notes will be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        entity_types = {
            TAB_CHARS: ("pc",),
            TAB_NPCS: ("npc",),
            TAB_ITEMS: ("item",),
        }.get(tab, ())

        imported, errors = import_campaign_entities(
            Path(self._campaign_combo.currentData()),
            self._config,
            entity_types=entity_types,
            overwrite=True,
        )

        msg = f"Imported {imported}/{len(entities)}"
        if errors:
            QMessageBox.warning(self, "Import Errors", "\n".join(errors[:10]))
        set_current_object(
            self._config,
            WorkspaceObjectRef(
                kind="fgu_import",
                path=str(Path(self._campaign_combo.currentData())),
                title=Path(self._campaign_combo.currentData()).name,
                source="fgu_panel",
                metadata={"imported_count": imported, "errors": len(errors)},
            ),
        )
        self._db_status.setText(msg)
        self.status_message.emit(msg)

    # ── Preview ────────────────────────────────────────────────────────────────

    def _preview_selected(self) -> None:
        tree = self._current_tree()
        selected = tree.selectedItems()
        if not selected:
            return

        entity = self._entity_from_item(selected[0])
        if entity is None:
            return

        if isinstance(entity, FGUCharacter):
            md = character_to_markdown(entity)
        elif isinstance(entity, FGUNPC):
            md = npc_to_markdown(entity)
        elif isinstance(entity, FGUItem):
            md = item_to_markdown(entity)
        else:
            return

        dlg = _PreviewDialog(entity.name, md, self)
        dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()  # type: ignore[attr-defined]

    def closeEvent(self, event) -> None:
        """Stop background workers before the panel closes."""
        for worker in (self._import_worker, self._export_worker):
            if worker is not None and worker.isRunning():
                worker.quit()
                worker.wait(2000)
        super().closeEvent(event)


# ── Preview dialog ─────────────────────────────────────────────────────────────

class _PreviewDialog:
    """Simple modal dialog showing the markdown preview of an entity."""

    def __init__(self, title: str, markdown: str, parent=None) -> None:
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        except ImportError:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox  # type: ignore

        self._dlg = __import__(
            "PyQt5.QtWidgets" if "PyQt5" in __import__("sys").modules else "PySide6.QtWidgets",
            fromlist=["QDialog"]
        ).QDialog(parent)
        self._dlg.setWindowTitle(f"Preview — {title}")
        self._dlg.resize(600, 500)

        layout = __import__(
            "PyQt5.QtWidgets" if "PyQt5" in __import__("sys").modules else "PySide6.QtWidgets",
            fromlist=["QVBoxLayout"]
        ).QVBoxLayout(self._dlg)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(markdown)
        txt.setStyleSheet(f"background: {PANEL}; color: {TEXT}; font-family: Consolas, monospace;")
        layout.addWidget(txt)

        from PyQt5.QtWidgets import QDialogButtonBox as DBB
        btns = DBB(DBB.StandardButton.Close)
        btns.rejected.connect(self._dlg.reject)
        layout.addWidget(btns)

    def exec(self):
        return self._dlg.exec()

    def exec_(self):
        return self._dlg.exec_()  # type: ignore[attr-defined]
