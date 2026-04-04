"""
Fantasy Grounds Unity (FGU) integration module for Project Ceres.

Provides functionality to import FGU chat logs (including dice rolls) and
attach them to session notes in campaigns.

This module is part of the Messor domain in the Pantheon architecture,
responsible for collecting session data from various sources.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


@dataclass
class FGUEvent:
    """
    Represents a single event from a Fantasy Grounds chat log.
    
    Attributes:
        timestamp: When the event occurred
        speaker: Name of the speaker/character
        message: The message text
        is_roll: Whether this event is a dice roll
        roll_expression: The dice expression (e.g., "1d20+5") if is_roll is True
        roll_result: The numeric result of the roll if is_roll is True
    """
    timestamp: datetime
    speaker: str
    message: str
    is_roll: bool
    roll_expression: Optional[str] = None
    roll_result: Optional[int] = None


def parse_fgu_chat_log(log_path: Path) -> list[FGUEvent]:
    """
    Parse a Fantasy Grounds chat log file and return a list of FGUEvent objects.
    
    Initial implementation assumes a simple text or HTML log format:
    - Each line contains a timestamp, speaker, and message
    - Dice rolls can be detected via patterns like:
      - "Rolling [1d20+5] = 17"
      - "Result: [1d20+5] = 17"
      - "[1d20+5] = 17"
    
    This is a basic parser scaffold; more sophisticated parsing can be added later.
    
    Args:
        log_path: Path to the FGU chat log file
        
    Returns:
        List of FGUEvent objects parsed from the log
        
    Raises:
        FileNotFoundError: If the log file doesn't exist
        PermissionError: If the log file cannot be read
        OSError: If file operations fail
    """
    if not log_path.exists():
        raise FileNotFoundError(f"FGU log file not found: {log_path}")
    
    if not log_path.is_file():
        raise ValueError(f"Path is not a file: {log_path}")
    
    events: list[FGUEvent] = []
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except PermissionError as e:
        raise PermissionError(f"Permission denied reading FGU log: {e}")
    except OSError as e:
        raise OSError(f"Failed to read FGU log: {e}")
    
    # Remove HTML tags if present (basic cleanup)
    content = re.sub(r'<[^>]+>', '', content)
    
    # Pattern to match dice rolls: [XdY+Z] = N or [XdY-Z] = N or [XdY] = N
    roll_pattern = re.compile(r'\[(\d+)d(\d+)([+-]\d+)?\]\s*=\s*(\d+)', re.IGNORECASE)
    
    # Pattern to match common timestamp formats
    # Examples: "2024-01-15 14:30:00", "[14:30:00]", "14:30"
    timestamp_patterns = [
        re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'),  # Full datetime
        re.compile(r'\[(\d{2}:\d{2}:\d{2})\]'),  # Time in brackets
        re.compile(r'(\d{2}:\d{2}:\d{2})'),  # Just time
        re.compile(r'(\d{2}:\d{2})'),  # Time without seconds
    ]
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Try to extract timestamp
        timestamp = None
        timestamp_str = None
        for pattern in timestamp_patterns:
            match = pattern.search(line)
            if match:
                timestamp_str = match.group(1)
                try:
                    # Try full datetime first
                    if '-' in timestamp_str and len(timestamp_str) > 10:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    # Try time with seconds
                    elif ':' in timestamp_str and timestamp_str.count(':') == 2:
                        timestamp = datetime.strptime(timestamp_str, "%H:%M:%S")
                    # Try time without seconds
                    elif ':' in timestamp_str:
                        timestamp = datetime.strptime(timestamp_str, "%H:%M")
                    # If we can't parse, use current time as fallback
                    if timestamp is None:
                        timestamp = datetime.now()
                    break
                except ValueError:
                    continue
        
        # If no timestamp found, use current time
        if timestamp is None:
            timestamp = datetime.now()
        
        # Try to detect dice roll
        roll_match = roll_pattern.search(line)
        is_roll = roll_match is not None
        roll_expression = None
        roll_result = None
        
        if is_roll:
            dice_count = roll_match.group(1)
            dice_size = roll_match.group(2)
            modifier = roll_match.group(3) or ""
            roll_result = int(roll_match.group(4))
            roll_expression = f"{dice_count}d{dice_size}{modifier}"
        
        # Extract speaker and message
        # Common patterns: "Speaker: message", "[Speaker] message", "Speaker - message"
        speaker = "Unknown"
        message = line
        
        # Remove timestamp from line for parsing
        if timestamp_str:
            message = message.replace(timestamp_str, "").strip()
            # Remove brackets if they were around the timestamp
            message = re.sub(r'^\[|\]$', '', message).strip()
        
        # Try to extract speaker
        speaker_patterns = [
            re.compile(r'^([^:]+):\s*(.+)$'),  # "Speaker: message"
            re.compile(r'^\[([^\]]+)\]\s*(.+)$'),  # "[Speaker] message"
            re.compile(r'^([^-]+)-\s*(.+)$'),  # "Speaker - message"
        ]
        
        for pattern in speaker_patterns:
            match = pattern.match(message)
            if match:
                speaker = match.group(1).strip()
                message = match.group(2).strip()
                break
        
        # If no speaker pattern matched, try to use first word as speaker
        if speaker == "Unknown" and message:
            parts = message.split(maxsplit=1)
            if len(parts) > 1:
                speaker = parts[0]
                message = parts[1]
            else:
                message = parts[0] if parts else ""
        
        # Create event
        event = FGUEvent(
            timestamp=timestamp,
            speaker=speaker,
            message=message,
            is_roll=is_roll,
            roll_expression=roll_expression,
            roll_result=roll_result
        )
        events.append(event)
    
    return events


def attach_fgu_log_to_session(
    campaign_name: str,
    session_identifier: str,
    log_path: Path,
    config: "Config",
) -> Path:
    """
    Attach parsed FGU chat log events to a session note.
    
    Locates the campaign folder under Campaigns/<CampaignName>/ and finds the
    session note in Sessions/ matching session_identifier (e.g., "Session-003"
    prefix or exact filename). Uses history/backup before modifying the note.
    Appends a section with the chat log events.
    
    Args:
        campaign_name: Name of the campaign
        session_identifier: Session identifier (e.g., "003", "Session-003", or filename)
        log_path: Path to the FGU chat log file
        config: Config object containing vault information
        
    Returns:
        Path to the modified session note
        
    Raises:
        ValueError: If campaign not found, session not found, or log parsing fails
        FileNotFoundError: If log file doesn't exist
        OSError: If file operations fail
        PermissionError: If permissions are insufficient
    """
    if not config.current_vault:
        raise ValueError("No current vault set")
    
    if config.current_vault not in config.vaults:
        raise ValueError(f"Current vault '{config.current_vault}' not found in vaults")
    
    vault_path = Path(config.vaults[config.current_vault])
    campaign_dir = vault_path / "Campaigns" / campaign_name
    
    if not campaign_dir.exists() or not campaign_dir.is_dir():
        raise ValueError(f"Campaign '{campaign_name}' not found")
    
    sessions_dir = campaign_dir / "Sessions"
    if not sessions_dir.exists() or not sessions_dir.is_dir():
        raise ValueError(f"Sessions directory not found for campaign '{campaign_name}'")
    
    # Find session file by identifier
    session_file = None
    session_identifier_clean = session_identifier.strip()
    
    # Try exact filename match first
    if session_identifier_clean.endswith('.md'):
        session_file = sessions_dir / session_identifier_clean
        if not session_file.exists():
            session_file = None
    else:
        # Try to match by session number pattern (e.g., "003" or "Session-003")
        session_number = None
        if session_identifier_clean.isdigit():
            session_number = int(session_identifier_clean)
        elif session_identifier_clean.lower().startswith('session-'):
            # Extract number from "Session-003" or "session-003"
            match = re.search(r'(\d+)', session_identifier_clean)
            if match:
                session_number = int(match.group(1))
        
        # Search for matching session file
        pattern = re.compile(r'^Session-(\d+)-', re.IGNORECASE)
        for file in sessions_dir.iterdir():
            if file.is_file() and file.name.endswith('.md'):
                match = pattern.match(file.name)
                if match:
                    file_session_num = int(match.group(1))
                    if session_number is not None and file_session_num == session_number:
                        session_file = file
                        break
                    elif session_identifier_clean.lower() in file.name.lower():
                        # Partial match on identifier
                        session_file = file
                        break
    
    if session_file is None or not session_file.exists():
        raise ValueError(f"Session '{session_identifier}' not found in campaign '{campaign_name}'")
    
    # Parse FGU log
    try:
        events = parse_fgu_chat_log(log_path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise ValueError(f"Failed to parse FGU log: {e}")
    
    if not events:
        raise ValueError("No events found in FGU log file")
    
    # Backup the session note using history system
    from pantheon.conditor import HistoryManager
    history_manager = HistoryManager()
    history_manager.backup_note(session_file)
    
    # Read existing content
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            existing_content = f.read()
    except (PermissionError, OSError) as e:
        raise OSError(f"Failed to read session note: {e}")
    
    # Check if FGU log section already exists
    fgu_section_header = "## Fantasy Grounds Log"
    if fgu_section_header in existing_content:
        # Append to existing section
        # Find the end of the existing FGU section
        section_start = existing_content.find(fgu_section_header)
        # Find the next ## header or end of file
        next_section_match = re.search(r'\n## ', existing_content[section_start + len(fgu_section_header):])
        if next_section_match:
            insert_pos = section_start + len(fgu_section_header) + next_section_match.start()
        else:
            insert_pos = len(existing_content)
        
        # Insert new events before the next section
        new_content = existing_content[:insert_pos] + "\n"
    else:
        # Append new section at the end
        new_content = existing_content.rstrip() + "\n\n" + fgu_section_header + "\n"
        insert_pos = len(new_content)
    
    # Format events for markdown
    event_lines = []
    for event in events:
        time_str = event.timestamp.strftime("%H:%M:%S")
        
        if event.is_roll and event.roll_expression and event.roll_result is not None:
            # Format dice roll
            event_lines.append(f"- [{time_str}] {event.speaker}: rolled [{event.roll_expression}] = {event.roll_result}")
        else:
            # Format regular message
            event_lines.append(f"- [{time_str}] {event.speaker}: {event.message}")
    
    # Append events
    new_content = new_content + "\n".join(event_lines) + "\n"
    
    # If we inserted in the middle, add the rest of the content
    if fgu_section_header in existing_content and insert_pos < len(existing_content):
        new_content = new_content + existing_content[insert_pos:]
    
    # Write updated content
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(new_content)
    except (PermissionError, OSError) as e:
        raise OSError(f"Failed to write session note: {e}")
    
    return session_file

