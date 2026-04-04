"""
Main window for Project Ceres — GM Assistant UI.

QMainWindow with a dark game theme, dockable Winamp-style panels, and a
menu bar for toggling each panel on/off.

Panel slots (initial layout):
  LEFT    — Vault / Notes
  RIGHT   — Discord  |  Spotify  (tabbed)
  BOTTOM  — Console
  FLOAT   — Soundboard, Fantasy Grounds (start floating, user can dock)
"""

from __future__ import annotations

from typing import Callable, Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QLabel, QStatusBar, QMenuBar,
        QAction, QSizePolicy, QDockWidget, QMessageBox,
    )
    from PyQt5.QtCore import Qt, QSize, QSettings
    from PyQt5.QtGui import QFont, QIcon, QPalette, QColor
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QMainWindow, QWidget, QLabel, QStatusBar, QMenuBar,
        QAction, QSizePolicy, QDockWidget, QMessageBox,
    )
    from PySide6.QtCore import Qt, QSize, QSettings  # type: ignore
    from PySide6.QtGui import QFont, QIcon, QPalette, QColor  # type: ignore

from ui.theme import (
    ACCENT, BG, PANEL, SURFACE, TEXT, MUTED, BORDER, STYLESHEET
)
from ui.panels.vault_notes_panel  import VaultNotesPanel
from ui.panels.console_panel      import ConsolePanel
from ui.panels.soundboard_panel   import SoundboardPanel
from ui.panels.discord_panel      import DiscordPanel
from ui.panels.spotify_panel      import SpotifyPanel
from ui.panels.fgu_panel          import FGUPanel
from ui.panels.scheduler_panel    import SchedulerPanel


