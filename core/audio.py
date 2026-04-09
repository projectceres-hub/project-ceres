"""
Audio module for Project Ceres.

Provides generic audio transcription utilities and voice command handling.
This is a scaffold module for future audio transcription features.

**Note:** Session-specific audio functions (transcribe_audio, attach_transcript_to_session)
have moved to `pantheon.messor.audio_session` as part of the Pantheon architecture.
This module retains generic utilities like attach_transcript_to_note and handle_spoken_command.

Future implementations may integrate:
- OpenAI Whisper API for transcription
- Discord bot integration for capturing voice channel transcripts
- Local microphone recording and transcription
- File-based audio processing (MP3, WAV, etc.)
"""

from pathlib import Path
from typing import TYPE_CHECKING

# Re-export Transcript and transcribe_audio from Messor for backward compatibility
from pantheon.messor.audio_session import Transcript, transcribe_audio

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


def attach_transcript_to_note(note_path: Path, transcript: Transcript) -> None:
    """
    Attach a transcript to a markdown note.
    
    Appends the transcript text to the end of the note with a formatted heading
    and metadata. If the note doesn't exist, it will be created.
    
    Future enhancements may include:
    - Detecting and preserving existing transcript sections
    - Adding YAML frontmatter fields for transcript metadata
    - Formatting with timestamps if available
    - Speaker labels if multiple speakers detected
    
    Args:
        note_path: Path to the markdown note file
        transcript: Transcript object to attach
        
    Raises:
        PermissionError: If the note file cannot be written
        OSError: If file system operations fail
    """
    # Read existing note content if it exists
    existing_content = ""
    if note_path.exists():
        try:
            with open(note_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        except PermissionError as e:
            print(f"Error: Permission denied reading note '{note_path}': {e}")
            print("Hint: Check that you have read permissions for the note file.")
            raise
        except OSError as e:
            print(f"Error: Failed to read note '{note_path}': {e}")
            print("Hint: Check that the file exists and is accessible.")
            raise
    
    # Prepare transcript section
    transcript_section = "\n\n## Transcript\n\n"
    
    # Add metadata if available
    if transcript.metadata:
        transcript_section += "**Metadata:**\n"
        for key, value in transcript.metadata.items():
            transcript_section += f"- {key}: {value}\n"
        transcript_section += "\n"
    
    # Add source and timestamp
    transcript_section += f"**Source:** {transcript.source}\n"
    transcript_section += f"**Created:** {transcript.created_at.isoformat()}\n\n"
    
    # Add transcript text
    transcript_section += transcript.text
    
    # Append to existing content
    new_content = existing_content.rstrip() + transcript_section
    
    # Write back to file
    try:
        # Ensure parent directory exists
        note_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    except PermissionError as e:
        print(f"Error: Permission denied writing to note '{note_path}': {e}")
        print("Hint: Check that you have write permissions for the note file.")
        raise
    except OSError as e:
        print(f"Error: Failed to write note '{note_path}': {e}")
        print("Hint: Check that the directory exists and is writable.")
        raise
    except Exception as e:
        print(f"Error: Unexpected error writing transcript to note: {e}")
        raise RuntimeError(f"Failed to attach transcript: {e}")


def handle_spoken_command(transcript: Transcript, config: "Config") -> None:
    """
    High-level entry point for voice commands.
    
    Parses transcript text as a spoken command and executes it if recognized.
    This function wires transcript text into the command system without
    performing any audio recording or external API calls.
    
    If the transcript text matches a known command pattern, it will be parsed
    and executed using the same command handlers as the CLI. If no pattern
    matches, the function silently ignores it (no error is raised).
    
    Args:
        transcript: Transcript object containing the spoken text
        config: Config object containing command registry and application state
        
    Note:
        This function does NOT record audio or call external APIs. It only
        processes already-transcribed text. Audio recording and transcription
        should be handled by other functions (e.g., transcribe_audio).
    """
    if not transcript.text or not transcript.text.strip():
        return
    
    # Import here to avoid circular import
    from core.voice_commands import parse_spoken_command, execute_parsed_command
    
    # Parse the transcript text as a command
    parsed = parse_spoken_command(transcript.text)
    
    if parsed is None:
        # Not a recognized command, silently ignore
        return
    
    # Execute the parsed command
    try:
        execute_parsed_command(parsed, config)
    except Exception as e:
        # Log errors but don't raise (voice commands should be non-blocking)
        print(f"Error executing voice command '{parsed.command_name}': {e}")

