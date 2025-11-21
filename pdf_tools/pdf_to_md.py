"""
PDF to Markdown conversion module for Project Ceres.

Provides functionality for converting PDF documents to Markdown format,
including text extraction, page processing, and document structure handling.
"""

import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional


class PDFConverter:
    """
    Main converter class for PDF to Markdown transformation.
    
    Handles the conversion pipeline from PDF input to Markdown output,
    including text extraction, structure analysis, and formatting.
    """
    
    def __init__(self, config: Optional[Dict] = None) -> None:
        """
        Initialize the PDF converter.
        
        Args:
            config: Optional configuration dictionary for converter settings
        """
        pass
    
    def convert(
        self,
        pdf_path: Path,
        output_dir: Path,
        options: Optional[Dict] = None
    ) -> List[Path]:
        """
        Convert a PDF file to Markdown.
        
        Args:
            pdf_path: Path to the input PDF file
            output_dir: Directory where output Markdown files should be written
            options: Optional dictionary of conversion options
            
        Returns:
            List of paths to created Markdown files
            
        Raises:
            FileNotFoundError: If the PDF file does not exist
            ValueError: If the PDF file is invalid or corrupted
        """
        pass
    
    def extract_text(self, pdf_path: Path) -> List[str]:
        """
        Extract text content from PDF pages.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of strings, one per page
            
        Raises:
            FileNotFoundError: If the PDF file does not exist
            ValueError: If text extraction fails
        """
        pass
    
    def extract_metadata(self, pdf_path: Path) -> Dict[str, str]:
        """
        Extract metadata from PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary of metadata fields (title, author, etc.)
        """
        pass


def convert_pdf_to_md(
    pdf_path: Path,
    output_dir: Path,
    options: Optional[Dict] = None
) -> List[Path]:
    """
    Convert PDF to Markdown using Marker.
    
    Uses Marker (via subprocess) to convert a PDF file to Markdown format.
    The markdown is written to a file in the output directory.
    
    Args:
        pdf_path: Path to the input PDF file
        output_dir: Directory where output Markdown files should be written
        options: Optional dictionary of conversion options.
                 Supported keys:
                 - override_filename: Base filename (without .md extension) for output
                 - marker_command: Custom Marker command (default: "marker")
                 - marker_args: Additional arguments to pass to Marker
        
    Returns:
        List of paths to created Markdown files
        
    Raises:
        FileNotFoundError: If the PDF file does not exist or Marker is not found
        ValueError: If the PDF file is invalid or conversion fails
        PermissionError: If output directory is not writable
        RuntimeError: If Marker execution fails
    """
    if options is None:
        options = {}
    
    # Validate input PDF exists
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if not pdf_path.is_file():
        raise ValueError(f"Path is not a file: {pdf_path}")
    
    # Check if Marker is available
    marker_command = options.get("marker_command", "marker")
    marker_path = shutil.which(marker_command)
    if marker_path is None:
        raise FileNotFoundError(
            f"Marker not found. Please install Marker or ensure '{marker_command}' is in your PATH."
        )
    
    # Ensure output directory exists
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Permission denied creating output directory '{output_dir}': {e}"
        )
    except OSError as e:
        raise RuntimeError(
            f"Failed to create output directory '{output_dir}': {e}"
        )
    
    # Determine output filename
    if "override_filename" in options:
        base_name = options["override_filename"]
    else:
        base_name = pdf_path.stem
    
    output_file = output_dir / f"{base_name}.md"
    
    # Build Marker command
    marker_args = options.get("marker_args", [])
    cmd = [marker_path] + marker_args + [str(pdf_path)]
    
    # Run Marker and capture output
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # We'll check return code manually
            timeout=300  # 5 minute timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Marker conversion timed out after 5 minutes for file: {pdf_path}"
        )
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Marker executable not found at '{marker_path}'. "
            f"Please ensure Marker is installed and accessible."
        )
    except PermissionError:
        raise PermissionError(
            f"Permission denied executing Marker. "
            f"Check that '{marker_path}' is executable."
        )
    except OSError as e:
        raise RuntimeError(
            f"Failed to execute Marker: {e}"
        )
    
    # Check for errors
    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        raise ValueError(
            f"Marker conversion failed (exit code {result.returncode}): {error_msg}\n"
            f"Command: {' '.join(cmd)}"
        )
    
    # Get markdown from stdout
    markdown_content = result.stdout
    
    if not markdown_content:
        raise ValueError(
            f"Marker produced no output for file: {pdf_path}. "
            f"The PDF may be empty or corrupted."
        )
    
    # Write markdown to file
    try:
        output_file.write_text(markdown_content, encoding="utf-8")
    except PermissionError as e:
        raise PermissionError(
            f"Permission denied writing to output file '{output_file}': {e}"
        )
    except OSError as e:
        raise RuntimeError(
            f"Failed to write output file '{output_file}': {e}"
        )
    
    return [output_file]


def send_md_to_obsidian(md: str, target_folder: Path, filename: Optional[str] = None) -> Path:
    """
    Write markdown content to the current Obsidian vault.
    
    Creates the target folder structure if it doesn't exist and writes
    the markdown file to the specified location within the vault.
    
    Args:
        md: Markdown content to write
        target_folder: Full path to the target folder within the vault
                      (e.g., Path("path/to/vault/PDFs/Converted"))
        filename: Optional filename (without .md extension). If not provided,
                  generates a timestamp-based filename.
        
    Returns:
        Path to the created markdown file
        
    Raises:
        FileNotFoundError: If target_folder parent does not exist
        PermissionError: If target_folder is not writable
        OSError: If file creation fails
        ValueError: If target_folder is invalid or filename is invalid
    """
    from datetime import datetime
    
    # Validate and normalize target folder
    target_folder = Path(target_folder)
    
    # Ensure target_folder is a directory path (not a file)
    # If it ends with .md, treat it as a file path and extract directory
    if target_folder.suffix == ".md":
        full_target_dir = target_folder.parent
        if filename is None:
            filename = target_folder.stem
    else:
        full_target_dir = target_folder
    
    # Create directory structure
    try:
        full_target_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Permission denied creating directory '{full_target_dir}': {e}"
        )
    except OSError as e:
        raise OSError(
            f"Failed to create directory '{full_target_dir}': {e}"
        )
    
    # Validate parent directory exists (for safety)
    if not full_target_dir.exists():
        raise FileNotFoundError(
            f"Target directory does not exist and could not be created: {full_target_dir}"
        )
    
    # Determine filename
    if filename is None:
        # Generate timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"converted_{timestamp}"
    else:
        # Sanitize filename
        filename = str(filename).strip()
        if not filename:
            raise ValueError("Filename cannot be empty")
        # Remove .md extension if present (we'll add it)
        if filename.endswith(".md"):
            filename = filename[:-3]
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
    
    # Build full file path
    output_file = full_target_dir / f"{filename}.md"
    
    # Check if file already exists and handle it
    if output_file.exists():
        # Generate numbered version
        counter = 1
        while output_file.exists():
            output_file = full_target_dir / f"{filename}_{counter}.md"
            counter += 1
            if counter > 1000:  # Safety limit
                raise OSError(
                    f"Too many files with similar names in '{full_target_dir}'"
                )
    
    # Write markdown content
    try:
        output_file.write_text(md, encoding="utf-8")
    except PermissionError as e:
        raise PermissionError(
            f"Permission denied writing to '{output_file}': {e}"
        )
    except OSError as e:
        raise OSError(
            f"Failed to write file '{output_file}': {e}"
        )
    
    return output_file

