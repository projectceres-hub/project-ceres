"""
Backup module for Project Ceres.

Provides functionality for creating vault-level backups and managing backup retention.

This module is part of the Conditor domain in the Pantheon architecture,
responsible for storage, backups, history, and undo operations.
"""

import os
import zipfile
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


def create_vault_backup(config: "Config", max_backups: int = 7) -> Path:
    """
    Create a zip backup of the current vault directory.
    
    Creates a zip archive of the entire current vault directory and saves it
    under backups/YYYY-MM-DD/vault-backup-YYYY-MM-DD_HHMMSS.zip.
    
    Args:
        config: Config object containing:
            - current_vault: Name of the current vault to backup
            - vaults: Dictionary mapping vault names to paths
        max_backups: Maximum number of backups to keep (default: 7)
        
    Returns:
        Path to the created backup zip file
        
    Raises:
        ValueError: If current_vault is not set or not found in vaults
        OSError: If backup directory cannot be created or file operations fail
        PermissionError: If vault directory cannot be read or backup cannot be written
    """
    if not config.current_vault:
        raise ValueError("No current vault set in context")
    
    if config.current_vault not in config.vaults:
        raise ValueError(f"Current vault '{config.current_vault}' not found in vaults")
    
    vault_name = config.current_vault
    vault_path = Path(config.vaults[vault_name])
    
    if not vault_path.exists() or not vault_path.is_dir():
        raise ValueError(f"Vault path does not exist or is not a directory: {vault_path}")
    
    # Determine backup directory (relative to project root where assistant.py is)
    # File is at pantheon/conditor/backup.py, so go up 3 levels to project root
    project_root = Path(__file__).parent.parent.parent
    backups_dir = project_root / "backups"
    
    # Create dated subdirectory
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    dated_backup_dir = backups_dir / date_str
    dated_backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Create zip file name with timestamp: vault-backup-YYYY-MM-DD_HHMMSS.zip
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
    zip_filename = f"vault-backup-{timestamp_str}.zip"
    zip_path = dated_backup_dir / zip_filename
    
    # Create zip archive
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through vault directory and add all files
            for root, dirs, files in os.walk(vault_path):
                # Skip hidden directories and files
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    
                    file_path = Path(root) / file
                    try:
                        # Calculate relative path for archive
                        arcname = file_path.relative_to(vault_path)
                        zipf.write(file_path, arcname)
                    except PermissionError as e:
                        # Skip files we can't read, but continue with others
                        print(f"Warning: Cannot read file '{file_path}': {e}")
                        continue
                    except OSError as e:
                        # Skip files with errors, but continue with others
                        print(f"Warning: Error processing file '{file_path}': {e}")
                        continue
    
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating backup '{zip_path}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create backup '{zip_path}': {e}")
    
    # Clean up old backups (keep only last N zip files)
    try:
        prune_old_backups(config, keep=max_backups)
    except Exception as e:
        # Don't fail the backup if cleanup fails, just warn
        print(f"Warning: Failed to cleanup old backups: {e}")
    
    return zip_path


def prune_old_backups(config: "Config", keep: int = 7) -> int:
    """
    Remove old backup zip files, keeping only the last N backups.
    
    Searches all dated subdirectories for vault-backup-*.zip files and removes
    older ones beyond the keep limit.
    
    Args:
        config: Config object (used to determine project root)
        keep: Maximum number of backup zip files to keep (default: 7)
        
    Returns:
        Number of backup files deleted
    """
    # Determine backup directory (relative to project root where assistant.py is)
    # File is at pantheon/conditor/backup.py, so go up 3 levels to project root
    project_root = Path(__file__).parent.parent.parent
    backups_dir = project_root / "backups"
    
    if not backups_dir.exists():
        return 0
    
    # Collect all backup zip files from all dated subdirectories
    backup_files = []
    for dated_dir in backups_dir.iterdir():
        if not dated_dir.is_dir():
            continue
        
        for item in dated_dir.iterdir():
            if item.is_file() and item.name.startswith("vault-backup-") and item.name.endswith(".zip"):
                try:
                    # Try to parse timestamp from filename: vault-backup-YYYY-MM-DD_HHMMSS.zip
                    timestamp_part = item.name[13:-4]  # Remove "vault-backup-" prefix and ".zip" suffix
                    datetime.strptime(timestamp_part, "%Y-%m-%d_%H%M%S")
                    backup_files.append(item)
                except ValueError:
                    # Skip files that don't match expected format
                    continue
    
    # Sort by modification time (newest first)
    backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # Remove files beyond keep limit
    deleted_count = 0
    if len(backup_files) > keep:
        for old_file in backup_files[keep:]:
            try:
                old_file.unlink()
                deleted_count += 1
                # Optionally remove empty dated directories
                dated_dir = old_file.parent
                if dated_dir.exists() and not any(dated_dir.iterdir()):
                    dated_dir.rmdir()
            except PermissionError as e:
                print(f"Warning: Cannot delete old backup file '{old_file}': {e}")
            except OSError as e:
                print(f"Warning: Error deleting old backup file '{old_file}': {e}")
    
    return deleted_count


