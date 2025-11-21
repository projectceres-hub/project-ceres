"""
Configuration management for Project Ceres.

This module provides a centralized Config class to manage application state,
replacing global variables with a clean, dependency-injectable configuration object.
"""

import os
import json
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
            except json.JSONDecodeError as e:
                print(f"Error: Failed to parse settings.json: {e}")
                print("Hint: The settings.json file may be corrupted. Check its format.")
                self.current_vault = next(iter(self.vaults), None)
                self.ignored_vaults = []
            except PermissionError as e:
                print(f"Error: Permission denied reading settings.json: {e}")
                print("Hint: Check that you have read permissions for settings.json")
                self.current_vault = next(iter(self.vaults), None)
                self.ignored_vaults = []
            except OSError as e:
                print(f"Error: Failed to read settings.json: {e}")
                print("Hint: Check that the file exists and is accessible.")
                self.current_vault = next(iter(self.vaults), None)
                self.ignored_vaults = []
            except Exception as e:
                print(f"Error: Unexpected error loading settings: {e}")
                self.current_vault = next(iter(self.vaults), None)
                self.ignored_vaults = []
        else:
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
    
    def save_settings(self) -> None:
        """
        Save current settings to settings.json file.
        
        Note: openai_key is NOT saved to file for security reasons.
        """
        try:
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump({
                    "current_vault": self.current_vault,
                    "ignored_vaults": self.ignored_vaults,
                    "default_model": self.default_model,
                    "templates_remote_url": self.templates_remote_url,
                    "templates_local_path": str(self.templates_local_path) if self.templates_local_path else None
                }, f)
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
            with open("vaults.json", "w", encoding="utf-8") as f:
                json.dump(self.vaults, f, ensure_ascii=False, indent=2)
        except PermissionError as e:
            print(f"Error: Permission denied writing to vaults.json: {e}")
            print("Hint: Check that you have write permissions in the current directory.")
        except OSError as e:
            print(f"Error: Failed to save vaults.json: {e}")
            print("Hint: Check that the current directory is writable and disk space is available.")
        except Exception as e:
            print(f"Error: Unexpected error saving vaults: {e}")
            print("Hint: Check file permissions and disk space.")
    
    def register_command(self, name: str, func: Callable, help_text: str) -> None:
        """
        Register a command in the command registry.
        
        Args:
            name: Command name
            func: Command function
            help_text: Help text for the command
        """
        self.commands[name] = (func, help_text)

