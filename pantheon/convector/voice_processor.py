"""
Voice Command Processor module for Project Ceres.

Provides functionality to process VoiceCommand JSON files from the inbox,
routing them to appropriate Pantheon domains (Insitor, Messor, etc.) for execution.

This module is part of the Convector domain in the Pantheon architecture,
responsible for processing voice commands that have been structured and stored.
"""

from pathlib import Path
from typing import Iterable, Optional

from .voice_commands import (
    VoiceCommand,
    VOICE_COMMAND_INBOX,
    ensure_voice_command_inbox,
    load_voice_command_from_path,
)

# Import Config with TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


PROCESSED_SUBDIR = "processed"


def get_processed_dir() -> Path:
    """
    Return the directory used to store processed voice command files.
    Create it if necessary.
    
    Returns:
        Path to the processed subdirectory within the voice command inbox
    """
    inbox = ensure_voice_command_inbox()
    processed = inbox / PROCESSED_SUBDIR
    processed.mkdir(parents=True, exist_ok=True)
    return processed


def iter_voice_command_files() -> Iterable[Path]:
    """
    Yield all JSON files in the voice command inbox (non-recursive).
    
    Yields:
        Path objects for each JSON file in the inbox directory
    """
    inbox = ensure_voice_command_inbox()
    for path in inbox.glob("*.json"):
        if path.is_file():
            yield path


def _resolve_note_path_from_string(
    note_path_str: str,
    vaults: dict[str, str],
    current_vault: Optional[str]
) -> Optional[Path]:
    """
    Resolve a note path string to a full Path object.
    
    Args:
        note_path_str: Note path as string (relative to vault or absolute)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        
    Returns:
        Path object if note exists, None otherwise
    """
    if not current_vault or current_vault not in vaults:
        return None
    
    # Try as relative path first
    note_path = Path(note_path_str)
    if note_path.is_absolute():
        # If absolute, check if it exists
        if note_path.exists():
            return note_path
        return None
    
    # Try relative to current vault
    vault_path = Path(vaults[current_vault])
    full_path = vault_path / note_path
    
    # Ensure .md extension
    if not full_path.suffix:
        full_path = full_path.with_suffix(".md")
    elif full_path.suffix != ".md":
        full_path = full_path.with_suffix(".md")
    
    if full_path.exists():
        return full_path
    
    return None


def _resolve_session_note(
    session_id: str,
    vaults: dict[str, str],
    current_vault: Optional[str]
) -> Optional[Path]:
    """
    Resolve a session note path from a session_id.
    
    For now, this is a simple implementation that looks for session notes
    in the Sessions/ directory of campaigns. The session_id format is expected
    to be something like "CampaignName/Session-XXX" or just a session filename.
    
    Args:
        session_id: Session identifier (campaign/session string or session filename)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        
    Returns:
        Path to the session note if found, None otherwise
    """
    if not current_vault or current_vault not in vaults:
        return None
    
    vault_path = Path(vaults[current_vault])
    
    # Try to find session note in Sessions directories
    # Look for patterns like: Campaigns/*/Sessions/Session-*.md
    sessions_dirs = list(vault_path.glob("Campaigns/*/Sessions"))
    
    # If session_id contains a slash, try to parse it as CampaignName/SessionName
    if "/" in session_id:
        parts = session_id.split("/", 1)
        campaign_name = parts[0]
        session_name = parts[1]
        campaign_sessions = vault_path / "Campaigns" / campaign_name / "Sessions"
        if campaign_sessions.exists():
            # Try exact match first
            session_file = campaign_sessions / f"{session_name}.md"
            if session_file.exists():
                return session_file
            # Try without .md extension
            session_file = campaign_sessions / session_name
            if session_file.exists() and session_file.suffix == ".md":
                return session_file
    
    # Search all Sessions directories for matching session files
    session_name = session_id
    if not session_name.endswith(".md"):
        session_name = f"{session_name}.md"
    
    for sessions_dir in sessions_dirs:
        session_file = sessions_dir / session_name
        if session_file.exists():
            return session_file
        
        # Also try without .md extension
        session_file = sessions_dir / session_id
        if session_file.exists() and session_file.suffix == ".md":
            return session_file
    
    return None


