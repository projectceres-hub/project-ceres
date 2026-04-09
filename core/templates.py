"""
Templates module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.reparator.templates` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.templates` will
continue to work, but new code should import from `pantheon.reparator` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.reparator.templates import (
    find_all_templates,
    cmd_showtemplates,
    cmd_createtemplate,
    cmd_uploadtemplate,
    cmd_uploadalltemplates,
    cmd_deletetemplate,
    apply_template_preview,
    sync_templates_from_remote,
)

__all__ = [
    "find_all_templates",
    "cmd_showtemplates",
    "cmd_createtemplate",
    "cmd_uploadtemplate",
    "cmd_uploadalltemplates",
    "cmd_deletetemplate",
    "apply_template_preview",
    "sync_templates_from_remote",
]
