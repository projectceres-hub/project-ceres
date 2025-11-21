"""
Scheduler module for Project Ceres (Compatibility Shim).

This module provides backwards compatibility by re-exporting the scheduler
implementation from the automation engine package.

The canonical implementation now lives in:
- automation.job (Job dataclass)
- automation.task_scheduler (Scheduler class and register_default_jobs function)

This file is kept for backwards compatibility. New code should import directly
from automation.job or automation.task_scheduler.
"""

# Re-export from automation package for backwards compatibility
from automation.job import Job
from automation.task_scheduler import Scheduler, register_default_jobs

__all__ = ["Job", "Scheduler", "register_default_jobs"]

