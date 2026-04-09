"""
Task scheduler module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.serritor.task_scheduler` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `automation.task_scheduler` will
continue to work, but new code should import from `pantheon.serritor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.serritor.task_scheduler import (
    Scheduler,
    register_default_jobs,
    register_template_sync_job,
    register_srd_index_job,
    register_session_reminder_job,
    register_cache_clean_job,
    register_snapshot_job,
)

__all__ = [
    "Scheduler",
    "register_default_jobs",
    "register_template_sync_job",
    "register_srd_index_job",
    "register_session_reminder_job",
    "register_cache_clean_job",
    "register_snapshot_job",
]
