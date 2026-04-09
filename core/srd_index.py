"""
SRD Index module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.occator.srd_index` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.srd_index` will
continue to work, but new code should import from `pantheon.occator` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.occator.srd_index import (
    extract_first_paragraph,
    extract_content_sample,
    extract_frontmatter,
    extract_inline_tags,
    build_srd_index,
    search_srd_index,
    search_index,
    cmd_srd_index,
    cmd_search_srd,
)

__all__ = [
    "extract_first_paragraph",
    "extract_content_sample",
    "extract_frontmatter",
    "extract_inline_tags",
    "build_srd_index",
    "search_srd_index",
    "search_index",
    "cmd_srd_index",
    "cmd_search_srd",
]
