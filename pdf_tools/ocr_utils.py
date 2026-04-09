"""
OCR utilities module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.imporcitor.pdf_tools.ocr_utils` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `pdf_tools.ocr_utils` will
continue to work, but new code should import from `pantheon.imporcitor.pdf_tools` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.imporcitor.pdf_tools.ocr_utils import (
    OCRProcessor,
    extract_text_with_ocr,
)

__all__ = [
    "OCRProcessor",
    "extract_text_with_ocr",
]
