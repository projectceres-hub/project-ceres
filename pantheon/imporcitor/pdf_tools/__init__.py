"""
PDF Tools package for Project Ceres.

Provides utilities for PDF to Markdown conversion, OCR processing,
and text cleaning operations.

This package is part of the Imporcitor domain in the Pantheon architecture,
responsible for bulk import, PDF→MD conversion, and large-scale content ingestion.
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

