"""
Imporcitor domain for Project Ceres.

This domain handles bulk import, PDF→MD conversion, and large-scale content
ingestion - processing documents in bulk and transforming them for use in Ceres.

Public API exports from the PDF and import modules.
"""

from .pdf_core import (
    convert_pdf_to_md,
    extract_text_pages,
    pages_to_blocks,
    apply_map_rules,
    render_frontmatter,
    sanitize_filename,
)
from .pdf_tools import (
    PDFConverter,
    convert_pdf_to_md as convert_pdf_to_md_marker,
    send_md_to_obsidian,
    TextCleaner,
    clean_markdown,
    OCRProcessor,
    extract_text_with_ocr,
)

__all__ = [
    # PDF core functions (legacy string-based API)
    "convert_pdf_to_md",
    "extract_text_pages",
    "pages_to_blocks",
    "apply_map_rules",
    "render_frontmatter",
    "sanitize_filename",
    # PDF tools (Marker-based API)
    "PDFConverter",
    "convert_pdf_to_md_marker",
    "send_md_to_obsidian",
    "TextCleaner",
    "clean_markdown",
    "OCRProcessor",
    "extract_text_with_ocr",
]

