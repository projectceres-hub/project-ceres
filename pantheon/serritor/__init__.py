"""
Serritor domain for Project Ceres.

This domain handles automation and background jobs - keeping the system running
smoothly through scheduled tasks, recurring maintenance, and ongoing operations.

Public API exports from the automation engine modules.
"""

from .job import Job
from .task_scheduler import (
    Scheduler,
    register_default_jobs,
    register_template_sync_job,
    register_srd_index_job,
    register_session_reminder_job,
    register_cache_clean_job,
    register_snapshot_job,
)
from .jobs import (
    backup_vault,
    register_backup_job,
    sync_templates_job,
    rebuild_srd_index_job,
    session_reminder_job,
    clean_cache_job,
    daily_snapshot_job,
)

__all__ = [
    "Job",
    "Scheduler",
    "register_default_jobs",
    "register_template_sync_job",
    "register_srd_index_job",
    "register_session_reminder_job",
    "register_cache_clean_job",
    "register_snapshot_job",
    "backup_vault",
    "register_backup_job",
    "sync_templates_job",
    "rebuild_srd_index_job",
    "session_reminder_job",
    "clean_cache_job",
    "daily_snapshot_job",
]

