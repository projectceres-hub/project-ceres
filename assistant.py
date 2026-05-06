#!/usr/bin/env python3

"""
GM Assistant - Terminal assistant for managing Obsidian markdown vaults.

Main entry point for Project Ceres.
"""

# 1. IMPORTS AND STUFF
from dotenv import load_dotenv
import os
import json
import time
from pathlib import Path
from core.config import Config
from core.errors import install_error_handler, guarded_main
from core.gpt import cmd_gptwrite, cmd_editnote, create_gpt_client
from core.notes import cmd_read, cmd_list, cmd_send, list_md_files, read_md_file, cmd_createnote, cmd_tree
from pantheon.reparator import cmd_showtemplates, cmd_createtemplate, cmd_deletetemplate, cmd_uploadalltemplates, cmd_uploadtemplate
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
except ImportError:
    try:
        from prompt_toolkit.shortcuts.prompt import CompleteStyle
    except ImportError:
        try:
            from prompt_toolkit.enums import CompleteStyle
        except ImportError:
            CompleteStyle = None  # Fallback if not found
from pantheon.occator import cmd_search, build_search_index, cmd_srd_index, cmd_search_srd
from pantheon.imporcitor import convert_pdf_to_md
from pantheon.promitor import (
    schedule_next_session,
    plan_session_interactively,
    build_session_event_package_from_scheduler,
)
from pantheon.convector import write_session_event_json
from pathlib import Path
from core.scheduler import Scheduler, register_default_jobs
from pantheon.conditor import HistoryManager
from pantheon.obarator import get_tags_for_note, add_tag, remove_tag, list_all_tags, get_all_tags
from typing import Callable, Dict, List, Optional, Any, Tuple
from functools import partial
import yaml
import shlex


def _assert_within(base: Path, target: Path, label: str = "path") -> Path:
    """Resolve target and assert it is inside base. Raises ValueError if not."""
    resolved = target.resolve()
    base_resolved = base.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Refusing to access {label} outside allowed directory: {resolved}")
    return resolved


# Constants
VERSION: str = "0.1"

DEFAULT_PDF_MAP_PATH: str = "maps/" "dnd5e.yaml"
DEFAULT_IMPORT_SUBFOLDER: str = "Converted"
ERROR_NO_VAULT: str = "No vault is currently set. Use 'switch' or 'addvault' to set one."
ERROR_VAULT_NOT_FOUND: str = "Vault '{name}' not found. Use 'vaults' to see available vaults."

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

    Holds a live reference to the Config object so that vault state is always
    current — even after the user runs addvault, switch, or ignorevault.

    Attributes:
        obsidian_json_path: Path to Obsidian configuration file
        config: Live Config reference (use config.vaults / config.current_vault
                instead of the old snapshot copies)
        save_vaults: Callable to save vaults dictionary
    """
    def __init__(self) -> None:
        """Initialize scheduler context with empty values."""
        self.obsidian_json_path: str = ""
        self.config: Optional["Config"] = None
        self.save_vaults: Optional[Callable[[Dict[str, str]], None]] = None

    # ---------------------------------------------------------------------------
    # Convenience properties that read live from config so callers that still
    # use the old attribute names (context.vaults, context.current_vault, etc.)
    # continue to work correctly without any changes.
    # ---------------------------------------------------------------------------

    @property
    def vaults(self) -> Dict[str, str]:
        """Snapshot of the vault map, taken under the config lock."""
        if self.config is None:
            return {}
        with self.config._lock:
            return dict(self.config.vaults)

    @property
    def ignored_vaults(self) -> List[str]:
        """Snapshot of the ignored-vaults list, taken under the config lock."""
        if self.config is None:
            return []
        with self.config._lock:
            return list(self.config.ignored_vaults)

    @property
    def current_vault(self) -> Optional[str]:
        """Current vault name, read under the config lock."""
        if self.config is None:
            return None
        with self.config._lock:
            return self.config.current_vault


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


def get_path_completions(
    config: Config,
    partial_path: str,
    include_files: bool = True
) -> List[str]:
    """
    Get path completions for a partial path within the current vault.
    
    Lists directories (with trailing '/') and optionally markdown files
    at the specified path level. Supports subdirectory traversal.
    
    Args:
        config: Configuration object
        partial_path: Partial path typed by user (e.g., "folder1/" or "folder1/sub")
        include_files: If True, include .md files; if False, only directories
        
    Returns:
        List of completion strings (directories with '/', files without)
    """
    if not config.current_vault or config.current_vault not in config.vaults:
        return []
    
    vault_path = Path(config.vaults[config.current_vault])
    if not vault_path.exists() or not vault_path.is_dir():
        return []
    
    # Resolve the base directory to list
    try:
        # Normalize path separators
        partial_path = partial_path.replace("\\", "/")
        # Remove leading slashes
        clean_path = partial_path.lstrip("/")
        
        # Determine base directory and prefix for completions
        if clean_path:
            # Split path into components
            path_parts = clean_path.split("/")
            # Filter out empty parts (from trailing slashes)
            path_parts = [p for p in path_parts if p]
            
            if path_parts:
                # Build path incrementally to find the deepest existing directory
                search_dir = vault_path
                prefix_parts = []
                remaining_partial = None
                
                for i, part in enumerate(path_parts):
                    test_dir = search_dir / part
                    if test_dir.is_dir():
                        # This part is a complete directory, continue deeper
                        search_dir = test_dir
                        prefix_parts.append(part)
                    else:
                        # This part is not a complete directory - might be partial match
                        # Remaining path (including this part) is what we need to match
                        remaining_partial = "/".join(path_parts[i:])
                        break
                
                # Determine prefix for completions
                if prefix_parts:
                    prefix = "/".join(prefix_parts) + "/"
                else:
                    prefix = ""
            else:
                # Only slashes (e.g., "/" or "//"), list vault root
                search_dir = vault_path
                prefix = ""
                remaining_partial = None
        else:
            # No path typed, list vault root
            search_dir = vault_path
            prefix = ""
            remaining_partial = None
        
        # List contents of the directory
        completions: List[str] = []
        if not search_dir.exists() or not search_dir.is_dir():
            return []
        
        for item in os.listdir(search_dir):
            item_path = search_dir / item
            # Skip hidden files/directories
            if item.startswith("."):
                continue
            
            # If we have a remaining partial match, filter by it
            if remaining_partial:
                if not item.lower().startswith(remaining_partial.lower()):
                    continue
            
            if item_path.is_dir():
                # Directory: add with trailing '/'
                completions.append(prefix + item + "/")
            elif include_files and item_path.is_file() and item.endswith(".md"):
                # Markdown file: add without trailing slash
                completions.append(prefix + item)
    except (OSError, ValueError, PermissionError):
        return []
    
    return sorted(completions)


class ContextAwareCompleter(Completer):
    """
    Context-aware completer for command-line autocompletion.
    
    Handles special cases for tag commands with argument-position-aware completion:
    - tag-add and tag-remove: note names for arg 2, tags for arg 3
    - tag-notes: tags for arg 2
    - Commands expecting paths: pdf-batch, pdf-send-to-vault, uploadalltemplates, uploadtemplate
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
        self._cache_ttl: float = 10.0
        self._last_cache_refresh: float = 0.0
    
    def _cache_is_stale(self) -> bool:
        """Return True if the cache TTL has expired and a refresh is needed."""
        return (time.monotonic() - self._last_cache_refresh) > self._cache_ttl

    def _refresh_caches(self) -> None:
        """Refresh cached note and tag lists."""
        self._note_cache = get_note_name_list(self.config, self.error_func)
        self._tag_cache = get_tag_completions(self.config)
        self._last_cache_refresh = time.monotonic()

    def invalidate_cache(self) -> None:
        """Force the next completion event to rebuild the cache immediately."""
        self._last_cache_refresh = 0.0
    
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
        
        # If no text, show command name completions with descriptions
        if not parts:
            # Get current text being typed
            current_text = document.text_before_cursor.strip().lower()
            # Yield command completions with descriptions
            for cmd_name, (handler, description) in self.config.commands.items():
                if cmd_name.lower().startswith(current_text):
                    yield Completion(
                        cmd_name,
                        start_position=-len(current_text),
                        display_meta=description or ""
                    )
            return
        
        cmd_name = parts[0].lower() if parts else ""
        arg_count = len(parts) - 1  # Number of arguments after command (including partial)
        
        # Check if the typed command name is a valid registered command
        # If not, user is typing a partial/invalid command name, show completions
        if arg_count == 0 and cmd_name not in self.config.commands:
            # User is typing a command name (possibly partial), show command completions with descriptions
            current_text = document.text_before_cursor.strip()
            for cmd_name_match, (handler, description) in self.config.commands.items():
                if cmd_name_match.lower().startswith(current_text.lower()):
                    yield Completion(
                        cmd_name_match,
                        start_position=-len(current_text),
                        display_meta=description or ""
                    )
            return
        
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
                if self._cache_is_stale():
                    self._refresh_caches()
                # Current word is the note name being typed
                search_word = current_word if len(parts) > 1 else ""
                for note in self._note_cache or []:
                    if note.lower().startswith(search_word.lower()):
                        yield Completion(note, start_position=-len(search_word))
            elif arg_count == 2:
                # Second argument (tag): suggest tags
                if self._cache_is_stale():
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
                    # Just the command name, show command completions with descriptions
                    current_text = document.text_before_cursor.strip()
                    for cmd_name_match, (handler, description) in self.config.commands.items():
                        if cmd_name_match.lower().startswith(current_text.lower()):
                            yield Completion(
                                cmd_name_match,
                                start_position=-len(current_text),
                                display_meta=description or ""
                            )
                return
        elif cmd_name == "tag-notes":
            if arg_count == 1:
                # First argument (tag): suggest tags
                if self._cache_is_stale():
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
                    # Just the command name, show command completions with descriptions
                    current_text = document.text_before_cursor.strip().lower()
                    for cmd_name, (handler, description) in self.config.commands.items():
                        if cmd_name.lower().startswith(current_text):
                            yield Completion(
                                cmd_name,
                                start_position=-len(current_text),
                                display_meta=description or ""
                            )
                return
        # Path completion commands
        elif cmd_name in ("uploadalltemplates",):
            if arg_count == 1:
                # First argument: folder path (directories only)
                partial_path = current_word if len(parts) > 1 else ""
                completions = get_path_completions(self.config, partial_path, include_files=False)
                for comp in completions:
                    # get_path_completions already handles partial matching, just yield results
                    yield Completion(comp, start_position=-len(partial_path))
                return
        elif cmd_name == "uploadtemplate":
            if arg_count == 1:
                # First argument: markdown file path (directories and .md files)
                partial_path = current_word if len(parts) > 1 else ""
                completions = get_path_completions(self.config, partial_path, include_files=True)
                for comp in completions:
                    # get_path_completions already handles partial matching, just yield results
                    yield Completion(comp, start_position=-len(partial_path))
                return
        elif cmd_name == "pdf-send-to-vault":
            # Special handling: path comes after --input flag
            # Check if we're completing the path after --input
            if arg_count >= 2:
                # Check if the previous argument was --input
                if len(parts) >= 2 and parts[1].lower() == "--input":
                    # Second argument after --input: path (directories and files)
                    partial_path = current_word if len(parts) > 2 else ""
                    completions = get_path_completions(self.config, partial_path, include_files=True)
                    for comp in completions:
                        # get_path_completions already handles partial matching, just yield results
                        yield Completion(comp, start_position=-len(partial_path))
                    return
        else:
            # For other commands, use base completer for nested completions
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


