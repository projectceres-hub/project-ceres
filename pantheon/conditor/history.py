"""
History module for Project Ceres.

Provides undo functionality for note edits and appends by maintaining
backup copies of files before modifications.

This module is part of the Conditor domain in the Pantheon architecture,
responsible for storage, backups, history, and undo operations.
"""

import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class HistoryEntry:
    """
    Represents a single history entry for a backed-up note.
    
    Attributes:
        note_path: Path to the original note file (as string for JSON serialization)
        backup_path: Path to the backup file (as string for JSON serialization)
        timestamp: When the backup was created (ISO format string for JSON serialization)
    """
    note_path: str
    backup_path: str
    timestamp: str  # ISO format string for JSON serialization
    
    @property
    def note_path_obj(self) -> Path:
        """Get note_path as a Path object."""
        return Path(self.note_path)
    
    @property
    def backup_path_obj(self) -> Path:
        """Get backup_path as a Path object."""
        return Path(self.backup_path)
    
    @property
    def timestamp_obj(self) -> datetime:
        """Get timestamp as a datetime object."""
        return datetime.fromisoformat(self.timestamp)
    
    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        """
        Create a HistoryEntry from a dictionary.
        
        Args:
            data: Dictionary with note_path, backup_path, and timestamp
            
        Returns:
            HistoryEntry instance
        """
        return cls(
            note_path=data["note_path"],
            backup_path=data["backup_path"],
            timestamp=data["timestamp"]
        )


