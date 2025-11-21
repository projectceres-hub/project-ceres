"""
Vaults module for Project Ceres.

Provides functions for managing Obsidian vaults, including loading, saving,
and syncing with Obsidian configuration.
"""

import os
import json
import time
import threading
import sys
from typing import Callable, Dict, List, Optional


def display_numbered_vaults(
    vaults: Dict[str, str],
    ignored_vaults: List[str],
    vault_number_map: Dict[str, str]
) -> None:
    """
    Display vaults with numbers and populate number mapping.
    
    Args:
        vaults: Dictionary mapping vault names to paths
        ignored_vaults: List of ignored vault names
        vault_number_map: Dictionary to populate with number-to-name mappings
    """
    vault_number_map.clear()
    print("Available vaults:")
    i = 1
    for name in vaults:
        if name not in ignored_vaults:
            print(f"  {i}. {name}")
            vault_number_map[str(i)] = name
            i += 1

def add_vault(
    path: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    save_vaults: Callable[[], None],
    save_settings: Callable[[], None]
) -> Optional[str]:
    """
    Add a new vault to the vaults dictionary.
    
    Args:
        path: Full path to the vault directory
        vaults: Dictionary mapping vault names to paths
        current_vault: Current active vault name (may be updated)
        save_vaults: Function to save vaults to disk
        save_settings: Function to save settings to disk
        
    Returns:
        Updated current_vault name
    """
    name = os.path.basename(path)
    if name in vaults:
        print("A vault with that name already exists.")
        return current_vault

    vaults[name] = path
    save_vaults()

    if not current_vault:
        current_vault = name
        save_settings()

    print(f"Vault '{name}' added at {path}.")
    return current_vault

def switch_vault(
    name_or_num: str,
    vaults: Dict[str, str],
    vault_number_map: Dict[str, str],
    save_settings: Callable[[], None]
) -> Optional[str]:
    """
    Switch to a different vault by name or number.
    
    Args:
        name_or_num: Vault name or number string
        vaults: Dictionary mapping vault names to paths
        vault_number_map: Dictionary mapping numbers to vault names
        save_settings: Function to save settings to disk
        
    Returns:
        New current vault name, or None if not found
    """
    target = name_or_num.strip().lower()
    if vault_number_map and target in vault_number_map:
        current_vault = vault_number_map[target]
        save_settings()
        print(f"Switched to vault '{current_vault}'.")
        return current_vault

    for k in vaults:
        if k.lower() == target:
            current_vault = k
            save_settings()
            print(f"Switched to vault '{k}'.")
            return current_vault

    print(f"The correct syntax is 'switch (number or vault name)'. You entered: '{name_or_num}'. Use the 'vaults' command to see available vaults.")
    return None

def list_vaults(
    vaults: Dict[str, str],
    current_vault: Optional[str],
    ignored_vaults: List[str]
) -> Dict[str, str]:
    """
    List all vaults and display them with numbers.
    
    Args:
        vaults: Dictionary mapping vault names to paths
        current_vault: Current active vault name
        ignored_vaults: List of ignored vault names
        
    Returns:
        Dictionary mapping numbers to vault names
    """
    if not current_vault or current_vault not in vaults:
        print("No current vault set.")
        return {}

    print("Current Vault:")
    print(f"- {current_vault}: {vaults[current_vault]}")
    print("\nOther Vaults:")
    other_vaults = [k for k in vaults if k != current_vault and k not in ignored_vaults]
    vault_number_map = {}
    for idx, k in enumerate(other_vaults, start=1):
        print(f"Vault {idx}: {k} ({vaults[k]})")
        vault_number_map[str(idx)] = k
    return vault_number_map

def load_vaults() -> Dict[str, str]:
    """
    Load vaults from vaults.json file.
    
    Returns:
        Dictionary mapping vault names to paths (empty if file doesn't exist)
    """
    if os.path.isfile("vaults.json"):
        try:
            with open("vaults.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse vaults.json: {e}")
            print("Hint: The vaults.json file may be corrupted. Check its format or delete it to start fresh.")
            return {}
        except PermissionError as e:
            print(f"Error: Permission denied reading vaults.json: {e}")
            print("Hint: Check that you have read permissions for vaults.json")
            return {}
        except OSError as e:
            print(f"Error: Failed to read vaults.json: {e}")
            print("Hint: Check that the file exists and is accessible.")
            return {}
        except Exception as e:
            print(f"Error: Unexpected error loading vaults: {e}")
            return {}
    return {}