def cmd_session_discord_export(prompt_input_func) -> None:
    """
    Command handler for session-discord-export.
    
    Interactively schedules a session and exports it as a Discord-ready JSON package
    (includes .ics file reference).
    
    Args:
        prompt_input_func: Function to get user input (takes prompt string, returns response)
    """
    # Use the common interactive planning helper
    result = plan_session_interactively(prompt_input_func)
    if result is None:
        return
    
    info, ics_path, message_text = result
    
    # Build SessionEventPackage using Promitor + Convector
    pkg = build_session_event_package_from_scheduler(
        info=info,
        ics_path=ics_path,
        message_text=message_text,
        google_calendar_url=None,  # Can be added later if needed
    )
    
    # Choose output path for JSON file
    exports_dir = Path("exports")
    json_path = exports_dir / "session_event.json"
    
    # Write JSON file using Convector
    try:
        write_session_event_json(pkg, json_path)
    except Exception as e:
        print(f"\nError: Failed to write JSON file: {e}")
        print(f"Hint: Check that '{exports_dir}' is writable.")
        return
    
    # Print friendly summary
    print("\n" + "-" * 60)
    print("Session event exported for Discord helper.")
    print("-" * 60)
    print(f"\nICS file:   {ics_path.resolve()}")
    print(f"JSON file:  {json_path.resolve()}")
    print("\nYou can now run your Discord bot helper and point it at the JSON")
    print("+ ICS to post this session to a channel.")
    print("-" * 60)


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

    vault_path = Path(vaults[current_vault])
    if not vault_path.exists():
        print(f"Error: Vault path '{vault_path}' does not exist on disk. "
              f"Use 'addvault' to re-register it or check that the directory is accessible.")
        return None

    # Resolve note path
    if not note_name.endswith(".md"):
        note_name += ".md"
    try:
        note_path = _assert_within(vault_path, vault_path / note_name, "note path")
    except ValueError as e:
        print(f"Error: {e}")
        return None
    
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
            print(f"Error: No history found for note: {note_path}.")


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
    
    entries = history_manager.list_history(note_path, limit=limit)

    if not entries:
        print(f"Error: No history found for note: {note_name}.")
        return

    print(f"\nHistory for '{note_name}' (showing {len(entries)} entries):\n")
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
        print(f"Error: No history found for note: {note_name}.")
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
            print("Error: Failed to restore version.")
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

    vault_path = Path(vaults[current_vault])
    if not vault_path.exists():
        print(f"Error: Vault path '{vault_path}' does not exist on disk. "
              f"Use 'addvault' to re-register it or check that the directory is accessible.")
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

    vault_path = Path(vaults[current_vault])
    if not vault_path.exists():
        print(f"Error: Vault path '{vault_path}' does not exist on disk. "
              f"Use 'addvault' to re-register it or check that the directory is accessible.")
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
    if not vault_path.exists():
        print(f"Error: Vault path '{vault_path}' does not exist on disk. "
              f"Use 'addvault' to re-register it or check that the directory is accessible.")
        return

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
    if not vault_path.exists():
        print(f"Error: Vault path '{vault_path}' does not exist on disk. "
              f"Use 'addvault' to re-register it or check that the directory is accessible.")
        return

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
        print(ERROR_VAULT_NOT_FOUND.format(name=target_vault) + f" Available: {', '.join(config.vaults.keys())}")
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
        print(ERROR_VAULT_NOT_FOUND.format(name=config.default_vault_name) + f" Available: {', '.join(config.vaults.keys())}")
        return None, None
    vault_path = config.vaults[config.default_vault_name]
    try:
        out_dir_path = _assert_within(
            Path(vault_path),
            Path(vault_path) / config.default_import_subfolder,
            "output directory",
        )
    except ValueError as e:
        print(f"Error: {e}")
        return None, None
    out_dir = str(out_dir_path)
    os.makedirs(out_dir, exist_ok=True)
    return vault_path, out_dir

