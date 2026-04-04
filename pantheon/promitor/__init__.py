"""
Promitor domain for Project Ceres.

This domain handles distribution - summaries, exports, calendar files, and other
ways Ceres "hands results" to the GM and players.

Public API exports from the session scheduler module.
"""

from .session_scheduler import (
    SessionInfo,
    create_ics_file,
    get_local_timezone,
    format_pretty_datetime,
    generate_share_message,
    generate_session_prompt,
    schedule_next_session,
    get_next_session_info,
    plan_session_interactively,
    build_session_event_package_from_scheduler,
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
    "plan_session_interactively",
    "build_session_event_package_from_scheduler",
]

