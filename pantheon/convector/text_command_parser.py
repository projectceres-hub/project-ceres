"""
Text Command Parser module for Project Ceres.

Provides functionality to parse plain English text commands (spoken-style text)
into structured VoiceCommand objects.

This module is part of the Convector domain in the Pantheon architecture,
responsible for converting natural language commands into structured command objects.

Uses the configured wake words (currently 'Veras' and 'Chroma') via the
wake_words helper module.
"""

import re
from datetime import datetime, timezone

from .voice_commands import VoiceCommand, VoiceCommandType
from .wake_words import strip_wake_word


def parse_text_to_voice_command(text: str) -> VoiceCommand:
    """
    Given a spoken-style text command, extract command type, payload fields,
    optional session_id or note_path, and return a VoiceCommand object.
    
    Expected basic formats:
        - "Veras, add bookmark: <label>"
        - "Veras add bookmark <label>"
        - "Veras, append note <note_path>: <content>"
        - "Veras, add session marker: <label>"
    
    Configured wake words (currently 'Veras' and 'Chroma') are accepted
    (case-insensitive). "Chroma" can be used in place of "Veras" in any
    of the above formats.
    
    If no wake word is found at the front,
    treat the entire text as a no-op "custom" command.
    
    Args:
        text: Raw text command string
        
    Returns:
        VoiceCommand object with parsed fields
        
    Note:
        - Command detection is case-insensitive
        - Timestamp is set to current UTC time
        - If wake word is missing, returns type="custom"
    """
    original_text = text.strip()
    
    # Use wake_words helper to detect and strip wake word
    wake_word, remainder = strip_wake_word(original_text)
    
    if wake_word is None:
        # No wake word found, return custom command
        return VoiceCommand(
            type="custom",
            session_id=None,
            note_path=None,
            timestamp=datetime.now(timezone.utc),
            text=original_text,
            payload={"text": original_text}
        )
    
    # Parse remainder for command types
    remainder_lower = remainder.lower()
    
    # Pattern 1: "add bookmark: <label>" or "add bookmark <label>"
    bookmark_pattern = r'^add\s+bookmark\s*:?\s*(.+)$'
    match = re.match(bookmark_pattern, remainder_lower, re.IGNORECASE)
    if match:
        label = match.group(1).strip()
        return VoiceCommand(
            type="add_bookmark",
            session_id=None,
            note_path=None,
            timestamp=datetime.now(timezone.utc),
            text=original_text,
            payload={"label": label}
        )
    
    # Pattern 2: "append note <note_path>: <content>" or "append note <note_path> <content>"
    append_pattern = r'^append\s+note\s+([^:]+?)\s*:?\s*(.+)$'
    match = re.match(append_pattern, remainder_lower, re.IGNORECASE)
    if match:
        note_path = match.group(1).strip()
        content = match.group(2).strip()
        return VoiceCommand(
            type="append_note",
            session_id=None,
            note_path=note_path,
            timestamp=datetime.now(timezone.utc),
            text=original_text,
            payload={"text": content}
        )
    
    # Pattern 3: "add session marker: <label>" or "add session marker <label>"
    marker_pattern = r'^add\s+session\s+marker\s*:?\s*(.+)$'
    match = re.match(marker_pattern, remainder_lower, re.IGNORECASE)
    if match:
        label = match.group(1).strip()
        return VoiceCommand(
            type="add_session_marker",
            session_id=None,
            note_path=None,
            timestamp=datetime.now(timezone.utc),
            text=original_text,
            payload={"label": label}
        )
    
    # If no pattern matches, return custom command
    return VoiceCommand(
        type="custom",
        session_id=None,
        note_path=None,
        timestamp=datetime.now(timezone.utc),
        text=original_text,
        payload={"text": original_text}
    )

