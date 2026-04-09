"""
Campaigns module for Project Ceres (Backward Compatibility Shim).

**Note:** The canonical implementation of this module has moved to
`pantheon.vervactor.campaigns` as part of the Pantheon architecture migration.

This module provides backward compatibility by re-exporting the public API
from the new location. Existing code importing from `core.campaigns` will
continue to work, but new code should import from `pantheon.vervactor` instead.

This shim will be maintained during the migration period and may be removed
in a future version once all imports have been updated.
"""

from pantheon.vervactor.campaigns import (
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
