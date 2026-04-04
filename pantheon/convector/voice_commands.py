"""
Voice Command module for Project Ceres.

Provides data structures and utilities for handling voice-derived commands
destined for Ceres. This module defines the contract for how voice commands
arrive and are stored in the inbox.

This module is part of the Convector domain in the Pantheon architecture,
responsible for data transport between external voice systems and Ceres core.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict


VoiceCommandType = Literal[
    "add_bookmark",
    "append_note",
    "add_session_marker",
    "set_flag",
    "custom"
]


@dataclass
class VoiceCommand:
    """
    Represents a single voice-derived command destined for Ceres.

    Attributes:
        type: High-level command type, e.g. "add_bookmark".
        session_id: Optional session identifier (campaign/session string).
        note_path: Optional explicit note path to target.
        timestamp: When the command was spoken (or approximated).
        text: Original raw text of the command (e.g. "Ceres, add bookmark: ...").
        payload: Structured arguments for the command,
                 e.g. {"label": "dragon lands on the tower"}.
    """
    type: VoiceCommandType
    session_id: str | None
    note_path: str | None
    timestamp: datetime
    text: str
    payload: dict[str, Any]


class VoiceCommandDict(TypedDict):
    """
    TypedDict for JSON-serialized VoiceCommand data.
    
    This structure matches the JSON format used for serialization/deserialization.
    The timestamp field is stored as an ISO8601 string in JSON.
    """
    type: VoiceCommandType
    session_id: str | None
    note_path: str | None
    timestamp: str  # ISO8601
    text: str
    payload: dict[str, Any]


VOICE_COMMAND_INBOX = Path("inbox/voice_commands")


def ensure_voice_command_inbox() -> Path:
    """
    Ensure the voice command inbox directory exists and return it.
    
    Returns:
        Path to the voice command inbox directory
        
    Note:
        Creates parent directories if they don't exist.
    """
    VOICE_COMMAND_INBOX.mkdir(parents=True, exist_ok=True)
    return VOICE_COMMAND_INBOX


def voice_command_to_dict(cmd: VoiceCommand) -> VoiceCommandDict:
    """
    Convert a VoiceCommand into a JSON-serializable dict.
    
    Args:
        cmd: VoiceCommand to convert
        
    Returns:
        Dictionary with timestamp converted to ISO8601 string
        
    Note:
        - timestamp is formatted as ISO8601 string
        - All other fields are preserved as-is
    """
    return {
        "type": cmd.type,
        "session_id": cmd.session_id,
        "note_path": cmd.note_path,
        "timestamp": cmd.timestamp.isoformat(),
        "text": cmd.text,
        "payload": cmd.payload,
    }


def voice_command_from_dict(data: VoiceCommandDict) -> VoiceCommand:
    """
    Convert a dict (e.g. loaded from JSON) into a VoiceCommand.
    
    Args:
        data: Dictionary containing voice command data
        
    Returns:
        VoiceCommand with timestamp parsed from ISO8601 string
        
    Raises:
        ValueError: If timestamp cannot be parsed from ISO8601 format
        
    Note:
        - timestamp is parsed from ISO8601 string using datetime.fromisoformat()
        - All other fields are used as-is from the dictionary
    """
    return VoiceCommand(
        type=data["type"],
        session_id=data["session_id"],
        note_path=data["note_path"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        text=data["text"],
        payload=data["payload"],
    )


def write_voice_command_to_inbox(cmd: VoiceCommand) -> Path:
    """
    Serialize the VoiceCommand to a JSON file in the inbox.
    
    The filename is based on ISO timestamp and command type, e.g.:
        2025-12-02T20-13-00Z_add_bookmark.json
    
    Args:
        cmd: VoiceCommand to serialize and write
        
    Returns:
        Path to the written JSON file
        
    Raises:
        OSError: If the file cannot be written (permission denied, disk full, etc.)
        
    Note:
        - Creates inbox directory if it doesn't exist
        - Replaces characters not suitable for filenames (':' etc.) with '-'
        - Uses UTF-8 encoding
        - Pretty-prints JSON with 2-space indentation
    """
    inbox = ensure_voice_command_inbox()
    
    # Generate filename from timestamp and type
    # Replace ':' with '-' and remove microseconds if present
    timestamp_str = cmd.timestamp.isoformat().replace(":", "-")
    # Remove microseconds if present (format: YYYY-MM-DDTHH-MM-SS.ffffff)
    if "." in timestamp_str:
        timestamp_str = timestamp_str.split(".")[0]
    
    # Ensure filename is safe by replacing any remaining problematic characters
    safe_timestamp = timestamp_str.replace("/", "-").replace("\\", "-")
    
    filename = f"{safe_timestamp}_{cmd.type}.json"
    file_path = inbox / filename
    
    # Serialize to JSON
    data = voice_command_to_dict(cmd)
    file_path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )
    
    return file_path


def load_voice_command_from_path(path: Path) -> VoiceCommand:
    """
    Load a VoiceCommand from a JSON file at the given path.
    
    Args:
        path: Path to the JSON file containing voice command data
        
    Returns:
        VoiceCommand parsed from the JSON file
        
    Raises:
        FileNotFoundError: If the file does not exist
        json.JSONDecodeError: If the file contains invalid JSON
        ValueError: If the JSON structure is invalid or timestamp cannot be parsed
        
    Note:
        - Uses UTF-8 encoding
        - Validates that the JSON matches VoiceCommandDict structure
    """
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    
    # Validate that we have the required fields
    required_fields = {"type", "timestamp", "text", "payload"}
    if not all(field in data for field in required_fields):
        missing = required_fields - set(data.keys())
        raise ValueError(f"Missing required fields in JSON: {missing}")
    
    # Convert to VoiceCommandDict and then to VoiceCommand
    return voice_command_from_dict(data)

