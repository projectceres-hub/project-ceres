"""
Obarator domain for Project Ceres.

This domain handles tags and metadata structure - tracing the first ploughing
that establishes the organizational foundation for notes and content.

Public API exports from the tags module.
"""

from .tags import (
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

