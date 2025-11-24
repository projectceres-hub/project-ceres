#!/usr/bin/env python3

"""
GM Assistant - Terminal assistant for managing Obsidian markdown vaults.

Main entry point for Project Ceres.
"""

# 1. IMPORTS AND STUFF
from dotenv import load_dotenv
import os
import json
from pathlib import Path
from core.config import Config
from core.gpt import cmd_gptwrite, cmd_editnote, create_gpt_client
from core.notes import cmd_read, cmd_list, cmd_send, list_md_files, read_md_file, cmd_createnote, cmd_tree
from core.templates import cmd_showtemplates, cmd_createtemplate, cmd_deletetemplate, cmd_uploadalltemplates, cmd_uploadtemplate
from core.vaults import (
    add_vault,
    list_vaults,
    load_vaults,
    sync_obsidian_vaults,
    periodic_obsidian_sync,
    get_obsidian_json_path,
    ensure_default_vault,
    cmd_addvault,
    cmd_switch,
    cmd_vaults,
    cmd_ignorevault,
    cmd_unignorevault,
    display_numbered_vaults
)
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import NestedCompleter, Completer, Completion
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
try:
    from prompt_toolkit.completion import CompleteStyle
except Exception:
    try:
        from prompt_toolkit.shortcuts.prompt import CompleteStyle
    except Exception:
        try:
            from prompt_toolkit.enums import CompleteStyle
        except Exception:
            CompleteStyle = None  # Fallback if not found
from core.search_index import cmd_search, build_search_index
from core.srd_index import cmd_srd_index, cmd_search_srd
from core.pdf import convert_pdf_to_md
from core.session_scheduler import schedule_next_session
from core.scheduler import Scheduler, register_default_jobs
from core.history import HistoryManager
from core.tags import get_tags_for_note, add_tag, remove_tag, list_all_tags, get_all_tags
from typing import Callable, Dict, List, Optional, Any, Tuple
import yaml
import shlex


# Constants
VERSION: str = "0.1"

# Error messages dictionary
ERRORS: Dict[str, str] = {
    "no_vault": "No current vault set. Use 'switch' to select one or 'addvault' to add one.",
    "file_not_found": "File not found: {filename}. Use 'list' to see available files or 'switch' to switch vaults.",
    "ambiguous_file": "Multiple notes found named '{filename}':",
    "vault_not_found": "Vault '{name}' not found.",
    "already_ignored": "Vault '{name}' is already ignored.",
    "not_ignored": "Vault '{name}' is not currently ignored.",
    "usage_ignorevault": "Usage: ignorevault VAULTNAME",
    "usage_unignorevault": "Usage: unignorevault VAULTNAME",
    "default_exists": "A vault with that name already exists.",
    "obsidian_not_found": "Obsidian config not found. Manual vault add only.",
    "unknown_command": "Unknown command. Type 'help' to see available commands.",
    "no_ignored_vaults": " There are currently no ignored vaults.",
    "specify_full_path": "Please specify the full path (e.g., '{example}').",
    "vault_switch_fail": "No vault named or numbered '{query}'. Use the 'vaults' command to see available vaults.",
}


class SchedulerContext:
    """
    Context object for scheduler jobs containing necessary dependencies.
    
    Attributes:
        obsidian_json_path: Path to Obsidian configuration file
        vaults: Dictionary mapping vault names to paths
        ignored_vaults: List of ignored vault names
        save_vaults: Callable to save vaults dictionary
        current_vault: Name of the current active vault
    """
    def __init__(self) -> None:
        """Initialize scheduler context with empty values."""
        self.obsidian_json_path: str = ""
        self.vaults: Dict[str, str] = {}
        self.ignored_vaults: List[str] = []
        self.save_vaults: Optional[Callable[[Dict[str, str]], None]] = None
        self.current_vault: Optional[str] = None


def create_save_vaults_wrapper(config: Config) -> Callable[[Dict[str, str]], None]:
    """
    Create a wrapper function to save vaults using config.
    
    Args:
        config: Configuration object
        
    Returns:
        Function that saves vaults dictionary
    """
    def save_vaults_wrapper(vaults_dict: Dict[str, str]) -> None:
        """Wrapper to save vaults using config."""
        config.vaults = vaults_dict
        config.save_vaults()
    return save_vaults_wrapper

# 1.1 Start Up


def print_startup_summary(config: Config) -> None:
    """Print startup summary with vault information."""
    print(f"\nGM Assistant v{VERSION}\n")
    active_vaults = [v for v in config.vaults if v not in config.ignored_vaults]
    print(f"Loaded {len(active_vaults)} vaults:")
    for v in active_vaults:
        print(f" - {v}")
    print(f"\nCurrent vault: {config.current_vault}")
    if config.ignored_vaults:
        print("Ignored vaults: " + ", ".join(config.ignored_vaults))
    else:
        print("Ignored vaults: (none)")
    print("Tip: Type 'help' to see available commands!\n")


# 2. APP SETTINGS

def get_note_names(config: Config, error_func: Callable[[str, ...], None]) -> Dict[str, Any]:
    """
    Build note tree structure for autocompletion.
    
    Args:
        config: Configuration object
        error_func: Error handling function
        
    Returns:
        Nested dictionary representing note tree structure
    """
    note_tree: Dict[str, Any] = {}
    notes = list_md_files(config.vaults, config.current_vault, error_func, config.default_vault_name)
    for note in notes:
        parts = note.split(os.sep)
        current_level = note_tree
        for part in parts[:-1]:  # folders
            current_level = current_level.setdefault(part + "/", {})
        current_level[parts[-1]] = None  # final file
    return note_tree

def get_vault_names(config: Config) -> Dict[str, None]:
    """
    Get vault names for autocompletion.
    
    Args:
        config: Configuration object
        
    Returns:
        Dictionary mapping vault names to None (for completer)
    """
    return {v: None for v in config.vaults}

def get_note_name_list(config: Config, error_func: Callable[[str, ...], None]) -> List[str]:
    """
    Get a flat list of note names for autocompletion.
    
    Args:
        config: Configuration object
        error_func: Error handling function
        
    Returns:
        List of note file paths (relative to vault root)
    """
    return list_md_files(config.vaults, config.current_vault, error_func, config.default_vault_name)

def get_tag_completions(config: Config) -> List[str]:
    """
    Get all tags for autocompletion.
    
    Args:
        config: Configuration object
        
    Returns:
        List of tag names (with and without # prefix for flexibility)
    """
    if not config.current_vault or config.current_vault not in config.vaults:
        return []
    
    vault_path = Path(config.vaults[config.current_vault])
    try:
        tags = get_all_tags(vault_path)
        # Return tags both with and without # prefix
        completions = []
        for tag in sorted(tags):
            completions.append(tag)  # Without #
            completions.append(f"#{tag}")  # With #
        return completions
    except Exception:
        return []


class ContextAwareCompleter(Completer):
    """
    Context-aware completer for command-line autocompletion.
    
    Handles special cases for tag commands with argument-position-aware completion:
    - tag-add and tag-remove: note names for arg 2, tags for arg 3
    - tag-notes: tags for arg 2
    - Other commands: use nested completer behavior
    """
    
    def __init__(
        self,
        config: Config,
        error_func: Callable[[str, ...], None],
        base_completer: NestedCompleter
    ) -> None:
        """
        Initialize the context-aware completer.
        
        Args:
            config: Configuration object
            error_func: Error handling function
            base_completer: Base NestedCompleter for standard command completion
        """
        self.config = config
        self.error_func = error_func
        self.base_completer = base_completer
        self._note_cache: Optional[List[str]] = None
        self._tag_cache: Optional[List[str]] = None
    
    def _refresh_caches(self) -> None:
        """Refresh cached note and tag lists."""
        self._note_cache = get_note_name_list(self.config, self.error_func)
        self._tag_cache = get_tag_completions(self.config)
    
    def get_completions(self, document, complete_event):
        """
        Get completions based on current context.
        
        Args:
            document: Current document being edited
            complete_event: Completion event
            
        Yields:
            Completion objects
        """
        text = document.text_before_cursor
        parts = text.strip().split()
        
        # If no text, use base completer for command names
        if not parts:
            yield from self.base_completer.get_completions(document, complete_event)
            return
        
        cmd_name = parts[0].lower()
        arg_count = len(parts) - 1  # Number of arguments after command (including partial)
        
        # Get the current word being typed (may be partial)
        current_word = ""
        if text.strip():
            # Find the last space to get the current word
            last_space = text.rfind(" ")
            if last_space >= 0:
                current_word = text[last_space + 1:]
            else:
                # No space, entire text is the current word (command name)
                current_word = text.strip()
        
        # Handle tag commands with context-aware completion
        if cmd_name in ("tag-add", "tag-remove"):
            if arg_count == 1:
                # First argument (note): suggest note names
                if self._note_cache is None:
                    self._refresh_caches()
                # Current word is the note name being typed
                search_word = current_word if len(parts) > 1 else ""
                for note in self._note_cache or []:
                    if note.lower().startswith(search_word.lower()):
                        yield Completion(note, start_position=-len(search_word))
            elif arg_count == 2:
                # Second argument (tag): suggest tags
                if self._tag_cache is None:
                    self._refresh_caches()
                # Current word is the tag being typed
                search_word = current_word.lstrip("#")
                for tag in self._tag_cache or []:
                    # Match if tag starts with search word (with or without #)
                    tag_clean = tag.lstrip("#")
                    if tag_clean.lower().startswith(search_word.lower()):
                        yield Completion(tag, start_position=-len(current_word))
            else:
                # Too many arguments or command only, no completion
                if arg_count == 0:
                    # Just the command, use base completer
                    yield from self.base_completer.get_completions(document, complete_event)
                return
        elif cmd_name == "tag-notes":
            if arg_count == 1:
                # First argument (tag): suggest tags
                if self._tag_cache is None:
                    self._refresh_caches()
                # Current word is the tag being typed
                search_word = current_word.lstrip("#")
                for tag in self._tag_cache or []:
                    # Match if tag starts with search word (with or without #)
                    tag_clean = tag.lstrip("#")
                    if tag_clean.lower().startswith(search_word.lower()):
                        yield Completion(tag, start_position=-len(current_word))
            else:
                # Too many arguments or command only, no completion
                if arg_count == 0:
                    # Just the command, use base completer
                    yield from self.base_completer.get_completions(document, complete_event)
                return
        else:
            # For other commands, use base completer
            yield from self.base_completer.get_completions(document, complete_event)

