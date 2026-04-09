"""
Vault / Notes panel for Project Ceres — GM Assistant UI.

A QDockWidget that lets the GM:
  • Switch between registered Obsidian vaults
  • Browse the note tree (folders + .md files)
  • Create / open / search notes
  • Run note-related backend commands via run_command()

Layout
------
  ┌─ VAULT / NOTES ──────────────────────────────┐
  │ [◉ Vault: ▾ GMAssistantVault        ] [⟳]   │
  ├──────────────────────────────────────────────│
  │ 🔍 [search filter          ]                 │
  ├──────────────────────────────────────────────│
  │ ▶ Characters/                                │
  │   ├─ Aragorn.md                              │
  │   └─ Gandalf.md                              │
  │ ▶ Locations/                                 │
  │ ▶ Sessions/                                  │
  ├──────────────────────────────────────────────│
  │ [+ New Note] [⊞ New Folder] [✎ Open] [🔍 FTS]│
  └──────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QLineEdit, QTreeWidget,
        QTreeWidgetItem, QSizePolicy, QMessageBox, QInputDialog, QMenu,
        QApplication,
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QColor
    _SIGNAL = "pyqt5"
    from PyQt5.QtCore import pyqtSignal as Signal
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QLineEdit, QTreeWidget,
        QTreeWidgetItem, QSizePolicy, QMessageBox, QInputDialog, QMenu,
        QApplication,
    )
    from PySide6.QtCore import Qt, QTimer, Signal  # type: ignore
    from PySide6.QtGui import QColor  # type: ignore
    _SIGNAL = "pyside6"

from ui.theme import ACCENT, MUTED, TEXT


class VaultNotesPanel(QDockWidget):
    """
    Dockable panel for vault browsing and note management.

    Signals:
        note_opened(path)   — emitted when the user double-clicks a note
        status_message(msg) — emitted to push text to the main status bar
    """

    note_opened = Signal(str)
    status_message = Signal(str)

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Vault / Notes", parent)
        self._config = config
        self._run_command = run_command
        self._current_vault_path: Optional[Path] = None

        self.setObjectName("VaultNotesPanel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._build_ui()
        self._populate_vault_selector()
        self._refresh_tree()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(5)

        # Vault selector row
        vault_row = QHBoxLayout()
        vault_row.setSpacing(4)

        vault_lbl = QLabel("Vault:")
        vault_lbl.setFixedWidth(38)
        vault_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        vault_row.addWidget(vault_lbl)

        self._vault_combo = QComboBox()
        self._vault_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._vault_combo.setToolTip("Switch active vault")
        self._vault_combo.currentIndexChanged.connect(self._on_vault_changed)
        vault_row.addWidget(self._vault_combo)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(30)
        refresh_btn.setToolTip("Refresh vault tree")
        refresh_btn.clicked.connect(self._refresh_tree)
        vault_row.addWidget(refresh_btn)

        root_layout.addLayout(vault_row)

        # Search filter
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("🔍  Filter notes…")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)
        root_layout.addWidget(self._search_box)

        # Note tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Modified"])
        self._tree.setColumnWidth(0, 220)
        self._tree.setAlternatingRowColors(True)
        self._tree.setAnimated(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        root_layout.addWidget(self._tree)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        new_note_btn = QPushButton("+ Note")
        new_note_btn.setProperty("class", "accent")
        new_note_btn.setToolTip("Create a new note in the active vault")
        new_note_btn.clicked.connect(self._cmd_new_note)
        btn_row.addWidget(new_note_btn)

        new_folder_btn = QPushButton("⊞ Folder")
        new_folder_btn.setToolTip("Create a new folder")
        new_folder_btn.clicked.connect(self._cmd_new_folder)
        btn_row.addWidget(new_folder_btn)

        open_btn = QPushButton("✎ Open")
        open_btn.setToolTip("Open selected note in Obsidian")
        open_btn.clicked.connect(self._cmd_open_selected)
        btn_row.addWidget(open_btn)

        search_btn = QPushButton("🔍 FTS")
        search_btn.setToolTip("Full-text search across all notes")
        search_btn.clicked.connect(self._cmd_full_text_search)
        btn_row.addWidget(search_btn)

        root_layout.addLayout(btn_row)
        self.setWidget(container)

    # ── Vault selector ─────────────────────────────────────────────────────────

    def _populate_vault_selector(self) -> None:
        self._vault_combo.blockSignals(True)
        self._vault_combo.clear()
        vaults: Dict[str, str] = self._config.vaults or {}
        for name, path in vaults.items():
            self._vault_combo.addItem(name, userData=path)
        current = self._config.current_vault
        if current and current in vaults:
            idx = list(vaults.keys()).index(current)
            self._vault_combo.setCurrentIndex(idx)
        self._vault_combo.blockSignals(False)

    def refresh_vault_selector(self) -> None:
        """Public slot — call after vaults are added or removed."""
        self._populate_vault_selector()
        self._refresh_tree()

    def _on_vault_changed(self, index: int) -> None:
        if index < 0:
            return
        vault_name = self._vault_combo.currentText()
        vault_path = self._vault_combo.currentData()
        if vault_name and vault_name != self._config.current_vault:
            self._run_command("switch", vault_name, self._config)
            self.status_message.emit(f"Vault: {vault_name}")
        if vault_path:
            self._current_vault_path = Path(vault_path)
        self._refresh_tree()

    # ── Note tree ──────────────────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        self._tree.clear()
        vault_path = self._resolve_vault_path()
        if vault_path is None or not vault_path.exists():
            item = QTreeWidgetItem(["(no vault selected)"])
            item.setForeground(0, QColor(MUTED))
            self._tree.addTopLevelItem(item)
            return
        self._walk_directory(vault_path, self._tree.invisibleRootItem(), depth=0)
        self._tree.expandToDepth(1)
        self._apply_filter(self._search_box.text())
        self.status_message.emit(f"Vault: {vault_path.name}  |  {vault_path}")

    def _resolve_vault_path(self) -> Optional[Path]:
        data = self._vault_combo.currentData()
        if data:
            p = Path(data)
            if p.exists():
                return p
        current = self._config.current_vault
        vaults = self._config.vaults or {}
        if current and current in vaults:
            p = Path(vaults[current])
            if p.exists():
                return p
        return None

    def _walk_directory(self, directory: Path, parent_item, depth: int = 0) -> None:
        if depth > 10:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if entry.is_dir():
                folder_item = QTreeWidgetItem(parent_item, [f"📁 {entry.name}", ""])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                folder_item.setData(0, Qt.ItemDataRole.UserRole + 1, "folder")
                self._walk_directory(entry, folder_item, depth + 1)
            elif entry.suffix.lower() == ".md":
                try:
                    modified = datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d")
                except OSError:
                    modified = ""
                note_item = QTreeWidgetItem(parent_item, [f"📄 {entry.stem}", modified])
                note_item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                note_item.setData(0, Qt.ItemDataRole.UserRole + 1, "note")

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        self._filter_item(self._tree.invisibleRootItem(), text)

    def _filter_item(self, item, text: str) -> bool:
        child_visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            vis = self._filter_item(child, text)
            child_visible = child_visible or vis
        if item is self._tree.invisibleRootItem():
            return child_visible
        match = not text or text in item.text(0).lower()
        visible = match or child_visible
        item.setHidden(not visible)
        if child_visible and text:
            item.setExpanded(True)
        return visible

    # ── Interaction ────────────────────────────────────────────────────────────

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        kind = item.data(0, Qt.ItemDataRole.UserRole + 1)
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if kind == "note" and path:
            self.note_opened.emit(path)
            self.status_message.emit(f"Opened: {Path(path).name}")

    def _show_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        menu = QMenu(self._tree)
        if item:
            kind = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if kind == "note":
                menu.addAction("✎  Open in Obsidian", self._cmd_open_selected)
                menu.addAction("📋  Copy path", lambda: self._copy_path(item))
                menu.addSeparator()
                menu.addAction("🗑  Delete note", lambda: self._cmd_delete_note(item))
        else:
            menu.addAction("+ New note", self._cmd_new_note)
            menu.addAction("⟳ Refresh", self._refresh_tree)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _copy_path(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            QApplication.clipboard().setText(path)
            self.status_message.emit(f"Copied: {path}")

    # ── Backend command helpers ────────────────────────────────────────────────

    def _cmd_new_note(self) -> None:
        name, ok = QInputDialog.getText(self, "New Note", "Note name:")
        if ok and name.strip():
            self._run_command("createnote", name.strip(), self._config)
            QTimer.singleShot(300, self._refresh_tree)

    def _cmd_new_folder(self) -> None:
        vault_path = self._resolve_vault_path()
        if vault_path is None:
            QMessageBox.warning(self, "No Vault", "Please select a vault first.")
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            new_dir = vault_path / name.strip()
            try:
                new_dir.mkdir(parents=True, exist_ok=True)
                self.status_message.emit(f"Created folder: {new_dir.name}")
            except OSError as e:
                QMessageBox.critical(self, "Error", f"Could not create folder:\n{e}")
            QTimer.singleShot(100, self._refresh_tree)

    def _cmd_open_selected(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        kind = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if kind != "note" or not path:
            return
        try:
            import subprocess
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self.status_message.emit(f"Opened: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Open Failed", str(e))

    def _cmd_full_text_search(self) -> None:
        query, ok = QInputDialog.getText(self, "Full-Text Search", "Search notes:")
        if ok and query.strip():
            self._run_command("search", query.strip(), self._config)

    def _cmd_delete_note(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        name = Path(path).name
        reply = QMessageBox.question(
            self, "Delete Note",
            f"Permanently delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                Path(path).unlink()
                self.status_message.emit(f"Deleted: {name}")
                QTimer.singleShot(100, self._refresh_tree)
            except OSError as e:
                QMessageBox.critical(self, "Delete Failed", str(e))