def _next_copy_name(out_dir: str, base: str, existing: set = None) -> str:
    """Return the next available numbered copy name (e.g. base1.md, base2.md).

    When `existing` is provided, membership is checked against the set instead
    of hitting the filesystem, allowing the batch loop to make a single
    os.listdir() call rather than one os.path.exists() per file.
    """
    i = 1
    while True:
        cand = f"{base}{i}.md"
        if existing is not None:
            if cand not in existing:
                return cand
        else:
            if not os.path.exists(os.path.join(out_dir, cand)):
                return cand
        i += 1


def _load_pdf_map(map_path: str) -> dict:
    """Load and validate a YAML mapping file.  Returns {} on any error."""
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f) or {}
        if not isinstance(result, dict):
            print(f"Warning: Map file '{map_path}' did not contain a mapping. Using defaults.")
            return {}
        return result
    except FileNotFoundError:
        print(f"Warning: Map file '{map_path}' not found. Using default rules.")
        return {}
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse map file '{map_path}': {e}")
        return {}
    except OSError as e:
        print(f"Error: Could not read map file '{map_path}': {e}")
        return {}


def _resolve_pdf_output(
    out_dir: str, base_name: str, prompt_input: Callable[[str], str]
) -> Optional[str]:
    """Check whether the output file already exists and ask the user what to do.

    Returns the filename stem to write (no extension), or None if the user
    chose to skip.
    """
    target = os.path.join(out_dir, base_name + ".md")
    if not os.path.exists(target):
        return base_name
    print(f"Output file '{base_name}.md' already exists.")
    choice = prompt_input("(R)eplace, (C)opy as new file, or (S)kip? ").strip().lower()
    if choice == "r":
        return base_name
    elif choice == "c":
        return os.path.splitext(_next_copy_name(out_dir, base_name))[0]
    else:
        print("Skipped.")
        return None


def cmd_pdf2md(args: str, config: Config, prompt_input_func: Callable[[str], str]) -> None:
    """
    Convert a PDF file to Markdown.
    
    Usage: pdf2md <PDF_PATH> [--map <map_file>]
    Output is always: {default_vault_name}/Converted/<original-filename>.md
    If exists: prompt to Replace or make numbered Copy.
    
    Args:
        args: Command arguments containing PDF path and optional map flag
        config: Configuration object
        prompt_input_func: Function to get user input
    """
    parts = shlex.split(args)
    if len(parts) < 1:
        print(f"Usage: pdf2md <PDF_PATH> [--map {DEFAULT_PDF_MAP_PATH}]")
        return

    pdf_path = parts[0]
    map_path = DEFAULT_PDF_MAP_PATH
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    vault_path, out_dir = _fixed_out_dir(config)
    if not out_dir:
        return
    try:
        pdf_path = str(_assert_within(Path(vault_path), Path(pdf_path), "PDF path"))
    except ValueError as e:
        print(f"Error: {e}")
        return

    if not os.path.isfile(pdf_path):
        print(f"Error: File not found: {pdf_path}.")
        return

    from pantheon.imporcitor import convert_pdf_to_md

    rules = _load_pdf_map(map_path)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    override_filename = _resolve_pdf_output(out_dir, base, prompt_input_func)
    if override_filename is None:
        return

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
    
    Usage: pdfbatch <PDF_FOLDER> [--map <map_file>]
    Output is always: {default_vault_name}/Converted/<original-filename>.md
    If exists: auto-number (base1.md, base2.md, ...)
    
    Args:
        args: Command arguments containing folder path and optional map flag
        config: Configuration object
    """
    parts = shlex.split(args)
    if len(parts) < 1:
        print(f"Usage: pdfbatch <PDF_FOLDER> [--map {DEFAULT_PDF_MAP_PATH}]")
        return

    folder = parts[0]
    map_path = DEFAULT_PDF_MAP_PATH
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    if not os.path.isdir(folder):
        print(f"Error: Folder not found: {folder}.")
        return

    vault_path, out_dir = _fixed_out_dir(config)
    if not out_dir:
        return

    from pantheon.imporcitor import convert_pdf_to_md

    rules = _load_pdf_map(map_path)

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

    # Build the set of existing output filenames once — avoids one os.path.exists()
    # call per file in the batch loop.
    existing_outputs = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()

    for fname in pdf_files:
        pdf_path = os.path.join(folder, fname)
        try:
            base = os.path.splitext(os.path.basename(pdf_path))[0]

            override_filename = base
            if (base + ".md") in existing_outputs:
                numbered = _next_copy_name(out_dir, base, existing=existing_outputs)
                override_filename = os.path.splitext(numbered)[0]

            convert_pdf_to_md(pdf_path, out_dir, rules, override_filename=override_filename)
            existing_outputs.add(override_filename + ".md")
            print(f"Converted: {fname}")
        except Exception as e:
            print(f"Error: Failed to convert '{fname}': {e}")
            print(f"Hint: Check that the PDF file is valid and not corrupted. Skipping this file.")
            continue

    print(f"Output: {os.path.abspath(out_dir)}")


def cmd_pdf_convert(args: str, config: Config, prompt_input_func: Callable[[str], str]) -> None:
    """
    Convert a PDF file to Markdown using pdf_tools.
    
    Usage: pdf-convert <PDF_PATH> [--map <map_file>]
    Output is always: {default_vault_name}/Converted/<original-filename>.md
    If exists: prompt to Replace or make numbered Copy.
    
    Args:
        args: Command arguments containing PDF path and optional map flag
        config: Configuration object
        prompt_input_func: Function to get user input
    """
    from pathlib import Path
    from pantheon.imporcitor.pdf_tools import convert_pdf_to_md
    
    parts = shlex.split(args)
    if len(parts) < 1:
        print(f"Usage: pdf-convert <PDF_PATH> [--map {DEFAULT_PDF_MAP_PATH}]")
        return

    pdf_path = parts[0]
    map_path = DEFAULT_PDF_MAP_PATH
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    vault_path, out_dir = _fixed_out_dir(config)
    if not out_dir:
        return
    try:
        pdf_path = str(_assert_within(Path(vault_path), Path(pdf_path), "PDF path"))
    except ValueError as e:
        print(f"Error: {e}")
        return

    if not os.path.isfile(pdf_path):
        print(f"Error: File not found: {pdf_path}.")
        return

    options = {}
    map_rules = _load_pdf_map(map_path)
    if map_rules:
        options["map_rules"] = map_rules

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    override_filename = _resolve_pdf_output(out_dir, base, prompt_input_func)
    if override_filename is None:
        return
    if override_filename != base:
        options["override_filename"] = override_filename

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
    
    Usage: pdf-batch <PDF_FOLDER> [--map <map_file>]
    Output is always: exports/pdf_md/<original-filename>.md
    If exists: auto-number (base1.md, base2.md, ...)
    
    Args:
        args: Command arguments containing folder path and optional map flag
        config: Configuration object
    """
    from pathlib import Path
    from pantheon.imporcitor.pdf_tools import convert_pdf_to_md
    
    parts = shlex.split(args)
    if len(parts) < 1:
        print(f"Usage: pdf-batch <PDF_FOLDER> [--map {DEFAULT_PDF_MAP_PATH}]")
        return

    folder = parts[0]
    map_path = DEFAULT_PDF_MAP_PATH
    for i, p in enumerate(parts[1:], start=1):
        if p == "--map" and i + 1 < len(parts):
            map_path = parts[i+1]
        elif p.startswith("--map="):
            map_path = p.split("=", 1)[1]

    if not os.path.isdir(folder):
        print(f"Error: Folder not found: {folder}.")
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

    options = {}
    map_rules = _load_pdf_map(map_path)
    if map_rules:
        options["map_rules"] = map_rules

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

    existing_outputs = set(os.listdir(str(out_dir))) if out_dir.is_dir() else set()

    for fname in pdf_files:
        pdf_path = os.path.join(folder, fname)
        try:
            base = os.path.splitext(os.path.basename(pdf_path))[0]

            file_options = options.copy()
            if (base + ".md") in existing_outputs:
                numbered = _next_copy_name(str(out_dir), base, existing=existing_outputs)
                file_options["override_filename"] = os.path.splitext(numbered)[0]

            final_name = file_options.get("override_filename", base) + ".md"
            convert_pdf_to_md(Path(pdf_path), out_dir, file_options)
            existing_outputs.add(final_name)
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
    from pantheon.imporcitor.pdf_tools import convert_pdf_to_md, send_md_to_obsidian, clean_markdown
    
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
                    print(f"Error: Failed to convert PDF: {e}.")
                    failed_count += 1
                    continue
                
                if not converted_files:
                    print("Error: No output files generated.")
                    failed_count += 1
                    continue
                
                # Read the converted markdown
                md_content = converted_files[0].read_text(encoding="utf-8")
                
                # Clean the markdown
                try:
                    md_content = clean_markdown(md_content)
                except Exception as e:
                    print(f"Warning: Failed to clean markdown: {e}.")
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
                    print(f"Error: Failed to save to vault: {e}.")
                    failed_count += 1
                    continue
        
        except Exception as e:
            print(f"Error: Unexpected error processing '{pdf_file.name}': {e}.")
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
    from pantheon.serritor import backup_vault
    
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
    from pantheon.serritor import sync_templates_job
    
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
    from pantheon.serritor import rebuild_srd_index_job
    
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
    from pantheon.serritor import clean_cache_job
    
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
    from pantheon.vervactor import create_campaign
    
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
    from pantheon.vervactor import find_campaign, create_party_member
    
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
    from pantheon.vervactor import find_campaign, create_npc
    
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
        
        npc_file, tag_added = create_npc(campaign, character_name, attitude, config)
        print(f"NPC '{character_name}' added to campaign '{campaign_name}' as {attitude}")
        # Only print tag success message if tag was actually added
        if tag_added:
            attitude_tag = attitude.strip().lower().capitalize()
            print(f"Tag #{attitude_tag} automatically added to NPC file.")
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
    from pantheon.vervactor import find_campaign, create_location
    
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