def build_completer(config: Config, error_func: Callable[[str, ...], None]) -> Completer:
    """
    Build command completer for prompt_toolkit.
    
    Dynamically generates the completer dictionary from all registered commands
    in config.commands. Commands that require nested completions (like note names
    or vault names) are handled specially.
    
    Args:
        config: Configuration object containing registered commands
        error_func: Error handling function
        
    Returns:
        NestedCompleter instance for command autocompletion
    """
    # Commands that need nested completions (note names or vault names)
    note_name_commands = {"read", "send", "editnote"}
    vault_name_commands = {"switch", "ignorevault", "unignorevault"}
    
    # Build completer dictionary from all registered commands
    completer_dict: Dict[str, Any] = {}
    
    # Add all registered commands to the completer
    for cmd_name in config.commands.keys():
        if cmd_name in note_name_commands:
            # Commands with note name completions
            completer_dict[cmd_name] = get_note_names(config, error_func)
        elif cmd_name in vault_name_commands:
            # Commands with vault name completions
            completer_dict[cmd_name] = get_vault_names(config)
        else:
            # Commands without nested completions
            completer_dict[cmd_name] = None
    
    # Create base nested completer
    base_completer = NestedCompleter.from_nested_dict(completer_dict)
    
    # Wrap in context-aware completer for tag commands
    return ContextAwareCompleter(config, error_func, base_completer)

def error(msg_key: str, **kwargs: Any) -> None:
    """
    Display an error message.
    
    Args:
        msg_key: Error message key from ERRORS dictionary
        **kwargs: Format arguments for the error message
    """
    msg = ERRORS.get(msg_key, "Unknown error.").format(**kwargs)
    print(msg)

def prompt_input(message: str) -> str:
    """
    Get user input with cancel support.
    
    Args:
        message: Prompt message to display
        
    Returns:
        User input string
        
    Raises:
        KeyboardInterrupt: If user types "cancel"
    """
    ans = input(message).strip()
    if ans.lower() == "cancel":
        print("Action canceled.")
        raise KeyboardInterrupt("Canceled by user")
    return ans

# Settings functions now use config.save_settings() and config.load_settings()



# 3. WHO COMMANDS THE COMMANDER

def register_command(config: Config, name: str, func: Callable[[str], None], help_text: str) -> None:
    """
    Register a command in the command registry.
    
    Args:
        config: Configuration object
        name: Command name
        func: Command function (takes args string)
        help_text: Help text for the command
    """
    config.register_command(name, func, help_text)

def cmd_exit(args: str) -> None:
    """
    Exit the assistant.
    
    Args:
        args: Command arguments (unused)
    """
    exit()

def cmd_help(args: str, config: Config) -> None:
    """
    Show help message with all available commands.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
    """
    print("Available commands:")
    for cmd, (_, help_text) in config.commands.items():
        print(f" {cmd}: {help_text}")

def _resolve_note_path(
    note_name: str,
    vaults: Dict[str, str],
    current_vault: Optional[str]
) -> Optional[Path]:
    """
    Resolve a note name to a full path.
    
    Helper function to convert a note name (e.g., "MyNote.md" or "MyNote")
    to a full Path object within the current vault.
    
    Args:
        note_name: Note name (with or without .md extension)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        
    Returns:
        Path object if note exists, None otherwise
    """
    if not current_vault or current_vault not in vaults:
        print("Error: No current vault selected.")
        return None
    
    # Resolve note path
    if not note_name.endswith(".md"):
        note_name += ".md"
    note_path = Path(vaults[current_vault]) / note_name
    
    if not note_path.exists():
        print(f"Error: Note '{note_name}' not found in current vault.")
        return None
    
    return note_path


def cmd_undo(
    args: str,
    history_manager: HistoryManager,
    vaults: Dict[str, str],
    current_vault: Optional[str]
) -> None:
    """
    Undo the last operation on a note.
    
    Convenience wrapper that restores the most recent version.
    
    Args:
        args: Optional note path. If provided, undo last operation for that note.
              If empty, undo the most recent operation across all notes.
        history_manager: History manager instance
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
    """
    note_path: Optional[Path] = None
    
    if args.strip():
        # User specified a note path
        note_path = _resolve_note_path(args.strip(), vaults, current_vault)
        if note_path is None:
            return
    else:
        # No path specified - undo most recent operation
        note_path = None
    
    # Perform undo
    success = history_manager.undo_last(note_path)
    if not success:
        if note_path is None:
            print("No operations to undo.")
        else:
            print(f"No history found for note: {note_path}")


def cmd_history_list(
    args: str,
    history_manager: HistoryManager,
    vaults: Dict[str, str],
    current_vault: Optional[str]
) -> None:
    """
    List history entries for a note.
    
    Shows the last N backups for that note with numbered entries.
    
    Usage: history-list <note> [limit]
    
    Args:
        args: Note name and optional limit (space-separated)
        history_manager: History manager instance
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
    """
    if not args.strip():
        print("Usage: history-list <note> [limit]")
        print("Example: history-list MyNote")
        print("Example: history-list MyNote 5")
        return
    
    parts = args.strip().split(None, 1)
    note_name = parts[0]
    limit = 10
    
    if len(parts) > 1:
        try:
            limit = int(parts[1])
            if limit < 1:
                print("Error: Limit must be a positive integer.")
                return
        except ValueError:
            print("Error: Limit must be a valid integer.")
            return
    
    # Resolve note path
    note_path = _resolve_note_path(note_name, vaults, current_vault)
    if note_path is None:
        return
    
    # Get history entries
    entries = history_manager.list_history(note_path, limit=limit)
    
    if not entries:
        print(f"No history found for note: {note_name}")
        return
    
    print(f"\nHistory for '{note_name}' (showing {len(entries)} of {len(entries)} entries):\n")
    print("=" * 80)
    
    for i, entry in enumerate(entries, 1):
        timestamp = entry.timestamp_obj.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{i}. {timestamp}")
        print(f"   Backup: {entry.backup_path}")
        if i < len(entries):
            print("-" * 80)
    
    print("=" * 80)
    print(f"\nUse 'history-restore {note_name} <index>' to restore a specific version.")


def cmd_history_restore(
    args: str,
    history_manager: HistoryManager,
    vaults: Dict[str, str],
    current_vault: Optional[str]
) -> None:
    """
    Restore a specific version of a note by index.
    
    Restores the note from the backup at the given index (as shown in history-list).
    
    Usage: history-restore <note> <index>
    
    Args:
        args: Note name and index (space-separated)
        history_manager: History manager instance
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
    """
    if not args.strip():
        print("Usage: history-restore <note> <index>")
        print("Example: history-restore MyNote 1")
        print("Use 'history-list <note>' to see available versions.")
        return
    
    parts = args.strip().split()
    if len(parts) < 2:
        print("Usage: history-restore <note> <index>")
        print("Example: history-restore MyNote 1")
        print("Use 'history-list <note>' to see available versions.")
        return
    
    note_name = parts[0]
    try:
        index = int(parts[1])
        if index < 1:
            print("Error: Index must be a positive integer (1, 2, 3, ...).")
            return
    except ValueError:
        print("Error: Index must be a valid integer (1, 2, 3, ...).")
        return
    
    # Resolve note path
    note_path = _resolve_note_path(note_name, vaults, current_vault)
    if note_path is None:
        return
    
    # Get history entries
    entries = history_manager.list_history(note_path, limit=index)
    
    if not entries:
        print(f"No history found for note: {note_name}")
        return
    
    if index > len(entries):
        print(f"Error: Index {index} is out of range. Only {len(entries)} history entries available.")
        print(f"Use 'history-list {note_name}' to see available versions.")
        return
    
    # Get the entry at the specified index (1-based, so subtract 1)
    entry = entries[index - 1]
    
    # Restore the version
    try:
        # Create a backup of the current version before restoring
        history_manager.backup_note(note_path)
        
        success = history_manager.restore_version(entry)
        if success:
            timestamp = entry.timestamp_obj.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Restored version from {timestamp}")
            print(f"Note '{note_name}' has been restored to this version.")
            print(f"A backup of the previous version was created before restore.")
        else:
            print("Failed to restore version.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Hint: The backup file may have been deleted manually.")
    except RuntimeError as e:
        print(f"Error: {e}")
        print("Hint: Check that you have write permissions for the note file.")
    except Exception as e:
        print(f"Error: Unexpected error during restore: {e}")

