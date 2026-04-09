"""
PDF Tools package for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this package has moved to
`pantheon.imporcitor.pdf_tools` as part of the Pantheon architecture migration.

This package provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `pdf_tools` will
continue to work, but new code should import from `pantheon.imporcitor.pdf_tools` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from .pdf_to_md import (
    PDFConverter,
    convert_pdf_to_md,
    send_md_to_obsidian,
)
from .cleaning import (
    TextCleaner,
    normalize_text,
    sanitize_filename,
    remove_duplicate_lines,
    clean_markdown,
)
from .ocr_utils import (
    OCRProcessor,
    extract_text_with_ocr,
)

__all__ = [
    # PDF conversion
    "PDFConverter",
    "convert_pdf_to_md",
    "send_md_to_obsidian",
    # Text cleaning
    "TextCleaner",
    "normalize_text",
    "sanitize_filename",
    "remove_duplicate_lines",
    "clean_markdown",
    # OCR
    "OCRProcessor",
    "extract_text_with_ocr",
]