def save_vaults(vaults: Dict[str, str]) -> None:
    """
    Save vaults dictionary to vaults.json file.
    
    Args:
        vaults: Dictionary mapping vault names to paths
    """
    try:
        with open("vaults.json", "w", encoding="utf-8") as f:
            json.dump(vaults, f, ensure_ascii=False, indent=2)
    except PermissionError as e:
        print(f"Error: Permission denied writing to vaults.json: {e}")
        print("Hint: Check that you have write permissions in the current directory.")
    except OSError as e:
        print(f"Error: Failed to save vaults.json: {e}")
        print("Hint: Check that the current directory is writable and disk space is available.")
    except Exception as e:
        print(f"Error: Unexpected error saving vaults: {e}")
        print("Hint: Check file permissions and disk space.")

def sync_obsidian_vaults(
    obsidian_json_path: str,
    vaults: Dict[str, str],
    ignored_vaults: List[str],
    save_vaults: Callable[[Dict[str, str]], None]
) -> None:
    """
    Sync vaults from Obsidian configuration file.
    
    Adds any new vaults found in Obsidian config that aren't in the vaults dict.
    
    Args:
        obsidian_json_path: Path to Obsidian's obsidian.json file
        vaults: Dictionary mapping vault names to paths (modified in place)
        ignored_vaults: List of ignored vault names
        save_vaults: Function to save vaults dictionary
    """
    if not os.path.isfile(obsidian_json_path):
        return

    try:
        with open(obsidian_json_path, "r", encoding="utf-8") as f:
            obsidian_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse Obsidian config file: {e}")
        print(f"Hint: The Obsidian config at '{obsidian_json_path}' may be corrupted.")
        return
    except PermissionError as e:
        print(f"Error: Permission denied reading Obsidian config: {e}")
        print(f"Hint: Check read permissions for '{obsidian_json_path}'")
        return
    except OSError as e:
        print(f"Error: Failed to read Obsidian config: {e}")
        print(f"Hint: Check that '{obsidian_json_path}' exists and is accessible.")
        return
    except Exception as e:
        print(f"Error: Unexpected error reading Obsidian config: {e}")
        return

    updated = False
    try:
        for vault, info in obsidian_data.get("vaults", {}).items():
            path = info["path"]
            name = os.path.basename(path)
            if name in ignored_vaults:
                continue
            if name not in vaults:
                vaults[name] = path
                updated = True
                print(f"[Auto-Import] New vault found in Obsidian: {name}")
    except (KeyError, TypeError) as e:
        print(f"Error: Invalid format in Obsidian config: {e}")
        print("Hint: The Obsidian config file structure may have changed.")
        return
    except Exception as e:
        print(f"Error: Unexpected error processing Obsidian vaults: {e}")
        return

    if updated:
        save_vaults(vaults)

def periodic_obsidian_sync(
    obsidian_json_path: str,
    vaults: Dict[str, str],
    ignored_vaults: List[str],
    save_vaults: Callable[[Dict[str, str]], None],
    interval: int = 15
) -> None:
    """
    Start a background thread to periodically sync Obsidian vaults.
    
    Args:
        obsidian_json_path: Path to Obsidian's obsidian.json file
        vaults: Dictionary mapping vault names to paths
        ignored_vaults: List of ignored vault names
        save_vaults: Function to save vaults dictionary
        interval: Sync interval in seconds (default: 15)
    """
    def sync_loop():
        while True:
            sync_obsidian_vaults(obsidian_json_path, vaults, ignored_vaults, save_vaults)
            time.sleep(interval)
    threading.Thread(target=sync_loop, daemon=True).start()

def get_obsidian_json_path() -> str:
    """
    Get the path to Obsidian's configuration file based on platform.
    
    Returns:
        Path to obsidian.json file
        
    Raises:
        KeyError: If required environment variable is missing (Windows)
    """
    try:
        if sys.platform == "win32":
            return os.path.join(os.environ["APPDATA"], "Obsidian", "obsidian.json")
        elif sys.platform == "darwin":
            return os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json")
        else:
            return os.path.expanduser("~/.config/obsidian/obsidian.json")
    except KeyError as e:
        print(f"Error: Required environment variable not found: {e}")
        print("Hint: On Windows, APPDATA should be set automatically. Check your system environment.")
        raise
    except Exception as e:
        print(f"Error: Unexpected error getting Obsidian config path: {e}")
        raise

