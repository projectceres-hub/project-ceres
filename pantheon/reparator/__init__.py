"""
Reparator domain for Project Ceres.

This domain handles templates, structured note preparation, and formatting tools -
preparing the foundation for consistent note creation and organization.

Public API exports from the templates module.
"""

from .templates import (
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