def cmd_tag_add(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error_func: Callable[[str, ...], None]
) -> None:
    """
    Add a tag to a note.
    
    Args:
        args: Command arguments in format "<note> <tag>"
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error_func: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error_func("no_vault")
        return
    
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        print("Usage: tag-add <note> <tag>")
        print("Example: tag-add MyNote.md spell")
        return
    
    note_name, tag = parts[0], parts[1]
    
    # Remove # prefix if present
    if tag.startswith("#"):
        tag = tag[1:]
    
    # Resolve note path
    if not note_name.endswith(".md"):
        note_name += ".md"
    
    # Find the note file
    files = list_md_files(vaults, current_vault, error_func)
    matches = [f for f in files if f.lower().endswith(note_name.lower())]
    
    if len(matches) == 0:
        print(f"Error: Note '{note_name}' not found.")
        return
    elif len(matches) > 1:
        print(f"Error: Multiple notes match '{note_name}':")
        for match in matches:
            print(f"  - {match}")
        print("Hint: Use the full path to specify which note.")
        return
    
    note_path = Path(vaults[current_vault]) / matches[0]
    
    try:
        add_tag(note_path, tag)
        print(f"Added tag '{tag}' to '{matches[0]}'")
    except FileNotFoundError:
        print(f"Error: Note '{matches[0]}' not found.")
    except RuntimeError as e:
        print(f"Error: {e}")

def cmd_tag_remove(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error_func: Callable[[str, ...], None]
) -> None:
    """
    Remove a tag from a note.
    
    Args:
        args: Command arguments in format "<note> <tag>"
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error_func: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error_func("no_vault")
        return
    
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        print("Usage: tag-remove <note> <tag>")
        print("Example: tag-remove MyNote.md spell")
        return
    
    note_name, tag = parts[0], parts[1]
    
    # Remove # prefix if present
    if tag.startswith("#"):
        tag = tag[1:]
    
    # Resolve note path
    if not note_name.endswith(".md"):
        note_name += ".md"
    
    # Find the note file
    files = list_md_files(vaults, current_vault, error_func)
    matches = [f for f in files if f.lower().endswith(note_name.lower())]
    
    if len(matches) == 0:
        print(f"Error: Note '{note_name}' not found.")
        return
    elif len(matches) > 1:
        print(f"Error: Multiple notes match '{note_name}':")
        for match in matches:
            print(f"  - {match}")
        print("Hint: Use the full path to specify which note.")
        return
    
    note_path = Path(vaults[current_vault]) / matches[0]
    
    try:
        remove_tag(note_path, tag)
        print(f"Removed tag '{tag}' from '{matches[0]}'")
    except FileNotFoundError:
        print(f"Error: Note '{matches[0]}' not found.")
    except RuntimeError as e:
        print(f"Error: {e}")

def cmd_tag_list(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error_func: Callable[[str, ...], None]
) -> None:
    """
    List all tags in the current vault.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error_func: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error_func("no_vault")
        return
    
    vault_path = Path(vaults[current_vault])
    
    try:
        tag_map = list_all_tags(vault_path)
        
        if not tag_map:
            print("No tags found in the current vault.")
            return
        
        # Sort tags alphabetically
        sorted_tags = sorted(tag_map.keys())
        
        print(f"Tags in '{current_vault}' ({len(sorted_tags)} total):")
        for tag in sorted_tags:
            note_count = len(tag_map[tag])
            print(f"  #{tag} ({note_count} note{'s' if note_count != 1 else ''})")
    except Exception as e:
        print(f"Error: Failed to list tags: {e}")

def cmd_tag_notes(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error_func: Callable[[str, ...], None]
) -> None:
    """
    List all notes with a specific tag.
    
    Args:
        args: Tag name (with or without # prefix)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error_func: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error_func("no_vault")
        return
    
    tag = args.strip()
    if not tag:
        print("Usage: tag-notes <tag>")
        print("Example: tag-notes spell")
        return
    
    # Remove # prefix if present
    if tag.startswith("#"):
        tag = tag[1:]
    
    vault_path = Path(vaults[current_vault])
    
    try:
        tag_map = list_all_tags(vault_path)
        
        if tag not in tag_map:
            print(f"No notes found with tag '#{tag}'")
            return
        
        notes = tag_map[tag]
        print(f"Notes with tag '#{tag}' ({len(notes)} total):")
        
        # Get relative paths for display
        for note_path in sorted(notes):
            try:
                rel_path = note_path.relative_to(vault_path)
                print(f"  - {rel_path}")
            except ValueError:
                print(f"  - {note_path}")
    except Exception as e:
        print(f"Error: Failed to list notes: {e}")

def cmd_showignored(args: str, config: Config, error_func: Callable[[str, ...], None]) -> None:
    """
    Show all currently ignored vaults.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
        error_func: Error handling function
    """
    if not config.ignored_vaults:
        error_func("no_ignored_vaults")
    else:
        print("Ignored vaults:")
        for name in config.ignored_vaults:
            print(f" - {name}")

def cmd_reset(args: str, config: Config, prompt_input_func: Callable[[str], str]) -> None:
    """
    Reset all GM Assistant settings.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
        prompt_input_func: Function to get user input
    """
    confirm = prompt_input_func("Are you sure you want to reset all GM Assistant settings? This will remove all saved vaults and settings (your notes will NOT be deleted). Type YES to confirm: ")
    if confirm.strip().upper() == "YES":
        for fname in ["settings.json", "vaults.json"]:
            if os.path.isfile(fname):
                try:
                    os.remove(fname)
                    print(f"Deleted {fname}.")
                except PermissionError as e:
                    print(f"Error: Permission denied deleting '{fname}': {e}")
                    print("Hint: Check that you have write permissions for the current directory.")
                except OSError as e:
                    print(f"Error: Failed to delete '{fname}': {e}")
                    print("Hint: Check that the file is not in use by another process.")
                except Exception as e:
                    print(f"Error: Unexpected error deleting '{fname}': {e}")
        print("GM Assistant settings reset. Please restart the program to see the onboarding/startup flow again.")
        exit()
    else:
        print("Reset cancelled.")

def _resolve_target_vault(config: Config, parts: List[str]) -> Optional[str]:
    """
    Resolve target vault from command parts.
    
    Looks for --vault flag or --vault=value in parts list.
    
    Args:
        config: Configuration object
        parts: List of command argument parts
        
    Returns:
        Target vault name, or None if not found
    """
    # Optional flag: --vault <VaultName> (e.g., --vault MyCampaignVault)
    # Default: config.default_vault_name
    target_vault = config.default_vault_name
    for i, p in enumerate(parts):
        if p == "--vault" and i + 1 < len(parts):
            target_vault = parts[i+1]
            break
        if p.startswith("--vault="):
            target_vault = p.split("=", 1)[1]
            break
    if target_vault not in config.vaults:
        print(f"Vault '{target_vault}' not found. Available: {', '.join(config.vaults.keys())}")
        return None
    return target_vault

def _fixed_out_dir(config: Config) -> Tuple[Optional[str], Optional[str]]:
    """
    Get fixed output directory for PDF conversions.
    
    Args:
        config: Configuration object
        
    Returns:
        Tuple of (vault_path, out_dir) or (None, None) if vault not found
    """
    if config.default_vault_name not in config.vaults:
        print(f"Vault '{config.default_vault_name}' not found. Available: {', '.join(config.vaults.keys())}")
        return None, None
    vault_path = config.vaults[config.default_vault_name]
    out_dir = os.path.join(vault_path, config.default_import_subfolder)
    os.makedirs(out_dir, exist_ok=True)
    return vault_path, out_dir

def _next_copy_name(out_dir: str, base: str) -> str:
    i = 1
    while True:
        cand = f"{base}{i}.md"
        if not os.path.exists(os.path.join(out_dir, cand)):
            return cand
        i += 1


def cmd_pdf2md(args: str, config: Config, prompt_input_func: Callable[[str], str]) -> None:
    """
    Convert a PDF file to Markdown.
    
    Usage: pdf2md <PDF_PATH> [--map maps/dnd5e.yaml]
    Output is always: {default_vault_name}/Converted/<original-filename>.md
    If exists: prompt to Replace or make numbered Copy.
    
    Args:
        args: Command arguments containing PDF path and optional map flag
        config: Configuration object
        prompt_input_func: Function to get user input
    """
    parts = shlex.split(args)
    if len(parts) < 1:
        print("Usage: pdf2md <PDF_PATH> [--map maps/dnd5e.yaml]")
        return

    pdf_path = parts[0]
    map_path = "maps/dnd5e.yaml"
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    if not os.path.isfile(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    vault_path, out_dir = _fixed_out_dir(config)
    if not out_dir:
        return

    from core.pdf import convert_pdf_to_md

    rules = {}
    if os.path.isfile(map_path):
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"Warning: Map file '{map_path}' not found. Using default rules.")
        except PermissionError as e:
            print(f"Warning: Permission denied reading map file '{map_path}': {e}")
            print("Hint: Check file permissions. Using default rules.")
        except yaml.YAMLError as e:
            print(f"Error: Failed to parse map file '{map_path}': {e}")
            print("Hint: Check that the YAML file is properly formatted. Using default rules.")
        except OSError as e:
            print(f"Warning: Failed to read map file '{map_path}': {e}")
            print("Hint: Check that the file is accessible. Using default rules.")
        except Exception as e:
            print(f"Warning: Unexpected error reading map file: {e}")
            print("Using default rules.")

    # Desired base name from the PDF
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    target = os.path.join(out_dir, base + ".md")

    override_filename = base  # default: use base name

    if os.path.exists(target):
        # Ask user: Replace or Copy
        print(f"'{base}.md' already exists in {config.default_vault_name}/{config.default_import_subfolder}.")
        choice = prompt_input_func("Replace (R) or make numbered Copy (C)? ").strip().lower()
        if choice.startswith('r'):
            # keep override_filename = base (will overwrite)
            pass
        else:
            # choose next available numbered name like base1.md, base2.md...
            numbered = _next_copy_name(out_dir, base)  # returns 'base1.md'
            override_filename = os.path.splitext(numbered)[0]  # strip '.md' for convert()

    try:
        written = convert_pdf_to_md(pdf_path, out_dir, rules, override_filename=override_filename)
        print("Written files:")
        for w in written:
            print(" -", os.path.relpath(w, vault_path))
            print("    ", os.path.abspath(w))
    except Exception as e:
        print(f"Error: Failed to convert PDF: {e}")
        print("Hint: Check that the PDF file is valid and not corrupted, and that the output directory is writable.")

def cmd_pdfbatch(args: str, config: Config) -> None:
    """
    Convert all PDFs in a folder to Markdown.
    
    Usage: pdfbatch <PDF_FOLDER> [--map maps/dnd5e.yaml]
    Output is always: {default_vault_name}/Converted/<original-filename>.md
    If exists: auto-number (base1.md, base2.md, ...)
    
    Args:
        args: Command arguments containing folder path and optional map flag
        config: Configuration object
    """
    parts = shlex.split(args)
    if len(parts) < 1:
        print("Usage: pdfbatch <PDF_FOLDER> [--map maps/dnd5e.yaml]")
        return

    folder = parts[0]
    map_path = "maps/dnd5e.yaml"
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return

    vault_path, out_dir = _fixed_out_dir(config)
    if not out_dir:
        return

    from core.pdf import convert_pdf_to_md

    rules = {}
    if os.path.isfile(map_path):
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f) or {}
        except (FileNotFoundError, PermissionError, yaml.YAMLError, OSError) as e:
            print(f"Warning: Failed to load map file '{map_path}': {e}")
            print("Using default rules.")

    try:
        pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    except PermissionError as e:
        print(f"Error: Permission denied reading folder '{folder}': {e}")
        print("Hint: Check that you have read permissions for the folder.")
        return
    except OSError as e:
        print(f"Error: Failed to read folder '{folder}': {e}")
        print("Hint: Check that the folder exists and is accessible.")
        return
    except Exception as e:
        print(f"Error: Unexpected error reading folder: {e}")
        return

    for fname in pdf_files:
        pdf_path = os.path.join(folder, fname)
        try:
            base = os.path.splitext(os.path.basename(pdf_path))[0]
            target = os.path.join(out_dir, base + ".md")

            override_filename = base
            if os.path.exists(target):
                numbered = _next_copy_name(out_dir, base)
                override_filename = os.path.splitext(numbered)[0]

            convert_pdf_to_md(pdf_path, out_dir, rules, override_filename=override_filename)
            print(f"Converted: {fname}")
        except Exception as e:
            print(f"Error: Failed to convert '{fname}': {e}")
            print(f"Hint: Check that the PDF file is valid and not corrupted. Skipping this file.")
            continue

    print(f"Output: {os.path.abspath(out_dir)}")


