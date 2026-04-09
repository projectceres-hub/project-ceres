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

from pathlib import Path
from typing import Callable, Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QLabel, QStatusBar, QMenuBar,
        QAction, QSizePolicy, QDockWidget, QMessageBox, QTabBar,
    )
    from PyQt5.QtCore import Qt, QSize, QSettings
    from PyQt5.QtGui import QFont, QIcon, QPalette, QColor
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QMainWindow, QWidget, QLabel, QStatusBar, QMenuBar,
        QAction, QSizePolicy, QDockWidget, QMessageBox, QTabBar,
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
from ui.panels.chat_panel         import ChatPanel
from ui.panels.browser_panel      import BrowserPanel
from ui.panels.syrinscape_panel   import SyrinscapePanel
from ui.panels.youtube_panel      import YouTubePanel
from ui.panels.tidal_panel        import TidalPanel
from ui.panels.local_music_panel  import LocalMusicPanel
from ui.panels.mixer_panel        import MixerPanel
from ui.dialogs.preferences_dialog import PreferencesDialog

_ASSETS = Path(__file__).resolve().parent / "assets"


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
        self._apply_tab_icons()   # must run AFTER restoreState() rebuilds tab bars

    # ── Central widget — Ceres Chat ────────────────────────────────────────────

    def _build_central_widget(self) -> None:
        """
        The central widget is the Ceres conversational chat panel.
        Users interact with the GM Assistant through plain English here;
        the agent interprets intent and dispatches to the right panel/module.
        """
        self._chat_panel = ChatPanel(self._config, self._run_command, self)
        self._chat_panel.status_message.connect(self._set_status)
        self._chat_panel.request_console.connect(self._show_console_output)
        self.setCentralWidget(self._chat_panel)

    # ── Panels ─────────────────────────────────────────────────────────────────

    def _build_panels(self) -> None:
        """Create and dock all panels."""

        # 1. Vault / Notes — left side
        self._vault_panel = VaultNotesPanel(self._config, self._run_command, self)
        self._vault_panel.status_message.connect(self._set_status)
        self._vault_panel.note_opened.connect(self._on_note_opened)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._vault_panel)  # type: ignore[attr-defined]

        # 2. Console — bottom (power-user / raw output; hidden by default)
        self._console_panel = ConsolePanel(self._config, self._run_command, self)
        self._console_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_panel)  # type: ignore[attr-defined]
        self._console_panel.setMaximumHeight(240)
        if getattr(self._config, "console_hidden_default", True):
            self._console_panel.hide()   # hidden per user preference (default: hidden)

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

        # 8. Browser — right side, tabbed with the other right panels
        self._browser_panel = BrowserPanel(self._config, self)
        self._browser_panel.status_message.connect(self._set_status)
        self._browser_panel.tab_title_changed.connect(self._apply_tab_icons)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._browser_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._scheduler_panel, self._browser_panel)

        # 9. Syrinscape — right side, tabbed with the other right panels
        self._syrinscape_panel = SyrinscapePanel(self._config, self._run_command, self)
        self._syrinscape_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._syrinscape_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._browser_panel, self._syrinscape_panel)

        # Wire Discord Syrinscape voice commands → Syrinscape panel (must come after panel exists)
        self._discord_panel.syrinscape_command.connect(
            self._syrinscape_panel.handle_command
        )

        # 10. YouTube — right side, tabbed with the other right panels
        self._youtube_panel = YouTubePanel(self._config, self._run_command, self)
        self._youtube_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._youtube_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._syrinscape_panel, self._youtube_panel)

        # Wire Discord YouTube voice commands → YouTube panel
        self._discord_panel.youtube_command.connect(self._youtube_panel.handle_command)

        # 11. Tidal — right side, tabbed with the other right panels
        self._tidal_panel = TidalPanel(self._config, self._run_command, self)
        self._tidal_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tidal_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._youtube_panel, self._tidal_panel)

        # Wire Discord Tidal voice commands → Tidal panel
        self._discord_panel.tidal_command.connect(self._tidal_panel.handle_command)

        # 12. Local Music — right side, tabbed with the other right panels
        self._local_music_panel = LocalMusicPanel(self._config, self._run_command, self)
        self._local_music_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._local_music_panel)  # type: ignore[attr-defined]
        self.tabifyDockWidget(self._tidal_panel, self._local_music_panel)

        # Wire Discord local music voice commands → Local Music panel
        self._discord_panel.local_music_command.connect(self._local_music_panel.handle_command)

        # 13. Mixer — left side (all source panels must exist before register_source)
        self._mixer_panel = MixerPanel(self)
        self._mixer_panel.status_message.connect(self._set_status)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._mixer_panel)  # type: ignore[attr-defined]

        self._mixer_panel.register_source("Soundboard", self._soundboard_panel)
        self._mixer_panel.register_source("Syrinscape", self._syrinscape_panel, "syrinscape.png")
        self._mixer_panel.register_source("Spotify",    self._spotify_panel,    "spotify.png")
        self._mixer_panel.register_source("YouTube",      self._youtube_panel,      "youtube.png")
        self._mixer_panel.register_source("Tidal",        self._tidal_panel,        "tidal.png")
        self._mixer_panel.register_source("Local Music",  self._local_music_panel,  "music.png")

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

    # ── Tab icons ─────────────────────────────────────────────────────────────

    # Maps dock-widget windowTitle() → icon filename in ui/assets/
    _TAB_ICONS: dict[str, str] = {
        "Vault / Notes":    "obsidian.png",
        "Discord":          "discord.png",
        "Spotify":          "spotify.png",
        "Fantasy Grounds":  "fantasygrounds.png",
        "Syrinscape":       "syrinscape.png",
        "YouTube":          "youtube.png",
        "Browser":          "chrome.png",
        "Tidal":            "tidal.png",
        "Local Music":      "music.png",
    }

    def _apply_tab_icons(self) -> None:
        """Set brand icons directly on every QTabBar tab created by dock tabification."""
        icon_cache: dict[str, QIcon] = {}
        for title, filename in self._TAB_ICONS.items():
            path = _ASSETS / filename
            if path.exists():
                icon_cache[title] = QIcon(str(path))

        # Browser uses dynamic window titles (page name) — map tab text → dock objectName
        titles_to_browser: set[str] = set()
        for dock in self.findChildren(QDockWidget):
            if dock.objectName() == "BrowserPanel":
                titles_to_browser.add(dock.windowTitle())

        for tab_bar in self.findChildren(QTabBar):
            tab_bar.setIconSize(QSize(20, 20))
            for idx in range(tab_bar.count()):
                title = tab_bar.tabText(idx)
                if title in icon_cache:
                    tab_bar.setTabIcon(idx, icon_cache[title])
                elif title in titles_to_browser and "Browser" in icon_cache:
                    tab_bar.setTabIcon(idx, icon_cache["Browser"])

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
        # Console is hidden by default; toggle here for power users
        console_action = self._console_panel.toggleViewAction()
        console_action.setText("🖥  Console  (power user)")
        view_menu.addAction(console_action)
        view_menu.addSeparator()
        view_menu.addAction(self._discord_panel.toggleViewAction())
        view_menu.addAction(self._spotify_panel.toggleViewAction())
        view_menu.addAction(self._soundboard_panel.toggleViewAction())
        view_menu.addAction(self._fgu_panel.toggleViewAction())
        view_menu.addAction(self._scheduler_panel.toggleViewAction())
        view_menu.addAction(self._browser_panel.toggleViewAction())
        view_menu.addAction(self._syrinscape_panel.toggleViewAction())
        view_menu.addAction(self._youtube_panel.toggleViewAction())
        view_menu.addAction(self._tidal_panel.toggleViewAction())
        view_menu.addAction(self._local_music_panel.toggleViewAction())
        view_menu.addAction(self._mixer_panel.toggleViewAction())
        view_menu.addSeparator()
        self._add_action(view_menu, "Reset Layout", self._reset_layout)

        # ── Modules menu ──
        mod_menu = mb.addMenu("&Modules")
        mod_menu.addAction(self._discord_panel.toggleViewAction())
        mod_menu.addAction(self._spotify_panel.toggleViewAction())
        mod_menu.addAction(self._soundboard_panel.toggleViewAction())
        mod_menu.addAction(self._fgu_panel.toggleViewAction())
        mod_menu.addAction(self._scheduler_panel.toggleViewAction())
        mod_menu.addAction(self._browser_panel.toggleViewAction())
        mod_menu.addAction(self._syrinscape_panel.toggleViewAction())
        mod_menu.addAction(self._youtube_panel.toggleViewAction())
        mod_menu.addAction(self._tidal_panel.toggleViewAction())
        mod_menu.addAction(self._local_music_panel.toggleViewAction())
        mod_menu.addAction(self._mixer_panel.toggleViewAction())

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

    def _on_preferences_saved(self) -> None:
        """Apply live preference changes immediately after the dialog saves."""
        # Console visibility
        if getattr(self._config, "console_hidden_default", True):
            self._console_panel.hide()
        # (Other live changes — vault path, FGU root — take effect on next command use)
        self._set_status("Preferences saved.")
        # Clear the chat agent's client so it re-reads the (possibly new) API key
        if hasattr(self._chat_panel, "_agent"):
            self._chat_panel._agent._client = None

    def _show_console_output(self, text: str) -> None:
        """Show the console panel and populate it with full command output."""
        self._console_panel.show()
        self._console_panel.raise_()
        self._console_panel.print_output("── Full command output ──", color=ACCENT)
        self._console_panel.print_output(text)

    def _on_note_opened(self, path: str) -> None:
        self._chat_panel.print_success(f"Opened note: {path}")
        self._set_status(f"Note: {path}")

    def _refresh_vaults(self) -> None:
        self._run_command("sync-obsidian", "", self._config)
        self._vault_panel.refresh_vault_selector()
        self._set_status("Vaults refreshed.")
        self._chat_panel.print_output("Vaults refreshed.")

    def _open_settings(self) -> None:
        dlg = PreferencesDialog(
            config=self._config,
            env_path=getattr(self._config, "env_file", "variables.env"),
            parent=self,
        )
        dlg.saved.connect(self._on_preferences_saved)
        dlg.exec()

    def _reset_layout(self) -> None:
        """Re-dock everything to default positions."""
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   self._vault_panel)      # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_panel)    # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._discord_panel)     # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._spotify_panel)     # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._soundboard_panel)  # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._fgu_panel)         # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._scheduler_panel)   # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._browser_panel)     # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._syrinscape_panel)  # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._youtube_panel)     # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._tidal_panel)            # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  self._local_music_panel)    # type: ignore[attr-defined]
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   self._mixer_panel)           # type: ignore[attr-defined]
        self.tabifyDockWidget(self._discord_panel,    self._spotify_panel)
        self.tabifyDockWidget(self._spotify_panel,    self._soundboard_panel)
        self.tabifyDockWidget(self._soundboard_panel, self._fgu_panel)
        self.tabifyDockWidget(self._fgu_panel,        self._scheduler_panel)
        self.tabifyDockWidget(self._scheduler_panel,  self._browser_panel)
        self.tabifyDockWidget(self._browser_panel,    self._syrinscape_panel)
        self.tabifyDockWidget(self._syrinscape_panel, self._youtube_panel)
        self.tabifyDockWidget(self._youtube_panel,    self._tidal_panel)
        self.tabifyDockWidget(self._tidal_panel,      self._local_music_panel)
        self._discord_panel.raise_()
        self._apply_tab_icons()

    # ── Window lifecycle ───────────────────────────────────────────────────────

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Re-apply tab icons after Qt rebuilds tab bars on first show."""
        super().showEvent(event)
        self._apply_tab_icons()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Close all docks explicitly to avoid QThread-destroyed warnings."""
        for dock in self.findChildren(QDockWidget):
            dock.close()
        self._restore_geometry()   # save geometry on close
        super().closeEvent(event)

    # ── Geometry persistence ────────────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        """Save or restore window geometry and dock state via QSettings."""
        settings = QSettings("ProjectCeres", "GMAssistant")
        # On close we save; on init we just initialise the settings object.
        # Called once at startup (no-op — state not yet saved) and once on close.
        if not self.isVisible():
            # Save on close
            settings.setValue("geometry", self.saveGeometry())
            settings.setValue("windowState", self.saveState())
        else:
            # Restore on startup if saved state exists
            geo = settings.value("geometry")
            state = settings.value("windowState")
            if geo:
                self.restoreGeometry(geo)
            if state:
                self.restoreState(state)

    # ── Help / About ────────────────────────────────────────────────────────────

    def _show_help(self) -> None:
        """Display a summary of available commands in a message box."""
        text = (
            "<b>GM Assistant — Quick Command Reference</b><br><br>"
            "<b>Vault:</b> vaults, switch, addvault<br>"
            "<b>Notes:</b> read, list, tree, createnote, editnote, search<br>"
            "<b>Campaigns:</b> campaign-create, campaign-add-pc, campaign-add-npc<br>"
            "<b>Sessions:</b> session-schedule, session-create, fgu-import-log<br>"
            "<b>Discord:</b> !play, !pause, !skip, !stop, !search (Spotify)<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "!ytplay, !ytstop, !ytpause, !ytsearch (YouTube)<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "!tidalplay, !tidalstop, !tidalpause, !tidalsearch (Tidal)<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "!localplay, !localstop, !localpause, !localnext (Local Music)<br>"
            "<b>Wake words:</b> Veras / Chroma — add bookmark, append note, "
            "add session marker, play &lt;track&gt; on youtube/tidal/locally<br><br>"
            "Full command list: see README.md"
        )
        QMessageBox.information(self, "Command Reference", text)

    def _show_about(self) -> None:
        """Display the About dialog."""
        QMessageBox.about(
            self,
            f"About {self.APP_NAME}",
            f"<b>{self.APP_NAME}</b><br>"
            f"Version {self.VERSION}<br><br>"
            "A modular GM Assistant for tabletop RPG game masters.<br>"
            "Connects Discord, Obsidian, Fantasy Grounds Unity, Spotify,<br>"
            "YouTube, Tidal, Syrinscape, and local audio — all in one Winamp-style interface.<br><br>"
            "<i>Project Ceres</i>",
        )