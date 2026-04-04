"""
Conditor domain for Project Ceres.

This domain handles storage, backups, history, and undo operations - managing
the long-term preservation and versioning of vault content.

Public API exports from the history and backup modules.
"""

from .history import (
    HistoryEntry,
    HistoryManager,
)
from .backup import (
    create_vault_backup,
    prune_old_backups,
)

__all__ = [
    # History
    "HistoryEntry",
    "HistoryManager",
    # Backup
    "create_vault_backup",
    "prune_old_backups",
]


