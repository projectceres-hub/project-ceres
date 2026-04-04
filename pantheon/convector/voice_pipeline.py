"""
Voice command pipeline helpers for Project Ceres.

Provides functionality to transcribe audio files and extract VoiceCommands
from the resulting transcripts using the configured wake words.

This module is part of the Convector domain in the Pantheon architecture,
responsible for the audio-file → transcript → VoiceCommand pipeline.
"""

from pathlib import Path
from typing import List

from pantheon.messor.audio_session import transcribe_audio
from .transcript_parser import (
    extract_voice_commands_from_transcript_text,
    enqueue_voice_commands,
)
from .voice_commands import VoiceCommand


def audio_file_to_voice_commands(audio_path: Path) -> List[VoiceCommand]:
    """
    Transcribe an audio file and extract VoiceCommands from its text
    using the configured wake words (e.g., 'Veras', 'Chroma').
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        A list of VoiceCommand objects (may be empty)
        
    Raises:
        FileNotFoundError: If the audio file does not exist
        PermissionError: If the audio file cannot be read
        NotImplementedError: If transcription is not yet implemented
        (transcribe_audio is currently a placeholder)
        
    Note:
        - Uses pantheon.messor.audio_session.transcribe_audio(...) to
          obtain a Transcript.
        - Then uses extract_voice_commands_from_transcript_text() to
          parse wake-word commands.
        - Currently returns empty list if transcription is not implemented
          (placeholder returns "(transcription not yet implemented)").
    """
    transcript = transcribe_audio(audio_path)
    
    # Check if transcription is actually implemented
    # (placeholder returns "(transcription not yet implemented)")
    if transcript.text == "(transcription not yet implemented)":
        return []
    
    commands = extract_voice_commands_from_transcript_text(transcript.text)
    return commands


def audio_file_to_inbox(audio_path: Path) -> List[Path]:
    """
    Transcribe an audio file, extract VoiceCommands, and enqueue them
    into the VoiceCommand inbox.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        A list of Paths to the created inbox files
        
    Raises:
        FileNotFoundError: If the audio file does not exist
        PermissionError: If the audio file cannot be read or inbox cannot be written
        NotImplementedError: If transcription is not yet implemented
        
    Note:
        - If no wake-word commands are found, returns an empty list.
        - Each extracted command is written to a separate JSON file in the inbox.
    """
    commands = audio_file_to_voice_commands(audio_path)
    if not commands:
        return []
    
    return enqueue_voice_commands(commands)

