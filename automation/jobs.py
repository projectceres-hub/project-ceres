"""
Jobs module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.serritor.jobs` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `automation.jobs` will
continue to work, but new code should import from `pantheon.serritor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.serritor.jobs import (
    backup_vault,
    register_backup_job,
    sync_templates_job,
    rebuild_srd_index_job,
    session_reminder_job,
    clean_cache_job,
    daily_snapshot_job,
)

__all__ = [
    "backup_vault",
    "register_backup_job",
    "sync_templates_job",
    "rebuild_srd_index_job",
    "session_reminder_job",
    "clean_cache_job",
    "daily_snapshot_job",
]
