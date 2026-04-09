"""
Tags module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.obarator.tags` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.tags` will
continue to work, but new code should import from `pantheon.obarator` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.obarator.tags import (
    extract_frontmatter,
    extract_inline_tags,
    get_tags_for_note,
    add_tag,
    remove_tag,
    list_all_tags,
    get_all_tags,
)

__all__ = [
    "extract_frontmatter",
    "extract_inline_tags",
    "get_tags_for_note",
    "add_tag",
    "remove_tag",
    "list_all_tags",
    "get_all_tags",
]