class MainWindow(QMainWindow):
    """
    Top-level GM Assistant window.

    Args:
        config:       Fully-initialised Config dataclass
        run_command:  assistant.run_command callable
    """

    APP_NAME = "GM Assistant — Project Ceres"
    VERSION  = "0.1.0-scaffold"

    def __init__(
        self,
        config,                  # core.config.Config
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._run_command = run_command

        self.setWindowTitle(self.APP_NAME)
        self.setMinimumSize(QSize(900, 620))
        self.resize(QSize(1400, 860))
        self.setDockNestingEnabled(True)

        # Apply global stylesheet
        self.setStyleSheet(STYLESHEET)

        self._build_central_widget()
        self._build_panels()
        self._build_menu_bar()
        self._build_status_bar()
        self._restore_geometry()

    # ── Central widget ─────────────────────────────────────────────────────────

    def _build_central_widget(self) -> None:
        """
        The central widget is a placeholder area that shows when no content
        panel is occupying the centre.  Future panels (e.g. a note editor or
        map viewer) will live here.
        """
        central = QWidget()
        central.setObjectName("CentralPlaceholder")
        central.setStyleSheet(f"background: {BG};")
        central.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Watermark label
        lbl = QLabel("⚔  GM Assistant", central)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        lbl.setStyleSheet(
            f"color: {BORDER}; font-size: 48px; font-weight: bold;"
            f"font-family: Consolas, 'Fira Code', monospace;"
        )
        lbl.setGeometry(0, 0, 800, 200)

        # Wire resize so the watermark stays centred
        central._label = lbl  # type: ignore[attr-defined]

        self.setCentralWidget(central)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cw = self.centralWidget()
        if cw and hasattr(cw, "_label"):
            lbl = cw._label
            lbl.setGeometry(
                (cw.width() - 800) // 2,
                (cw.height() - 200) // 2,
                800,
                200,
            )

    # ── Panels ─────────────────────────────────────────────────────────────────

    def _build_panels(self) -> None:
        """Create and dock all panels."""

        # 1. Vault / Notes — left side
        self._vault_panel = VaultNotesPanel(self._config, self._run_command, self)
        self._vault_panel.status_message.connect(self._set_status)
        self._vault_panel.note_opened.connect(self._on_note_opened)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._vault_panel)  # type: ignore[attr-defined]

        # 2. Console — bottom
        self._console_panel = ConsolePanel(self._config, self._run_command, self)
        self._console_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_panel)  # type: ignore[attr-defined]
        self._console_panel.setMaximumHeight(280)

        # 3. Discord — right side
        self._discord_panel = DiscordPanel(self._config, self._run_command, self)
        self._discord_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._discord_panel)  # type: ignore[attr-defined]

        # 4. Spotify — right side, tabbed with Discord
        self._spotify_panel = SpotifyPanel(self._config, self._run_command, self)
        self._spotify_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._spotify_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._discord_panel, self._spotify_panel)
        self._discord_panel.raise_()  # Discord tab on top by default

        # Wire Discord voice commands → Spotify panel
        self._discord_panel.spotify_command.connect(self._spotify_panel.handle_command)

        # 5. Soundboard — right side, tabbed below Discord/Spotify
        self._soundboard_panel = SoundboardPanel(self)
        self._soundboard_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._soundboard_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._spotify_panel, self._soundboard_panel)

        # 6. Fantasy Grounds — right side, tabbed with the others
        self._fgu_panel = FGUPanel(self._config, self._run_command, self)
        self._fgu_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._fgu_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._soundboard_panel, self._fgu_panel)

        # 7. Session Scheduler — right side, tabbed with the others
        self._scheduler_panel = SchedulerPanel(self._config, self._run_command, self)
        self._scheduler_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._scheduler_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._fgu_panel, self._scheduler_panel)

        # ── Wire Scheduler ↔ Discord ──────────────────────────────────────────
        # Scheduler → Discord
        self._scheduler_panel.request_channels.connect(
            self._discord_panel.request_text_channels
        )
        self._scheduler_panel.send_poll_sig.connect(
            self._discord_panel.send_poll
        )
        self._scheduler_panel.close_poll_sig.connect(
            self._discord_panel.close_poll
        )
        self._scheduler_panel.discord_post_ready.connect(
            self._discord_panel.post_message_to_channel
        )
        # Discord → Scheduler
        self._discord_panel.text_channels_available.connect(
            self._scheduler_panel.on_channels_available
        )
        self._discord_panel.poll_sent_ok.connect(
            self._scheduler_panel.on_poll_sent
        )
        self._discord_panel.vote_updated.connect(
            self._scheduler_panel.on_vote_updated
        )
        self._discord_panel.poll_error_sig.connect(
            self._scheduler_panel.on_poll_error
        )

    # ── Menu bar ───────────────────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        mb = self.menuBar()
        mb.setNativeMenuBar(False)  # keep custom style on macOS

        # ── File menu ──
        file_menu = mb.addMenu("&File")
        self._add_action(file_menu, "⟳  Refresh Vaults",   self._refresh_vaults, "Ctrl+R")
        self._add_action(file_menu, "⚙  Settings",         self._open_settings,  "Ctrl+,")
        file_menu.addSeparator()
        self._add_action(file_menu, "✕  Exit",             self.close,           "Ctrl+Q")

        # ── View menu — panel toggles ──
        view_menu = mb.addMenu("&View")
        view_menu.addAction(self._vault_panel.toggleViewAction())
        view_menu.addAction(self._console_panel.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(self._discord_panel.toggleViewAction())
        view_menu.addAction(self._spotify_panel.toggleViewAction())
        view_menu.addAction(self._soundboard_panel.toggleViewAction())
        view_menu.addAction(self._fgu_panel.toggleViewAction())
        view_menu.addAction(self._scheduler_panel.toggleViewAction())
        view_menu.addSeparator()
        self._add_action(view_menu, "Reset Layout", self._reset_layout)

        # ── Modules menu ──
        mod_menu = mb.addMenu("&Modules")
        mod_menu.addAction(self._discord_panel.toggleViewAction())
        mod_menu.addAction(self._spotify_panel.toggleViewAction())
        mod_menu.addAction(self._soundboard_panel.toggleViewAction())
        mod_menu.addAction(self._fgu_panel.toggleViewAction())
        mod_menu.addAction(self._scheduler_panel.toggleViewAction())

        # ── Help menu ──
        help_menu = mb.addMenu("&Help")
        self._add_action(help_menu, "📋  Command List", self._show_help)
        self._add_action(help_menu, "ℹ  About",         self._show_about)

    @staticmethod
    def _add_action(menu, label: str, slot: Callable, shortcut: str = "") -> QAction:
        action = QAction(label, menu)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    @staticmethod
    def _add_disabled(menu, label: str) -> None:
        action = QAction(label, menu)
        action.setEnabled(False)
        menu.addAction(action)

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        sb.setObjectName("MainStatusBar")

        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {TEXT};")
        sb.addWidget(self._status_label, 1)

        self._vault_status = QLabel()
        self._vault_status.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        sb.addPermanentWidget(self._vault_status)

        self._version_label = QLabel(f"v{self.VERSION}")
        self._version_label.setStyleSheet(f"color: {MUTED};")
        sb.addPermanentWidget(self._version_label)

        self.setStatusBar(sb)
        self._update_vault_status()

    def _set_status(self, msg: str) -> None:
        self._status_label.setText(msg)
        self._update_vault_status()

    def _update_vault_status(self) -> None:
        cv = self._config.current_vault or "—"
        self._vault_status.setText(f"  ⚔ {cv}  ")

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_note_opened(self, path: str) -> None:
        self._console_panel.print_success(f"Opened note: {path}")
        self._set_status(f"Note: {path}")

    def _refresh_vaults(self) -> None:
        self._run_command("sync-obsidian", "", self._config)
        self._vault_panel.refresh_vault_selector()
        self._set_status("Vaults refreshed.")
        self._console_panel.print_output("Vaults refreshed.")

    def _open_settings(self) -> None:
        # Placeholder — settings dialog to be implemented
        QMessageBox.information(
            self,
            "Settings",
            "Settings panel coming in a future update.\n\n"
            "Edit settings.json / variables.env directly for now.",
        )

    def _reset_layout(self) -> None:
        # Re-dock everything to default positions
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   self._vault_panel)      # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_panel)    # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._discord_panel)    # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._spotify_panel)    # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._soundboard_panel) # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._fgu_panel)        # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._scheduler_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._discord_panel,    self._spotify_panel)
        self.tabifyDockWidget(self._spotify_panel,    self._soundboard_panel)
        self.tabifyDockWidget(self._soundboard_panel, self._fgu_panel)
        self.tabifyDockWidget(self._fgu_panel,        self._scheduler_panel)
        for panel in (self._vault_panel, self._console_panel, self._discord_panel,
                      self._spotify_panel, self._soundboard_panel, self._fgu_panel,
                      self._scheduler_panel):
            panel.show()
        self._discord_panel.raise_()
        self._set_status("Layout reset.")

    def _show_help(self) -> None:
        cmds = sorted(self._config.commands.keys())
        text = "\n".join(f"  {c}" for c in cmds)
        self._console_panel.print_output("── Available commands ──", color=ACCENT)
        for cmd in cmds:
            _, help_text = self._config.commands[cmd]
            self._console_panel.print_output(f"  {cmd:<30} {help_text}")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GM Assistant",
            f"<b>GM Assistant — Project Ceres</b><br>"
            f"Version {self.VERSION}<br><br>"
            f"A modular Game Master assistant integrating<br>"
            f"Obsidian, Discord, Spotify, Fantasy Grounds,<br>"
            f"and a built-in soundboard.<br><br>"
            f"<i>Built with PyQt5 / PySide6</i>",
        )

    # ── Window geometry persistence ────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        settings = QSettings("ProjectCeres", "GMAssistant")
        geometry = settings.value("geometry")
        state    = settings.value("windowState")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        settings = QSettings("ProjectCeres", "GMAssistant")
        settings.setValue("geometry",    self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        super().closeEvent(event)
