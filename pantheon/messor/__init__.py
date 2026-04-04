"""
Messor domain for Project Ceres.

This domain handles session harvesting - collecting session data from various
sources like FGU logs, Discord logs, and audio transcripts, and integrating
them into session notes.

Public API exports from the session harvesting modules.
"""

from .fgu import (
    FGUEvent,
    parse_fgu_chat_log,
    attach_fgu_log_to_session,
)
from .audio_session import (
    Transcript,
    transcribe_audio,
    attach_transcript_to_session,
    attach_audio_and_extract_commands_for_session,
)

__all__ = [
    # FGU integration
    "FGUEvent",
    "parse_fgu_chat_log",
    "attach_fgu_log_to_session",
    # Audio/transcript integration
    "Transcript",
    "transcribe_audio",
    "attach_transcript_to_session",
    "attach_audio_and_extract_commands_for_session",
]

