"""
Vervactor domain for Project Ceres.

This domain handles campaign creation and vault setup - the foundational
work of preparing the workspace for a new campaign, establishing the
directory hierarchy, and creating initial campaign metadata.

Public API exports from the campaigns module.
"""

from .campaigns import (
    Campaign,
    Character,
    Location,
    create_campaign,
    create_party_member,
    create_npc,
    create_location,
    find_campaign,
    create_session,
)
from .workspace import (
    AudioSourceAdapter,
    AudioSourceState,
    PanelAudioSourceAdapter,
    WorkspaceObjectRef,
    WorkspaceState,
    load_scene_data,
    load_workspace_state,
    save_scene_data,
    save_workspace_state,
    set_current_object,
    workspace_dir,
)

__all__ = [
    "Campaign",
    "Character",
    "Location",
    "create_campaign",
    "create_party_member",
    "create_npc",
    "create_location",
    "find_campaign",
    "create_session",
    "AudioSourceAdapter",
    "AudioSourceState",
    "PanelAudioSourceAdapter",
    "WorkspaceObjectRef",
    "WorkspaceState",
    "load_scene_data",
    "load_workspace_state",
    "save_scene_data",
    "save_workspace_state",
    "set_current_object",
    "workspace_dir",
]

