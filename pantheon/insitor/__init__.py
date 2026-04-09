"""
Insitor domain for Project Ceres.

This domain handles note creation and seeding - planting new content in the
vault from templates, generating initial NPC/session/location notes, and
seeding structured information into campaigns.

Public API exports from the note_creator module.
"""

from .note_creator import (
    NoteSpec,
    create_note,
    safe_filename,
    resolve_unique_path,
)

__all__ = [
    "NoteSpec",
    "create_note",
    "safe_filename",
    "resolve_unique_path",
]
