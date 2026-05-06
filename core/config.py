"""
Configuration management for Project Ceres.

This module provides a centralized Config class to manage application state,
replacing global variables with a clean, dependency-injectable configuration object.
"""

import os
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field


@dataclass
class Config:
    """
    Centralized configuration object for GM Assistant.
    
    Manages vaults, current vault, ignored vaults, command registry, and
    application-wide settings like default paths and API keys.
    """
    
    # Application state
    vaults: Dict[str, str] = field(default_factory=dict)
    current_vault: Optional[str] = None
    ignored_vaults: List[str] = field(default_factory=list)
    vault_number_map: Dict[str, str] = field(default_factory=dict)
    commands: Dict[str, Tuple[Callable, str]] = field(default_factory=dict)
    
    # Central settings
    default_vault_path: Path = field(default_factory=lambda: Path("GMAssistantVault").resolve())
    default_vault_name: str = "GMAssistantVault"
    default_import_subfolder: str = "Converted"
    default_model: str = "gpt-4o"
    openai_key: Optional[str] = None
    env_file: str = "variables.env"
    templates_remote_url: Optional[str] = None
    templates_local_path: Optional[Path] = None
    session_reminder_hours_before: int = 24
    fgu_logs_root: Optional[Path] = None
    fgu_campaigns_root: Optional[Path] = None   # user-chosen campaigns folder
    voice_commands_enabled: bool = False
    console_hidden_default: bool = True     # hide the console panel on startup
    soundboard_folders: List[str] = field(default_factory=list)  # user-added SFX folders

    # Plex / Jellyfin
    plex_jellyfin_server_type: str = "Jellyfin"   # "Plex" | "Jellyfin"
    plex_jellyfin_url: str = ""                   # e.g. http://localhost:8096
    # Token is NOT stored here — lives in variables.env as PLEX_JELLYFIN_TOKEN

    # Equalizer
    eq_enabled: bool = False
    eq_preset: str = "Flat"
    eq_bands: List[float] = field(default_factory=lambda: [0.0] * 10)
    # bands index → Hz: [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
    # values: -12.0 to +12.0 dB; 0.0 = flat

    # Input provider — swappable callable used by all interactive command prompts.
    # Signature: (prompt_message: str) -> str
    #
    # CLI mode:  set to the module-level prompt_input() in assistant.py (uses input())
    # UI mode:   replace with a function that posts a dialog / uses a queue /
    #            awaits a callback — whatever the UI framework requires.
    #
    # Any command handler that needs to ask the user a question should receive
    # this via its prompt_input_func parameter (already the case for most handlers).
    # Never call input() directly in new code; always go through this provider.
    input_provider: Optional[Callable[[str], str]] = field(default=None, repr=False)

    # Thread-safety lock — guards vaults, ignored_vaults, and commands against
    # concurrent reads (scheduler thread) / writes (main thread).
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Initialize after dataclass creation."""
        # Ensure default_vault_name matches default_vault_path if not explicitly set
        if self.default_vault_name == "GMAssistantVault" and self.default_vault_path.name != "GMAssistantVault":
            self.default_vault_name = self.default_vault_path.name
    
    def load_settings(self) -> None:
        """
        Load settings from settings.json file.

        If file doesn't exist, sets current_vault to first vault if available.
        Also loads OpenAI key from environment if not set.
        """
        if os.path.isfile("settings.json"):
            try:
                with open("settings.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self.current_vault = data.get("current_vault")
                    self.ignored_vaults = data.get("ignored_vaults", [])
                    # Load optional config fields
                    if "default_model" in data:
                        self.default_model = data.get("default_model", self.default_model)
                    if "openai_key" in data:
                        self.openai_key = data.get("openai_key")
                    if "templates_remote_url" in data:
                        self.templates_remote_url = data.get("templates_remote_url")
                    if "templates_local_path" in data:
                        path_str = data.get("templates_local_path")
                        if path_str:
                            self.templates_local_path = Path(path_str)
                        else:
                            self.templates_local_path = None
                    if "session_reminder_hours_before" in data:
                        self.session_reminder_hours_before = data.get("session_reminder_hours_before", 24)
                    if "fgu_logs_root" in data:
                        path_str = data.get("fgu_logs_root")
                        if path_str:
                            self.fgu_logs_root = Path(path_str)
                        else:
                            self.fgu_logs_root = None
                    if "fgu_campaigns_root" in data:
                        path_str = data.get("fgu_campaigns_root")
                        if path_str:
                            self.fgu_campaigns_root = Path(path_str)
                        else:
                            self.fgu_campaigns_root = None
                    if "voice_commands_enabled" in data:
                        self.voice_commands_enabled = data.get("voice_commands_enabled", False)
                    if "console_hidden_default" in data:
                        self.console_hidden_default = data.get("console_hidden_default", True)
                    if "soundboard_folders" in data:
                        self.soundboard_folders = data.get("soundboard_folders", [])
                    if "plex_jellyfin_server_type" in data:
                        self.plex_jellyfin_server_type = str(data.get("plex_jellyfin_server_type", "Jellyfin"))
                    if "plex_jellyfin_url" in data:
                        self.plex_jellyfin_url = str(data.get("plex_jellyfin_url", ""))
                    if "eq_enabled" in data:
                        self.eq_enabled = bool(data.get("eq_enabled", False))
                    if "eq_preset" in data:
                        self.eq_preset = str(data.get("eq_preset", "Flat"))
                    if "eq_bands" in data:
                        raw = data.get("eq_bands", [0.0] * 10)
                        if isinstance(raw, list) and len(raw) == 10:
                            self.eq_bands = [float(v) for v in raw]
            except json.JSONDecodeError as e:
                print(f"Error: Failed to parse settings.json: {e}")
                print("Hint: The settings.json file may be corrupted. Check its format.")
                with self._lock:
                    self.current_vault = next(iter(self.vaults), None)
                    self.ignored_vaults = []
            except PermissionError as e:
                print(f"Error: Permission denied reading settings.json: {e}")
                print("Hint: Check that you have read permissions for settings.json")
                with self._lock:
                    self.current_vault = next(iter(self.vaults), None)
                    self.ignored_vaults = []
            except OSError as e:
                print(f"Error: Failed to read settings.json: {e}")
                print("Hint: Check that the file exists and is accessible.")
                with self._lock:
                    self.current_vault = next(iter(self.vaults), None)
                    self.ignored_vaults = []
            except Exception as e:
                print(f"Error: Unexpected error loading settings: {e}")
                with self._lock:
                    self.current_vault = next(iter(self.vaults), None)
                    self.ignored_vaults = []
        else:
            with self._lock:
                self.current_vault = next(iter(self.vaults), None)
                self.ignored_vaults = []

        # Load OpenAI key from environment if not set
        if self.openai_key is None:
            try:
                from dotenv import load_dotenv
                load_dotenv(self.env_file)
                self.openai_key = os.getenv("OPENAI_API_KEY")
            except Exception as e:
                print(f"Warning: Failed to load OpenAI key from environment: {e}")
                print(f"Hint: Check that '{self.env_file}' exists and contains OPENAI_API_KEY")

        # Normalize empty key to None so the rest of the app can treat None as "key not set"
        if self.openai_key is not None and self.openai_key.strip() == "":
            print("Warning: OPENAI_API_KEY is set but empty. GPT features will not work.")
            print("Hint: Set a valid key in your variables.env file or in settings.json.")
            self.openai_key = None

    def save_settings(self) -> None:
        """
        Save current settings to settings.json file.

        Note: openai_key is NOT saved to file for security reasons.
        """
        try:
            with self._lock:
                snapshot = {
                    "current_vault": self.current_vault,
                    "ignored_vaults": list(self.ignored_vaults),
                    "default_model": self.default_model,
                    "templates_remote_url": self.templates_remote_url,
                    "templates_local_path": str(self.templates_local_path) if self.templates_local_path else None,
                    "session_reminder_hours_before": self.session_reminder_hours_before,
                    "fgu_logs_root": str(self.fgu_logs_root) if self.fgu_logs_root else None,
                    "fgu_campaigns_root": str(self.fgu_campaigns_root) if self.fgu_campaigns_root else None,
                    "voice_commands_enabled": self.voice_commands_enabled,
                    "console_hidden_default": self.console_hidden_default,
                    "soundboard_folders": list(self.soundboard_folders),
                    "plex_jellyfin_server_type": self.plex_jellyfin_server_type,
                    "plex_jellyfin_url":         self.plex_jellyfin_url,
                    "eq_enabled":       self.eq_enabled,
                    "eq_preset":        self.eq_preset,
                    "eq_bands":         list(self.eq_bands),
                }
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(snapshot, f)
        except PermissionError as e:
            print(f"Error: Permission denied writing to settings.json: {e}")
            print("Hint: Check that you have write permissions in the current directory.")
        except OSError as e:
            print(f"Error: Failed to save settings.json: {e}")
            print("Hint: Check that the current directory is writable and disk space is available.")
        except Exception as e:
            print(f"Error: Unexpected error saving settings: {e}")
            print("Hint: Check file permissions and disk space.")
    
    def save_vaults(self) -> None:
        """Save vaults dictionary to vaults.json file."""
        try:
            with self._lock:
                vaults_snapshot = dict(self.vaults)
            with open("vaults.json", "w", encoding="utf-8") as f:
                json.dump(vaults_snapshot, f, ensure_ascii=False, indent=2)
        except PermissionError as e:
            print(f"Error: Permission denied writing to vaults.json: {e}")
            print("Hint: Check that you have write permissions in the current directory.")
        except OSError as e:
            print(f"Error: Failed to save vaults.json: {e}")
            print("Hint: Check that the current directory is writable and disk space is available.")
        except Exception as e:
            print(f"Error: Unexpected error saving vaults: {e}")
            print("Hint: Check file permissions and disk space.")

    def register_command(self, name: str, func: Callable[[str], None], help_text: str) -> None:
        """Register a command handler in the shared command registry."""
        with self._lock:
            self.commands[name.lower()] = (func, help_text)
