"""
Fantasy Grounds integration module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.messor.fgu` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.fgu_integration` will
continue to work, but new code should import from `pantheon.messor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.messor.fgu import (
    FGUEvent,
    parse_fgu_chat_log,
    attach_fgu_log_to_session,
)

__all__ = [
    "FGUEvent",
    "parse_fgu_chat_log",
    "attach_fgu_log_to_session",
]