def cmd_pdf_convert(args: str, config: Config, prompt_input_func: Callable[[str], str]) -> None:
    """
    Convert a PDF file to Markdown using pdf_tools.
    
    Usage: pdf-convert <PDF_PATH> [--map maps/dnd5e.yaml]
    Output is always: {default_vault_name}/Converted/<original-filename>.md
    If exists: prompt to Replace or make numbered Copy.
    
    Args:
        args: Command arguments containing PDF path and optional map flag
        config: Configuration object
        prompt_input_func: Function to get user input
    """
    from pathlib import Path
    from pdf_tools.pdf_to_md import convert_pdf_to_md
    
    parts = shlex.split(args)
    if len(parts) < 1:
        print("Usage: pdf-convert <PDF_PATH> [--map maps/dnd5e.yaml]")
        return

    pdf_path = parts[0]
    map_path = "maps/dnd5e.yaml"
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    if not os.path.isfile(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    vault_path, out_dir = _fixed_out_dir(config)
    if not out_dir:
        return

    # Load map rules if provided
    options = {}
    if os.path.isfile(map_path):
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                options["map_rules"] = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"Warning: Map file '{map_path}' not found. Using default rules.")
        except PermissionError as e:
            print(f"Warning: Permission denied reading map file '{map_path}': {e}")
            print("Hint: Check file permissions. Using default rules.")
        except yaml.YAMLError as e:
            print(f"Error: Failed to parse map file '{map_path}': {e}")
            print("Hint: Check that the YAML file is properly formatted. Using default rules.")
        except OSError as e:
            print(f"Warning: Failed to read map file '{map_path}': {e}")
            print("Hint: Check that the file is accessible. Using default rules.")
        except Exception as e:
            print(f"Warning: Unexpected error reading map file: {e}")
            print("Using default rules.")

    # Desired base name from the PDF
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    target = os.path.join(out_dir, base + ".md")

    if os.path.exists(target):
        # Ask user: Replace or Copy
        print(f"'{base}.md' already exists in {config.default_vault_name}/{config.default_import_subfolder}.")
        choice = prompt_input_func("Replace (R) or make numbered Copy (C)? ").strip().lower()
        if choice.startswith('r'):
            # Will overwrite
            pass
        else:
            # Choose next available numbered name
            numbered = _next_copy_name(out_dir, base)
            options["override_filename"] = os.path.splitext(numbered)[0]

    try:
        written = convert_pdf_to_md(Path(pdf_path), Path(out_dir), options)
        print("Written files:")
        for w in written:
            print(" -", os.path.relpath(str(w), vault_path))
            print("    ", os.path.abspath(str(w)))
    except FileNotFoundError as e:
        print(f"Error: PDF file not found: {e}")
        print("Hint: Check that the PDF file path is correct.")
    except ValueError as e:
        print(f"Error: Invalid PDF file: {e}")
        print("Hint: Check that the PDF file is valid and not corrupted.")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print(f"Hint: Check that the output directory '{out_dir}' is writable.")
    except OSError as e:
        print(f"Error: Failed to convert PDF: {e}")
        print("Hint: Check that the PDF file is valid and the output directory is accessible.")
    except Exception as e:
        print(f"Error: Unexpected error converting PDF: {e}")
        print("Hint: Check that the PDF file is valid and not corrupted, and that the output directory is writable.")


def cmd_pdf_batch(args: str, config: Config) -> None:
    """
    Convert all PDFs in a folder to Markdown using pdf_tools.
    
    Usage: pdf-batch <PDF_FOLDER> [--map maps/dnd5e.yaml]
    Output is always: exports/pdf_md/<original-filename>.md
    If exists: auto-number (base1.md, base2.md, ...)
    
    Args:
        args: Command arguments containing folder path and optional map flag
        config: Configuration object
    """
    from pathlib import Path
    from pdf_tools.pdf_to_md import convert_pdf_to_md
    
    parts = shlex.split(args)
    if len(parts) < 1:
        print("Usage: pdf-batch <PDF_FOLDER> [--map maps/dnd5e.yaml]")
        return

    folder = parts[0]
    map_path = "maps/dnd5e.yaml"
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return

    # Set output directory to exports/pdf_md/
    out_dir = Path("exports/pdf_md")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"Error: Permission denied creating output directory '{out_dir}': {e}")
        print("Hint: Check that you have write permissions in the current directory.")
        return
    except OSError as e:
        print(f"Error: Failed to create output directory '{out_dir}': {e}")
        print("Hint: Check that the current directory is writable and disk space is available.")
        return
    except Exception as e:
        print(f"Error: Unexpected error creating output directory: {e}")
        return

    # Load map rules if provided
    options = {}
    if os.path.isfile(map_path):
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                options["map_rules"] = yaml.safe_load(f) or {}
        except (FileNotFoundError, PermissionError, yaml.YAMLError, OSError) as e:
            print(f"Warning: Failed to load map file '{map_path}': {e}")
            print("Using default rules.")
        except Exception as e:
            print(f"Warning: Unexpected error reading map file: {e}")
            print("Using default rules.")

    try:
        pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    except PermissionError as e:
        print(f"Error: Permission denied reading folder '{folder}': {e}")
        print("Hint: Check that you have read permissions for the folder.")
        return
    except OSError as e:
        print(f"Error: Failed to read folder '{folder}': {e}")
        print("Hint: Check that the folder exists and is accessible.")
        return
    except Exception as e:
        print(f"Error: Unexpected error reading folder: {e}")
        return

    for fname in pdf_files:
        pdf_path = os.path.join(folder, fname)
        try:
            base = os.path.splitext(os.path.basename(pdf_path))[0]
            target = out_dir / f"{base}.md"

            file_options = options.copy()
            if target.exists():
                numbered = _next_copy_name(str(out_dir), base)
                file_options["override_filename"] = os.path.splitext(numbered)[0]

            convert_pdf_to_md(Path(pdf_path), out_dir, file_options)
            print(f"Converted: {fname}")
        except FileNotFoundError as e:
            print(f"Error: PDF file not found '{fname}': {e}")
            print("Hint: Check that the PDF file path is correct. Skipping this file.")
            continue
        except ValueError as e:
            print(f"Error: Invalid PDF file '{fname}': {e}")
            print("Hint: Check that the PDF file is valid and not corrupted. Skipping this file.")
            continue
        except PermissionError as e:
            print(f"Error: Permission denied for '{fname}': {e}")
            print(f"Hint: Check that the output directory '{out_dir}' is writable. Skipping this file.")
            continue
        except OSError as e:
            print(f"Error: Failed to convert '{fname}': {e}")
            print("Hint: Check that the PDF file is valid and the output directory is accessible. Skipping this file.")
            continue
        except Exception as e:
            print(f"Error: Unexpected error converting '{fname}': {e}")
            print("Hint: Check that the PDF file is valid and not corrupted. Skipping this file.")
            continue

    print(f"Output: {out_dir.resolve()}")


