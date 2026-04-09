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
from typing import Callable, Dict, Optional, Union

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QLineEdit, QFileDialog, QSizePolicy,
        QMessageBox, QTextEdit, QSplitter, QApplication,
    )
    from PyQt5.QtCore import Qt, QTimer, QSettings, pyqtSignal as Signal
    from PyQt5.QtGui import QColor, QFont
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem,
        QTabWidget, QLineEdit, QFileDialog, QSizePolicy,
        QMessageBox, QTextEdit, QSplitter, QApplication,
    )
    from PySide6.QtCore import Qt, QTimer, QSettings, Signal  # type: ignore
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

# Tab indices
TAB_CHARS = 0
TAB_NPCS  = 1
TAB_ITEMS = 2

# TreeWidget column indices
COL_NAME   = 0
COL_DETAIL = 1
COL_HP     = 2
COL_AC     = 3


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
        return [self._char_tree, self._npc_tree, self._item_tree][tab]

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

        imported, errors = 0, []
        for entity in entities:
            try:
                import_entity_to_vault(entity, vault_path, overwrite=True)
                imported += 1
            except Exception as e:
                errors.append(f"{entity.name}: {e}")

        msg = f"Imported {imported}/{len(entities)}"
        if errors:
            QMessageBox.warning(self, "Import Errors", "\n".join(errors[:10]))
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
