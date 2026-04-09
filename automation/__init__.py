"""
Automation engine package for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this package has moved to
`pantheon.serritor` as part of the Pantheon architecture migration.

This package provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `automation` will
continue to work, but new code should import from `pantheon.serritor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from automation.job import Job
from automation.task_scheduler import Scheduler, register_default_jobs

__all__ = ["Job", "Scheduler", "register_default_jobs"]

