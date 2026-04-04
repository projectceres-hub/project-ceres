"""
Voice commands module for Project Ceres.

Provides functionality to parse and execute spoken/natural-language commands
from audio transcripts. This module bridges voice input to the CLI command system.
"""

import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


@dataclass
class ParsedCommand:
    """
    Represents a parsed spoken command.
    
    Attributes:
        raw_text: The original raw text that was parsed
        command_name: The canonical command name (e.g., "read", "create-session")
        args: List of command arguments as strings
    """
    raw_text: str
    command_name: str
    args: list[str]


def parse_spoken_command(text: str) -> Optional[ParsedCommand]:
    """
    Parse a natural-language or semi-structured spoken command into a ParsedCommand.
    
    Implements a simple pattern-based parser that supports common command phrases:
    - "read note <name>" -> command: "read", args: ["<name>"]
    - "create session <campaign> <title>" -> command: "session-create", args: ["<campaign>", "<title>"]
    - "search srd <query>" -> command: "search-srd", args: ["<query>"]
    - "tag note <note> with <tag>" -> command: "tag-add", args: ["<note>", "<tag>"]
    
    Patterns are matched case-insensitively and support variations in phrasing.
    If no known pattern is matched, returns None.
    
    Args:
        text: The spoken command text to parse
        
    Returns:
        ParsedCommand if a pattern matches, None otherwise
    """
    if not text or not text.strip():
        return None
    
    text_lower = text.strip().lower()
    
    # Pattern: "read note <name>" or "read <name>"
    match = re.match(r'^read\s+(?:note\s+)?(.+)$', text_lower)
    if match:
        note_name = match.group(1).strip()
        return ParsedCommand(
            raw_text=text,
            command_name="read",
            args=[note_name]
        )
    
    # Pattern: "create session <campaign> <title>" or "create session for <campaign> <title>"
    match = re.match(r'^create\s+session\s+(?:for\s+)?(.+?)\s+(.+)$', text_lower)
    if match:
        campaign = match.group(1).strip()
        title = match.group(2).strip()
        return ParsedCommand(
            raw_text=text,
            command_name="session-create",
            args=[campaign, title]
        )
    
    # Pattern: "search srd <query>" or "search srd for <query>"
    match = re.match(r'^search\s+srd\s+(?:for\s+)?(.+)$', text_lower)
    if match:
        query = match.group(1).strip()
        return ParsedCommand(
            raw_text=text,
            command_name="search-srd",
            args=[query]
        )
    
    # Pattern: "tag note <note> with <tag>" or "tag <note> with <tag>"
    match = re.match(r'^tag\s+(?:note\s+)?(.+?)\s+with\s+(.+)$', text_lower)
    if match:
        note_name = match.group(1).strip()
        tag = match.group(2).strip()
        return ParsedCommand(
            raw_text=text,
            command_name="tag-add",
            args=[note_name, tag]
        )
    
    # Pattern: "list notes" or "list all notes"
    match = re.match(r'^list\s+(?:all\s+)?notes?$', text_lower)
    if match:
        return ParsedCommand(
            raw_text=text,
            command_name="list",
            args=[]
        )
    
    # Pattern: "create campaign <name>" or "create new campaign <name>"
    match = re.match(r'^create\s+(?:new\s+)?campaign\s+(.+)$', text_lower)
    if match:
        campaign_name = match.group(1).strip()
        return ParsedCommand(
            raw_text=text,
            command_name="campaign-create",
            args=[campaign_name]
        )
    
    # Pattern: "add pc <name> to <campaign>" or "add player <name> to <campaign>"
    match = re.match(r'^add\s+(?:pc|player)\s+(.+?)\s+to\s+(.+)$', text_lower)
    if match:
        pc_name = match.group(1).strip()
        campaign = match.group(2).strip()
        return ParsedCommand(
            raw_text=text,
            command_name="campaign-add-pc",
            args=[campaign, pc_name]
        )
    
    # Pattern: "help" or "show help"
    match = re.match(r'^(?:show\s+)?help$', text_lower)
    if match:
        return ParsedCommand(
            raw_text=text,
            command_name="help",
            args=[]
        )
    
    # No pattern matched
    return None


def execute_parsed_command(parsed: ParsedCommand, config: "Config") -> None:
    """
    Execute a ParsedCommand by dispatching to the underlying CLI command handlers.
    
    Uses the same command registry and handlers as the CLI in assistant.py.
    This ensures voice commands execute the same logic as typed commands.
    
    Args:
        parsed: ParsedCommand object to execute
        config: Config object containing command registry and application state
        
    Raises:
        KeyError: If the command_name is not found in the command registry
        Exception: Any exception raised by the command handler
    """
    # Import here to avoid circular import
    from assistant import run_command
    
    # Join args into a single string (as CLI commands expect)
    args_str = " ".join(parsed.args) if parsed.args else ""
    
    # Use default error handler (prints to console)
    run_command(parsed.command_name, args_str, config)

