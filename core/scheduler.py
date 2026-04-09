"""
Scheduler module for Project Ceres (Compatibility Shim).

This module provides backwards compatibility by re-exporting the scheduler
implementation from the Pantheon Serritor automation engine.

The canonical implementation now lives in:
- pantheon.serritor.job (Job dataclass)
- pantheon.serritor.task_scheduler (Scheduler class and register_default_jobs function)

This file is kept for backwards compatibility. New code should import directly
from pantheon.serritor.
"""

# Re-export from Pantheon Serritor domain for backwards compatibility
from pantheon.serritor import Job, Scheduler, register_default_jobs

__all__ = ["Job", "Scheduler", "register_default_jobs"]