class HistoryManager:
    """
    Manages note history and undo functionality.
    
    Maintains a JSON index of backup files and provides methods to
    backup notes before modification and restore them.
    """
    
    def __init__(self, history_dir: Optional[Path] = None) -> None:
        """
        Initialize the history manager.
        
        Args:
            history_dir: Directory to store history files. If None, uses
                        .ceres_history in the current working directory.
        """
        if history_dir is None:
            history_dir = Path(".ceres_history")
        self.history_dir = Path(history_dir)
        self.index_path = self.history_dir / "history_index.json"
        self._ensure_history_dir()
    
    def _ensure_history_dir(self) -> None:
        """Create the history directory if it doesn't exist."""
        try:
            self.history_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Failed to create history directory '{self.history_dir}': {e}")
    
    def _load_index(self) -> List[HistoryEntry]:
        """
        Load the history index from JSON file.
        
        Returns:
            List of HistoryEntry objects
        """
        if not self.index_path.exists():
            return []
        
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [HistoryEntry.from_dict(entry) for entry in data]
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            print(f"Warning: Failed to load history index: {e}")
            print("Hint: History index may be corrupted. Starting with empty history.")
            return []
        except (PermissionError, OSError) as e:
            print(f"Warning: Failed to read history index: {e}")
            print("Hint: Check file permissions for the history directory.")
            return []
    
    def _save_index(self, entries: List[HistoryEntry]) -> None:
        """
        Save the history index to JSON file.
        
        Args:
            entries: List of HistoryEntry objects to save
        """
        try:
            # Convert to JSON-serializable format
            data = [asdict(entry) for entry in entries]
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Failed to save history index: {e}")
    
    def backup_note(self, note_path: Path) -> None:
        """
        Create a backup of a note file before modification.
        
        Copies the note to .ceres_history/<mirrored path>--<timestamp>.bak
        and adds an entry to the history index.
        
        Args:
            note_path: Path to the note file to backup
            
        Raises:
            FileNotFoundError: If the note file doesn't exist
            RuntimeError: If backup creation fails
        """
        note_path = Path(note_path).resolve()
        
        if not note_path.exists():
            # Don't backup non-existent files (e.g., new notes)
            return
        
        if not note_path.is_file():
            raise ValueError(f"Path is not a file: {note_path}")
        
        # Generate backup path: mirror the original path structure
        # e.g., vault/notes/note.md -> .ceres_history/vault/notes/note--20240101_120000.bak
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_name = note_path.stem
        note_suffix = note_path.suffix
        backup_name = f"{note_name}--{timestamp_str}{note_suffix}.bak"
        
        # Create mirrored directory structure in history dir
        # For simplicity, we'll store all backups in history_dir with a flat structure
        # but include the original path in the backup name to avoid collisions
        backup_path = self.history_dir / backup_name
        
        # If there's a collision, add a counter
        counter = 1
        original_backup_path = backup_path
        while backup_path.exists():
            backup_name = f"{note_name}--{timestamp_str}_{counter}{note_suffix}.bak"
            backup_path = self.history_dir / backup_name
            counter += 1
        
        try:
            # Copy the file
            shutil.copy2(note_path, backup_path)
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Failed to create backup: {e}")
        
        # Add entry to index
        entries = self._load_index()
        entry = HistoryEntry(
            note_path=str(note_path),
            backup_path=str(backup_path),
            timestamp=datetime.now().isoformat()
        )
        entries.append(entry)
        self._save_index(entries)
    
    def list_history(self, note_path: Path, limit: int = 10) -> List[HistoryEntry]:
        """
        Return the most recent history entries for the given note, up to 'limit'.
        
        Args:
            note_path: Path to the note file to get history for
            limit: Maximum number of entries to return (default: 10)
            
        Returns:
            List of HistoryEntry objects, sorted by timestamp (most recent first)
        """
        note_path_str = str(Path(note_path).resolve())
        entries = self._load_index()
        
        # Filter entries for this specific note
        matching_entries = [e for e in entries if e.note_path == note_path_str]
        
        # Sort by timestamp (most recent first)
        matching_entries.sort(key=lambda e: e.timestamp, reverse=True)
        
        # Limit results
        return matching_entries[:limit]
    
    def restore_version(self, entry: HistoryEntry) -> bool:
        """
        Restore the note from the given backup_path.
        
        Copies the backup file back to the original note location.
        Does not remove the entry from history (unlike undo_last).
        
        Args:
            entry: HistoryEntry containing the backup to restore
            
        Returns:
            True if restore was successful, False otherwise
            
        Raises:
            FileNotFoundError: If the backup file doesn't exist
            RuntimeError: If restore operation fails
        """
        backup_path = Path(entry.backup_path)
        original_path = Path(entry.note_path)
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        try:
            # Ensure the directory exists
            original_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy backup back to original location
            shutil.copy2(backup_path, original_path)
            return True
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Failed to restore file: {e}")
    
    def undo_last(self, note_path: Optional[Path] = None) -> bool:
        """
        Undo the last operation for a note or the most recent operation overall.
        
        Args:
            note_path: If provided, undo the last backup for this specific note.
                      If None, undo the most recent backup across all notes.
        
        Returns:
            True if an undo operation was performed, False otherwise
        """
        entries = self._load_index()
        
        if not entries:
            print("No history entries found. Nothing to undo.")
            return False
        
        # Find the entry to restore
        entry_to_restore: Optional[HistoryEntry] = None
        
        if note_path is not None:
            # Find the most recent entry for this specific note
            note_path_str = str(Path(note_path).resolve())
            matching_entries = [e for e in entries if e.note_path == note_path_str]
            if matching_entries:
                # Sort by timestamp (most recent last)
                matching_entries.sort(key=lambda e: e.timestamp)
                entry_to_restore = matching_entries[-1]
        else:
            # Find the most recent entry overall
            entries.sort(key=lambda e: e.timestamp)
            entry_to_restore = entries[-1]
        
        if entry_to_restore is None:
            if note_path is not None:
                print(f"No history found for note: {note_path}")
            else:
                print("No history entries found.")
            return False
        
        # Verify backup file exists
        backup_path = Path(entry_to_restore.backup_path)
        if not backup_path.exists():
            print(f"Warning: Backup file not found: {backup_path}")
            print("Hint: The backup may have been deleted manually.")
            # Remove the entry from index
            entries.remove(entry_to_restore)
            self._save_index(entries)
            return False
        
        # Restore the file
        original_path = Path(entry_to_restore.note_path)
        try:
            # Ensure the directory exists
            original_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy backup back to original location
            shutil.copy2(backup_path, original_path)
            print(f"Restored: {original_path}")
            
            # Remove the entry from index (undo is one-time)
            entries.remove(entry_to_restore)
            self._save_index(entries)
            
            return True
        except (PermissionError, OSError) as e:
            print(f"Error: Failed to restore file: {e}")
            print(f"Hint: Check that you have write permissions for '{original_path.parent}'")
            return False