def cmd_pdf_send_to_vault(args: str, config: Config) -> None:
    """
    Convert PDF(s) to Markdown and send to current Obsidian vault.
    
    Usage: pdf-send-to-vault --input <PDF_PATH or FOLDER>
    Converts PDF(s) to markdown, cleans the output, and writes to the current vault.
    
    Args:
        args: Command arguments containing --input flag and path
        config: Configuration object
    """
    from pathlib import Path
    from pdf_tools.pdf_to_md import convert_pdf_to_md, send_md_to_obsidian
    from pdf_tools.cleaning import clean_markdown
    
    parts = shlex.split(args)
    
    # Parse arguments
    input_path = None
    i = 0
    while i < len(parts):
        if parts[i] == "--input" and i + 1 < len(parts):
            input_path = parts[i + 1]
            i += 2
        elif parts[i].startswith("--input="):
            input_path = parts[i].split("=", 1)[1]
            i += 1
        else:
            i += 1
    
    if not input_path:
        print("Usage: pdf-send-to-vault --input <PDF_PATH or FOLDER>")
        print("Example: pdf-send-to-vault --input document.pdf")
        print("Example: pdf-send-to-vault --input ./pdfs/")
        return
    
    input_path = Path(input_path)
    
    # Validate input exists
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        return
    
    # Check current vault
    if not config.current_vault or config.current_vault not in config.vaults:
        print("Error: No current vault set. Use 'switch' to select a vault.")
        return
    
    vault_path = Path(config.vaults[config.current_vault])
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}")
        return
    
    # Determine target folder in vault (default: Converted)
    target_folder = vault_path / config.default_import_subfolder
    
    # Collect PDF files to process
    pdf_files = []
    if input_path.is_file():
        if input_path.suffix.lower() == ".pdf":
            pdf_files = [input_path]
        else:
            print(f"Error: Input file is not a PDF: {input_path}")
            return
    elif input_path.is_dir():
        try:
            pdf_files = [Path(f) for f in input_path.iterdir() 
                        if f.is_file() and f.suffix.lower() == ".pdf"]
        except PermissionError as e:
            print(f"Error: Permission denied reading folder '{input_path}': {e}")
            return
        except OSError as e:
            print(f"Error: Failed to read folder '{input_path}': {e}")
            return
    else:
        print(f"Error: Input path is neither a file nor a directory: {input_path}")
        return
    
    if not pdf_files:
        print(f"No PDF files found in: {input_path}")
        return
    
    print(f"Found {len(pdf_files)} PDF file(s) to convert.")
    print(f"Target vault: {config.current_vault}")
    try:
        rel_path = target_folder.relative_to(vault_path)
        print(f"Target folder: {rel_path}")
    except ValueError:
        print(f"Target folder: {target_folder}")
    print()
    
    # Process each PDF
    converted_count = 0
    failed_count = 0
    
    for pdf_file in pdf_files:
        try:
            print(f"Converting: {pdf_file.name}...")
            
            # Convert PDF to markdown (using temporary directory)
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Convert PDF
                try:
                    converted_files = convert_pdf_to_md(
                        pdf_file,
                        temp_path,
                        options={"override_filename": pdf_file.stem}
                    )
                except Exception as e:
                    print(f"  Error converting PDF: {e}")
                    failed_count += 1
                    continue
                
                if not converted_files:
                    print(f"  Error: No output files generated")
                    failed_count += 1
                    continue
                
                # Read the converted markdown
                md_content = converted_files[0].read_text(encoding="utf-8")
                
                # Clean the markdown
                try:
                    md_content = clean_markdown(md_content)
                except Exception as e:
                    print(f"  Warning: Error cleaning markdown: {e}")
                    # Continue with uncleaned content
                
                # Send to vault
                try:
                    output_path = send_md_to_obsidian(
                        md=md_content,
                        target_folder=target_folder,
                        filename=pdf_file.stem
                    )
                    try:
                        rel_output = output_path.relative_to(vault_path)
                        print(f"  ✓ Saved to: {rel_output}")
                    except ValueError:
                        print(f"  ✓ Saved to: {output_path}")
                    converted_count += 1
                except Exception as e:
                    print(f"  Error saving to vault: {e}")
                    failed_count += 1
                    continue
        
        except Exception as e:
            print(f"  Unexpected error processing '{pdf_file.name}': {e}")
            failed_count += 1
            continue
    
    # Summary
    print()
    print("=" * 60)
    print(f"Conversion complete: {converted_count} succeeded, {failed_count} failed")
    print("=" * 60)


def cmd_schedule_start(args: str, scheduler: Scheduler, context: SchedulerContext) -> None:
    """
    Start the scheduler and register default jobs.
    
    Args:
        args: Command arguments (unused)
        scheduler: Scheduler instance
        context: Scheduler context object
    """
    try:
        # Register default jobs before starting
        register_default_jobs(scheduler, context)
        scheduler.start()
        print("Scheduler started successfully.")
        print(f"Registered {scheduler.get_job_count()} job(s).")
    except RuntimeError as e:
        print(f"Error: {e}")


def cmd_schedule_stop(args: str, scheduler: Scheduler) -> None:
    """
    Stop the scheduler.
    
    Args:
        args: Command arguments (unused)
        scheduler: Scheduler instance
    """
    scheduler.stop()
    print("Scheduler stopped.")


def cmd_schedule_run_once(args: str, scheduler: Scheduler) -> None:
    """
    Run all pending jobs once (synchronous).
    
    Args:
        args: Command arguments (unused)
        scheduler: Scheduler instance
    """
    count = scheduler.run_pending_once()
    print(f"Executed {count} job(s).")


def cmd_schedule_status(args: str, scheduler: Scheduler) -> None:
    """
    Show scheduler status and registered jobs.
    
    Args:
        args: Command arguments (unused)
        scheduler: Scheduler instance
    """
    is_running = scheduler.is_running()
    job_count = scheduler.get_job_count()
    jobs = scheduler.list_jobs()
    
    print(f"Scheduler status: {'Running' if is_running else 'Stopped'}")
    print(f"Registered jobs: {job_count}")
    if jobs:
        print("\nRegistered jobs:")
        for job_name in jobs:
            print(f"  - {job_name}")
    else:
        print("\nNo jobs registered.")


def cmd_schedule_backup_run_now(args: str, config: Config) -> None:
    """
    Run the vault backup job immediately.
    
    Executes the backup_vault function synchronously without waiting for
    the scheduled interval.
    
    Args:
        args: Command arguments (unused)
        config: Config object containing vault information
    """
    from automation.jobs import backup_vault
    
    try:
        print("Running vault backup...")
        backup_vault(config)
    except ValueError as e:
        print(f"Error: Cannot backup vault: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied during backup: {e}")
        print("Hint: Check that you have read permissions for the vault and write permissions for the backup directory.")
    except OSError as e:
        print(f"Error: Failed to create backup: {e}")
        print("Hint: Check that the vault directory exists and the backup directory is writable.")
    except Exception as e:
        print(f"Error: Unexpected error during backup: {e}")


def cmd_template_sync_now(args: str, config: Config) -> None:
    """
    Run the template sync job immediately.
    
    Executes the sync_templates_job function synchronously without waiting for
    the scheduled interval.
    
    Args:
        args: Command arguments (unused)
        config: Config object containing template sync configuration
    """
    from automation.jobs import sync_templates_job
    
    try:
        print("Running template sync...")
        sync_templates_job(config)
        print("Template sync completed.")
    except ValueError as e:
        print(f"Error: Cannot sync templates: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied during template sync: {e}")
        print("Hint: Check that you have read permissions for the remote source and write permissions for the template directory.")
    except OSError as e:
        print(f"Error: Failed to sync templates: {e}")
        print("Hint: Check that the template directory path exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error during template sync: {e}")


def cmd_srd_index_run_now(args: str, config: Config) -> None:
    """
    Run the SRD index rebuild job immediately.
    
    Executes the rebuild_srd_index_job function synchronously without waiting for
    the scheduled interval.
    
    Args:
        args: Command arguments (unused)
        config: Config object containing vault information
    """
    from automation.jobs import rebuild_srd_index_job
    
    try:
        print("Running SRD index rebuild...")
        rebuild_srd_index_job(config)
        print("SRD index rebuild completed.")
    except ValueError as e:
        print(f"Error: Cannot rebuild SRD index: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied during SRD index rebuild: {e}")
        print("Hint: Check that you have read permissions for the SRDs directory and write permissions for the index directory.")
    except OSError as e:
        print(f"Error: Failed to rebuild SRD index: {e}")
        print("Hint: Check that the vault directory exists and the index directory is writable.")
    except Exception as e:
        print(f"Error: Unexpected error during SRD index rebuild: {e}")


