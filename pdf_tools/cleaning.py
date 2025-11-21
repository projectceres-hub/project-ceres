"""
Text cleaning utilities module for Project Ceres.

Provides functionality for cleaning and normalizing text extracted from PDFs,
including whitespace normalization, encoding fixes, and structure cleanup.
"""

import re
from typing import Dict, List, Optional, Pattern


class TextCleaner:
    """
    Text cleaner for normalizing and cleaning extracted PDF text.
    
    Handles various text cleaning operations including whitespace
    normalization, encoding fixes, and structural cleanup.
    """
    
    def __init__(self, config: Optional[Dict] = None) -> None:
        """
        Initialize the text cleaner.
        
        Args:
            config: Optional configuration dictionary for cleaning rules
        """
        pass
    
    def clean(self, text: str) -> str:
        """
        Clean and normalize text content.
        
        Applies all configured cleaning rules to the input text.
        
        Args:
            text: Raw text to clean
            
        Returns:
            Cleaned text string
        """
        pass
    
    def normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text.
        
        Unifies line endings, removes trailing whitespace, and
        collapses excessive blank lines.
        
        Args:
            text: Text to normalize
            
        Returns:
            Text with normalized whitespace
        """
        pass
    
    def fix_encoding(self, text: str) -> str:
        """
        Fix common encoding issues in extracted text.
        
        Handles common PDF extraction encoding problems like
        smart quotes, dashes, and special characters.
        
        Args:
            text: Text with potential encoding issues
            
        Returns:
            Text with encoding issues fixed
        """
        pass
    
    def remove_headers_footers(
        self,
        text: str,
        patterns: Optional[List[Pattern]] = None
    ) -> str:
        """
        Remove headers and footers from text.
        
        Args:
            text: Text that may contain headers/footers
            patterns: Optional list of regex patterns to match headers/footers
            
        Returns:
            Text with headers and footers removed
        """
        pass
    
    def clean_page_numbers(self, text: str) -> str:
        """
        Remove standalone page numbers from text.
        
        Args:
            text: Text that may contain page numbers
            
        Returns:
            Text with page numbers removed
        """
        pass
    
    def split_into_blocks(self, text: str) -> List[str]:
        """
        Split text into logical blocks (paragraphs, sections).
        
        Args:
            text: Text to split
            
        Returns:
            List of text blocks
        """
        pass


def normalize_text(text: str) -> str:
    """
    Convenience function to normalize text.
    
    Applies standard normalization including whitespace cleanup
    and encoding fixes.
    
    Args:
        text: Raw text to normalize
        
    Returns:
        Normalized text string
    """
    pass


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for filesystem use
    """
    pass


def remove_duplicate_lines(text: str) -> str:
    """
    Remove consecutive duplicate lines from text.
    
    Args:
        text: Text that may contain duplicate lines
        
    Returns:
        Text with duplicate lines removed
    """
    pass


