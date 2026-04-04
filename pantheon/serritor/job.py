"""
Job module for Project Ceres automation engine.

Provides the Job dataclass for representing scheduled tasks.

This module is part of the Serritor domain in the Pantheon architecture,
responsible for automation and background jobs.
"""

from dataclasses import dataclass
from typing import Callable, Optional
from datetime import datetime


@dataclass
class Job:
    """
    Represents a scheduled job.
    
    Attributes:
        name: Unique identifier for the job
        interval_seconds: Time interval between job executions in seconds
        callable: Function to execute when the job runs
        last_run: Timestamp of the last execution (None if never run)
    """
    name: str
    interval_seconds: float
    callable: Callable[[], None]
    last_run: Optional[datetime] = None
    
    def should_run(self) -> bool:
        """
        Check if the job should run based on its interval.
        
        Returns:
            True if enough time has passed since last run, False otherwise
        """
        if self.last_run is None:
            return True
        
        elapsed = (datetime.now() - self.last_run).total_seconds()
        return elapsed >= self.interval_seconds
    
    def mark_run(self) -> None:
        """Mark the job as having been executed."""
        self.last_run = datetime.now()