def cmd_cache_clean_now(args: str, config: Config) -> None:
    """
    Run the cache clean job immediately.
    
    Executes the clean_cache_job function synchronously without waiting for
    the scheduled interval.
    
    Args:
        args: Command arguments (unused)
        config: Config object containing vault information
    """
    from automation.jobs import clean_cache_job
    
    try:
        print("Running cache cleanup...")
        clean_cache_job(config)
        print("Cache cleanup completed.")
    except ValueError as e:
        print(f"Error: Cannot clean cache: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied during cache cleanup: {e}")
    except OSError as e:
        print(f"Error: Failed to clean cache: {e}")
    except Exception as e:
        print(f"Error: Unexpected error during cache cleanup: {e}")


def cmd_campaign_create(args: str, config: Config) -> None:
    """
    Create a new campaign.
    
    Usage: campaign-create <name>
    
    Args:
        args: Campaign name
        config: Config object containing vault information
    """
    from core.campaigns import create_campaign
    
    if not args.strip():
        print("Usage: campaign-create <name>")
        print("Example: campaign-create \"The Lost Mines\"")
        return
    
    try:
        campaign = create_campaign(args.strip(), config)
        print(f"Campaign '{campaign.name}' created successfully!")
    except ValueError as e:
        print(f"Error: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have write permissions for the vault directory.")
    except OSError as e:
        print(f"Error: Failed to create campaign: {e}")
        print("Hint: Check that the vault directory exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error: {e}")


def cmd_campaign_add_pc(args: str, config: Config) -> None:
    """
    Add a party member (PC) to a campaign.
    
    Usage: campaign-add-pc <campaign> <name>
    
    Args:
        args: Campaign name and character name (space-separated)
        config: Config object containing vault information
    """
    from core.campaigns import find_campaign, create_party_member
    
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        print("Usage: campaign-add-pc <campaign> <name>")
        print("Example: campaign-add-pc \"The Lost Mines\" \"Aragorn\"")
        return
    
    campaign_name = parts[0]
    character_name = parts[1]
    
    try:
        campaign = find_campaign(campaign_name, config)
        if not campaign:
            print(f"Error: Campaign '{campaign_name}' not found")
            return
        
        create_party_member(campaign, character_name, config)
        print(f"Party member '{character_name}' added to campaign '{campaign_name}'")
    except ValueError as e:
        print(f"Error: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have write permissions for the campaign directory.")
    except OSError as e:
        print(f"Error: Failed to add party member: {e}")
        print("Hint: Check that the campaign directory exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error: {e}")


def cmd_campaign_add_npc(args: str, config: Config) -> None:
    """
    Add an NPC to a campaign.
    
    Usage: campaign-add-npc <campaign> <attitude> <name>
    
    Attitudes: ally, friendly, neutral, adversarial, antagonist
    
    Args:
        args: Campaign name, attitude, and character name (space-separated)
        config: Config object containing vault information
    """
    from core.campaigns import find_campaign, create_npc
    
    parts = args.strip().split(None, 2)
    if len(parts) < 3:
        print("Usage: campaign-add-npc <campaign> <attitude> <name>")
        print("Example: campaign-add-npc \"The Lost Mines\" friendly \"Innkeeper Bob\"")
        print("Valid attitudes: ally, friendly, neutral, adversarial, antagonist")
        return
    
    campaign_name = parts[0]
    attitude = parts[1]
    character_name = parts[2]
    
    try:
        campaign = find_campaign(campaign_name, config)
        if not campaign:
            print(f"Error: Campaign '{campaign_name}' not found")
            return
        
        create_npc(campaign, character_name, attitude, config)
        print(f"NPC '{character_name}' added to campaign '{campaign_name}' as {attitude}")
    except ValueError as e:
        print(f"Error: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have write permissions for the campaign directory.")
    except OSError as e:
        print(f"Error: Failed to add NPC: {e}")
        print("Hint: Check that the campaign directory exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error: {e}")


def cmd_campaign_add_location(args: str, config: Config) -> None:
    """
    Add a location to a campaign.
    
    Usage: campaign-add-location <campaign> <name>
    
    Args:
        args: Campaign name and location name (space-separated)
        config: Config object containing vault information
    """
    from core.campaigns import find_campaign, create_location
    
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        print("Usage: campaign-add-location <campaign> <name>")
        print("Example: campaign-add-location \"The Lost Mines\" \"Phandalin\"")
        return
    
    campaign_name = parts[0]
    location_name = parts[1]
    
    try:
        campaign = find_campaign(campaign_name, config)
        if not campaign:
            print(f"Error: Campaign '{campaign_name}' not found")
            return
        
        create_location(campaign, location_name, config)
        print(f"Location '{location_name}' added to campaign '{campaign_name}'")
    except ValueError as e:
        print(f"Error: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have write permissions for the campaign directory.")
    except OSError as e:
        print(f"Error: Failed to add location: {e}")
        print("Hint: Check that the campaign directory exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error: {e}")


def cmd_session_create(args: str, config: Config) -> None:
    """
    Create a new session note for a campaign.
    
    Usage: session-create <campaign> "<session title>"
    
    Creates a new session note in the campaign's Sessions/ directory with
    automatic numbering, proper frontmatter, and linking to campaign and
    previous session.
    
    Args:
        args: Campaign name and session title (space-separated, title in quotes recommended)
        config: Config object containing vault information
    """
    from core.campaigns import find_campaign, create_session
    
    if not args.strip():
        print("Usage: session-create <campaign> \"<session title>\"")
        print("Example: session-create \"The Lost Mines\" \"The Goblin Ambush\"")
        return
    
    # Split on first space only to get campaign name and title
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        print("Usage: session-create <campaign> \"<session title>\"")
        print("Example: session-create \"The Lost Mines\" \"The Goblin Ambush\"")
        print("Note: Use quotes around the session title if it contains spaces.")
        return
    
    campaign_name = parts[0]
    session_title = parts[1]
    
    # Remove quotes if present (handles both "title" and 'title')
    if (session_title.startswith('"') and session_title.endswith('"')) or \
       (session_title.startswith("'") and session_title.endswith("'")):
        session_title = session_title[1:-1]
    
    try:
        campaign = find_campaign(campaign_name, config)
        if not campaign:
            print(f"Error: Campaign '{campaign_name}' not found")
            return
        
        session_file = create_session(campaign, session_title, config)
        print(f"Session note created: {session_file.name}")
    except ValueError as e:
        print(f"Error: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have write permissions for the campaign's Sessions directory.")
    except OSError as e:
        print(f"Error: Failed to create session: {e}")
        print("Hint: Check that the campaign directory exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error: {e}")


def cmd_template_preview(args: str, config: Config) -> None:
    """
    Preview a template with variable replacement without writing to disk.
    
    Usage: template-preview <template> [var=value var2=value2 ...]
    
    Examples:
    - template-preview MyTemplate
    - template-preview MyTemplate title="My Note" campaign="Lost Mines"
    - template-preview MyTemplate title="NPC Name" npc_attitude="friendly"
    
    Args:
        args: Template name and optional variable assignments (space-separated)
        config: Config object containing vault information
    """
    from core.templates import apply_template_preview
    import shlex
    
    if not args.strip():
        print("Usage: template-preview <template> [var=value var2=value2 ...]")
        print("Example: template-preview MyTemplate title=\"My Note\" campaign=\"Lost Mines\"")
        return
    
    # Parse arguments
    parts = shlex.split(args.strip())
    if not parts:
        print("Usage: template-preview <template> [var=value var2=value2 ...]")
        return
    
    template_name = parts[0]
    variables: Dict[str, str] = {}
    
    # Parse variable assignments: var=value
    for part in parts[1:]:
        if "=" in part:
            var_parts = part.split("=", 1)
            if len(var_parts) == 2:
                var_name = var_parts[0].strip()
                var_value = var_parts[1].strip()
                # Remove quotes if present
                if (var_value.startswith('"') and var_value.endswith('"')) or \
                   (var_value.startswith("'") and var_value.endswith("'")):
                    var_value = var_value[1:-1]
                variables[var_name] = var_value
            else:
                print(f"Warning: Invalid variable assignment '{part}'. Expected format: var=value")
        else:
            print(f"Warning: Ignoring argument '{part}'. Expected format: var=value")
    
    try:
        rendered = apply_template_preview(template_name, config, variables)
        print(f"\n--- Preview: {template_name} ---\n{rendered}\n{'-' * 50}")
        if variables:
            print(f"\nVariables used: {', '.join(f'{k}={v}' for k, v in variables.items())}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Hint: Check that the template name is correct and the template exists.")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have read permissions for the template directory.")
    except OSError as e:
        print(f"Error: Failed to read template: {e}")
        print("Hint: Check that the template file exists and is accessible.")
    except Exception as e:
        print(f"Error: Unexpected error: {e}")


def cmd_session_reminder_run_now(args: str, config: Config) -> None:
    """
    Run the session reminder job immediately.
    
    Executes the session_reminder_job function synchronously without waiting for
    the scheduled interval.
    
    Args:
        args: Command arguments (unused)
        config: Config object containing session reminder configuration
    """
    from automation.jobs import session_reminder_job
    
    try:
        print("Checking for upcoming sessions...")
        session_reminder_job(config)
    except ValueError as e:
        print(f"Error: Cannot check session reminders: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied reading session files: {e}")
        print("Hint: Check that you have read permissions for the exports directory.")
    except OSError as e:
        print(f"Error: Failed to check session reminders: {e}")
        print("Hint: Check that the exports directory exists and is accessible.")
    except Exception as e:
        print(f"Error: Unexpected error during session reminder check: {e}")


