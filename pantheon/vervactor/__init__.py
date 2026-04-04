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
]

