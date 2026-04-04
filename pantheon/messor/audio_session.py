"""
Audio session module for Project Ceres.

Provides functionality for transcribing audio and attaching transcripts to
session notes in campaigns.

This module is part of the Messor domain in the Pantheon architecture,
responsible for collecting session data from various sources.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


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


def _load_openai_api_key() -> Optional[str]:
    """
    Resolve the OpenAI API key from environment or variables.env.

    Priority:
      1. OPENAI_API_KEY environment variable (already set in the process)
      2. OPENAI_API_KEY= line in variables.env (next to the project root)
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key

    # Walk up from this file to find variables.env
    here = Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
        env_file = parent / "variables.env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("OPENAI_API_KEY="):
                    return stripped.split("=", 1)[1].strip()
    return None


def transcribe_audio(file: Path) -> Transcript:
    """
    Transcribe an audio file to text using the OpenAI Whisper API.

    Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm.
    The Discord panel sends 48 kHz 16-bit stereo WAV files.

    Args:
        file: Path to the audio file to transcribe.

    Returns:
        Transcript with the recognised text, source="whisper-api", and
        metadata containing the file name and duration estimate.

    Raises:
        FileNotFoundError: If the audio file does not exist.
        ValueError: If the path is not a file.
        RuntimeError: If the openai package is not installed, or if the
                      OPENAI_API_KEY cannot be found.

    Note:
        Falls back gracefully to a stub transcript when the openai package
        is not installed, so the rest of the pipeline keeps running during
        development without the dependency.
    """
    if not file.exists():
        raise FileNotFoundError(f"Audio file not found: {file}")
    if not file.is_file():
        raise ValueError(f"Path is not a file: {file}")

    # ── Attempt real Whisper transcription ────────────────────────────────
    try:
        import openai as _openai
    except ImportError:
        # openai not installed — return placeholder so callers don't crash
        return Transcript(
            text="(transcription not yet implemented)",
            source="file",
            created_at=datetime.now(),
            metadata={"file_path": str(file), "file_name": file.name, "status": "no-openai-package"},
        )

    api_key = _load_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "OpenAI API key not found.\n"
            "Add  OPENAI_API_KEY=<key>  to variables.env."
        )

    client = _openai.OpenAI(api_key=api_key)

    with open(file, "rb") as audio_fh:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_fh,
            response_format="text",
        )

    # response_format="text" returns a plain string
    text: str = response if isinstance(response, str) else getattr(response, "text", "")

    return Transcript(
        text=text.strip(),
        source="whisper-api",
        created_at=datetime.now(),
        metadata={
            "file_path": str(file),
            "file_name": file.name,
            "model": "whisper-1",
        },
    )


def attach_transcript_to_session(
    campaign_name: str,
    session_identifier: str,
    transcript: Transcript,
    config: "Config",
) -> Path:
    """
    Attach a transcript to a session note in a campaign.
    
    Locates the campaign folder under Campaigns/<CampaignName>/ and finds the
    session note in Sessions/ matching session_identifier (e.g., "Session-003"
    prefix or exact filename). Uses history/backup before modifying the note.
    Appends a section with the transcript content.
    
    Args:
        campaign_name: Name of the campaign
        session_identifier: Session identifier (e.g., "003", "Session-003", or filename)
        transcript: Transcript object to attach
        config: Config object containing vault information
        
    Returns:
        Path to the modified session note
        
    Raises:
        ValueError: If campaign not found, session not found
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
    
    # Check if transcript section already exists
    transcript_section_header = "## Transcript"
    if transcript_section_header in existing_content:
        # Append to existing section
        # Find the end of the existing transcript section
        section_start = existing_content.find(transcript_section_header)
        # Find the next ## header or end of file
        next_section_match = re.search(r'\n## ', existing_content[section_start + len(transcript_section_header):])
        if next_section_match:
            insert_pos = section_start + len(transcript_section_header) + next_section_match.start()
        else:
            insert_pos = len(existing_content)
        
        # Insert new transcript before the next section
        new_content = existing_content[:insert_pos] + "\n\n"
    else:
        # Append new section at the end
        new_content = existing_content.rstrip() + "\n\n" + transcript_section_header + "\n\n"
        insert_pos = len(new_content)
    
    # Format transcript for markdown
    transcript_lines = []
    
    # Add metadata if available
    if transcript.metadata:
        transcript_lines.append("**Metadata:**")
        for key, value in transcript.metadata.items():
            transcript_lines.append(f"- {key}: {value}")
        transcript_lines.append("")
    
    # Add source and timestamp
    transcript_lines.append(f"**Source:** {transcript.source}")
    transcript_lines.append(f"**Created:** {transcript.created_at.isoformat()}")
    transcript_lines.append("")
    
    # Add transcript text
    transcript_lines.append(transcript.text)
    
    # Append transcript
    new_content = new_content + "\n".join(transcript_lines) + "\n"
    
    # If we inserted in the middle, add the rest of the content
    if transcript_section_header in existing_content and insert_pos < len(existing_content):
        new_content = new_content + existing_content[insert_pos:]
    
    # Write updated content
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(new_content)
    except (PermissionError, OSError) as e:
        raise OSError(f"Failed to write session note: {e}")
    
    return session_file


def attach_audio_and_extract_commands_for_session(
    campaign_name: str,
    session_name: str,
    audio_path: Path,
    config: "Config",
) -> list[Path]:
    """
    Transcribe an audio file, attach the transcript to the session note,
    and enqueue any wake-word VoiceCommands discovered in the transcript.
    
    Args:
        campaign_name: Name of the campaign (used to locate session note)
        session_name: Name or identifier of the session
        audio_path: Path to the audio file for this session
        config: Config object containing vault information
        
    Returns:
        A list of Paths to the created VoiceCommand inbox files
        (may be empty if no commands found)
        
    Raises:
        FileNotFoundError: If the audio file does not exist
        ValueError: If campaign or session not found
        OSError: If file operations fail
        
    Note:
        - Uses transcribe_audio(...) to obtain a Transcript
        - Uses attach_transcript_to_session(...) to attach transcript
          text to the session note
        - Uses audio_file_to_voice_commands(...) and enqueue_voice_commands(...)
          to write VoiceCommands to the inbox
    """
    from pantheon.convector import (
        extract_voice_commands_from_transcript_text,
        enqueue_voice_commands,
    )
    
    # 1. Transcribe the audio file
    transcript = transcribe_audio(audio_path)
    
    # 2. Attach transcript to session note
    attach_transcript_to_session(
        campaign_name=campaign_name,
        session_identifier=session_name,
        transcript=transcript,
        config=config,
    )
    
    # 3. Extract VoiceCommands from transcript text
    commands = extract_voice_commands_from_transcript_text(transcript.text)
    
    # 4. Enqueue commands to inbox
    if not commands:
        return []
    
    inbox_paths = enqueue_voice_commands(commands)
    return inbox_paths