def cmd_debug(args: str, config: Config, gpt_client) -> None:
    """
    Print diagnostic information about the system.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
        gpt_client: GPT client instance (may be None)
    """
    import sys
    
    print("=" * 60)
    print("DEBUG INFORMATION")
    print("=" * 60)
    
    # Python version
    print(f"\nPython Version: {sys.version}")
    print(f"Python Executable: {sys.executable}")
    
    # Config settings (safe fields only)
    print("\n--- Config Settings (Safe Fields) ---")
    print(f"Default Vault Name: {config.default_vault_name}")
    print(f"Default Vault Path: {config.default_vault_path}")
    print(f"Default Import Subfolder: {config.default_import_subfolder}")
    print(f"Default Model: {config.default_model}")
    print(f"Environment File: {config.env_file}")
    print(f"OpenAI Key: {'***SET***' if config.openai_key else '***NOT SET***'}")
    print(f"Current Vault: {config.current_vault if config.current_vault else 'None'}")
    print(f"Ignored Vaults: {config.ignored_vaults if config.ignored_vaults else 'None'}")
    print(f"Total Vaults: {len(config.vaults)}")
    
    # Current vault path
    print("\n--- Current Vault ---")
    if config.current_vault and config.current_vault in config.vaults:
        vault_path = config.vaults[config.current_vault]
        print(f"Vault Name: {config.current_vault}")
        print(f"Vault Path: {vault_path}")
        print(f"Path Exists: {os.path.exists(vault_path)}")
        print(f"Path Is Directory: {os.path.isdir(vault_path) if os.path.exists(vault_path) else 'N/A'}")
    else:
        print("No current vault set.")
    
    # Templates folder
    print("\n--- Templates Folder ---")
    if config.default_vault_name in config.vaults:
        templates_dir = os.path.join(config.vaults[config.default_vault_name], "templates")
        exists = os.path.exists(templates_dir)
        is_dir = os.path.isdir(templates_dir) if exists else False
        print(f"Templates Path: {templates_dir}")
        print(f"Exists: {exists}")
        print(f"Is Directory: {is_dir}")
        if exists and is_dir:
            try:
                template_count = len([f for f in os.listdir(templates_dir) if f.endswith(".md")])
                print(f"Template Files: {template_count}")
            except Exception as e:
                print(f"Error reading templates: {e}")
    else:
        print(f"Default vault '{config.default_vault_name}' not found in vaults.")
    
    # OpenAI connection test
    print("\n--- OpenAI Connection Test ---")
    if gpt_client is None:
        print("GPT Client: Not initialized")
        print("Connection Test: SKIPPED (client not available)")
    else:
        print("GPT Client: Initialized")
        print(f"Default Model: {gpt_client.default_model}")
        try:
            # Simple test prompt
            test_response = gpt_client.chat("Say 'OK' if you can read this.")
            if test_response:
                print("Connection Test: SUCCEEDED")
                print(f"Test Response: {test_response[:50]}..." if len(test_response) > 50 else f"Test Response: {test_response}")
            else:
                print("Connection Test: FAILED (empty response)")
        except Exception as e:
            print(f"Connection Test: FAILED")
            print(f"Error: {e}")
    
    print("\n" + "=" * 60)


def initialize_application() -> Tuple[Config, Any, Scheduler, SchedulerContext, HistoryManager]:
    """
    Initialize the application and return all required components.
    
    Returns:
        Tuple of (config, gpt_client, scheduler, scheduler_context, history_manager)
    """
    # Initialize configuration
    config = Config()
    config.vaults = load_vaults()
    config.load_settings()
    
    # Initialize GPT client after config loads
    gpt_client = create_gpt_client(api_key=config.openai_key, default_model=config.default_model)
    
    # Initialize scheduler
    scheduler = Scheduler()
    
    # Initialize scheduler context
    scheduler_context = SchedulerContext()
    obsidian_json_path = get_obsidian_json_path()
    save_vaults_wrapper = create_save_vaults_wrapper(config)
    
    # Populate scheduler context
    scheduler_context.obsidian_json_path = obsidian_json_path
    scheduler_context.vaults = config.vaults
    scheduler_context.ignored_vaults = config.ignored_vaults
    scheduler_context.save_vaults = save_vaults_wrapper
    scheduler_context.current_vault = config.current_vault
    
    # Sync with Obsidian if available
    if os.path.isfile(obsidian_json_path):
        sync_obsidian_vaults(obsidian_json_path, config.vaults, config.ignored_vaults, save_vaults_wrapper)
        periodic_obsidian_sync(obsidian_json_path, config.vaults, config.ignored_vaults, save_vaults_wrapper)
    else:
        error("obsidian_not_found")
    
    # Ensure default vault exists
    config.current_vault = ensure_default_vault(config, save_vaults_wrapper, config.save_settings)
    
    # Initialize history manager
    history_manager = HistoryManager()
    
    return config, gpt_client, scheduler, scheduler_context, history_manager


