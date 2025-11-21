"""
Task scheduler module for Project Ceres automation engine.

Provides the Scheduler class for managing and executing periodic tasks.
"""

import time
import threading
from typing import Callable, Dict, Optional, Any
from datetime import datetime

from automation.job import Job


class Scheduler:
    """
    Lightweight job scheduler for periodic task execution.
    
    Runs jobs in a background thread, checking for pending jobs at regular intervals.
    No global state - external code controls creation and lifecycle.
    """
    
    def __init__(self, check_interval_seconds: float = 1.0) -> None:
        """
        Initialize the scheduler.
        
        Args:
            check_interval_seconds: How often to check for pending jobs (default: 1.0)
        """
        self._jobs: Dict[str, Job] = {}
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._check_interval: float = check_interval_seconds
        self._lock: threading.Lock = threading.Lock()
    
    def register_job(
        self,
        name: str,
        interval_seconds: float,
        callable: Callable[[], None]
    ) -> None:
        """
        Register a new job with the scheduler.
        
        Args:
            name: Unique identifier for the job
            interval_seconds: Time interval between executions in seconds
            callable: Function to execute (must take no arguments)
            
        Raises:
            ValueError: If a job with the same name already exists
        """
        with self._lock:
            if name in self._jobs:
                raise ValueError(f"Job '{name}' is already registered")
            
            self._jobs[name] = Job(
                name=name,
                interval_seconds=interval_seconds,
                callable=callable
            )
    
    def unregister_job(self, name: str) -> None:
        """
        Remove a job from the scheduler.
        
        Args:
            name: Name of the job to remove
            
        Raises:
            KeyError: If the job doesn't exist
        """
        with self._lock:
            if name not in self._jobs:
                raise KeyError(f"Job '{name}' is not registered")
            del self._jobs[name]
    
    def start(self) -> None:
        """
        Start the scheduler in a background thread.
        
        Raises:
            RuntimeError: If the scheduler is already running
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Scheduler is already running")
            
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
    
    def stop(self) -> None:
        """
        Stop the scheduler and wait for the background thread to finish.
        
        Does nothing if the scheduler is not running.
        """
        with self._lock:
            if not self._running:
                return
            
            self._running = False
        
        # Wait for thread to finish (with timeout to avoid hanging)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
    
    def run_pending_once(self) -> int:
        """
        Run all pending jobs once (synchronous).
        
        Useful for testing or manual execution without starting the scheduler.
        
        Returns:
            Number of jobs that were executed
        """
        executed_count = 0
        
        with self._lock:
            for job in self._jobs.values():
                if job.should_run():
                    try:
                        job.callable()
                        job.mark_run()
                        executed_count += 1
                    except Exception as e:
                        # Log error but continue with other jobs
                        print(f"Error executing job '{job.name}': {e}")
        
        return executed_count
    
    def _run_loop(self) -> None:
        """
        Main scheduler loop running in background thread.
        
        Continuously checks for pending jobs and executes them.
        """
        while self._running:
            self.run_pending_once()
            time.sleep(self._check_interval)
    
    def is_running(self) -> bool:
        """
        Check if the scheduler is currently running.
        
        Returns:
            True if running, False otherwise
        """
        with self._lock:
            return self._running
    
    def get_job_count(self) -> int:
        """
        Get the number of registered jobs.
        
        Returns:
            Number of registered jobs
        """
        with self._lock:
            return len(self._jobs)
    
    def list_jobs(self) -> list[str]:
        """
        Get a list of all registered job names.
        
        Returns:
            List of job names
        """
        with self._lock:
            return list(self._jobs.keys())


def register_template_sync_job(
    scheduler: Scheduler,
    context: Any,
    interval_seconds: int = 6 * 60 * 60
) -> None:
    """
    Register a recurring 'template-sync' job that runs every N seconds.
    
    Registers a job that syncs templates from a remote source (if configured)
    at the specified interval. Default interval is 6 hours (21600 seconds).
    
    Args:
        scheduler: Scheduler instance to register the job with
        context: Context object (should be Config or have compatible attributes):
            - templates_remote_url: Optional URL to remote template source
            - templates_local_path: Optional path to local templates directory
            - default_vault_name: Name of default vault
            - vaults: Dictionary mapping vault names to paths
        interval_seconds: Time interval between syncs in seconds (default: 21600 = 6 hours)
    """
    from automation.jobs import sync_templates_job
    
    def template_sync_job() -> None:
        """Wrapper function for the template sync job."""
        sync_templates_job(context)
    
    try:
        scheduler.register_job(
            name="template-sync",
            interval_seconds=float(interval_seconds),
            callable=template_sync_job
        )
    except ValueError:
        # Job already registered, skip
        pass


def register_default_jobs(scheduler: Scheduler, context: Any) -> None:
    """
    Register default recurring jobs with the scheduler.
    
    This function sets up standard background jobs that should run periodically.
    Jobs are registered but not started - call scheduler.start() to begin execution.
    
    Args:
        scheduler: Scheduler instance to register jobs with
        context: Context object containing necessary dependencies for jobs.
                 Expected attributes:
                 - obsidian_json_path: Path to Obsidian config file
                 - vaults: Dictionary of vault names to paths
                 - ignored_vaults: List of ignored vault names
                 - save_vaults: Callable to save vaults dictionary
                 - current_vault: Name of the current active vault
                 - templates_remote_url: Optional URL for template sync (for template-sync job)
                 - templates_local_path: Optional path for template sync
                 - default_vault_name: Name of default vault
    """
    # Sync vaults job - runs every 10 minutes
    def sync_vaults_job() -> None:
        """Periodically sync vaults from Obsidian configuration."""
        from core.vaults import sync_obsidian_vaults
        sync_obsidian_vaults(
            context.obsidian_json_path,
            context.vaults,
            context.ignored_vaults,
            context.save_vaults
        )
    
    try:
        scheduler.register_job(
            name="sync-vaults",
            interval_seconds=600.0,  # 10 minutes
            callable=sync_vaults_job
        )
    except ValueError:
        # Job already registered, skip
        pass
    
    # Vault backup job - runs every 24 hours
    # Note: context should be a Config object for backup job
    # If using SchedulerContext, ensure it has current_vault and vaults attributes
    try:
        from automation.jobs import register_backup_job
        # Pass context (Config or SchedulerContext with compatible attributes)
        register_backup_job(scheduler, context, interval_seconds=24 * 60 * 60)  # 24 hours
    except ValueError:
        # Job already registered, skip
        pass
    
    # Template sync job - runs every 6 hours (only if remote URL is configured)
    if hasattr(context, 'templates_remote_url') and context.templates_remote_url:
        try:
            register_template_sync_job(scheduler, context, interval_seconds=6 * 60 * 60)  # 6 hours
        except ValueError:
            # Job already registered, skip
            pass