def cmd_fgu_import_log(args: str, config: Config) -> None:
    """
    Import a Fantasy Grounds chat log and attach it to a session note.
    
    Usage: fgu-import-log <campaign> <session> <log_path>
    
    Args:
        args: Campaign name, session identifier, and log file path (space-separated)
        config: Config object containing vault information
    """
    from pantheon.messor import attach_fgu_log_to_session, parse_fgu_chat_log
    from pathlib import Path
    
    parts = args.strip().split(None, 2)
    if len(parts) < 3:
        print("Usage: fgu-import-log <campaign> <session> <log_path>")
        print("Example: fgu-import-log \"The Lost Mines\" \"003\" \"C:/FGU/logs/chat.log\"")
        print("Session can be: session number (e.g., \"003\"), \"Session-003\", or exact filename")
        return
    
    campaign_name = parts[0]
    session_identifier = parts[1]
    log_path_str = parts[2]
    
    # Resolve log path
    log_path = Path(log_path_str).expanduser().resolve()
    
    if not log_path.exists():
        print(f"Error: Log file not found: {log_path}")
        return
    
    try:
        # Parse log first to get event count
        events = parse_fgu_chat_log(log_path)
        roll_count = sum(1 for e in events if e.is_roll)
        
        # Attach to session
        session_file = attach_fgu_log_to_session(
            campaign_name,
            session_identifier,
            log_path,
            config
        )
        
        print(f"FGU log imported successfully!")
        print(f"  Session: {session_file.name}")
        print(f"  Events imported: {len(events)}")
        print(f"  Dice rolls: {roll_count}")
        print(f"  Regular messages: {len(events) - roll_count}")
        
    except ValueError as e:
        print(f"Error: {e}")
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        print("Hint: Check that you have read permissions for the log file and write permissions for the session note.")
    except OSError as e:
        print(f"Error: Failed to import log: {e}")
        print("Hint: Check that the log file is readable and the session note is writable.")
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
    from pantheon.vervactor import find_campaign, create_session
    
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
    from pantheon.reparator import apply_template_preview
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
    from pantheon.serritor import session_reminder_job
    
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


def cmd_snapshot_run_now(args: str, config: Config) -> None:
    """
    Run the daily snapshot job immediately.
    
    Executes the daily_snapshot_job function synchronously without waiting for
    the scheduled interval.
    
    Args:
        args: Command arguments (unused)
        config: Config object containing vault information
    """
    from pantheon.serritor import daily_snapshot_job
    
    try:
        print("Running daily snapshot...")
        daily_snapshot_job(config)
    except ValueError as e:
        print(f"Error: Cannot create snapshot: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied during snapshot: {e}")
        print("Hint: Check that you have read permissions for the vault and write permissions for the snapshots directory.")
    except OSError as e:
        print(f"Error: Failed to create snapshot: {e}")
        print("Hint: Check that the vault directory exists and the snapshots directory is writable.")
    except Exception as e:
        print(f"Error: Unexpected error during snapshot: {e}")


def cmd_voice_enable(args: str, config: Config) -> None:
    """
    Enable voice commands for this installation.
    
    This sets config.voice_commands_enabled = True and persists
    the change to settings.json.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
    """
    config.voice_commands_enabled = True
    config.save_settings()
    print("Voice commands have been ENABLED.")