def clean_markdown(md: str) -> str:
    """
    Clean and normalize markdown content for Obsidian.
    
    Performs comprehensive cleaning including:
    - Normalizing heading levels (# to ####)
    - Removing OCR artifacts
    - Fixing duplicated markdown elements
    - Cleaning table formatting
    - Producing Obsidian-ready markdown
    
    Args:
        md: Raw markdown text to clean
        
    Returns:
        Cleaned markdown string ready for Obsidian
    """
    if not md:
        return ""
    
    # Step 1: Normalize line endings
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    
    # Step 2: Remove common OCR artifacts
    # Remove isolated punctuation marks on their own lines
    md = re.sub(r"^\s*[^\w\s#*`\[\](){}|\\\-=+_.,;:!?/<>@$%^&~`]{1,2}\s*$", "", md, flags=re.MULTILINE)
    # Remove lines with only special characters and numbers (common OCR noise)
    md = re.sub(r"^\s*[^\w\s#*`\[\](){}|\\\-=+_.,;:!?/<>@$%^&~`]{3,}\s*$", "", md, flags=re.MULTILINE)
    # Remove weird character sequences (like "l|" or "|l" which are OCR errors)
    md = re.sub(r"\b[l|1]\|", "I", md)  # Fix "l|" -> "I"
    md = re.sub(r"\|\s*[l|1]\b", "I", md)  # Fix "|l" -> "I"
    # Remove excessive spaces within words (OCR spacing errors)
    md = re.sub(r"(\w)\s{2,}(\w)", r"\1 \2", md)
    
    # Step 3: Normalize headings
    # Ensure headings have proper spacing after #
    md = re.sub(r"^(\#{1,6})([^\s#])", r"\1 \2", md, flags=re.MULTILINE)
    # Remove headings with more than 6 # symbols (invalid)
    md = re.sub(r"^#{7,}\s*", "", md, flags=re.MULTILINE)
    # Remove empty headings
    md = re.sub(r"^#{1,6}\s*$", "", md, flags=re.MULTILINE)
    # Normalize heading spacing (remove extra spaces)
    md = re.sub(r"^(#{1,6})\s+", r"\1 ", md, flags=re.MULTILINE)
    
    # Step 4: Fix duplicated markdown elements
    # Remove duplicate consecutive headings
    lines = md.split("\n")
    cleaned_lines = []
    prev_heading = None
    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            if current_heading == prev_heading:
                continue  # Skip duplicate heading
            prev_heading = current_heading
        else:
            prev_heading = None
        cleaned_lines.append(line)
    md = "\n".join(cleaned_lines)
    
    # Remove duplicate list items (consecutive identical items)
    md = re.sub(r"^([-*+]|\d+\.)\s+(.+)$\n\1\s+\2$", r"\1 \2", md, flags=re.MULTILINE)
    
    # Step 5: Clean tables
    # Normalize table separators (ensure proper | alignment)
    lines = md.split("\n")
    in_table = False
    table_lines = []
    cleaned_table_lines = []
    
    for i, line in enumerate(lines):
        # Detect table rows (contain | and not code blocks)
        if "|" in line and not line.strip().startswith("```"):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append((i, line))
        else:
            if in_table:
                # Process accumulated table lines
                cleaned_table_lines.extend(_clean_table_block(table_lines))
                table_lines = []
                in_table = False
            cleaned_table_lines.append(line)
    
    # Handle table at end of document
    if in_table:
        cleaned_table_lines.extend(_clean_table_block(table_lines))
    
    md = "\n".join(cleaned_table_lines)
    
    # Step 6: Fix markdown formatting issues
    # Remove empty code blocks
    md = re.sub(r"```\s*\n\s*```", "", md)
    # Fix broken code blocks (unclosed)
    md = re.sub(r"```([^`\n]+)\n(?!```)", r"`\1`\n", md)
    # Normalize bold/italic (remove spaces inside markers)
    md = re.sub(r"\*\*\s+([^*]+)\s+\*\*", r"**\1**", md)
    md = re.sub(r"\*\s+([^*]+)\s+\*", r"*\1*", md)
    md = re.sub(r"_\s+([^_]+)\s+_", r"_\1_", md)
    
    # Step 7: Remove duplicate blank lines (max 2 consecutive)
    md = re.sub(r"\n{3,}", "\n\n", md)
    
    # Step 8: Clean up whitespace
    # Remove trailing whitespace from lines
    md = re.sub(r"[ \t]+$", "", md, flags=re.MULTILINE)
    # Remove leading/trailing blank lines
    md = md.strip()
    
    # Step 9: Fix common Obsidian-specific issues
    # Ensure proper spacing around links
    md = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r"[\1](\2)", md)
    # Fix broken wikilinks [[text]] (remove extra brackets)
    md = re.sub(r"\[\[\[([^\]]+)\]\]", r"[[\1]]", md)
    md = re.sub(r"\[\[([^\]]+)\]\]\]", r"[[\1]]", md)
    
    # Step 10: Remove orphaned markdown syntax
    # Remove standalone markdown markers without content
    md = re.sub(r"^\s*[-*+]\s*$", "", md, flags=re.MULTILINE)
    md = re.sub(r"^\s*\d+\.\s*$", "", md, flags=re.MULTILINE)
    
    return md


def _clean_table_block(table_lines: List[tuple]) -> List[str]:
    """
    Clean a block of table lines.
    
    Args:
        table_lines: List of (line_index, line_content) tuples
        
    Returns:
        List of cleaned table lines
    """
    if not table_lines:
        return []
    
    cleaned = []
    separator_found = False
    
    for idx, (line_idx, line) in enumerate(table_lines):
        stripped = line.strip()
        
        # Check if this is a separator row (contains --- or ===)
        is_separator = re.match(r"^[\|\s:|-]+$", stripped) and ("---" in stripped or "===" in stripped)
        if is_separator:
            if not separator_found and idx > 0:
                # Ensure separator row has proper format
                num_cols = table_lines[0][1].count("|") - 1
                separator = "|" + "|".join(["---"] * num_cols) + "|"
                cleaned.append(separator)
                separator_found = True
            continue  # Skip duplicate separators
        
        # Normalize table row
        # Remove extra spaces around |
        normalized = re.sub(r"\s*\|\s*", "|", stripped)
        # Ensure row starts and ends with |
        if not normalized.startswith("|"):
            normalized = "|" + normalized
        if not normalized.endswith("|"):
            normalized = normalized + "|"
        # Add spaces back for readability
        normalized = re.sub(r"\|", " | ", normalized)
        normalized = normalized.strip()
        
        cleaned.append(normalized)
    
    # Ensure we have a separator if we have header rows
    if cleaned and not separator_found and len(cleaned) > 1:
        # Insert separator after first row
        num_cols = cleaned[0].count("|") - 1
        separator = "|" + "|".join(["---"] * num_cols) + "|"
        cleaned.insert(1, separator)
    
    return cleaned

