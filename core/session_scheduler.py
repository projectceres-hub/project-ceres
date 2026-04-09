"""
Session Scheduler module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.promitor.session_scheduler` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.session_scheduler` will
continue to work, but new code should import from `pantheon.promitor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.promitor.session_scheduler import (
    SessionInfo,
    create_ics_file,
    get_local_timezone,
    format_pretty_datetime,
    generate_share_message,
    generate_session_prompt,
    schedule_next_session,
    get_next_session_info,
)

__all__ = [
    "SessionInfo",
    "create_ics_file",
    "get_local_timezone",
    "format_pretty_datetime",
    "generate_share_message",
    "generate_session_prompt",
    "schedule_next_session",
    "get_next_session_info",
]