def cmd_voice_disable(args: str, config: Config) -> None:
    """
    Disable voice commands for this installation.
    
    This sets config.voice_commands_enabled = False and persists
    the change to settings.json.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
    """
    config.voice_commands_enabled = False
    config.save_settings()
    print("Voice commands have been DISABLED.")


def cmd_voice_status(args: str, config: Config) -> None:
    """
    Show whether voice commands are currently enabled or disabled.
    
    Args:
        args: Command arguments (unused)
        config: Configuration object
    """
    state = "ENABLED" if config.voice_commands_enabled else "DISABLED"
    print(f"Voice commands are currently: {state}")


def cmd_voice_command(args: str, config: Config) -> None:
    """
    Parse a text command into a VoiceCommand and write it to the inbox.
    
    Usage: voice-command <text>
    
    Args:
        args: Command text to parse (e.g., "Veras, add bookmark: dragon lands")
        config: Configuration object
        
    Note:
        The wake words are 'Veras' and 'Chroma' (case-insensitive).
    """
    from pantheon.convector import (
        parse_text_to_voice_command,
        write_voice_command_to_inbox,
    )
    
    text = args.strip()
    if not text:
        print("Error: No command text provided.")
        print("Usage: voice-command <text>")
        print('Example: voice-command "Veras, add bookmark: dragon lands on the tower"')
        return
    
    cmd = parse_text_to_voice_command(text)
    path = write_voice_command_to_inbox(cmd)
    print(f"Voice command queued: {path}")


def cmd_voice_commands_from_transcript(args: str, config: Config) -> None:
    """
    Read a transcript text file, extract all lines that start with the
    wake words "Veras" or "Chroma", parse them into VoiceCommands, and
    enqueue those commands into the Convector inbox.
    
    Usage:
        voice-commands-from-transcript <path>
    
    Args:
        args: Path to the transcript file
        config: Configuration object
        
    Note:
        This command does NOT execute the commands. Use
        'voice-commands-process' afterwards to apply them.
        This command respects config.voice_commands_enabled.
    """
    from pathlib import Path
    from pantheon.convector import transcript_to_inbox_from_file
    
    if not config.voice_commands_enabled:
        print("Voice commands are currently DISABLED.")
        print("Use 'voice-enable' to enable them before running this command.")
        return
    
    raw = args.strip()
    if not raw:
        print("Error: No transcript path provided.")
        print("Usage: voice-commands-from-transcript <path>")
        return
    
    path = Path(raw)
    if not path.exists():
        print(f"Error: Transcript file not found: {path}")
        return
    
    inbox_paths = transcript_to_inbox_from_file(path)
    if not inbox_paths:
        print("No Veras/Chroma commands found in transcript.")
        return
    
    print("Enqueued voice commands from transcript:")
    for p in inbox_paths:
        print(f"  - {p}")


def cmd_voice_commands_from_audio(args: str, config: Config) -> None:
    """
    Read an audio file, transcribe it, extract all lines that start
    with one of the configured wake words ("Veras", "Chroma"), and
    enqueue those commands into the Convector inbox.
    
    Usage:
        voice-commands-from-audio <path>
    
    Args:
        args: Path to the audio file
        config: Configuration object
        
    Note:
        - This command respects config.voice_commands_enabled.
        - If voice commands are disabled, it will refuse to run and
          explain how to enable them.
    """
    from pathlib import Path
    from pantheon.convector import audio_file_to_inbox
    
    if not config.voice_commands_enabled:
        print("Voice commands are currently DISABLED.")
        print("Use 'voice-enable' to enable them before running this command.")
        return
    
    raw = args.strip()
    if not raw:
        print("Error: No audio file path provided.")
        print("Usage: voice-commands-from-audio <path>")
        return
    
    path = Path(raw)
    if not path.exists():
        print(f"Error: Audio file not found: {path}")
        return
    
    inbox_paths = audio_file_to_inbox(path)
    if not inbox_paths:
        print("No wake-word commands (Veras/Chroma) found in this audio.")
        return
    
    print("Enqueued voice commands from audio:")
    for p in inbox_paths:
        print(f"  - {p}")


def cmd_session_audio_ingest(args: str, config: Config) -> None:
    """
    Attach an audio recording to a specific session, transcribe it,
    attach the transcript to the session note, and extract wake-word
    VoiceCommands (Veras/Chroma) into the inbox.
    
    Usage:
        session-audio-ingest "<campaign_name>" "<session_name>" <audio_path>
    
    Args:
        args: Command-line arguments as a single string
        config: Configuration object
        
    Note:
        - Respects config.voice_commands_enabled. If disabled,
          this command will refuse to run and tell the user to
          enable voice commands first.
    """
    from pathlib import Path
    from pantheon.messor import attach_audio_and_extract_commands_for_session
    
    if not config.voice_commands_enabled:
        print("Voice commands are currently DISABLED.")
        print("Use 'voice-enable' to enable them before running this command.")
        return
    
    # Basic parsing:
    # Expect: "<campaign_name>" "<session_name>" <audio_path>
    # Use shlex.split so quoted names and paths with spaces are handled correctly.
    try:
        parts = shlex.split(args.strip())
    except ValueError as e:
        print(f"Error: Could not parse arguments: {e}")
        print('Usage: session-audio-ingest "<campaign_name>" "<session_name>" <audio_path>')
        return
    if len(parts) < 3:
        print("Error: Missing arguments.")
        print('Usage: session-audio-ingest "<campaign_name>" "<session_name>" <audio_path>')
        return

    campaign_name = parts[0]
    session_name = parts[1]
    audio_path = Path(parts[2])
    
    if not audio_path.exists():
        print(f"Error: Audio file not found: {audio_path}")
        return
    
    inbox_paths = attach_audio_and_extract_commands_for_session(
        campaign_name=campaign_name,
        session_name=session_name,
        audio_path=audio_path,
        config=config,
    )
    
    if not inbox_paths:
        print("No wake-word commands (Veras/Chroma) found in this audio.")
        print("Transcript was still attached to the session note.")
        return
    
    print("Transcript attached; enqueued voice commands from session audio:")
    for p in inbox_paths:
        print(f"  - {p}")
    print("Use 'voice-commands-process' to apply them.")


def cmd_voice_commands_process(args: str, config: Config) -> None:
    """
    Process all queued VoiceCommand files in the inbox.
    
    Usage: voice-commands-process [--dry-run]
    
    Args:
        args: Command arguments (optional --dry-run flag)
        config: Configuration object
    """
    from pantheon.convector import process_all_voice_commands
    
    # Check for --dry-run flag
    dry_run = args.strip() == "--dry-run"
    
    summaries = process_all_voice_commands(
        config=config,
        move_on_success=not dry_run,
    )
    
    if not summaries:
        print("No voice commands found in inbox.")
        return
    
    print("Processed voice commands:")
    print("------------------------------------------------------------")
    for line in summaries:
        print(line)
    print("------------------------------------------------------------")
    
    if dry_run:
        print("(Dry run only – no files were moved.)")


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
        print("Error: No vault is currently set.")
    
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
                print(f"Error: Failed to read templates: {e}")
    else:
        print(ERROR_VAULT_NOT_FOUND.format(name=config.default_vault_name))
    
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
                print("Error: Connection test failed with an empty response.")
        except Exception as e:
            print("Error: Connection test failed.")
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

    # Wire the CLI input provider.  The UI layer swaps this for its own
    # implementation (dialog box, async queue, etc.) before calling
    # register_all_commands — no other code needs to change.
    config.input_provider = prompt_input

    # Initialize GPT client after config loads
    gpt_client = create_gpt_client(api_key=config.openai_key, default_model=config.default_model)
    
    # Initialize scheduler
    scheduler = Scheduler()
    
    # Initialize scheduler context
    scheduler_context = SchedulerContext()
    obsidian_json_path = get_obsidian_json_path()
    save_vaults_wrapper = create_save_vaults_wrapper(config)

    # Store a live Config reference so vault state is always current.
    # context.vaults / context.current_vault / context.ignored_vaults are now
    # read-through properties backed by config — no stale snapshots.
    scheduler_context.obsidian_json_path = obsidian_json_path
    scheduler_context.config = config
    scheduler_context.save_vaults = save_vaults_wrapper
    
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


