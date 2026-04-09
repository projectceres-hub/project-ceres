"""
Search index module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.occator.search_index` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.search_index` will
continue to work, but new code should import from `pantheon.occator` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.occator.search_index import (
    extract_frontmatter,
    extract_inline_tags,
    build_search_index,
    save_index,
    load_index,
    search_index,
    cmd_search,
)

__all__ = [
    "extract_frontmatter",
    "extract_inline_tags",
    "build_search_index",
    "save_index",
    "load_index",
    "search_index",
    "cmd_search",
]
