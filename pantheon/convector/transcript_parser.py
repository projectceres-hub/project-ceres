"""
Transcript Parser module for Project Ceres.

Provides functionality to extract VoiceCommands from plain text transcripts
by identifying lines that start with configured wake words (currently 'Veras'
and 'Chroma') and parsing them into structured command objects.

This module is part of the Convector domain in the Pantheon architecture,
responsible for extracting voice commands from transcript sources.
"""

from pathlib import Path
from typing import Iterable

from .voice_commands import VoiceCommand, write_voice_command_to_inbox
from .text_command_parser import parse_text_to_voice_command
from .wake_words import find_wake_word_prefix


def iter_wake_word_lines(lines: Iterable[str]) -> Iterable[str]:
    """
    Yield lines that start with one of the configured wake words
    (e.g., "Veras" or "Chroma") after leading whitespace is stripped.

    This function does not parse the commands; it only filters.

    Args:
        lines: Iterable of text lines to filter

    Yields:
        Lines that start with a configured wake word (case-insensitive) after
        stripping leading whitespace. The original line (with whitespace) is yielded.

    Example:
        >>> list(iter_wake_word_lines(["  Veras, add bookmark: test", "Regular line", "  chroma append note"]))
        ['  Veras, add bookmark: test', '  chroma append note']
    """
    for line in lines:
        stripped = line.lstrip()
        if find_wake_word_prefix(stripped) is not None:
            yield line


def extract_voice_commands_from_transcript_text(text: str) -> list[VoiceCommand]:
    """
    Given the full transcript text as a single string, split it into
    lines, filter down to those that start with configured wake words
    (currently 'Veras' and 'Chroma'), and parse each into a VoiceCommand
    using parse_text_to_voice_command().
    
    Args:
        text: Full transcript text as a single string
        
    Returns:
        A list of VoiceCommand objects (may be empty)
        
    Note:
        - Lines are split using text.splitlines()
        - Only lines starting with configured wake words (case-insensitive) are processed
        - Each matching line is parsed into a VoiceCommand
    """
    lines = text.splitlines()
    vero_lines = iter_wake_word_lines(lines)
    
    commands: list[VoiceCommand] = []
    for line in vero_lines:
        cmd = parse_text_to_voice_command(line)
        commands.append(cmd)
    
    return commands


def extract_voice_commands_from_transcript_file(path: Path) -> list[VoiceCommand]:
    """
    Read a transcript file from disk and extract all VoiceCommands
    from it by calling extract_voice_commands_from_transcript_text().
    
    Args:
        path: Path to the transcript file
        
    Returns:
        A list of VoiceCommand objects
        
    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read
        UnicodeDecodeError: If the file is not valid UTF-8
        
    Note:
        - File is read as UTF-8 text
        - Empty files return an empty list
    """
    content = path.read_text(encoding="utf-8")
    return extract_voice_commands_from_transcript_text(content)


def enqueue_voice_commands(commands: list[VoiceCommand]) -> list[Path]:
    """
    Given a list of VoiceCommand objects, write each one to the
    Convector inbox as JSON.
    
    Args:
        commands: List of VoiceCommand objects to enqueue
        
    Returns:
        A list of Paths to the created JSON files
        
    Note:
        - Each command is written to a separate JSON file in the inbox
        - File names are generated based on timestamp and command type
        - Returns paths in the order commands were processed
    """
    paths: list[Path] = []
    for cmd in commands:
        path = write_voice_command_to_inbox(cmd)
        paths.append(path)
    return paths


def transcript_to_inbox_from_file(path: Path) -> list[Path]:
    """
    Convenience function:
    - Read transcript from a file.
    - Extract VoiceCommands.
    - Enqueue them into the inbox.
    
    Args:
        path: Path to the transcript file
        
    Returns:
        A list of paths to the created inbox files
        
    Raises:
        FileNotFoundError: If the transcript file does not exist
        PermissionError: If the file cannot be read or inbox cannot be written
        
    Note:
        - If no wake-word commands are found, returns an empty list
        - Each extracted command is written to a separate JSON file
    """
    commands = extract_voice_commands_from_transcript_file(path)
    return enqueue_voice_commands(commands)