def process_voice_command(cmd: VoiceCommand, config: "Config") -> str:
    """
    Process a single VoiceCommand and return a short human-readable
    description of what was done (for logging / CLI output).
    
    This function dispatches based on cmd.type and calls into
    the appropriate Pantheon domains (Insitor, Messor, etc.).
    
    Args:
        cmd: VoiceCommand to process
        config: Configuration object containing vault information
        
    Returns:
        Human-readable summary string describing what was done
        
    Note:
        - If note resolution fails, returns a skip message
        - Uses Conditor's history manager for backups before modifications
        - Minimal implementations for each command type
    """
    from pantheon.conditor.history import HistoryManager
    
    # Initialize history manager for backups
    history_manager = HistoryManager()
    
    # Resolve note path if needed
    note_path: Optional[Path] = None
    
    if cmd.note_path:
        note_path = _resolve_note_path_from_string(
            cmd.note_path,
            config.vaults,
            config.current_vault
        )
        if note_path is None:
            return f"skipped: could not resolve note path '{cmd.note_path}'"
    
    elif cmd.session_id:
        note_path = _resolve_session_note(
            cmd.session_id,
            config.vaults,
            config.current_vault
        )
        if note_path is None:
            return f"skipped: could not resolve session note for '{cmd.session_id}'"
    
    # Process based on command type
    if cmd.type == "add_bookmark":
        if note_path is None:
            return "skipped: no note_path or session_id provided for add_bookmark"
        
        # Get label from payload
        label = cmd.payload.get("label", "Voice Marker")
        timestamp_str = cmd.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Backup before modification
        try:
            history_manager.backup_note(note_path)
        except Exception:
            pass  # Continue even if backup fails
        
        # Append bookmark line
        marker_line = f"\n\n> [VOICE MARKER] {label} ({timestamp_str})"
        
        try:
            with open(note_path, "a", encoding="utf-8") as f:
                f.write(marker_line)
            return f"added bookmark '{label}' to {note_path.name}"
        except (OSError, PermissionError) as e:
            return f"error: failed to write bookmark to {note_path.name}: {e}"
    
    elif cmd.type == "append_note":
        if note_path is None:
            return "skipped: note_path required for append_note"
        
        # Get text from payload
        text = cmd.payload.get("text", "")
        if not text:
            return "skipped: no text provided in payload for append_note"
        
        # Backup before modification
        try:
            history_manager.backup_note(note_path)
        except Exception:
            pass  # Continue even if backup fails
        
        # Append text
        try:
            with open(note_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n{text}")
            return f"appended text to {note_path.name}"
        except (OSError, PermissionError) as e:
            return f"error: failed to append to {note_path.name}: {e}"
    
    elif cmd.type == "add_session_marker":
        if note_path is None:
            return "skipped: no note_path or session_id provided for add_session_marker"
        
        # Get label from payload
        label = cmd.payload.get("label", "Voice Marker")
        timestamp_str = cmd.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Backup before modification
        try:
            history_manager.backup_note(note_path)
        except Exception:
            pass  # Continue even if backup fails
        
        # Append prominent marker
        marker_line = f"\n\n## [VOICE MARKER] {label} ({timestamp_str})"
        
        try:
            with open(note_path, "a", encoding="utf-8") as f:
                f.write(marker_line)
            return f"added session marker '{label}' to {note_path.name}"
        except (OSError, PermissionError) as e:
            return f"error: failed to write marker to {note_path.name}: {e}"
    
    elif cmd.type == "set_flag":
        # For now, this is a no-op
        flag_name = cmd.payload.get("flag", "unknown")
        return f"skipped: set_flag not yet implemented (flag: {flag_name})"
    
    elif cmd.type == "custom":
        # For now, just log the payload
        return f"skipped: custom command not yet implemented (payload keys: {list(cmd.payload.keys())})"
    
    else:
        return f"skipped: unknown command type '{cmd.type}'"


def process_voice_command_file(
    path: Path,
    config: "Config",
    move_on_success: bool = True
) -> str:
    """
    Load a VoiceCommand from the given path, process it, and
    optionally move it to the processed directory on success.
    
    Args:
        path: Path to the JSON file containing the voice command
        config: Configuration object
        move_on_success: If True, move file to processed/ on success
        
    Returns:
        Human-readable summary string
        
    Note:
        - If JSON is invalid, returns an error message
        - Does not raise exceptions; errors are returned as strings
    """
    try:
        cmd = load_voice_command_from_path(path)
        summary = process_voice_command(cmd, config)
        
        if move_on_success:
            processed_dir = get_processed_dir()
            target = processed_dir / path.name
            path.replace(target)
        
        return summary
    except FileNotFoundError:
        return f"error: file not found: {path.name}"
    except ValueError as e:
        return f"error: invalid voice command in {path.name}: {e}"
    except Exception as e:
        return f"error: failed to process {path.name}: {e}"


def process_all_voice_commands(
    config: "Config",
    move_on_success: bool = True
) -> list[str]:
    """
    Process all queued voice command JSON files in the inbox.
    
    Args:
        config: Configuration object
        move_on_success: If True, move processed files to processed/ directory
        
    Returns:
        List of summary strings for each processed command (format: "filename: summary")
    """
    summaries: list[str] = []
    
    for path in sorted(iter_voice_command_files()):
        summary = process_voice_command_file(path, config, move_on_success=move_on_success)
        summaries.append(f"{path.name}: {summary}")
    
    return summaries

