"""
Jobs module for Project Ceres automation engine.

Provides concrete job implementations for scheduled tasks.
"""

import os
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
    from automation.task_scheduler import Scheduler
else:
    # Avoid circular import at runtime
    Config = object
    Scheduler = object


def backup_vault(context: "Config", max_backups: int = 7) -> None:
    """
    Create a zip backup of the current vault directory.
    
    Creates a zip archive of the entire current vault directory and saves it
    under backups/YYYY-MM-DD/vault-backup-YYYY-MM-DD_HHMMSS.zip. Maintains
    only the last N backups (default: 7) by deleting older zip files.
    
    Args:
        context: Config object containing:
            - current_vault: Name of the current vault to backup
            - vaults: Dictionary mapping vault names to paths
        max_backups: Maximum number of backups to keep (default: 7)
        
    Raises:
        ValueError: If current_vault is not set or not found in vaults
        OSError: If backup directory cannot be created or file operations fail
        PermissionError: If vault directory cannot be read or backup cannot be written
    """
    if not context.current_vault:
        raise ValueError("No current vault set in context")
    
    if context.current_vault not in context.vaults:
        raise ValueError(f"Current vault '{context.current_vault}' not found in vaults")
    
    vault_name = context.current_vault
    vault_path = Path(context.vaults[vault_name])
    
    if not vault_path.exists() or not vault_path.is_dir():
        raise ValueError(f"Vault path does not exist or is not a directory: {vault_path}")
    
    # Determine backup directory (relative to project root where assistant.py is)
    # Use project root (where assistant.py is) as base
    project_root = Path(__file__).parent.parent
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
        _cleanup_old_backups(backups_dir, max_backups)
    except Exception as e:
        # Don't fail the backup if cleanup fails, just warn
        print(f"Warning: Failed to cleanup old backups: {e}")
    
    # Print success message
    rel_path = zip_path.relative_to(project_root)
    print(f"Vault backup created: {rel_path}")


def _cleanup_old_backups(backups_dir: Path, max_backups: int) -> None:
    """
    Clean up old backup zip files, keeping only the last N backups.
    
    Searches all dated subdirectories for vault-backup-*.zip files and removes
    older ones beyond the max_backups limit.
    
    Args:
        backups_dir: Root backups directory
        max_backups: Maximum number of backup zip files to keep
    """
    if not backups_dir.exists():
        return
    
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
    
    # Remove files beyond max_backups
    if len(backup_files) > max_backups:
        for old_file in backup_files[max_backups:]:
            try:
                old_file.unlink()
                # Optionally remove empty dated directories
                dated_dir = old_file.parent
                if dated_dir.exists() and not any(dated_dir.iterdir()):
                    dated_dir.rmdir()
            except PermissionError as e:
                print(f"Warning: Cannot delete old backup file '{old_file}': {e}")
            except OSError as e:
                print(f"Warning: Error deleting old backup file '{old_file}': {e}")


def register_backup_job(
    scheduler: "Scheduler",
    context: "Config",
    interval_seconds: int = 24 * 60 * 60
) -> None:
    """
    Register a recurring vault-backup job with the scheduler.
    
    Registers a job that backs up the current vault at the specified interval.
    Default interval is 24 hours (86400 seconds).
    
    Args:
        scheduler: Scheduler instance to register the job with
        context: Config object containing vault information
        interval_seconds: Time interval between backups in seconds (default: 86400 = 24 hours)
    """
    def backup_job() -> None:
        """Wrapper function for the backup job."""
        try:
            backup_vault(context)
        except ValueError as e:
            print(f"Error: Cannot backup vault: {e}")
        except PermissionError as e:
            print(f"Error: Permission denied during backup: {e}")
        except OSError as e:
            print(f"Error: Failed to create backup: {e}")
        except Exception as e:
            print(f"Error: Unexpected error during backup: {e}")
    
    try:
        scheduler.register_job(
            name="vault-backup",
            interval_seconds=float(interval_seconds),
            callable=backup_job
        )
    except ValueError:
        # Job already registered, skip
        pass


def sync_templates_job(context: "Config") -> None:
    """
    Wrapper job function that calls sync_templates_from_remote(context).
    
    Executes template synchronization from the remote source configured
    in the context's templates_remote_url.
    
    Args:
        context: Config object containing template sync configuration
    """
    from core.templates import sync_templates_from_remote
    
    try:
        sync_templates_from_remote(context)
    except ValueError as e:
        print(f"Error: Cannot sync templates: {e}")
    except PermissionError as e:
        print(f"Error: Permission denied during template sync: {e}")
    except OSError as e:
        print(f"Error: Failed to sync templates: {e}")
    except Exception as e:
        print(f"Error: Unexpected error during template sync: {e}")
