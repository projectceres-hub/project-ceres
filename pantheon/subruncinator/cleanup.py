"""
Cleanup module for Project Ceres.

Provides utilities for cleaning temporary files, caches, and other maintenance tasks.

This module is part of the Subruncinator domain in the Pantheon architecture,
responsible for cleanup and maintenance operations.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


def find_temp_files(config: "Config") -> list[Path]:
    """
    Return a list of temporary files that are safe to delete.
    
    Finds temporary files in the following locations:
    - .ceres_index/tmp/ directory (if exists) in current vault
    - pdf_tools/tmp/ directory (if exists) in project root
    - *.tmp.md or *.tmp files inside the current vault
    - OCR scratch files (*_ocr.*, *.ocr.*, *_scratch.*) in vault and pdf_tools
    
    Does NOT include:
    - .ceres_index/records.json (the actual index file)
    - Backup files (.bak files in .ceres_history/)
    - Any non-temporary files
    - .md or .txt files (to be safe)
    
    Args:
        config: Config object containing:
            - current_vault: Name of the current vault
            - vaults: Dictionary mapping vault names to paths
    
    Returns:
        List of Path objects representing temporary files that can be safely deleted
    """
    temp_files: list[Path] = []
    
    # File is at pantheon/subruncinator/cleanup.py, so go up 3 levels to project root
    project_root = Path(__file__).parent.parent.parent
    
    # Find temp files in current vault
    if config.current_vault and config.current_vault in config.vaults:
        vault_path = Path(config.vaults[config.current_vault])
        if vault_path.exists() and vault_path.is_dir():
            # .ceres_index/tmp/ directory contents
            index_tmp_dir = vault_path / ".ceres_index" / "tmp"
            if index_tmp_dir.exists() and index_tmp_dir.is_dir():
                try:
                    for item in index_tmp_dir.rglob("*"):
                        if item.is_file():
                            temp_files.append(item)
                except (PermissionError, OSError):
                    # Skip if we can't read the directory
                    pass
            
            # *.tmp.md and *.tmp files in vault
            try:
                for pattern in ["*.tmp.md", "*.tmp"]:
                    for tmp_file in vault_path.rglob(pattern):
                        if tmp_file.is_file():
                            temp_files.append(tmp_file)
            except (PermissionError, OSError):
                # Skip if we can't search
                pass
            
            # OCR scratch files in vault
            ocr_patterns = ["*_ocr.*", "*.ocr.*", "*_scratch.*", "*_scratch_*.*"]
            try:
                for pattern in ocr_patterns:
                    for scratch_file in vault_path.rglob(pattern):
                        if scratch_file.is_file():
                            # Only include if it's clearly a temp file (not a note)
                            # Skip .md and .txt files to be safe
                            if scratch_file.suffix not in [".md", ".txt"]:
                                temp_files.append(scratch_file)
            except (PermissionError, OSError):
                # Skip if we can't search
                pass
    
    # Find temp files in pdf_tools/tmp/
    pdf_tools_tmp = project_root / "pdf_tools" / "tmp"
    if pdf_tools_tmp.exists() and pdf_tools_tmp.is_dir():
        try:
            for item in pdf_tools_tmp.rglob("*"):
                if item.is_file():
                    temp_files.append(item)
        except (PermissionError, OSError):
            # Skip if we can't read
            pass
    
    # Find OCR scratch files in pdf_tools directory (not in tmp/)
    pdf_tools_dir = project_root / "pdf_tools"
    if pdf_tools_dir.exists() and pdf_tools_dir.is_dir():
        ocr_patterns = ["*_ocr.*", "*.ocr.*", "*_scratch.*", "*_scratch_*.*"]
        try:
            for pattern in ocr_patterns:
                for scratch_file in pdf_tools_dir.rglob(pattern):
                    if scratch_file.is_file():
                        # Skip if it's in tmp/ (already handled)
                        if "tmp" not in scratch_file.parts:
                            # Only include if it's clearly a temp file
                            if scratch_file.suffix not in [".md", ".txt", ".py"]:
                                temp_files.append(scratch_file)
        except (PermissionError, OSError):
            # Skip if we can't search
            pass
    
    return temp_files


def find_temp_directories(config: "Config") -> list[Path]:
    """
    Return a list of temporary directories that are safe to delete.
    
    Finds temporary directories that can be removed if empty:
    - .ceres_index/tmp/ directory in current vault
    - pdf_tools/tmp/ directory in project root
    
    Args:
        config: Config object containing:
            - current_vault: Name of the current vault
            - vaults: Dictionary mapping vault names to paths
    
    Returns:
        List of Path objects representing temporary directories
    """
    temp_dirs: list[Path] = []
    
    # File is at pantheon/subruncinator/cleanup.py, so go up 3 levels to project root
    project_root = Path(__file__).parent.parent.parent
    
    # Find temp directories in current vault
    if config.current_vault and config.current_vault in config.vaults:
        vault_path = Path(config.vaults[config.current_vault])
        if vault_path.exists() and vault_path.is_dir():
            # .ceres_index/tmp/ directory
            index_tmp_dir = vault_path / ".ceres_index" / "tmp"
            if index_tmp_dir.exists() and index_tmp_dir.is_dir():
                temp_dirs.append(index_tmp_dir)
    
    # Find temp directories in project root
    pdf_tools_tmp = project_root / "pdf_tools" / "tmp"
    if pdf_tools_tmp.exists() and pdf_tools_tmp.is_dir():
        temp_dirs.append(pdf_tools_tmp)
    
    return temp_dirs


def delete_files(paths: Iterable[Path]) -> int:
    """
    Delete the given file paths, returning the number of successfully removed files.
    
    Silently skips files that no longer exist or cannot be deleted.
    Logs warnings for permission errors but continues with other files.
    
    Args:
        paths: Iterable of Path objects representing files to delete
    
    Returns:
        Number of files successfully deleted
    """
    deleted_count = 0
    
    for file_path in paths:
        if not file_path.exists():
            # File already gone, skip
            continue
        
        if not file_path.is_file():
            # Not a file, skip
            continue
        
        try:
            file_path.unlink()
            deleted_count += 1
        except PermissionError as e:
            print(f"Warning: Cannot remove '{file_path}': {e}")
        except OSError as e:
            print(f"Warning: Error removing '{file_path}': {e}")
    
    return deleted_count


def delete_empty_directories(paths: Iterable[Path]) -> int:
    """
    Delete the given directory paths if they are empty.
    
    Attempts to remove directories and their nested subdirectories, but only
    if they are empty. Silently skips directories that are not empty or cannot be deleted.
    
    This matches the behavior of the original cache clean job which removes
    nested empty directories within temp directories.
    
    Args:
        paths: Iterable of Path objects representing directories to delete
    
    Returns:
        Number of directories successfully deleted
    """
    deleted_count = 0
    
    for dir_path in paths:
        if not dir_path.exists():
            # Directory already gone, skip
            continue
        
        if not dir_path.is_dir():
            # Not a directory, skip
            continue
        
        try:
            # Walk through directory and try to remove empty subdirectories
            # Process from deepest to shallowest
            dirs_to_remove = []
            
            # Collect all subdirectories
            for item in dir_path.rglob("*"):
                if item.is_dir():
                    dirs_to_remove.append(item)
            
            # Also include the root directory itself
            dirs_to_remove.append(dir_path)
            
            # Sort by depth (deepest first) so we remove nested dirs before parents
            dirs_to_remove.sort(key=lambda p: len(p.parts), reverse=True)
            
            # Try to remove each directory if it's empty
            for d in dirs_to_remove:
                if not d.exists():
                    continue
                try:
                    # Check if directory is empty before trying to remove
                    if not any(d.iterdir()):
                        d.rmdir()
                        deleted_count += 1
                except OSError:
                    # Directory not empty or other error, skip
                    pass
        except (PermissionError, OSError) as e:
            print(f"Warning: Error removing directory '{dir_path}': {e}")
    
    return deleted_count


def clean_cache(config: "Config") -> int:
    """
    High-level entry point for cache cleaning.
    
    Finds and deletes temporary files and directories:
    - .ceres_index/tmp/ directory (if exists) in current vault
    - pdf_tools/tmp/ directory (if exists) in project root
    - *.tmp.md or *.tmp files inside the current vault
    - Any leftover OCR scratch files (if present)
    
    Does NOT delete:
    - .ceres_index/records.json (the actual index file)
    - Backup files (.bak files in .ceres_history/)
    - Any non-temporary files
    
    Args:
        config: Config object containing:
            - current_vault: Name of the current vault
            - vaults: Dictionary mapping vault names to paths
    
    Returns:
        Number of files successfully deleted
    """
    files_removed = 0
    
    # Find and delete temp files
    try:
        temp_files = find_temp_files(config)
        files_removed += delete_files(temp_files)
    except Exception as e:
        print(f"Warning: Error finding temp files: {e}")
    
    # Find and delete empty temp directories
    try:
        temp_dirs = find_temp_directories(config)
        # Delete files in directories first, then try to remove directories
        # (This is handled by the directory deletion logic)
        delete_empty_directories(temp_dirs)
    except Exception as e:
        print(f"Warning: Error cleaning temp directories: {e}")
    
    return files_removed

