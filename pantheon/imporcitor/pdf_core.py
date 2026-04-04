"""
PDF conversion module for Project Ceres.

Provides functionality for converting PDF files to Markdown format using
various extraction methods (PyMuPDF, pdfplumber, etc.).

This module is part of the Imporcitor domain in the Pantheon architecture,
responsible for bulk import, PDF→MD conversion, and large-scale content ingestion.
"""

import os
import re
import pathlib
from typing import Dict, List, Optional, Any


def convert_pdf_to_md(
    pdf_path: str,
    out_dir: str,
    map_rules: Dict[str, Any],
    override_filename: Optional[str] = None
) -> List[str]:
    """
    Convert a PDF file to Markdown format.
    
    Args:
        pdf_path: Path to the input PDF file
        out_dir: Output directory for Markdown files
        map_rules: Dictionary of mapping rules for document structure
        override_filename: Optional filename override (without .md extension)
        
    Returns:
        List of paths to created Markdown files
    """
    raw_pages = extract_text_pages(pdf_path, debug=False)
    blocks = pages_to_blocks(raw_pages)
    md_docs = apply_map_rules(blocks, map_rules)

    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    written = []

    # Prefer the original PDF base name unless an override is provided
    base_name = override_filename or os.path.splitext(os.path.basename(pdf_path))[0]

    for idx, doc in enumerate(md_docs):
        # If someday we split into multiple docs, add an index suffix
        title_for_file = base_name if idx == 0 else f"{base_name}_{idx+1}"
        fname = sanitize_filename(title_for_file) + ".md"
        path = os.path.join(out_dir, fname)

        with open(path, "w", encoding="utf-8") as f:
            fm = render_frontmatter(doc)
            if fm:
                f.write(fm + "\n")
            f.write(doc.get("body") or "")

        written.append(path)
    return written

def _normalize_text(text: str) -> str:
    """
    Normalize text by unifying line endings and cleaning whitespace.
    
    Args:
        text: Raw text to normalize
        
    Returns:
        Normalized text string
    """
    # Unify line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing whitespace
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    # Collapse 3+ blank lines to at most 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# -------- Extraction Layer --------


def extract_text_pages(pdf_path: str, debug: bool = False) -> List[str]:
    """
    Extract text from all pages of a PDF file.
    
    Tries multiple extraction backends in order: PyMuPDF, pdfminer.six.
    Falls back to placeholder text if all methods fail.
    
    Args:
        pdf_path: Path to the PDF file
        debug: Whether to print debug information (default: False)
        
    Returns:
        List of page text strings
    """
    # Try PyMuPDF
    try:
        import fitz  # PyMuPDF
        pages: List[str] = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                pages.append(page.get_text("text"))
        if debug:
            print(f"[pdf] backend=PyMuPDF pages={len(pages)}")
        return pages
    except Exception:
        pass

    # Fallback: pdfminer.six
    try:
        from io import StringIO
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        output = StringIO()
        with open(pdf_path, "rb") as fh:
            extract_text_to_fp(fh, output, laparams=LAParams(), output_type="text", codec=None)
        full_text = output.getvalue()
        chunks = re.split(r"\f", full_text)
        pages = [c.strip() for c in chunks if c.strip()] or [full_text]
        if debug:
            print(f"[pdf] backend=pdfminer pages={len(pages)}")
        return pages
    except Exception:
        pass

    if debug:
        print("[pdf] backend=fallback pages=2 (placeholders)")
    return ["[PAGE 1 RAW TEXT placeholder]", "[PAGE 2 RAW TEXT placeholder]"]


def pages_to_blocks(pages: List[str]) -> List[Dict[str, str]]:
    """
    Convert page text list into document blocks.
    
    Args:
        pages: List of page text strings
        
    Returns:
        List of document block dictionaries with 'title' and 'text' keys
    """
    joined = "\n\n".join(pages)
    return [{"title": "Converted Document", "text": _normalize_text(joined)}]


# -------- Mapping / Rules Layer --------


def apply_map_rules(
    blocks: List[Dict[str, str]],
    rules: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Apply mapping rules to document blocks.
    
    Args:
        blocks: List of document block dictionaries
        rules: Dictionary of mapping rules (rename, frontmatter, default_title)
        
    Returns:
        List of processed document dictionaries
    """
    docs = []
    rename_rules = rules.get("rename", [])
    frontmatter = rules.get("frontmatter", {})
    default_title = rules.get("default_title", "Converted Document")

    for b in blocks:
        text = b["text"]
        for r in rename_rules:
            pat = r.get("pattern", "")
            rep = r.get("replace", "")
            if pat:
                text = re.sub(pat, rep, text, flags=re.MULTILINE)
        text = _normalize_text(text)
        docs.append({
            "title": default_title,
            "frontmatter": frontmatter,
            "body": text
        })
    return docs


def render_frontmatter(doc: Dict[str, Any]) -> str:
    """
    Render frontmatter YAML from document dictionary.
    
    Args:
        doc: Document dictionary with optional 'frontmatter' key
        
    Returns:
        YAML frontmatter string (empty if no frontmatter)
    """
    fm = doc.get("frontmatter", {}) or {}
    if not fm:
        return ""
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(map(str, v))}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def sanitize_filename(name: str) -> str:
    """
    Sanitize a filename by removing invalid characters.
    
    Args:
        name: Original filename
        
    Returns:
        Sanitized filename safe for filesystem use
    """
    sanitized = re.sub(r"[^a-zA-Z0-9._ -]+", "_", name).strip()
    return sanitized if sanitized else "Document"