def register_all_commands(
    config: Config,
    gpt_client: Any,
    scheduler: Scheduler,
    scheduler_context: SchedulerContext,
    history_manager: HistoryManager
) -> None:
    """
    Register all CLI commands with the command registry.
    
    Args:
        config: Configuration object
        gpt_client: GPT client instance
        scheduler: Scheduler instance
        scheduler_context: Scheduler context object
        history_manager: History manager instance for undo functionality
    """
    save_vaults_wrapper = create_save_vaults_wrapper(config)
    
    register_command(config, "exit", cmd_exit, "Exit the assistant.")
    register_command(
        config,
        "help",
        lambda args: cmd_help(args, config),
        "Show this help message."
    )
    register_command(
        config,
        "showignored",
        lambda args: cmd_showignored(args, config, error),
        "Show all currently ignored vaults"
    )
    register_command(
        config,
        "reset",
        lambda args: cmd_reset(args, config, prompt_input),
        "Reset all GM Assistant settings to first-launch state (will not delete notes, just assistant config)."
    )
    register_command(
        config,
        "tree",
        lambda args: cmd_tree(args, config.vaults, config.current_vault, error),
        "Show the current vault's folder and note structure (tree view)."
    )
    register_command(
        config,
        "createnote",
        lambda args: cmd_createnote(args, config.vaults, config.current_vault, prompt_input, config.default_vault_name, history_manager, config),
        "Create a new note, optionally from a template. Usage: createnote [--template X] [--dry-run] [var=value ...]"
    )
    register_command(
        config,
        "gptwrite",
        lambda args: cmd_gptwrite(args, config.vaults, config.current_vault, prompt_input, gpt_client, history_manager),
        "Ask ChatGPT a question and optionally save to a note: gptwrite NoteName.md: prompt text"
    )
    register_command(
        config,
        "editnote",
        lambda args: cmd_editnote(args, config.vaults, config.current_vault, prompt_input, list_md_files, read_md_file, gpt_client, history_manager),
        "Edit a note with ChatGPT and choose how to save: editnote"
    )
    register_command(
        config,
        "showtemplates",
        lambda args: cmd_showtemplates(args, config.vaults, prompt_input, config.default_vault_name),
        "List and preview note templates."
    )
    register_command(
        config,
        "template-preview",
        lambda args: cmd_template_preview(args, config),
        "Preview a template with variable replacement. Usage: template-preview <template> [var=value ...]"
    )
    register_command(
        config,
        "createtemplate",
        lambda args: cmd_createtemplate(args, config.vaults, prompt_input, config.default_vault_name, history_manager),
        "Create a new markdown template by typing or pasting content."
    )
    register_command(
        config,
        "uploadtemplate",
        lambda args: cmd_uploadtemplate(args, config.vaults, prompt_input, config.default_vault_name, history_manager),
        "Upload an existing .md file into the default vault's templates."
    )
    register_command(
        config,
        "uploadalltemplates",
        lambda args: cmd_uploadalltemplates(args, config.vaults, prompt_input, config.default_vault_name, history_manager),
        "Upload all .md files from a folder into the default vault's templates."
    )
    register_command(
        config,
        "deletetemplate",
        lambda args: cmd_deletetemplate(args, config.vaults, prompt_input, config.default_vault_name),
        "Delete a template."
    )
    register_command(
        config,
        "addvault",
        lambda args: setattr(config, 'current_vault', cmd_addvault(args, config.vaults, config.current_vault, save_vaults_wrapper, config.save_settings, prompt_input, list_vaults, config.ignored_vaults)),
        "Add a new Obsidian vault."
    )
    register_command(
        config,
        "switch",
        lambda args: setattr(config, 'current_vault', cmd_switch(args, config.vaults, config.current_vault, config.vault_number_map, config.save_settings, prompt_input, list_vaults, config.ignored_vaults, display_numbered_vaults)),
        "Switch to a different vault."
    )
    register_command(
        config,
        "vaults",
        lambda args: cmd_vaults(config.vaults, config.current_vault, config.ignored_vaults),
        "List available vaults."
    )
    register_command(
        config,
        "ignorevault",
        lambda args: cmd_ignorevault(args, config.ignored_vaults, config.save_settings),
        "Ignore a vault from auto-importing."
    )
    register_command(
        config,
        "unignorevault",
        lambda args: cmd_unignorevault(args, config.ignored_vaults, config.save_settings),
        "Stop ignoring a vault."
    )
    register_command(
        config,
        "read",
        lambda args: cmd_read(args, config.vaults, config.current_vault, error),
        "Read a markdown file: read FILENAME"
    )
    register_command(
        config,
        "list",
        lambda args: cmd_list(args, config.vaults, config.current_vault, error),
        "List markdown files in the current vault."
    )
    register_command(
        config,
        "send",
        lambda args: cmd_send(args, config.vaults, config.current_vault, error, gpt_client),
        "Send a note to ChatGPT: 'send NOTE' or 'upload FOLDER/NOTE'"
    )
    register_command(
        config,
        "upload",
        lambda args: print("Use 'send' instead. This command is deprecated."),
        "Deprecated. Use 'send' instead."
    )
    register_command(
        config,
        "search",
        lambda args: cmd_search(args, config.vaults, config.current_vault, error),
        "Search notes using title, type, system, or tags (e.g., 'spell system:dnd-5e')"
    )
    register_command(
        config,
        "index",
        lambda args: build_search_index(config.vaults[config.current_vault]) if config.current_vault else None,
        "Build or rebuild the search index for the current vault."
    )
    register_command(
        config,
        "srd-index",
        lambda args: cmd_srd_index(args, config.vaults, config.current_vault, error),
        "Build or rebuild the SRD index for the current vault's /SRDs/ directory."
    )
    register_command(
        config,
        "search-srd",
        lambda args: cmd_search_srd(args, config.vaults, config.current_vault, error),
        "Search SRD markdown files. Usage: search-srd <query> [tag:<value>] [system:<value>] [name:<value>]"
    )
    register_command(
        config,
        "pdf2md",
        lambda args: cmd_pdf2md(args, config, prompt_input),
        "Convert a single PDF to Markdown. Output → default vault/Converted. Usage: pdf2md \"PDF_PATH\" --map maps/mapname.yaml"
    )
    register_command(
        config,
        "pdfbatch",
        lambda args: cmd_pdfbatch(args, config),
        "Convert all PDFs in a folder. Output → default vault/Converted. Usage: pdfbatch \"PDF_FOLDER\" --map maps/mapname.yaml"
    )
    register_command(
        config,
        "pdf-convert",
        lambda args: cmd_pdf_convert(args, config, prompt_input),
        "Convert a single PDF to Markdown using pdf_tools. Output → default vault/Converted. Usage: pdf-convert \"PDF_PATH\" [--map maps/mapname.yaml]"
    )
    register_command(
        config,
        "pdf-batch",
        lambda args: cmd_pdf_batch(args, config),
        "Convert all PDFs in a folder using pdf_tools. Output → exports/pdf_md/. Usage: pdf-batch \"PDF_FOLDER\" [--map maps/mapname.yaml]"
    )
    register_command(
        config,
        "pdf-send-to-vault",
        lambda args: cmd_pdf_send_to_vault(args, config),
        "Convert PDF(s) to Markdown and send to current Obsidian vault. Usage: pdf-send-to-vault --input <PDF_PATH or FOLDER>"
    )
    register_command(
        config,
        "session-schedule",
        lambda args: schedule_next_session(prompt_input),
        "Schedule the next TTRPG session and generate calendar invite (.ics) file."
    )
    register_command(
        config,
        "schedule-start",
        lambda args: cmd_schedule_start(args, scheduler, scheduler_context),
        "Start the background job scheduler."
    )
    register_command(
        config,
        "schedule-stop",
        lambda args: cmd_schedule_stop(args, scheduler),
        "Stop the background job scheduler."
    )
    register_command(
        config,
        "schedule-run-once",
        lambda args: cmd_schedule_run_once(args, scheduler),
        "Run all pending scheduled jobs once (synchronous, for testing)."
    )
    register_command(
        config,
        "schedule-status",
        lambda args: cmd_schedule_status(args, scheduler),
        "Show scheduler status and list registered jobs."
    )
    register_command(
        config,
        "schedule-backup-run-now",
        lambda args: cmd_schedule_backup_run_now(args, config),
        "Run the vault backup job immediately."
    )
    register_command(
        config,
        "template-sync-now",
        lambda args: cmd_template_sync_now(args, config),
        "Run the template sync job immediately."
    )
    register_command(
        config,
        "srd-index-run-now",
        lambda args: cmd_srd_index_run_now(args, config),
        "Run the SRD index rebuild job immediately."
    )
    register_command(
        config,
        "cache-clean-now",
        lambda args: cmd_cache_clean_now(args, config),
        "Run the cache clean job immediately."
    )
    register_command(
        config,
        "session-reminder-run-now",
        lambda args: cmd_session_reminder_run_now(args, config),
        "Run the session reminder job immediately."
    )
    register_command(
        config,
        "campaign-create",
        lambda args: cmd_campaign_create(args, config),
        "Create a new campaign. Usage: campaign-create <name>"
    )
    register_command(
        config,
        "campaign-add-pc",
        lambda args: cmd_campaign_add_pc(args, config),
        "Add a party member (PC) to a campaign. Usage: campaign-add-pc <campaign> <name>"
    )
    register_command(
        config,
        "campaign-add-npc",
        lambda args: cmd_campaign_add_npc(args, config),
        "Add an NPC to a campaign. Usage: campaign-add-npc <campaign> <attitude> <name>"
    )
    register_command(
        config,
        "campaign-add-location",
        lambda args: cmd_campaign_add_location(args, config),
        "Add a location to a campaign. Usage: campaign-add-location <campaign> <name>"
    )
    register_command(
        config,
        "session-create",
        lambda args: cmd_session_create(args, config),
        "Create a new session note for a campaign. Usage: session-create <campaign> \"<session title>\""
    )
    register_command(
        config,
        "debug",
        lambda args: cmd_debug(args, config, gpt_client),
        "Print diagnostic information about the system."
    )
    register_command(
        config,
        "undo",
        lambda args: cmd_undo(args, history_manager, config.vaults, config.current_vault),
        "Undo the last operation on a note. Usage: undo [note_path]"
    )
    register_command(
        config,
        "history-list",
        lambda args: cmd_history_list(args, history_manager, config.vaults, config.current_vault),
        "List history entries for a note. Usage: history-list <note> [limit]"
    )
    register_command(
        config,
        "history-restore",
        lambda args: cmd_history_restore(args, history_manager, config.vaults, config.current_vault),
        "Restore a specific version of a note. Usage: history-restore <note> <index>"
    )
    register_command(
        config,
        "tag-add",
        lambda args: cmd_tag_add(args, config.vaults, config.current_vault, error),
        "Add a tag to a note. Usage: tag-add <note> <tag>"
    )
    register_command(
        config,
        "tag-remove",
        lambda args: cmd_tag_remove(args, config.vaults, config.current_vault, error),
        "Remove a tag from a note. Usage: tag-remove <note> <tag>"
    )
    register_command(
        config,
        "tag-list",
        lambda args: cmd_tag_list(args, config.vaults, config.current_vault, error),
        "List all tags in the current vault."
    )
    register_command(
        config,
        "tag-notes",
        lambda args: cmd_tag_notes(args, config.vaults, config.current_vault, error),
        "List all notes with a specific tag. Usage: tag-notes <tag>"
    )


def run_main_loop(
    config: Config,
    error_func: Callable[[str, ...], None]
) -> None:
    """
    Run the main command loop.
    
    Args:
        config: Configuration object
        error_func: Error handling function
    """
    # Create the session (keep your FileHistory)
    session = PromptSession(
        history=FileHistory(".gm_assistant_history"),
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory()
    )
    
    # Build the completer
    command_completer = build_completer(config, error_func)
    
    prompt_kwargs: Dict[str, Any] = {
        "completer": command_completer,
        "reserve_space_for_menu": 8,
    }
    if CompleteStyle is not None:
        prompt_kwargs["complete_style"] = CompleteStyle.MULTI_COLUMN
    
    # Main command loop
    while True:
        try:
            cmd_line = session.prompt("> ", **prompt_kwargs).strip()
            if not cmd_line:
                continue
            
            parts = cmd_line.split(None, 1)
            cmd_name = parts[0].lower()
            cmd_args = parts[1] if len(parts) > 1 else ""
            
            if cmd_name in config.commands:
                func, _ = config.commands[cmd_name]
                func(cmd_args)
            else:
                error_func("unknown_command")
        except KeyboardInterrupt:
            print("\nExiting GM Assistant. Goodbye!")
            break
        except EOFError:
            print("\nExiting GM Assistant. Goodbye!")
            break


def main() -> None:
    """
    Main entry point for GM Assistant.
    
    Initializes the application, registers commands, and runs the main loop.
    """
    # Initialize application components
    config, gpt_client, scheduler, scheduler_context, history_manager = initialize_application()
    
    # Print startup summary
    print_startup_summary(config)
    
    # Ensure we have a current vault
    save_vaults_wrapper = create_save_vaults_wrapper(config)
    if not config.current_vault:
        error("no_vault")
        while not config.current_vault:
            user_path = prompt_input("Please enter the path to your Obsidian vault folder (or type 'quit' to exit): ").strip()
            if user_path.lower() == "quit":
                print("Exiting GM Assistant. Goodbye!")
                return
            config.current_vault = add_vault(
                user_path,
                config.vaults,
                config.current_vault,
                save_vaults_wrapper,
                config.save_settings
            )
    
    # Register all commands
    register_all_commands(config, gpt_client, scheduler, scheduler_context, history_manager)
    
    # Run main loop
    run_main_loop(config, error)


if __name__ == "__main__":
    main()