# ---------------------------------------------------------------------------
# Private command-handler adapters
#
# Each _wrap_* function normalises the underlying cmd_* call signature to
# (args, config[, extras]) so that functools.partial can bind `config` (and
# any stable extra params such as gpt_client or history_manager) at
# registration time, while still resolving config attributes lazily at
# call time — preserving the same behaviour as the original lambdas.
# ---------------------------------------------------------------------------

def _wrap_showignored(args: str, config: Config) -> None:
    cmd_showignored(args, config, error)

def _wrap_reset(args: str, config: Config) -> None:
    cmd_reset(args, config, config.input_provider)

def _wrap_tree(args: str, config: Config) -> None:
    cmd_tree(args, config.vaults, config.current_vault, error)

def _wrap_createnote(
    args: str, config: Config, history_manager: HistoryManager
) -> None:
    cmd_createnote(
        args, config.vaults, config.current_vault,
        config.input_provider, config.default_vault_name,
        history_manager, config,
    )
    completer = getattr(config, "_command_completer", None)
    if completer is not None:
        completer.invalidate_cache()

def _wrap_gptwrite(
    args: str, config: Config, gpt_client: Any, history_manager: HistoryManager
) -> None:
    cmd_gptwrite(
        args, config.vaults, config.current_vault,
        config.input_provider, gpt_client, history_manager,
    )

def _wrap_editnote(
    args: str, config: Config, gpt_client: Any, history_manager: HistoryManager
) -> None:
    cmd_editnote(
        args, config.vaults, config.current_vault,
        config.input_provider, list_md_files, read_md_file,
        gpt_client, history_manager,
    )

def _wrap_showtemplates(args: str, config: Config) -> None:
    cmd_showtemplates(args, config.vaults, config.input_provider, config.default_vault_name)

def _wrap_createtemplate(
    args: str, config: Config, history_manager: HistoryManager
) -> None:
    cmd_createtemplate(
        args, config.vaults, config.input_provider,
        config.default_vault_name, history_manager,
    )

def _wrap_uploadtemplate(
    args: str, config: Config, history_manager: HistoryManager
) -> None:
    cmd_uploadtemplate(
        args, config.vaults, config.input_provider,
        config.default_vault_name, history_manager,
    )

def _wrap_uploadalltemplates(
    args: str, config: Config, history_manager: HistoryManager
) -> None:
    cmd_uploadalltemplates(
        args, config.vaults, config.input_provider,
        config.default_vault_name, history_manager,
    )

def _wrap_deletetemplate(args: str, config: Config) -> None:
    cmd_deletetemplate(args, config.vaults, config.input_provider, config.default_vault_name)

def _wrap_addvault(args: str, config: Config, save_vaults_wrapper: Any) -> None:
    config.current_vault = cmd_addvault(
        args, config.vaults, config.current_vault, save_vaults_wrapper,
        config.save_settings, config.input_provider, list_vaults, config.ignored_vaults,
    )
    completer = getattr(config, "_command_completer", None)
    if completer is not None:
        completer.invalidate_cache()

def _wrap_switch(args: str, config: Config) -> None:
    config.current_vault = cmd_switch(
        args, config.vaults, config.current_vault, config.vault_number_map,
        config.save_settings, config.input_provider, list_vaults,
        config.ignored_vaults, display_numbered_vaults,
    )
    completer = getattr(config, "_command_completer", None)
    if completer is not None:
        completer.invalidate_cache()

def _wrap_vaults(args: str, config: Config) -> None:
    cmd_vaults(config.vaults, config.current_vault, config.ignored_vaults)

def _wrap_ignorevault(args: str, config: Config) -> None:
    cmd_ignorevault(args, config.ignored_vaults, config.save_settings)

def _wrap_unignorevault(args: str, config: Config) -> None:
    cmd_unignorevault(args, config.ignored_vaults, config.save_settings)

def _wrap_read(args: str, config: Config) -> None:
    cmd_read(args, config.vaults, config.current_vault, error)

def _wrap_list(args: str, config: Config) -> None:
    cmd_list(args, config.vaults, config.current_vault, error)

def _wrap_send(args: str, config: Config, gpt_client: Any) -> None:
    cmd_send(args, config.vaults, config.current_vault, error, gpt_client)

def _wrap_search(args: str, config: Config) -> None:
    cmd_search(args, config.vaults, config.current_vault, error)

def _wrap_index(args: str, config: Config) -> None:
    if config.current_vault:
        build_search_index(config.vaults[config.current_vault])

def _wrap_srd_index(args: str, config: Config) -> None:
    cmd_srd_index(args, config.vaults, config.current_vault, error)

def _wrap_search_srd(args: str, config: Config) -> None:
    cmd_search_srd(args, config.vaults, config.current_vault, error)

def _wrap_pdf2md(args: str, config: Config) -> None:
    cmd_pdf2md(args, config, config.input_provider)

def _wrap_session_schedule(args: str, config: Config) -> None:
    schedule_next_session(config.input_provider)

def _wrap_session_discord_export(args: str, config: Config) -> None:
    cmd_session_discord_export(config.input_provider)

def _wrap_undo(args: str, config: Config, history_manager: HistoryManager) -> None:
    cmd_undo(args, history_manager, config.vaults, config.current_vault)

def _wrap_history_list(args: str, config: Config, history_manager: HistoryManager) -> None:
    cmd_history_list(args, history_manager, config.vaults, config.current_vault)

def _wrap_history_restore(
    args: str, config: Config, history_manager: HistoryManager
) -> None:
    cmd_history_restore(args, history_manager, config.vaults, config.current_vault)

def _wrap_tag_add(args: str, config: Config) -> None:
    cmd_tag_add(args, config.vaults, config.current_vault, error)

def _wrap_tag_remove(args: str, config: Config) -> None:
    cmd_tag_remove(args, config.vaults, config.current_vault, error)

def _wrap_tag_list(args: str, config: Config) -> None:
    cmd_tag_list(args, config.vaults, config.current_vault, error)

def _wrap_tag_notes(args: str, config: Config) -> None:
    cmd_tag_notes(args, config.vaults, config.current_vault, error)


# ---------------------------------------------------------------------------
# Domain-grouped registration helpers
# ---------------------------------------------------------------------------

