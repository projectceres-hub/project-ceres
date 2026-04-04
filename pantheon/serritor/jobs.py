"""
Jobs module for Project Ceres automation engine.

Provides concrete job implementations for scheduled tasks.

This module is part of the Serritor domain in the Pantheon architecture,
responsible for automation and background jobs.
"""

import os
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
    from pantheon.serritor.task_scheduler import Scheduler
else:
    # Avoid circular import at runtime
    Config = object
    Scheduler = object


def backup_vault(context: "Config", max_backups: int = 7) -> None:
    """
    Automation job wrapper for Conditor vault backups.
    
    Delegates to pantheon.conditor.backup to perform the actual vault backup
    and cleanup operations.
    
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
    from pantheon.conditor import create_vault_backup, prune_old_backups
    
    # Create the backup (this also calls prune_old_backups internally)
    backup_path = create_vault_backup(context, max_backups=max_backups)
    
    # Get project root for relative path display
    project_root = Path(__file__).parent.parent.parent
    rel_path = backup_path.relative_to(project_root)
    print(f"Vault backup created: {rel_path}")


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
    from pantheon.reparator import sync_templates_from_remote
    
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


def rebuild_srd_index_job(context: "Config") -> None:
    """
    Rebuild the SRD index using paths from the context.
    
    Uses context.current_vault to determine the vault path, then indexes
    the SRDs/ directory under that vault and saves the index to
    .ceres_index/records.json in the vault root.
    
    Args:
        context: Config object containing:
            - current_vault: Name of the current vault
            - vaults: Dictionary mapping vault names to paths
    """
    from pantheon.occator import build_srd_index
    
    if not context.current_vault:
        raise ValueError("No current vault set in context")
    
    if context.current_vault not in context.vaults:
        raise ValueError(f"Current vault '{context.current_vault}' not found in vaults")
    
    vault_name = context.current_vault
    vault_path = Path(context.vaults[vault_name])
    
    if not vault_path.exists() or not vault_path.is_dir():
        raise ValueError(f"Vault path does not exist or is not a directory: {vault_path}")
    
    # Determine SRD directory and index output path
    srd_dir = vault_path / "SRDs"
    index_dir = vault_path / ".ceres_index"
    index_path = index_dir / "records.json"
    
    # Build the index
    build_srd_index(srd_dir, index_path)


def session_reminder_job(context: "Config") -> None:
    """
    Check if there is an upcoming session and, if so, print a reminder message.
    
    Checks for upcoming sessions within the configured reminder window
    (default: 24 hours). If a session is found, prints a reminder to the console.
    
    Future extension:
    - Hook into Discord, email, or desktop notifications
    - Support multiple reminder windows (e.g., 24h, 1h before)
    
    Args:
        context: Config object containing:
            - session_reminder_hours_before: Hours before session to send reminder (default: 24)
    """
    from pantheon.promitor import get_next_session_info
    from datetime import datetime, timedelta
    
    # Get reminder window from config (default: 24 hours)
    reminder_hours = getattr(context, 'session_reminder_hours_before', 24)
    
    # Get next session info
    session_info = get_next_session_info(context)
    if not session_info:
        # No upcoming session found
        return
    
    # Calculate time until session
    now = datetime.now(session_info.start.tzinfo) if session_info.start.tzinfo else datetime.now()
    time_until = session_info.start - now
    
    # Check if session is within reminder window
    reminder_window = timedelta(hours=reminder_hours)
    if time_until > reminder_window:
        # Too far in the future, don't remind yet
        return
    
    if time_until <= timedelta(0):
        # Session is in the past or happening now
        return
    
    # Format time until session
    hours = int(time_until.total_seconds() / 3600)
    minutes = int((time_until.total_seconds() % 3600) / 60)
    
    if hours > 0:
        time_str = f"{hours} hour{'s' if hours != 1 else ''}"
        if minutes > 0:
            time_str += f" {minutes} minute{'s' if minutes != 1 else ''}"
    else:
        time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
    
    # Format session start time
    if session_info.start.tzinfo:
        start_str = session_info.start.strftime("%A, %B %d at %I:%M %p %Z")
    else:
        start_str = session_info.start.strftime("%A, %B %d at %I:%M %p")
    
    # Print reminder
    print("=" * 60)
    print("📅 SESSION REMINDER")
    print("=" * 60)
    print(f"Upcoming Session: {session_info.title}")
    print(f"Starts in: {time_str}")
    print(f"Date & Time: {start_str}")
    
    duration = session_info.end - session_info.start
    duration_hours = int(duration.total_seconds() / 3600)
    duration_minutes = int((duration.total_seconds() % 3600) / 60)
    if duration_minutes == 0:
        duration_str = f"{duration_hours} hour{'s' if duration_hours != 1 else ''}"
    else:
        duration_str = f"{duration_hours}h {duration_minutes}m"
    print(f"Duration: {duration_str}")
    
    if session_info.description:
        print(f"\nDescription: {session_info.description}")
    
    print("=" * 60)


def clean_cache_job(context: "Config") -> None:
    """
    Automation job wrapper for Subruncinator cache cleaning.
    
    Delegates to pantheon.subruncinator.clean_cache to perform the actual
    cleanup of temporary files and directories.
    
    Safely removes temporary files and directories:
    - .ceres_index/tmp/ directory (if exists) in current vault
    - pdf_tools/tmp/ directory (if exists) in project root
    - *.tmp.md or *.tmp files inside the current vault
    - Any leftover OCR scratch files (if present)
    
    Does NOT delete:
    - .ceres_index/records.json (the actual index file)
    - Backup files (.bak files in .ceres_history/)
    - Any non-temporary files
    
    Args:
        context: Config object containing:
            - current_vault: Name of the current vault
            - vaults: Dictionary mapping vault names to paths
            
    Raises:
        ValueError: If current_vault is not set or not found in vaults
        OSError: If file operations fail (non-critical, continues with other files)
    """
    from pantheon.subruncinator import clean_cache
    
    files_removed = clean_cache(context)
    
    # Print summary (preserving original message format)
    if files_removed > 0:
        print(f"Cache cleanup complete: Removed {files_removed} temporary file(s).")
    else:
        print("Cache cleanup complete: No temporary files found.")


def daily_snapshot_job(context: "Config") -> None:
    """
    Create a snapshot directory under snapshots/YYYY-MM-DD/ and copy all .md files as-is.
    
    Creates a daily snapshot of the current vault by copying all markdown files
    to a dated snapshot directory. Files are copied as-is without compression.
    This provides quick recovery without needing to extract from zip archives.
    
    Args:
        context: Config object containing:
            - current_vault: Name of the current vault to snapshot
            - vaults: Dictionary mapping vault names to paths
            
    Raises:
        ValueError: If current_vault is not set or not found in vaults
        OSError: If snapshot directory cannot be created or file operations fail
        PermissionError: If vault directory cannot be read or snapshot cannot be written
    """
    if not context.current_vault:
        raise ValueError("No current vault set in context")
    
    if context.current_vault not in context.vaults:
        raise ValueError(f"Current vault '{context.current_vault}' not found in vaults")
    
    vault_name = context.current_vault
    vault_path = Path(context.vaults[vault_name])
    
    if not vault_path.exists() or not vault_path.is_dir():
        raise ValueError(f"Vault path does not exist or is not a directory: {vault_path}")
    
    # Determine snapshot directory (relative to project root where assistant.py is)
    # File is at pantheon/serritor/jobs.py, so go up 3 levels to project root
    project_root = Path(__file__).parent.parent.parent
    snapshots_dir = project_root / "snapshots"
    
    # Create dated subdirectory
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    dated_snapshot_dir = snapshots_dir / date_str
    dated_snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    # Count files copied
    files_copied = 0
    
    try:
        # Walk through vault directory and copy all .md files
        for root, dirs, files in os.walk(vault_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            # Calculate relative path from vault root
            rel_root = Path(root).relative_to(vault_path)
            
            # Create corresponding directory in snapshot (if not root)
            if rel_root != Path('.'):
                snapshot_subdir = dated_snapshot_dir / rel_root
                snapshot_subdir.mkdir(parents=True, exist_ok=True)
            else:
                snapshot_subdir = dated_snapshot_dir
            
            # Copy .md files
            for file in files:
                if file.startswith('.'):
                    continue
                
                if not file.endswith('.md'):
                    continue
                
                source_file = Path(root) / file
                dest_file = snapshot_subdir / file
                
                try:
                    # Copy file as-is
                    shutil.copy2(source_file, dest_file)
                    files_copied += 1
                except PermissionError as e:
                    # Skip files we can't read, but continue with others
                    print(f"Warning: Cannot read file '{source_file}': {e}")
                    continue
                except OSError as e:
                    # Skip files with errors, but continue with others
                    print(f"Warning: Error copying file '{source_file}': {e}")
                    continue
    
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating snapshot '{dated_snapshot_dir}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create snapshot '{dated_snapshot_dir}': {e}")
    
    # Print success message
    rel_path = dated_snapshot_dir.relative_to(project_root)
    print(f"Daily snapshot created: {rel_path} ({files_copied} .md file(s) copied)")

