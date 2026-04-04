"""
Convector domain for Project Ceres.

This domain handles data transport between Ceres core (Promitor, Messor, etc.)
and external systems like Discord bots, webhooks, and other integrations.

Public API exports from the session package and voice commands modules.
"""

from .session_package import (
    SessionEventPackage,
    build_session_event_package,
    session_event_to_dict,
    write_session_event_json,
)
from .voice_commands import (
    VoiceCommand,
    VoiceCommandType,
    VoiceCommandDict,
    VOICE_COMMAND_INBOX,
    ensure_voice_command_inbox,
    voice_command_to_dict,
    voice_command_from_dict,
    write_voice_command_to_inbox,
    load_voice_command_from_path,
)
from .voice_processor import (
    process_voice_command,
    process_voice_command_file,
    process_all_voice_commands,
    get_processed_dir,
    iter_voice_command_files,
)
from .text_command_parser import parse_text_to_voice_command
from .transcript_parser import (
    iter_vero_lines,
    extract_voice_commands_from_transcript_text,
    extract_voice_commands_from_transcript_file,
    enqueue_voice_commands,
    transcript_to_inbox_from_file,
)
from .wake_words import (
    WAKE_WORDS,
    is_wake_word,
    find_wake_word_prefix,
    strip_wake_word,
)
from .voice_pipeline import (
    audio_file_to_voice_commands,
    audio_file_to_inbox,
)

__all__ = [
    "SessionEventPackage",
    "build_session_event_package",
    "session_event_to_dict",
    "write_session_event_json",
    "VoiceCommand",
    "VoiceCommandType",
    "VoiceCommandDict",
    "VOICE_COMMAND_INBOX",
    "ensure_voice_command_inbox",
    "voice_command_to_dict",
    "voice_command_from_dict",
    "write_voice_command_to_inbox",
    "load_voice_command_from_path",
    "process_voice_command",
    "process_voice_command_file",
    "process_all_voice_commands",
    "get_processed_dir",
    "iter_voice_command_files",
    "parse_text_to_voice_command",
    "iter_vero_lines",
    "extract_voice_commands_from_transcript_text",
    "extract_voice_commands_from_transcript_file",
    "enqueue_voice_commands",
    "transcript_to_inbox_from_file",
    "WAKE_WORDS",
    "is_wake_word",
    "find_wake_word_prefix",
    "strip_wake_word",
    "audio_file_to_voice_commands",
    "audio_file_to_inbox",
]

