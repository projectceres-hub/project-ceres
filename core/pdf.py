"""
PDF conversion module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.imporcitor.pdf_core` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.pdf` will
continue to work, but new code should import from `pantheon.imporcitor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.imporcitor.pdf_core import (
    convert_pdf_to_md,
    extract_text_pages,
    pages_to_blocks,
    apply_map_rules,
    render_frontmatter,
    sanitize_filename,
)

__all__ = [
    "convert_pdf_to_md",
    "extract_text_pages",
    "pages_to_blocks",
    "apply_map_rules",
    "render_frontmatter",
    "sanitize_filename",
]
