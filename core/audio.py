"""
Audio module for Project Ceres.

Provides functionality for audio transcription and attaching transcripts to notes.
This is a scaffold module for future audio transcription features.

Future implementations may integrate:
- OpenAI Whisper API for transcription
- Discord bot integration for capturing voice channel transcripts
- Local microphone recording and transcription
- File-based audio processing (MP3, WAV, etc.)
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


@dataclass
class Transcript:
    """
    Represents a transcribed audio recording.
    
    Attributes:
        text: The transcribed text content
        source: Source of the audio (e.g., "discord", "local-mic", "file")
        created_at: Timestamp when the transcript was created
        metadata: Optional dictionary of additional metadata (e.g., speaker names, duration, file path)
    """
    text: str
    source: str
    created_at: datetime
    metadata: Optional[Dict[str, str]] = None


def transcribe_audio(file: Path) -> Transcript:
    """
    Transcribe an audio file to text.
    
    This is a placeholder implementation. Future implementations should:
    - Support common audio formats (MP3, WAV, OGG, M4A, etc.)
    - Integrate with transcription services (OpenAI Whisper, AssemblyAI, etc.)
    - Handle long audio files with chunking
    - Support multiple speakers (speaker diarization)
    - Extract metadata (duration, sample rate, channels)
    
    Args:
        file: Path to the audio file to transcribe
        
    Returns:
        Transcript object containing the transcribed text and metadata
        
    Raises:
        NotImplementedError: This is a placeholder implementation
        FileNotFoundError: If the audio file does not exist
        PermissionError: If the audio file cannot be read
    """
    if not file.exists():
        raise FileNotFoundError(f"Audio file not found: {file}")
    
    if not file.is_file():
        raise ValueError(f"Path is not a file: {file}")
    
    # Placeholder implementation
    # TODO: Integrate real transcription service (e.g., OpenAI Whisper API)
    # Example future implementation:
    #   import openai
    #   with open(file, "rb") as audio_file:
    #       transcript_response = openai.Audio.transcribe("whisper-1", audio_file)
    #       text = transcript_response["text"]
    
    # Return dummy transcript for now
    return Transcript(
        text="(transcription not yet implemented)",
        source="file",
        created_at=datetime.now(),
        metadata={
            "file_path": str(file),
            "file_name": file.name,
            "status": "placeholder"
        }
    )


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

