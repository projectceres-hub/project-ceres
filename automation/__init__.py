"""
Automation engine package for Project Ceres.

Provides job scheduling and task automation functionality.
"""

from automation.job import Job
from automation.task_scheduler import Scheduler, register_default_jobs

__all__ = ["Job", "Scheduler", "register_default_jobs"]

