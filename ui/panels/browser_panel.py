"""
Browser Panel for Project Ceres — GM Assistant UI.

An embedded web browser with two GM-focused features layered on top:

  1. Clip to Obsidian — select any text on a page and save it as a
     formatted markdown note in the active vault, with YAML frontmatter,
     source URL, and blockquote body.

  2. Bookmark manager — pre-loaded with popular TTRPG websites, fully
     editable, persisted via QSettings.

Layout
------
  ┌─ BROWSER ─────────────────────────────────────────────────────────┐
  │ [←][→][↺][ address / search …                          ][🔖▾][+] │
  │ [✂ Clip to Obsidian]  [🗂 Research ▾]  [🏷 tags …]               │
  ├───────────────────────────────────────────────────────────────────┤
  │                       QWebEngineView                              │
  ├───────────────────────────────────────────────────────────────────┤
  │ ● https://dndbeyond.com/…                         Loading 47%    │
  └───────────────────────────────────────────────────────────────────┘

Requirements
------------
    pip install PyQtWebEngine      # for PyQt5
    # or just use PySide6 which bundles QtWebEngine

Notes
-----
- If PyQtWebEngine is not installed a friendly fallback message is shown.
- Text selection uses JavaScript: window.getSelection().toString()
- Clips are saved as Obsidian-compatible markdown with YAML frontmatter.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

_QT_BINDING = "PyQt5"
try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QComboBox,
        QDialog, QDialogButtonBox, QTextEdit, QFormLayout,
        QMenu, QAction, QMessageBox, QSizePolicy, QFrame,
        QInputDialog, QScrollArea,
    )
    from PyQt5.QtCore import Qt, QUrl, QSettings, pyqtSignal as Signal
    from PyQt5.QtGui import QFont
except ImportError:
    _QT_BINDING = "PySide6"
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QComboBox,
        QDialog, QDialogButtonBox, QTextEdit, QFormLayout,
        QMenu, QAction, QMessageBox, QSizePolicy, QFrame,
        QInputDialog, QScrollArea,
    )
    from PySide6.QtCore import Qt, QUrl, QSettings, Signal  # type: ignore
    from PySide6.QtGui import QFont  # type: ignore

from ui.theme import ACCENT, BG, BORDER, MUTED, TEXT, PANEL, SURFACE, SUCCESS, ERROR

# ── Web engine — import ONLY from the same binding used for widgets ───────────
# Mixing PyQt5 (Qt5) and PySide6 (Qt6) in one process is a fatal conflict.

_WEBENGINE_OK = False
if _QT_BINDING == "PyQt5":
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView  # type: ignore
        _WEBENGINE_OK = True
    except ImportError:
        pass
else:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
        _WEBENGINE_OK = True
    except ImportError:
        pass

# ── Pre-loaded TTRPG bookmarks ─────────────────────────────────────────────────

DEFAULT_BOOKMARKS: List[Tuple[str, str]] = [
    ("D&D Beyond",           "https://www.dndbeyond.com"),
    ("D&D 5e SRD API",       "https://www.dnd5eapi.co/docs/2014/"),
    ("Syrinscape Online",    "https://syrinscape.com/online/frontend/"),
    ("Roll20",               "https://roll20.net"),
    ("Foundry VTT",          "https://foundryvtt.com"),
    ("Pathfinder 2e SRD",    "https://2e.aonprd.com"),
    ("Donjon RPG Tools",     "https://donjon.bin.sh"),
    ("Improved Initiative",  "https://www.improved-initiative.com"),
    ("Kobold Fight Club",    "https://koboldplus.club"),
    ("r/rpg",                "https://www.reddit.com/r/rpg/"),
]

# Vault sub-folders offered in the Clip dialog
CLIP_FOLDERS: List[str] = [
    "Research",
    "Reference",
    "Sessions/Notes",
    "Characters",
    "Locations",
    "Items",
    "NPCs",
    "(vault root)",
]

_JS_GET_SELECTION = "window.getSelection().toString()"


def _dialog_accepted(result: object) -> bool:
    """PyQt5 returns QDialog.Accepted; PySide6 returns QDialog.DialogCode.Accepted."""
    try:
        if result == QDialog.Accepted:  # type: ignore[attr-defined]
            return True
    except AttributeError:
        pass
    dc = getattr(QDialog, "DialogCode", None)
    if dc is not None:
        try:
            return bool(result == dc.Accepted)
        except Exception:
            pass
    return result == 1


def _safe_filename(text: str, max_len: int = 60) -> str:
    """Convert a page title into a safe filesystem stem."""
    text = re.sub(r'[\\/*?:"<>|]', "_", text).strip().strip(".")
    text = re.sub(r"\s+", " ", text)
    return text[:max_len] if text else "Clipped_Page"


def _resolve_url(raw: str) -> str:
    """
    Turn address-bar input into a navigable URL.
    - Looks like a URL  → navigate directly (prepend https:// if needed)
    - Looks like text   → DuckDuckGo search
    """
    raw = raw.strip()
    if not raw:
        return "about:blank"
    if raw.startswith(("http://", "https://", "file://", "about:")):
        return raw
    # Domain-ish input (e.g. "dndbeyond.com")
    if "." in raw and " " not in raw:
        return "https://" + raw
    # Treat as a search query
    return f"https://duckduckgo.com/?q={quote_plus(raw)}"


# ══════════════════════════════════════════════════════════════════════════════
#  Clip Dialog
# ══════════════════════════════════════════════════════════════════════════════

class ClipDialog(QDialog):
    """
    Modal dialog shown when the GM clips a web page to Obsidian.

    Lets the GM set the note title, destination folder, tags, and preview
    the text that will be saved before committing.
    """

    def __init__(
        self,
        page_title: str,
        page_url: str,
        selected_text: str,
        config,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._page_title = page_title
        self._page_url = page_url
        self._selected_text = selected_text.strip()
        self._config = config

        self.setWindowTitle("✂  Clip to Obsidian")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            f"QDialog {{ background: {BG}; color: {TEXT}; }}"
            f"QLabel {{ color: {TEXT}; }}"
            f"QLineEdit, QComboBox, QTextEdit {{"
            f"  background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            f"  border-radius: 3px; padding: 4px 6px; }}"
            f"QLineEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 12, 14, 12)

        form = QFormLayout()
        form.setSpacing(6)

        # Note title
        self._title_edit = QLineEdit(_safe_filename(self._page_title))
        form.addRow("Note title:", self._title_edit)

        # Destination folder
        self._folder_combo = QComboBox()
        for f in CLIP_FOLDERS:
            self._folder_combo.addItem(f)
        form.addRow("Folder:", self._folder_combo)

        # Tags
        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("research, dnd5e, paladin  (comma-separated)")
        form.addRow("Tags:", self._tags_edit)

        layout.addLayout(form)

        # Source URL (read-only info)
        src_lbl = QLabel(f"Source: {self._page_url[:80]}{'…' if len(self._page_url) > 80 else ''}")
        src_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        src_lbl.setWordWrap(True)
        layout.addWidget(src_lbl)

        # Selected text preview
        if self._selected_text:
            preview_lbl = QLabel("Clipping:")
            preview_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 10px;")
            layout.addWidget(preview_lbl)

            self._preview = QTextEdit()
            self._preview.setPlainText(self._selected_text)
            self._preview.setReadOnly(True)
            self._preview.setMaximumHeight(120)
            self._preview.setStyleSheet(
                f"background: {PANEL}; color: {MUTED}; font-size: 10px;"
                f"border: 1px solid {BORDER}; border-radius: 3px;"
            )
            layout.addWidget(self._preview)
        else:
            no_sel = QLabel("ℹ  No text selected — saving title + URL as a reference note.")
            no_sel.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
            no_sel.setWordWrap(True)
            layout.addWidget(no_sel)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        btns.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT};"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton[text='Save'] {{ background: {ACCENT}; color: white;"
            f"  border-color: {ACCENT}; font-weight: bold; }}"
        )
        layout.addWidget(btns)

    def _on_save(self) -> None:
        vault_path = self._get_vault_path()
        if vault_path is None:
            QMessageBox.warning(
                self, "No Vault Selected",
                "Select an Obsidian vault in the Vault / Notes panel first."
            )
            return

        folder_name = self._folder_combo.currentText()
        if folder_name == "(vault root)":
            dest_dir = vault_path
        else:
            dest_dir = vault_path / folder_name

        dest_dir.mkdir(parents=True, exist_ok=True)

        title = self._title_edit.text().strip() or _safe_filename(self._page_title)
        tags_raw = self._tags_edit.text().strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else ["research"]

        # Resolve unique file path
        stem = _safe_filename(title)
        out_path = dest_dir / f"{stem}.md"
        counter = 2
        while out_path.exists():
            out_path = dest_dir / f"{stem} ({counter}).md"
            counter += 1

        self._write_note(out_path, title, tags)
        self.accept()

    def _write_note(self, path: Path, title: str, tags: List[str]) -> None:
        today = date.today().isoformat()
        tags_yaml = "[" + ", ".join(tags) + "]"

        lines = [
            "---",
            f'title: "{title}"',
            f'source: "{self._page_url}"',
            f"clipped: {today}",
            f"tags: {tags_yaml}",
            "---",
            "",
            f"# {title}",
            "",
        ]

        if self._selected_text:
            lines += [
                f"> [!quote] Clipped from [{self._page_title}]({self._page_url})",
                ">",
            ]
            for line in self._selected_text.splitlines():
                lines.append(f"> {line}" if line.strip() else ">")
            lines += [
                "",
                "---",
                f"*Clipped by Project Ceres · {today}*",
                "",
            ]
        else:
            lines += [
                f"**Source:** [{self._page_title}]({self._page_url})",
                "",
                f"*Reference saved by Project Ceres · {today}*",
                "",
            ]

        path.write_text("\n".join(lines), encoding="utf-8")

    def _get_vault_path(self) -> Optional[Path]:
        if (
            self._config
            and getattr(self._config, "current_vault", None)
            and self._config.current_vault in (getattr(self._config, "vaults", None) or {})
        ):
            return Path(self._config.vaults[self._config.current_vault])
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Browser Panel
# ══════════════════════════════════════════════════════════════════════════════

class BrowserPanel(QDockWidget):
    """
    Dockable embedded web browser with Obsidian clip and TTRPG bookmarks.

    Signals:
        status_message(msg) — forwarded to main-window status bar
        tab_title_changed() — emitted after dock tab text updates (for tab icons)
    """

    status_message: Signal = Signal(str)
    tab_title_changed: Signal = Signal()

    def __init__(self, config, parent: Optional[QWidget] = None) -> None:
        super().__init__("Browser", parent)
        self.setObjectName("BrowserPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable    |  # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable  |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config = config
        self._bookmarks: List[Tuple[str, str]] = []
        self._pending_clip_url: str = ""
        self._pending_clip_title: str = ""

        self._settings = QSettings("ProjectCeres", "GMAssistant")

        self._load_bookmarks()
        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        if not _WEBENGINE_OK:
            self._build_no_engine_ui()
            return

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(4, 4, 4, 2)
        outer_layout.setSpacing(3)

        # ── Navigation toolbar ────────────────────────────────────────────
        nav = QHBoxLayout()
        nav.setSpacing(3)

        self._back_btn = QPushButton("←")
        self._back_btn.setFixedWidth(28)
        self._back_btn.setToolTip("Go back")
        self._back_btn.clicked.connect(lambda: self._view.back())
        self._style_nav_btn(self._back_btn)
        nav.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("→")
        self._fwd_btn.setFixedWidth(28)
        self._fwd_btn.setToolTip("Go forward")
        self._fwd_btn.clicked.connect(lambda: self._view.forward())
        self._style_nav_btn(self._fwd_btn)
        nav.addWidget(self._fwd_btn)

        self._reload_btn = QPushButton("↺")
        self._reload_btn.setFixedWidth(28)
        self._reload_btn.setToolTip("Reload page")
        self._reload_btn.clicked.connect(lambda: self._view.reload())
        self._style_nav_btn(self._reload_btn)
        nav.addWidget(self._reload_btn)

        self._addr_bar = QLineEdit()
        self._addr_bar.setPlaceholderText("Enter URL or search…")
        self._addr_bar.returnPressed.connect(self._on_addr_entered)
        self._addr_bar.setStyleSheet(
            f"QLineEdit {{ background: {PANEL}; color: {TEXT};"
            f"  border: 1px solid {BORDER}; border-radius: 4px;"
            f"  padding: 4px 8px; font-size: 11px; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
        )
        nav.addWidget(self._addr_bar, 1)

        # Bookmarks dropdown button
        self._bm_btn = QPushButton("🔖")
        self._bm_btn.setFixedWidth(34)
        self._bm_btn.setToolTip("Bookmarks")
        self._bm_btn.clicked.connect(self._show_bookmarks_menu)
        self._style_nav_btn(self._bm_btn)
        nav.addWidget(self._bm_btn)

        # Add bookmark button
        add_bm_btn = QPushButton("+")
        add_bm_btn.setFixedWidth(28)
        add_bm_btn.setToolTip("Bookmark this page  (Ctrl+D)")
        add_bm_btn.clicked.connect(self._add_bookmark)
        add_bm_btn.setShortcut("Ctrl+D")
        self._style_nav_btn(add_bm_btn)
        nav.addWidget(add_bm_btn)

        outer_layout.addLayout(nav)

        # ── Clip toolbar ──────────────────────────────────────────────────
        clip_row = QHBoxLayout()
        clip_row.setSpacing(4)

        clip_btn = QPushButton("✂  Clip to Obsidian")
        clip_btn.setToolTip(
            "Save selected text (or just the page reference) to the active Obsidian vault"
        )
        clip_btn.clicked.connect(self._on_clip)
        clip_btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; font-size: 10px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )
        clip_row.addWidget(clip_btn)

        clip_row.addStretch()

        home_btn = QPushButton("🏠")
        home_btn.setFixedWidth(28)
        home_btn.setToolTip("Go to D&D Beyond")
        home_btn.clicked.connect(lambda: self.navigate_to("https://www.dndbeyond.com"))
        self._style_nav_btn(home_btn)
        clip_row.addWidget(home_btn)

        outer_layout.addLayout(clip_row)

        # ── Separator ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER};")
        outer_layout.addWidget(sep)

        # ── Web view ──────────────────────────────────────────────────────
        self._view = QWebEngineView()
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._view.urlChanged.connect(self._on_url_changed)
        self._view.loadStarted.connect(self._on_load_started)
        self._view.loadProgress.connect(self._on_load_progress)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.titleChanged.connect(self._on_title_changed)
        outer_layout.addWidget(self._view, 1)

        # ── Status bar ────────────────────────────────────────────────────
        self._status_lbl = QLabel("● Ready")
        self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px; padding: 2px 4px;")
        self._status_lbl.setWordWrap(False)
        outer_layout.addWidget(self._status_lbl)

        self.setWidget(outer)

        # Navigate to first bookmark (DnD Beyond) on open
        if self._bookmarks:
            self.navigate_to(self._bookmarks[0][1])

    def _build_no_engine_ui(self) -> None:
        """Friendly fallback when PyQtWebEngine is not installed."""
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]

        lbl = QLabel(
            "⚠  PyQtWebEngine is not installed.\n\n"
            "Install it to enable the browser panel:\n\n"
            "    pip install PyQtWebEngine\n\n"
            "Then restart Project Ceres."
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px; padding: 30px;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.setWidget(outer)

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation
    # ══════════════════════════════════════════════════════════════════════════

    def navigate_to(self, url: str) -> None:
        """Public method — navigate the browser to a URL (called by other panels)."""
        if _WEBENGINE_OK and hasattr(self, "_view"):
            self._view.setUrl(QUrl(url))

    def _on_addr_entered(self) -> None:
        raw = self._addr_bar.text().strip()
        url = _resolve_url(raw)
        self.navigate_to(url)

    def _on_url_changed(self, qurl) -> None:
        url_str = qurl.toString()
        self._addr_bar.setText(url_str)

    def _on_load_started(self) -> None:
        self._status_lbl.setText("⟳  Loading…")
        self._status_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 10px; padding: 2px 4px;"
        )

    def _on_load_progress(self, pct: int) -> None:
        if pct < 100:
            self._status_lbl.setText(f"⟳  Loading {pct}%")
            self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px; padding: 2px 4px;")

    def _on_load_finished(self, ok: bool) -> None:
        url = self._view.url().toString()
        short = url[:80] + ("…" if len(url) > 80 else "")
        if ok:
            self._status_lbl.setText(f"●  {short}")
            self._status_lbl.setStyleSheet(
                f"color: {SUCCESS}; font-size: 10px; padding: 2px 4px;"
            )
        else:
            self._status_lbl.setText(f"✗  Failed to load: {short}")
            self._status_lbl.setStyleSheet(
                f"color: {ERROR}; font-size: 10px; padding: 2px 4px;"
            )

    def _on_title_changed(self, title: str) -> None:
        """Update dock tab text with page title (no emoji — tab icon is chrome.png)."""
        display = title[:40] if title else "Browser"
        self.setWindowTitle(display)
        self.tab_title_changed.emit()

    # ══════════════════════════════════════════════════════════════════════════
    # Bookmarks
    # ══════════════════════════════════════════════════════════════════════════

    def _show_bookmarks_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {PANEL}; color: {TEXT}; border: 1px solid {ACCENT};"
            f"  padding: 4px 0; }}"
            f"QMenu::item {{ padding: 5px 20px; }}"
            f"QMenu::item:selected {{ background: {ACCENT}; color: white; }}"
            f"QMenu::separator {{ height: 1px; background: {BORDER}; margin: 3px 0; }}"
        )

        for name, url in self._bookmarks:
            action = QAction(name, self)
            action.setToolTip(url)
            action.triggered.connect(lambda checked, u=url: self.navigate_to(u))
            menu.addAction(action)

        if self._bookmarks:
            menu.addSeparator()

        manage_action = QAction("✎ Manage bookmarks…", self)
        manage_action.triggered.connect(self._manage_bookmarks)
        menu.addAction(manage_action)

        # Show below the button
        btn_pos = self._bm_btn.mapToGlobal(self._bm_btn.rect().bottomLeft())
        menu.exec(btn_pos)  # type: ignore[attr-defined]

    def _add_bookmark(self) -> None:
        if not hasattr(self, "_view"):
            return
        url = self._view.url().toString()
        title = self._view.title() or url
        if not url or url in ("about:blank", ""):
            QMessageBox.information(
                self,
                "Bookmark",
                "Load a page in the browser before adding a bookmark.",
            )
            return

        for _, existing_url in self._bookmarks:
            if existing_url == url:
                QMessageBox.information(
                    self,
                    "Bookmark",
                    "This URL is already in your bookmarks.",
                )
                self.status_message.emit(f"Already bookmarked: {title[:40]}")
                return

        default_name = (title or url)[:120]
        name, ok = QInputDialog.getText(
            self,
            "Add bookmark",
            "Bookmark name:",
            text=default_name,
        )
        if not ok or not name.strip():
            return

        self._bookmarks.append((name.strip()[:120], url))
        self._save_bookmarks()
        self.status_message.emit(f"Bookmarked: {name.strip()[:40]}")

    def _prompt_new_bookmark_pair(self) -> Optional[Tuple[str, str]]:
        """Ask for name and URL (e.g. add without loading the page first)."""
        name, ok = QInputDialog.getText(self, "New bookmark", "Bookmark name:")
        if not ok or not name.strip():
            return None
        url, ok = QInputDialog.getText(self, "New bookmark", "URL:", text="https://")
        if not ok or not url.strip():
            return None
        u = url.strip()
        if not u.startswith(("http://", "https://", "file://")):
            u = "https://" + u.lstrip("/")
        return (name.strip()[:120], u)

    def _manage_bookmarks(self) -> None:
        """Bookmark manager — add, rename, remove; scrollable list."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Bookmarks")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet(
            f"QDialog {{ background: {BG}; color: {TEXT}; }}"
            f"QLabel {{ color: {TEXT}; }}"
        )
        layout = QVBoxLayout(dialog)
        layout.setSpacing(6)

        info = QLabel(
            "Add bookmarks by URL, rename entries, or remove with ✕. Changes save immediately."
        )
        info.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        add_btn = QPushButton("➕  Add bookmark…")
        add_btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
            f"  border-radius: 4px; padding: 5px 12px; font-size: 10px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )

        def _add_manual() -> None:
            pair = self._prompt_new_bookmark_pair()
            if not pair:
                return
            n, u = pair
            if any(u == eu for _, eu in self._bookmarks):
                QMessageBox.warning(self, "Bookmarks", "That URL is already bookmarked.")
                return
            self._bookmarks.append((n, u))
            self._save_bookmarks()
            dialog.accept()
            self._manage_bookmarks()

        add_btn.clicked.connect(_add_manual)
        layout.addWidget(add_btn)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(3)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        def _make_row(idx: int, name: str, url: str) -> QWidget:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            url_short = url[:56] + ("…" if len(url) > 56 else "")
            lbl = QLabel(
                f"<b>{name}</b><br/>"
                f"<span style='color:{MUTED};font-size:10px;'>{url_short}</span>"
            )
            lbl.setStyleSheet(f"color: {TEXT};")
            lbl.setWordWrap(True)
            rl.addWidget(lbl, 1)

            ren_btn = QPushButton("✎")
            ren_btn.setFixedSize(26, 26)
            ren_btn.setToolTip("Rename")
            ren_btn.setStyleSheet(
                f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
                f"  border-radius: 3px; font-size: 11px; }}"
                f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            )

            def _rename(checked: bool = False, i: int = idx) -> None:
                if not (0 <= i < len(self._bookmarks)):
                    return
                old_n, u = self._bookmarks[i]
                new_n, ok = QInputDialog.getText(
                    self, "Rename bookmark", "Name:", text=old_n
                )
                if ok and new_n.strip():
                    self._bookmarks[i] = (new_n.strip()[:120], u)
                    self._save_bookmarks()
                    dialog.accept()
                    self._manage_bookmarks()

            ren_btn.clicked.connect(_rename)
            rl.addWidget(ren_btn)

            rm_btn = QPushButton("✕")
            rm_btn.setFixedSize(26, 26)
            rm_btn.setToolTip("Remove")
            rm_btn.setStyleSheet(
                f"QPushButton {{ background: {SURFACE}; color: {MUTED}; border: 1px solid {BORDER};"
                f"  border-radius: 3px; }}"
                f"QPushButton:hover {{ color: {ERROR}; border-color: {ERROR}; }}"
            )

            def _remove(checked: bool = False, i: int = idx) -> None:
                if 0 <= i < len(self._bookmarks):
                    self._bookmarks.pop(i)
                    self._save_bookmarks()
                    dialog.accept()
                    self._manage_bookmarks()

            rm_btn.clicked.connect(_remove)
            rl.addWidget(rm_btn)
            return row

        for i, (name, url) in enumerate(self._bookmarks):
            scroll_layout.addWidget(_make_row(i, name, url))

        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        scroll.setMaximumHeight(360)
        scroll.setWidget(scroll_widget)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER}; border-radius: 4px;"
            f"  background: {PANEL}; }}"
        )
        layout.addWidget(scroll, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
            f"  border-radius: 4px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]

        dialog.exec()  # type: ignore[attr-defined]

    def _save_bookmarks(self) -> None:
        data = [{"name": n, "url": u} for n, u in self._bookmarks]
        self._settings.setValue("browser/bookmarks", json.dumps(data))

    def _load_bookmarks(self) -> None:
        raw = self._settings.value("browser/bookmarks", "", type=str)
        if raw:
            try:
                data = json.loads(raw)
                self._bookmarks = [(d["name"], d["url"]) for d in data]
                return
            except Exception:
                pass
        # First run — use defaults
        self._bookmarks = list(DEFAULT_BOOKMARKS)
        self._save_bookmarks()

    # ══════════════════════════════════════════════════════════════════════════
    # Clip to Obsidian
    # ══════════════════════════════════════════════════════════════════════════

    def _on_clip(self) -> None:
        if not hasattr(self, "_view"):
            return
        url = self._view.url().toString()
        if not url or url in ("about:blank", "about:srcdoc"):
            QMessageBox.information(
                self,
                "Clip to Obsidian",
                "Load a page in the browser before clipping.",
            )
            return
        # Stash page info before JS callback (page URL might change by the time
        # the async callback fires, though unlikely)
        self._pending_clip_url = url
        self._pending_clip_title = self._view.title() or url
        self._view.page().runJavaScript(_JS_GET_SELECTION, self._on_got_selection)

    def _on_got_selection(self, selected_text: Optional[str]) -> None:
        text = (selected_text or "").strip()
        dialog = ClipDialog(
            page_title=self._pending_clip_title,
            page_url=self._pending_clip_url,
            selected_text=text,
            config=self._config,
            parent=self,
        )
        if _dialog_accepted(dialog.exec()):  # type: ignore[arg-type]
            short = (self._pending_clip_title or "")[:40]
            self.status_message.emit(f"Clipped to Obsidian: {short}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """
        Tear down WebEngine cleanly: disconnect slots, stop loads, blank the page.
        Avoids Qt6 / Chromium callbacks firing during dock destruction (Windows crash).
        """
        view = getattr(self, "_view", None)
        if _WEBENGINE_OK and view is not None:
            try:
                for sig, slot in (
                    (view.loadStarted, self._on_load_started),
                    (view.loadProgress, self._on_load_progress),
                    (view.loadFinished, self._on_load_finished),
                    (view.urlChanged, self._on_url_changed),
                    (view.titleChanged, self._on_title_changed),
                ):
                    try:
                        sig.disconnect(slot)
                    except TypeError:
                        pass
            except Exception:
                pass
            try:
                stop = getattr(view, "stop", None)
                if callable(stop):
                    stop()
            except Exception:
                pass
            try:
                view.setUrl(QUrl("about:blank"))
            except Exception:
                pass
        super().closeEvent(event)

    # ══════════════════════════════════════════════════════════════════════════
    # Style helpers
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _style_nav_btn(btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 3px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
            f"QPushButton:pressed {{ background: {PANEL}; }}"
        )
