"""
Text cleaning utilities module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.imporcitor.pdf_tools.cleaning` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `pdf_tools.cleaning` will
continue to work, but new code should import from `pantheon.imporcitor.pdf_tools` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.imporcitor.pdf_tools.cleaning import (
    TextCleaner,
    normalize_text,
    sanitize_filename,
    remove_duplicate_lines,
    clean_markdown,
)

__all__ = [
    "TextCleaner",
    "normalize_text",
    "sanitize_filename",
    "remove_duplicate_lines",
    "clean_markdown",
]
