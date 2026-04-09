"""
History module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.conditor.history` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.history` will
continue to work, but new code should import from `pantheon.conditor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.conditor.history import (
    HistoryEntry,
    HistoryManager,
)

__all__ = [
    "HistoryEntry",
    "HistoryManager",
]