def ensure_default_vault(
    config,
    save_vaults: Callable[[Dict[str, str]], None],
    save_settings: Callable[[], None]
) -> Optional[str]:
    """
    Ensure the default vault exists and is set as current if needed.
    
    Args:
        config: Config object containing default_vault_name and default_vault_path
        save_vaults: Function to save vaults dictionary
        save_settings: Function to save settings to disk
        
    Returns:
        Updated current_vault name
    """
    default_vault_name = config.default_vault_name
    default_vault_path = str(config.default_vault_path)
    if default_vault_name not in config.vaults:
        config.vaults[default_vault_name] = default_vault_path
        save_vaults(config.vaults)
        print(f"Default vault '{default_vault_name}' added.")
    else:
        print(f"Default vault '{default_vault_name}' already present.")

    if not config.current_vault:
        config.current_vault = default_vault_name
        save_settings()
        print(f"Current vault set to '{default_vault_name}'.")
    else:
        print(f"Current vault remains '{config.current_vault}'.")

    return config.current_vault

def cmd_addvault(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    save_vaults: Callable[[Dict[str, str]], None],
    save_settings: Callable[[], None],
    prompt_input: Callable[[str], str],
    list_vaults: Callable,
    ignored_vaults: List[str]
) -> Optional[str]:
    """
    Command handler for adding a vault.
    
    Args:
        args: Vault path
        vaults: Dictionary mapping vault names to paths
        current_vault: Current active vault name
        save_vaults: Function to save vaults dictionary
        save_settings: Function to save settings to disk
        prompt_input: Function to get user input
        list_vaults: Function to list vaults
        ignored_vaults: List of ignored vault names
        
    Returns:
        Updated current_vault name
    """
    path = args.strip()
    current_vault = add_vault(path, vaults, current_vault, save_vaults, save_settings)
    list_vaults(vaults, current_vault, ignored_vaults)
    return current_vault

def cmd_switch(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    vault_number_map: Dict[str, str],
    save_settings: Callable[[], None],
    prompt_input: Callable[[str], str],
    list_vaults: Callable,
    ignored_vaults: List[str],
    display_numbered_vaults: Callable
) -> Optional[str]:
    """
    Command handler for switching vaults.
    
    Args:
        args: Vault name or number (empty to prompt)
        vaults: Dictionary mapping vault names to paths
        current_vault: Current active vault name
        vault_number_map: Dictionary mapping numbers to vault names
        save_settings: Function to save settings to disk
        prompt_input: Function to get user input
        list_vaults: Function to list vaults
        ignored_vaults: List of ignored vault names
        display_numbered_vaults: Function to display numbered vaults
        
    Returns:
        Updated current_vault name
    """
    if not args.strip():
        display_numbered_vaults(vaults, ignored_vaults, vault_number_map)
        args = prompt_input("Enter vault name or number: ").strip()

    return switch_vault(args, vaults, vault_number_map, save_settings) or current_vault


def cmd_vaults(
    vaults: Dict[str, str],
    current_vault: Optional[str],
    ignored_vaults: List[str]
) -> Dict[str, str]:
    """
    Command handler for listing vaults.
    
    Args:
        vaults: Dictionary mapping vault names to paths
        current_vault: Current active vault name
        ignored_vaults: List of ignored vault names
        
    Returns:
        Dictionary mapping numbers to vault names
    """
    return list_vaults(vaults, current_vault, ignored_vaults)

def cmd_ignorevault(
    args: str,
    ignored_vaults: List[str],
    save_settings: Callable[[], None]
) -> None:
    """
    Command handler for ignoring a vault.
    
    Args:
        args: Vault name to ignore
        ignored_vaults: List of ignored vault names (modified in place)
        save_settings: Function to save settings to disk
    """
    name = args.strip()
    if name not in ignored_vaults:
        ignored_vaults.append(name)
        save_settings()
        print(f"Vault '{name}' added to ignore list.")
    else:
        print(f"Vault '{name}' is already in the ignore list.")

def cmd_unignorevault(
    args: str,
    ignored_vaults: List[str],
    save_settings: Callable[[], None]
) -> None:
    """
    Command handler for unignoring a vault.
    
    Args:
        args: Vault name to unignore
        ignored_vaults: List of ignored vault names (modified in place)
        save_settings: Function to save settings to disk
    """
    name = args.strip()
    if name in ignored_vaults:
        ignored_vaults.remove(name)
        save_settings()
        print(f"Vault '{name}' removed from ignore list.")
    else:
        print(f"Vault '{name}' was not in the ignore list.")
