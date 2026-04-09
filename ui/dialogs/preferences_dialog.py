"""
ui/dialogs/preferences_dialog.py — Project Ceres
==================================================
Preferences dialog — sidebar navigation with stacked content pages.

Sections
--------
  🔑  API Keys      OpenAI · Spotify · Discord  (writes variables.env)
  📁  Paths         Default vault · Backup location  (writes settings.json)
  🖥  Interface     Console visibility · startup options  (writes settings.json)
  ⚔   Fantasy Grounds  FGU campaigns + logs folders  (writes settings.json)
  🔊  Soundboard    Folder list for SFX sources  (writes settings.json)

Changes take effect immediately where possible (paths, UI prefs).
API-key changes update os.environ and config in-memory; panels that
have already connected (Discord, Spotify) will need a reconnect.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QDialog, QWidget, QHBoxLayout, QVBoxLayout, QFormLayout,
        QListWidget, QListWidgetItem, QStackedWidget, QLabel,
        QLineEdit, QPushButton, QCheckBox, QFileDialog, QFrame,
        QSizePolicy, QAbstractItemView, QDialogButtonBox,
        QComboBox, QSpinBox,
    )
    from PyQt5.QtCore import Qt, pyqtSignal as Signal
    from PyQt5.QtGui import QFont, QIcon, QPixmap
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDialog, QWidget, QHBoxLayout, QVBoxLayout, QFormLayout,
        QListWidget, QListWidgetItem, QStackedWidget, QLabel,
        QLineEdit, QPushButton, QCheckBox, QFileDialog, QFrame,
        QSizePolicy, QAbstractItemView, QDialogButtonBox,
        QComboBox, QSpinBox,
    )
    from PySide6.QtCore import Qt, Signal  # type: ignore
    from PySide6.QtGui import QFont, QIcon, QPixmap  # type: ignore

from ui.theme import ACCENT, BG, PANEL, SURFACE, TEXT, MUTED, BORDER

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_env(env_path: str) -> dict[str, str]:
    """Read KEY=VALUE pairs from an env file, preserving comments."""
    result: dict[str, str] = {}
    path = Path(env_path)
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(env_path: str, updates: dict[str, str]) -> None:
    """
    Update specific keys in an env file, preserving all comments and
    existing key order.  New keys are appended at the end.
    """
    path = Path(env_path)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    # Append any keys not previously in the file
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Small reusable widgets
# ─────────────────────────────────────────────────────────────────────────────

_FIELD_STYLE = (
    f"QLineEdit {{"
    f"  background: {SURFACE}; color: {TEXT}; font-size: 11px;"
    f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 10px;"
    f"}}"
    f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
    f"QLineEdit:disabled {{ background: {BG}; color: {MUTED}; }}"
)

_BTN_STYLE = (
    f"QPushButton {{"
    f"  background: {SURFACE}; color: {TEXT}; font-size: 10px;"
    f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 12px;"
    f"}}"
    f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
)

_ACCENT_BTN_STYLE = (
    f"QPushButton {{"
    f"  background: {ACCENT}; color: white; font-size: 11px; font-weight: bold;"
    f"  border: none; border-radius: 4px; padding: 7px 20px;"
    f"}}"
    f"QPushButton:hover {{ background: #ff6b7a; }}"
    f"QPushButton:pressed {{ background: #c73050; }}"
)

_SECTION_LABEL_STYLE = (
    f"color: {MUTED}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
    f"background: transparent; border: none; padding: 0; margin-top: 8px;"
)

_HINT_STYLE = (
    f"color: {MUTED}; font-size: 9px; font-style: italic;"
    f"background: transparent; border: none; padding: 0;"
)


def _section_label(text: str, icon_file: str = "") -> QWidget:
    """Section header with optional brand icon (looked up in ui/assets/)."""
    if icon_file:
        icon_path = _ASSETS / icon_file
        if icon_path.exists():
            row = QWidget()
            row.setStyleSheet("background: transparent; border: none;")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 8, 0, 0)
            lay.setSpacing(6)
            icon_lbl = QLabel()
            pm = QPixmap(str(icon_path)).scaled(
                16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_lbl.setPixmap(pm)
            icon_lbl.setFixedSize(16, 16)
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            lay.addWidget(icon_lbl)
            txt = QLabel(text.upper())
            txt.setStyleSheet(_SECTION_LABEL_STYLE + "margin-top: 0;")
            lay.addWidget(txt)
            lay.addStretch()
            return row
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(_SECTION_LABEL_STYLE)
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(_HINT_STYLE)
    return lbl


def _password_row(placeholder: str = "") -> tuple[QLineEdit, QPushButton]:
    """Return (field, show_toggle_button) for a masked text field."""
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(placeholder)
    field.setStyleSheet(_FIELD_STYLE)

    btn = QPushButton("show")
    btn.setFixedWidth(44)
    btn.setCheckable(True)
    btn.setStyleSheet(
        f"QPushButton {{ background: transparent; color: {MUTED}; font-size: 9px;"
        f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 6px; }}"
        f"QPushButton:checked {{ color: {ACCENT}; border-color: {ACCENT}; }}"
    )

    def _toggle(checked: bool) -> None:
        field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        btn.setText("hide" if checked else "show")

    btn.toggled.connect(_toggle)
    return field, btn


def _password_widget(placeholder: str = "") -> tuple[QWidget, QLineEdit]:
    """Return (wrapper_widget, line_edit) for a password field with show/hide toggle."""
    field, toggle = _password_row(placeholder)
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(field)
    row.addWidget(toggle)
    return w, field


def _path_widget(placeholder: str = "", folder_only: bool = True) -> tuple[QWidget, QLineEdit]:
    """Return (wrapper_widget, line_edit) for a path field with Browse button."""
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setStyleSheet(_FIELD_STYLE)

    btn = QPushButton("Browse…")
    btn.setFixedWidth(70)
    btn.setStyleSheet(_BTN_STYLE)

    def _browse() -> None:
        if folder_only:
            path = QFileDialog.getExistingDirectory(None, "Select folder", field.text() or "")
        else:
            path, _ = QFileDialog.getOpenFileName(None, "Select file", field.text() or "")
        if path:
            field.setText(path)

    btn.clicked.connect(_browse)

    w = QWidget()
    w.setStyleSheet("background: transparent;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(field)
    row.addWidget(btn)
    return w, field


# ─────────────────────────────────────────────────────────────────────────────
# Content pages
# ─────────────────────────────────────────────────────────────────────────────

def _page_wrapper(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
    """Create a standard page container with title and body layout."""
    page = QWidget()
    page.setStyleSheet(f"background: {BG};")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(10)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {ACCENT}; font-size: 15px; font-weight: bold;"
        f"font-family: Georgia, serif; background: transparent; border: none;"
    )
    layout.addWidget(title_lbl)

    sub_lbl = QLabel(subtitle)
    sub_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px; background: transparent; border: none;")
    layout.addWidget(sub_lbl)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px; border: none;")
    layout.addWidget(sep)

    return page, layout


class _ApiKeysPage(QWidget):
    def __init__(self, env_path: str, parent=None) -> None:
        super().__init__(parent)
        self._env_path = env_path
        page, body = _page_wrapper(
            "🔑  API Keys",
            "Stored in variables.env  ·  API key changes take effect on the next agent call or panel reconnect"
        )

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # OpenAI
        body.addWidget(_section_label("OpenAI"))
        openai_w, self._openai = _password_widget("sk-…")
        form.addRow("API Key", openai_w)
        body.addLayout(form)

        form2 = QFormLayout()
        form2.setSpacing(8)
        form2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Spotify
        body.addWidget(_section_label("Spotify", "spotify.png"))
        body.addWidget(_hint(
            "Create an app at developer.spotify.com/dashboard  "
            "·  set Redirect URI to http://localhost:8888/callback"
        ))
        self._spotify_id = QLineEdit()
        self._spotify_id.setPlaceholderText("Client ID")
        self._spotify_id.setStyleSheet(_FIELD_STYLE)

        spotify_secret_w, self._spotify_secret = _password_widget("Client Secret")
        self._spotify_redirect = QLineEdit()
        self._spotify_redirect.setPlaceholderText("http://localhost:8888/callback")
        self._spotify_redirect.setStyleSheet(_FIELD_STYLE)

        form2.addRow("Client ID",       self._spotify_id)
        form2.addRow("Client Secret",   spotify_secret_w)
        form2.addRow("Redirect URI",    self._spotify_redirect)
        body.addLayout(form2)

        form3 = QFormLayout()
        form3.setSpacing(8)
        form3.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form3.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Discord
        body.addWidget(_section_label("Discord", "discord.png"))
        body.addWidget(_hint(
            "Create a bot at discord.com/developers/applications  "
            "·  enable Message Content Intent and voice permissions"
        ))
        discord_w, self._discord_token = _password_widget("Bot token")
        form3.addRow("Bot Token",  discord_w)
        body.addLayout(form3)

        form4 = QFormLayout()
        form4.setSpacing(8)
        form4.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form4.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # YouTube
        body.addWidget(_section_label("YouTube", "youtube.png"))
        body.addWidget(_hint(
            "Get a Data API v3 key from console.cloud.google.com/apis/credentials  ·  "
            "client_secrets.json is only needed for playlist browsing (OAuth2)"
        ))
        yt_key_w, self._youtube_key = _password_widget("YouTube Data API v3 key")
        yt_secrets_w, self._youtube_secrets = _path_widget(
            "Path to client_secrets.json (optional)", folder_only=False
        )
        form4.addRow("API Key",         yt_key_w)
        form4.addRow("Client Secrets",  yt_secrets_w)
        body.addLayout(form4)

        form5 = QFormLayout()
        form5.setSpacing(8)
        form5.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form5.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Syrinscape
        body.addWidget(_section_label("Syrinscape", "syrinscape.png"))
        body.addWidget(_hint(
            "Get your auth token at syrinscape.com/account/auth-token/"
        ))
        syr_w, self._syrinscape_token = _password_widget("Auth token")
        form5.addRow("Auth Token",  syr_w)
        body.addLayout(form5)

        body.addStretch()

        # Embed page into self
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        self._load()

    def _load(self) -> None:
        env = _read_env(self._env_path)
        self._openai.setText(env.get("OPENAI_API_KEY", ""))
        self._spotify_id.setText(env.get("SPOTIFY_CLIENT_ID", ""))
        self._spotify_secret.setText(env.get("SPOTIFY_CLIENT_SECRET", ""))
        self._spotify_redirect.setText(env.get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"))
        self._discord_token.setText(env.get("DISCORD_BOT_TOKEN", ""))
        self._youtube_key.setText(env.get("YOUTUBE_API_KEY", ""))
        self._youtube_secrets.setText(env.get("YOUTUBE_CLIENT_SECRETS_FILE", ""))
        self._syrinscape_token.setText(env.get("SYRINSCAPE_AUTH_TOKEN", ""))

    def save(self) -> dict[str, str]:
        """Write to variables.env and return {key: value} of updated keys."""
        updates = {
            "OPENAI_API_KEY":              self._openai.text().strip(),
            "SPOTIFY_CLIENT_ID":           self._spotify_id.text().strip(),
            "SPOTIFY_CLIENT_SECRET":       self._spotify_secret.text().strip(),
            "SPOTIFY_REDIRECT_URI":        self._spotify_redirect.text().strip()
                                           or "http://localhost:8888/callback",
            "DISCORD_BOT_TOKEN":           self._discord_token.text().strip(),
            "YOUTUBE_API_KEY":             self._youtube_key.text().strip(),
            "YOUTUBE_CLIENT_SECRETS_FILE": self._youtube_secrets.text().strip(),
            "SYRINSCAPE_AUTH_TOKEN":       self._syrinscape_token.text().strip(),
        }
        _write_env(self._env_path, updates)
        for k, v in updates.items():
            if v:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]
        return updates


class _PathsPage(QWidget):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        page, body = _page_wrapper(
            "📁  Paths",
            "Vault and backup locations  ·  changes apply immediately"
        )

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        body.addWidget(_section_label("Obsidian / Vault", "obsidian.png"))
        vault_w, self._vault_path = _path_widget("Path to your Obsidian vault folder")
        form.addRow("Vault folder", vault_w)
        body.addLayout(form)

        body.addWidget(_hint(
            "This sets the default vault Ceres opens at startup. "
            "You can still switch vaults from the Vault panel."
        ))

        body.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        self._load()

    def _load(self) -> None:
        p = getattr(self._config, "default_vault_path", None)
        if p:
            self._vault_path.setText(str(p))

    def save(self) -> None:
        vp = self._vault_path.text().strip()
        if vp:
            self._config.default_vault_path = Path(vp)
            self._config.default_vault_name = Path(vp).name
        self._config.save_settings()


class _InterfacePage(QWidget):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        page, body = _page_wrapper(
            "🖥  Interface",
            "UI behaviour and display options  ·  changes apply on next launch unless noted"
        )

        body.addWidget(_section_label("Console panel"))
        self._hide_console = QCheckBox("Hide console panel on startup  (recommended for most users)")
        self._hide_console.setStyleSheet(
            f"QCheckBox {{ color: {TEXT}; font-size: 11px; background: transparent; }}"
            f"QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px; }}"
            f"QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}"
        )
        body.addWidget(self._hide_console)
        body.addWidget(_hint(
            "The console shows raw command output for power users. "
            "When hidden, you can still open it from View → Console."
        ))

        body.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        self._load()

    def _load(self) -> None:
        self._hide_console.setChecked(
            getattr(self._config, "console_hidden_default", True)
        )

    def save(self) -> None:
        self._config.console_hidden_default = self._hide_console.isChecked()
        self._config.save_settings()


class _FguPage(QWidget):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        page, body = _page_wrapper(
            "Fantasy Grounds",
            "Tell Ceres where to find your FGU data  ·  changes apply immediately"
        )

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        body.addWidget(_section_label("Folders", "fantasygrounds.png"))
        campaigns_w, self._campaigns = _path_widget("e.g.  C:\\Users\\You\\AppData\\Roaming\\SmiteWorks\\Fantasy Grounds\\campaigns")
        logs_w, self._logs = _path_widget("e.g.  C:\\Users\\You\\AppData\\Roaming\\SmiteWorks\\Fantasy Grounds")

        form.addRow("Campaigns folder", campaigns_w)
        form.addRow("FGU data root",    logs_w)
        body.addLayout(form)

        body.addWidget(_hint(
            "The campaigns folder is usually inside your Fantasy Grounds "
            "AppData directory.  The FGU data root is the parent folder "
            "containing campaigns, modules, and images."
        ))

        body.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        self._load()

    def _load(self) -> None:
        c = getattr(self._config, "fgu_campaigns_root", None)
        if c:
            self._campaigns.setText(str(c))
        l = getattr(self._config, "fgu_logs_root", None)
        if l:
            self._logs.setText(str(l))

    def save(self) -> None:
        c = self._campaigns.text().strip()
        self._config.fgu_campaigns_root = Path(c) if c else None
        l = self._logs.text().strip()
        self._config.fgu_logs_root = Path(l) if l else None
        self._config.save_settings()


class _SoundboardPage(QWidget):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        page, body = _page_wrapper(
            "🔊  Soundboard",
            "Add folders full of audio files so Ceres can find them quickly"
        )

        body.addWidget(_section_label("Sound folders"))
        body.addWidget(_hint(
            "Add any folder that contains .mp3, .wav, or .ogg files. "
            "Ceres will scan these when you browse sounds in the Soundboard panel."
        ))

        # Folder list
        self._folder_list = QListWidget()
        self._folder_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._folder_list.setStyleSheet(
            f"QListWidget {{"
            f"  background: {SURFACE}; color: {TEXT}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px;"
            f"}}"
            f"QListWidget::item:selected {{ background: {ACCENT}; color: white; border-radius: 3px; }}"
        )
        self._folder_list.setMinimumHeight(140)
        body.addWidget(self._folder_list)

        # Add / Remove row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        add_btn = QPushButton("+ Add folder")
        add_btn.setStyleSheet(_BTN_STYLE)
        add_btn.clicked.connect(self._add_folder)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove selected")
        remove_btn.setStyleSheet(_BTN_STYLE)
        remove_btn.clicked.connect(self._remove_folder)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        body.addLayout(btn_row)

        body.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        self._load()

    def _load(self) -> None:
        for folder in getattr(self._config, "soundboard_folders", []):
            self._folder_list.addItem(folder)

    def _add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select sound folder", "")
        if path and not self._folder_list.findItems(path, Qt.MatchFlag.MatchExactly):
            self._folder_list.addItem(path)

    def _remove_folder(self) -> None:
        row = self._folder_list.currentRow()
        if row >= 0:
            self._folder_list.takeItem(row)

    def save(self) -> None:
        folders = [
            self._folder_list.item(i).text()
            for i in range(self._folder_list.count())
        ]
        self._config.soundboard_folders = folders
        self._config.save_settings()


class _GeneralPage(QWidget):
    """AI model, voice commands, and session scheduling preferences."""

    _MODELS = ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        page, body = _page_wrapper(
            "⚙  General",
            "AI model, voice commands, and session scheduling"
        )

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # AI Model
        body.addWidget(_section_label("AI Model"))
        self._model_combo = QComboBox()
        self._model_combo.addItems(self._MODELS)
        self._model_combo.setStyleSheet(
            f"QComboBox {{ background: {SURFACE}; color: {TEXT}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 10px; }}"
            f"QComboBox:hover {{ border-color: {ACCENT}; }}"
            f"QComboBox::drop-down {{ border: none; background: {SURFACE}; width: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT};"
            f"  border: 1px solid {ACCENT}; selection-background-color: {ACCENT}; }}"
        )
        form.addRow("Default model", self._model_combo)
        body.addLayout(form)
        body.addWidget(_hint(
            "The model used by the Chat agent and other OpenAI-powered features.  "
            "gpt-4o is recommended for best quality at reasonable cost."
        ))

        # Voice commands
        body.addWidget(_section_label("Voice Commands"))
        self._voice_enabled = QCheckBox("Enable wake-word detection  (Veras / Chroma)")
        self._voice_enabled.setStyleSheet(
            f"QCheckBox {{ color: {TEXT}; font-size: 11px; background: transparent; }}"
            f"QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px; }}"
            f"QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}"
        )
        body.addWidget(self._voice_enabled)
        body.addWidget(_hint(
            "When enabled, the Discord panel listens for wake words in voice "
            "transcriptions and dispatches commands to Spotify, Syrinscape, and YouTube."
        ))

        # Session reminder
        form2 = QFormLayout()
        form2.setSpacing(8)
        form2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        body.addWidget(_section_label("Session Scheduling"))
        self._reminder_hours = QSpinBox()
        self._reminder_hours.setRange(1, 72)
        self._reminder_hours.setSuffix(" hours before")
        self._reminder_hours.setStyleSheet(
            f"QSpinBox {{ background: {SURFACE}; color: {TEXT}; font-size: 11px;"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 10px; }}"
            f"QSpinBox:focus {{ border-color: {ACCENT}; }}"
        )
        form2.addRow("Reminder lead time", self._reminder_hours)
        body.addLayout(form2)
        body.addWidget(_hint(
            "How many hours before a scheduled session to send a reminder "
            "to the Discord channel."
        ))

        body.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        self._load()

    def _load(self) -> None:
        model = getattr(self._config, "default_model", "gpt-4o")
        idx = self._model_combo.findText(model)
        self._model_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self._voice_enabled.setChecked(
            getattr(self._config, "voice_commands_enabled", False)
        )
        self._reminder_hours.setValue(
            getattr(self._config, "session_reminder_hours_before", 24)
        )

    def save(self) -> None:
        self._config.default_model = self._model_combo.currentText()
        self._config.voice_commands_enabled = self._voice_enabled.isChecked()
        self._config.session_reminder_hours_before = self._reminder_hours.value()
        self._config.save_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class PreferencesDialog(QDialog):
    """
    Modal preferences dialog for Project Ceres.

    Args:
        config:    Live Config dataclass (modified in-place on Save).
        env_path:  Path to variables.env (default: "variables.env").
        parent:    Optional parent widget.

    Signals:
        saved: Emitted when the user clicks Save.  Callers can listen to
               apply live changes (e.g. show/hide the console panel).
    """

    saved = Signal()

    _SECTIONS = [
        ("🔑  API Keys",        "API keys for OpenAI, Spotify, Discord, YouTube, Syrinscape", ""),
        ("📁  Paths",            "Vault folder and backup locations",                          ""),
        ("🖥  Interface",        "Console visibility and startup behaviour",                   ""),
        ("⚙  General",          "AI model, voice commands, session scheduling",               ""),
        ("Fantasy Grounds",     "Campaigns folder and FGU data root",             "fantasygrounds.png"),
        ("🔊  Soundboard",       "Sound effect folders",                                      ""),
    ]

    def __init__(self, config, env_path: str = "variables.env", parent=None) -> None:
        super().__init__(parent)
        self._config   = config
        self._env_path = env_path

        self.setWindowTitle("Preferences — Project Ceres")
        self.setMinimumSize(820, 540)
        self.resize(860, 580)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left sidebar ──────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(196)
        sidebar.setStyleSheet(
            f"QWidget {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}"
        )
        slay = QVBoxLayout(sidebar)
        slay.setContentsMargins(0, 12, 0, 12)
        slay.setSpacing(0)

        brand = QLabel("⚙  Preferences")
        brand.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: bold;"
            f"font-family: Georgia, serif; padding: 8px 16px 16px 16px;"
            f"background: transparent; border: none;"
        )
        slay.addWidget(brand)

        self._nav = QListWidget()
        self._nav.setStyleSheet(
            f"QListWidget {{"
            f"  background: transparent; border: none;"
            f"  font-size: 11px; color: {TEXT};"
            f"}}"
            f"QListWidget::item {{"
            f"  padding: 10px 16px; border-left: 3px solid transparent;"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background: {SURFACE}; color: {ACCENT};"
            f"  border-left: 3px solid {ACCENT};"
            f"}}"
            f"QListWidget::item:hover:!selected {{"
            f"  background: {SURFACE}; color: {TEXT};"
            f"}}"
        )
        self._nav.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for label, tooltip, icon_file in self._SECTIONS:
            item = QListWidgetItem(label)
            item.setToolTip(tooltip)
            if icon_file:
                icon_path = _ASSETS / icon_file
                if icon_path.exists():
                    item.setIcon(QIcon(str(icon_path)))
            self._nav.addItem(item)

        self._nav.currentRowChanged.connect(self._switch_page)
        slay.addWidget(self._nav, 1)
        root.addWidget(sidebar)

        # ── Right content area ────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background: {BG};")
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {BG};")

        # Build pages (order must match _SECTIONS)
        self._api_page  = _ApiKeysPage(self._env_path)
        self._path_page = _PathsPage(self._config)
        self._ui_page   = _InterfacePage(self._config)
        self._gen_page  = _GeneralPage(self._config)
        self._fgu_page  = _FguPage(self._config)
        self._sfx_page  = _SoundboardPage(self._config)

        for page in (self._api_page, self._path_page, self._ui_page,
                     self._gen_page, self._fgu_page, self._sfx_page):
            self._stack.addWidget(page)

        rlay.addWidget(self._stack, 1)

        # ── Bottom button bar ─────────────────────────────────────────────────
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}"
        )
        blay = QHBoxLayout(bar)
        blay.setContentsMargins(20, 10, 20, 10)
        blay.setSpacing(10)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 10px; font-style: italic; background: transparent; border: none;"
        )
        blay.addWidget(self._status_lbl, 1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(80, 34)
        cancel_btn.setStyleSheet(_BTN_STYLE)
        cancel_btn.clicked.connect(self.reject)
        blay.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setFixedSize(80, 34)
        save_btn.setStyleSheet(_ACCENT_BTN_STYLE)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        blay.addWidget(save_btn)

        rlay.addWidget(bar)
        root.addWidget(right, 1)

        # Select first section
        self._nav.setCurrentRow(0)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _switch_page(self, row: int) -> None:
        self._stack.setCurrentIndex(row)

    def _save(self) -> None:
        """Save all sections and emit saved signal."""
        try:
            env_updates = self._api_page.save()

            # Update config.openai_key in-memory if the key changed
            new_key = env_updates.get("OPENAI_API_KEY", "")
            if new_key:
                self._config.openai_key = new_key

            self._path_page.save()
            self._ui_page.save()
            self._gen_page.save()
            self._fgu_page.save()
            self._sfx_page.save()

            self._status_lbl.setText("✓  Saved")
            self._status_lbl.setStyleSheet(
                f"color: #66cc66; font-size: 10px; background: transparent; border: none;"
            )
            self.saved.emit()
            self.accept()

        except Exception as exc:
            self._status_lbl.setText(f"⚠  Save failed: {exc}")
            self._status_lbl.setStyleSheet(
                f"color: #e05260; font-size: 10px; background: transparent; border: none;"
            )