def _register_misc_commands(config: Config, gpt_client: Any) -> None:
    register_command(config, "exit", cmd_exit, "Exit the assistant.")
    register_command(
        config, "help",
        partial(cmd_help, config=config),
        "Show this help message.",
    )
    register_command(
        config, "showignored",
        partial(_wrap_showignored, config=config),
        "Show all currently ignored vaults",
    )
    register_command(
        config, "reset",
        partial(_wrap_reset, config=config),
        "Reset all GM Assistant settings to first-launch state (will not delete notes, just assistant config).",
    )
    register_command(
        config, "debug",
        partial(cmd_debug, config=config, gpt_client=gpt_client),
        "Print diagnostic information about the system.",
    )


def _register_vault_commands(config: Config, save_vaults_wrapper: Any) -> None:
    register_command(
        config, "addvault",
        partial(_wrap_addvault, config=config, save_vaults_wrapper=save_vaults_wrapper),
        "Add a new Obsidian vault.",
    )
    register_command(
        config, "switch",
        partial(_wrap_switch, config=config),
        "Switch to a different vault.",
    )
    register_command(
        config, "vaults",
        partial(_wrap_vaults, config=config),
        "List available vaults.",
    )
    register_command(
        config, "ignorevault",
        partial(_wrap_ignorevault, config=config),
        "Ignore a vault from auto-importing.",
    )
    register_command(
        config, "unignorevault",
        partial(_wrap_unignorevault, config=config),
        "Stop ignoring a vault.",
    )


def _register_note_commands(config: Config, history_manager: HistoryManager) -> None:
    register_command(
        config, "tree",
        partial(_wrap_tree, config=config),
        "Show the current vault's folder and note structure (tree view).",
    )
    register_command(
        config, "createnote",
        partial(_wrap_createnote, config=config, history_manager=history_manager),
        "Create a new note, optionally from a template. Usage: createnote [--template X] [--dry-run] [var=value ...]",
    )
    register_command(
        config, "read",
        partial(_wrap_read, config=config),
        "Read a markdown file: read FILENAME",
    )
    register_command(
        config, "list",
        partial(_wrap_list, config=config),
        "List markdown files in the current vault.",
    )
    register_command(
        config, "search",
        partial(_wrap_search, config=config),
        "Search notes using title, type, system, or tags (e.g., 'spell system:dnd-5e')",
    )
    register_command(
        config, "index",
        partial(_wrap_index, config=config),
        "Build or rebuild the search index for the current vault.",
    )
    register_command(
        config, "srd-index",
        partial(_wrap_srd_index, config=config),
        "Build or rebuild the SRD index for the current vault's /SRDs/ directory.",
    )
    register_command(
        config, "search-srd",
        partial(_wrap_search_srd, config=config),
        "Search SRD markdown files. Usage: search-srd <query> [tag:<value>] [system:<value>] [name:<value>]",
    )


def _register_template_commands(config: Config, history_manager: HistoryManager) -> None:
    register_command(
        config, "showtemplates",
        partial(_wrap_showtemplates, config=config),
        "List and preview note templates.",
    )
    register_command(
        config, "template-preview",
        partial(cmd_template_preview, config=config),
        "Preview a template with variable replacement. Usage: template-preview <template> [var=value ...]",
    )
    register_command(
        config, "createtemplate",
        partial(_wrap_createtemplate, config=config, history_manager=history_manager),
        "Create a new markdown template by typing or pasting content.",
    )
    register_command(
        config, "uploadtemplate",
        partial(_wrap_uploadtemplate, config=config, history_manager=history_manager),
        "Upload an existing .md file into the default vault's templates.",
    )
    register_command(
        config, "uploadalltemplates",
        partial(_wrap_uploadalltemplates, config=config, history_manager=history_manager),
        "Upload all .md files from a folder into the default vault's templates.",
    )
    register_command(
        config, "deletetemplate",
        partial(_wrap_deletetemplate, config=config),
        "Delete a template.",
    )


def _register_gpt_commands(
    config: Config, gpt_client: Any, history_manager: HistoryManager
) -> None:
    register_command(
        config, "gptwrite",
        partial(_wrap_gptwrite, config=config, gpt_client=gpt_client, history_manager=history_manager),
        "Ask ChatGPT a question and optionally save to a note: gptwrite NoteName.md: prompt text",
    )
    register_command(
        config, "editnote",
        partial(_wrap_editnote, config=config, gpt_client=gpt_client, history_manager=history_manager),
        "Edit a note with ChatGPT and choose how to save: editnote",
    )
    register_command(
        config, "send",
        partial(_wrap_send, config=config, gpt_client=gpt_client),
        "Send a note to ChatGPT: 'send NOTE' or 'upload FOLDER/NOTE'",
    )
    register_command(
        config, "undo",
        partial(_wrap_undo, config=config, history_manager=history_manager),
        "Undo the last operation on a note. Usage: undo [note_path]",
    )
    register_command(
        config, "history-list",
        partial(_wrap_history_list, config=config, history_manager=history_manager),
        "List history entries for a note. Usage: history-list <note> [limit]",
    )
    register_command(
        config, "history-restore",
        partial(_wrap_history_restore, config=config, history_manager=history_manager),
        "Restore a specific version of a note. Usage: history-restore <note> <index>",
    )


def _register_pdf_commands(config: Config) -> None:
    register_command(
        config, "pdf2md",
        partial(_wrap_pdf2md, config=config),
        'Convert a single PDF to Markdown. Output → default vault/Converted. Usage: pdf2md "PDF_PATH" --map maps/mapname.yaml',
    )
    register_command(
        config, "pdfbatch",
        partial(cmd_pdfbatch, config=config),
        'Convert all PDFs in a folder. Output → default vault/Converted. Usage: pdfbatch "PDF_FOLDER" --map maps/mapname.yaml',
    )
    # pdf-convert and pdf-batch removed: they were duplicates of pdf2md/pdfbatch
    # that additionally required the external Marker CLI and wrote to a different
    # output directory (exports/pdf_md/), creating confusion with no added value.
    # Use pdf2md / pdfbatch instead — they work without any external dependencies.
    register_command(
        config, "pdf-send-to-vault",
        partial(cmd_pdf_send_to_vault, config=config),
        "Convert PDF(s) to Markdown and send to current vault's Converted folder. [requires Marker CLI] Usage: pdf-send-to-vault --input <PDF_PATH or FOLDER>",
    )


def _register_scheduler_commands(
    config: Config, scheduler: Scheduler, scheduler_context: SchedulerContext
) -> None:
    register_command(
        config, "session-schedule",
        partial(_wrap_session_schedule, config=config),
        "Schedule the next TTRPG session and generate calendar invite (.ics) file.",
    )
    register_command(
        config, "session-discord-export",
        partial(_wrap_session_discord_export, config=config),
        "Schedule a session and export it as a Discord-ready JSON package (includes .ics file).",
    )
    register_command(
        config, "schedule-start",
        partial(cmd_schedule_start, scheduler=scheduler, context=scheduler_context),
        "Start the background job scheduler.",
    )
    register_command(
        config, "schedule-stop",
        partial(cmd_schedule_stop, scheduler=scheduler),
        "Stop the background job scheduler.",
    )
    register_command(
        config, "schedule-run-once",
        partial(cmd_schedule_run_once, scheduler=scheduler),
        "Run all pending scheduled jobs once (synchronous, for testing).",
    )
    register_command(
        config, "schedule-status",
        partial(cmd_schedule_status, scheduler=scheduler),
        "Show scheduler status and list registered jobs.",
    )
    register_command(
        config, "schedule-backup-run-now",
        partial(cmd_schedule_backup_run_now, config=config),
        "Run the vault backup job immediately.",
    )
    register_command(
        config, "template-sync-now",
        partial(cmd_template_sync_now, config=config),
        "Run the template sync job immediately.",
    )
    register_command(
        config, "srd-index-run-now",
        partial(cmd_srd_index_run_now, config=config),
        "Run the SRD index rebuild job immediately.",
    )
    register_command(
        config, "cache-clean-now",
        partial(cmd_cache_clean_now, config=config),
        "Run the cache clean job immediately.",
    )
    register_command(
        config, "session-reminder-run-now",
        partial(cmd_session_reminder_run_now, config=config),
        "Run the session reminder job immediately.",
    )
    register_command(
        config, "snapshot-run-now",
        partial(cmd_snapshot_run_now, config=config),
        "Run the daily snapshot job immediately.",
    )


def _register_campaign_commands(config: Config) -> None:
    register_command(
        config, "campaign-create",
        partial(cmd_campaign_create, config=config),
        "Create a new campaign. Usage: campaign-create <name>",
    )
    register_command(
        config, "campaign-add-pc",
        partial(cmd_campaign_add_pc, config=config),
        "Add a party member (PC) to a campaign. Usage: campaign-add-pc <campaign> <name>",
    )
    register_command(
        config, "campaign-add-npc",
        partial(cmd_campaign_add_npc, config=config),
        "Add an NPC to a campaign. Usage: campaign-add-npc <campaign> <attitude> <name>",
    )
    register_command(
        config, "campaign-add-location",
        partial(cmd_campaign_add_location, config=config),
        "Add a location to a campaign. Usage: campaign-add-location <campaign> <name>",
    )
    register_command(
        config, "session-create",
        partial(cmd_session_create, config=config),
        'Create a new session note for a campaign. Usage: session-create <campaign> "<session title>"',
    )
    register_command(
        config, "fgu-import-log",
        partial(cmd_fgu_import_log, config=config),
        "Import a Fantasy Grounds chat log and attach it to a session note. Usage: fgu-import-log <campaign> <session> <log_path>",
    )


def _register_voice_commands(config: Config) -> None:
    register_command(
        config, "voice-command",
        partial(cmd_voice_command, config=config),
        "Parse a text command into a VoiceCommand and write it to the inbox. Usage: voice-command <text>",
    )
    register_command(
        config, "voice-commands-from-transcript",
        partial(cmd_voice_commands_from_transcript, config=config),
        "Extract VoiceCommands from a transcript file and enqueue them. Usage: voice-commands-from-transcript <path>",
    )
    register_command(
        config, "voice-commands-from-audio",
        partial(cmd_voice_commands_from_audio, config=config),
        "Transcribe an audio file, extract wake-word commands, and enqueue them. Usage: voice-commands-from-audio <path>",
    )
    register_command(
        config, "session-audio-ingest",
        partial(cmd_session_audio_ingest, config=config),
        'Attach audio to a session, transcribe it, attach transcript, and enqueue wake-word commands. Usage: session-audio-ingest "<campaign_name>" "<session_name>" <audio_path>',
    )
    register_command(
        config, "voice-enable",
        partial(cmd_voice_enable, config=config),
        "Enable voice command features (transcript/audio parsing).",
    )
    register_command(
        config, "voice-disable",
        partial(cmd_voice_disable, config=config),
        "Disable voice command features.",
    )
    register_command(
        config, "voice-status",
        partial(cmd_voice_status, config=config),
        "Show whether voice commands are enabled or disabled.",
    )
    register_command(
        config, "voice-commands-process",
        partial(cmd_voice_commands_process, config=config),
        "Process all queued VoiceCommand files in the inbox. Usage: voice-commands-process [--dry-run]",
    )


def _register_tag_commands(config: Config) -> None:
    register_command(
        config, "tag-add",
        partial(_wrap_tag_add, config=config),
        "Add a tag to a note. Usage: tag-add <note> <tag>",
    )
    register_command(
        config, "tag-remove",
        partial(_wrap_tag_remove, config=config),
        "Remove a tag from a note. Usage: tag-remove <note> <tag>",
    )
    register_command(
        config, "tag-list",
        partial(_wrap_tag_list, config=config),
        "List all tags in the current vault.",
    )
    register_command(
        config, "tag-notes",
        partial(_wrap_tag_notes, config=config),
        "List all notes with a specific tag. Usage: tag-notes <tag>",
    )


def register_all_commands(
    config: Config,
    gpt_client: Any,
    scheduler: Scheduler,
    scheduler_context: SchedulerContext,
    history_manager: HistoryManager,
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
    _register_misc_commands(config, gpt_client)
    _register_vault_commands(config, save_vaults_wrapper)
    _register_note_commands(config, history_manager)
    _register_template_commands(config, history_manager)
    _register_gpt_commands(config, gpt_client, history_manager)
    _register_pdf_commands(config)
    _register_scheduler_commands(config, scheduler, scheduler_context)
    _register_campaign_commands(config)
    _register_voice_commands(config)
    _register_tag_commands(config)

def run_command(
    command_name: str,
    args: str,
    config: Config,
    error_func: Optional[Callable[[str, ...], None]] = None
) -> None:
    """
    Execute a command programmatically by name and arguments.
    
    This function provides a programmatic interface to execute commands
    registered in the config.commands registry. Useful for voice commands,
    automation, and other non-interactive command execution.
    
    Args:
        command_name: Name of the command to execute (case-insensitive)
        args: Command arguments as a string
        config: Configuration object containing command registry
        error_func: Optional error handling function. If None, uses a default
                   that prints error messages.

    Note:
        Does NOT raise KeyError on unknown commands. If command_name is not
        found in the registry, error_func is called with "unknown_command" and
        the function returns normally. Callers should not wrap this in a
        try/except KeyError.
    """
    if error_func is None:
        def default_error(msg_key: str, **kwargs: Any) -> None:
            msg = ERRORS.get(msg_key, "Unknown error.").format(**kwargs)
            print(msg)
        error_func = default_error
    
    cmd_name = command_name.lower()
    
    if cmd_name not in config.commands:
        error_func("unknown_command")
        return
    
    func, _ = config.commands[cmd_name]
    func(args)


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
    
    # Build the completer and stash it on config so vault-mutating
    # wrappers can call invalidate_cache() without a circular dependency.
    command_completer = build_completer(config, error_func)
    config._command_completer = command_completer  # type: ignore[attr-defined]
    
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
            break


def main() -> None:
    """Main entry point for the GM Assistant CLI."""
    install_error_handler()
    config, gpt_client, scheduler, scheduler_context, history_manager = initialize_application()
    register_all_commands(config, gpt_client, scheduler, scheduler_context, history_manager)
    run_main_loop(config, error)


if __name__ == "__main__":
    guarded_main(main)
