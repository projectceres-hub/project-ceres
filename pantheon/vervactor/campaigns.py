"""
Campaigns module for Project Ceres.

Provides functionality for managing TTRPG campaigns, including creation
of campaign folders, party members, NPCs, locations, and session notes.

This module is part of the Vervactor domain in the Pantheon architecture,
responsible for campaign creation and vault setup.

Note file creation is delegated to the Insitor domain
(``pantheon.insitor.create_note``).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal, TYPE_CHECKING
from datetime import datetime

from pantheon.insitor import NoteSpec, create_note

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


@dataclass
class Campaign:
    """
    Represents a TTRPG campaign.
    
    Attributes:
        name: Campaign name
        path: Path to the campaign directory
    """
    name: str
    path: Path


@dataclass
class Character:
    """
    Represents a character (PC or NPC).
    
    Attributes:
        name: Character name
        campaign: Campaign name
        role: Character role ("pc" or "npc")
        attitude: NPC attitude (None for PCs, one of: "ally", "friendly", "neutral", "adversarial", "antagonist")
    """
    name: str
    campaign: str
    role: Literal["pc", "npc"]
    attitude: Optional[str] = None


@dataclass
class Location:
    """
    Represents a location in a campaign.
    
    Attributes:
        name: Location name
        campaign: Campaign name
    """
    name: str
    campaign: str


def create_campaign(name: str, config: "Config") -> Campaign:
    """
    Create a new campaign with the required folder structure.
    
    Creates the following structure under the current vault:
    Campaigns/<CampaignName>/
      _campaign.md
      Party/
      NPCs/
        Ally/
        Friendly/
        Neutral/
        Adversarial/
        Antagonist/
      Locations/
      Sessions/
    
    Args:
        name: Campaign name
        config: Config object containing vault information
        
    Returns:
        Campaign object representing the created campaign
        
    Raises:
        ValueError: If current_vault is not set or campaign name is invalid
        OSError: If directories cannot be created or files cannot be written
        PermissionError: If permissions are insufficient
    """
    if not config.current_vault:
        raise ValueError("No current vault set")
    
    if config.current_vault not in config.vaults:
        raise ValueError(f"Current vault '{config.current_vault}' not found in vaults")
    
    vault_path = Path(config.vaults[config.current_vault])
    
    if not vault_path.exists() or not vault_path.is_dir():
        raise ValueError(f"Vault path does not exist or is not a directory: {vault_path}")
    
    # Sanitize campaign name for use in paths
    safe_name = name.strip()
    if not safe_name:
        raise ValueError("Campaign name cannot be empty")
    
    # Create campaign directory
    campaigns_dir = vault_path / "Campaigns"
    campaign_dir = campaigns_dir / safe_name
    
    # Check if campaign already exists
    if campaign_dir.exists():
        raise ValueError(f"Campaign '{safe_name}' already exists")
    
    try:
        # Create campaign directory tree
        campaign_dir.mkdir(parents=True, exist_ok=True)
        (campaign_dir / "Party").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "NPCs").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "NPCs" / "Ally").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "NPCs" / "Friendly").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "NPCs" / "Neutral").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "NPCs" / "Adversarial").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "NPCs" / "Antagonist").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "Locations").mkdir(parents=False, exist_ok=True)
        (campaign_dir / "Sessions").mkdir(parents=False, exist_ok=True)
        
        # _campaign.md via Insitor
        folder = campaign_dir.relative_to(vault_path).as_posix()
        spec = NoteSpec(
            title="_campaign",
            folder=folder,
            frontmatter={
                "type": "campaign",
                "name": safe_name,
                "status": "active",
            },
            body=f"# {safe_name}\n\n## Campaign Overview\n\n",
        )
        create_note(spec, config)
        
        print(f"Campaign '{safe_name}' created successfully at: {campaign_dir.relative_to(vault_path)}")
        
        return Campaign(name=safe_name, path=campaign_dir)
        
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating campaign '{safe_name}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create campaign '{safe_name}': {e}")


def create_party_member(campaign: Campaign, name: str, config: "Config") -> Path:
    """
    Create a new party member (PC) file.
    
    Creates Party/<Name>.md with appropriate YAML frontmatter.
    
    Args:
        campaign: Campaign object
        name: Character name
        config: Config object (unused, kept for consistency)
        
    Returns:
        Path to the created character file
        
    Raises:
        ValueError: If character name is invalid
        OSError: If file cannot be created
        PermissionError: If permissions are insufficient
    """
    safe_name = name.strip()
    if not safe_name:
        raise ValueError("Character name cannot be empty")
    
    file_stem = safe_name.replace(" ", "_")
    character_file = campaign.path / "Party" / f"{file_stem}.md"
    
    if character_file.exists():
        raise ValueError(f"Party member '{safe_name}' already exists")
    
    vault_path = Path(config.vaults[config.current_vault])
    folder = (campaign.path / "Party").relative_to(vault_path).as_posix()
    
    try:
        spec = NoteSpec(
            title=file_stem,
            folder=folder,
            frontmatter={
                "type": "character",
                "role": "pc",
                "campaign": campaign.name,
            },
            body=f"# {safe_name}\n\n## Character Details\n\n",
        )
        result = create_note(spec, config)
        
        print(f"Party member '{safe_name}' created: {result.name}")
        return result
        
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating party member '{safe_name}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create party member '{safe_name}': {e}")


def create_npc(campaign: Campaign, name: str, attitude: str, config: "Config") -> tuple[Path, bool]:
    """
    Create a new NPC file.
    
    Creates NPCs/<Attitude>/<Name>.md with appropriate YAML frontmatter.
    Automatically attempts to add a tag based on the attitude.
    
    Args:
        campaign: Campaign object
        name: Character name
        attitude: NPC attitude (one of: "ally", "friendly", "neutral", "adversarial", "antagonist")
        config: Config object (unused, kept for consistency)
        
    Returns:
        Tuple of (Path to the created character file, bool indicating if tag was successfully added)
        
    Raises:
        ValueError: If character name or attitude is invalid
        OSError: If file cannot be created
        PermissionError: If permissions are insufficient
    """
    safe_name = name.strip()
    if not safe_name:
        raise ValueError("Character name cannot be empty")
    
    valid_attitudes = ["ally", "friendly", "neutral", "adversarial", "antagonist"]
    attitude_lower = attitude.strip().lower()
    if attitude_lower not in valid_attitudes:
        raise ValueError(f"Invalid attitude '{attitude}'. Must be one of: {', '.join(valid_attitudes)}")
    
    file_stem = safe_name.replace(" ", "_")
    npc_dir = campaign.path / "NPCs" / attitude_lower.capitalize()
    character_file = npc_dir / f"{file_stem}.md"
    
    if character_file.exists():
        raise ValueError(f"NPC '{safe_name}' already exists in {attitude_lower} category")
    
    vault_path = Path(config.vaults[config.current_vault])
    folder = npc_dir.relative_to(vault_path).as_posix()
    
    try:
        spec = NoteSpec(
            title=file_stem,
            folder=folder,
            frontmatter={
                "type": "character",
                "role": "npc",
                "attitude": attitude_lower,
                "campaign": campaign.name,
            },
            body=f"# {safe_name}\n\n## Character Details\n\n",
        )
        result = create_note(spec, config)
        
        tag_name = attitude_lower.capitalize()
        tag_added = False
        try:
            from pantheon.obarator import add_tag
            add_tag(result, tag_name)
            tag_added = True
        except Exception as e:
            print(f"Warning: Failed to add tag '{tag_name}' to NPC '{safe_name}': {e}")
        
        print(f"NPC '{safe_name}' created in {attitude_lower} category: {result.name}")
        return result, tag_added
        
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating NPC '{safe_name}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create NPC '{safe_name}': {e}")


def create_location(campaign: Campaign, name: str, config: "Config") -> Path:
    """
    Create a new location file.
    
    Creates Locations/<Name>.md with appropriate YAML frontmatter.
    
    Args:
        campaign: Campaign object
        name: Location name
        config: Config object (unused, kept for consistency)
        
    Returns:
        Path to the created location file
        
    Raises:
        ValueError: If location name is invalid
        OSError: If file cannot be created
        PermissionError: If permissions are insufficient
    """
    safe_name = name.strip()
    if not safe_name:
        raise ValueError("Location name cannot be empty")
    
    file_stem = safe_name.replace(" ", "_")
    location_file = campaign.path / "Locations" / f"{file_stem}.md"
    
    if location_file.exists():
        raise ValueError(f"Location '{safe_name}' already exists")
    
    vault_path = Path(config.vaults[config.current_vault])
    folder = (campaign.path / "Locations").relative_to(vault_path).as_posix()
    
    try:
        spec = NoteSpec(
            title=file_stem,
            folder=folder,
            frontmatter={
                "type": "location",
                "campaign": campaign.name,
            },
            body=f"# {safe_name}\n\n## Location Details\n\n",
        )
        result = create_note(spec, config)
        
        print(f"Location '{safe_name}' created: {result.name}")
        return result
        
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating location '{safe_name}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create location '{safe_name}': {e}")


def find_campaign(name: str, config: "Config") -> Optional[Campaign]:
    """
    Find a campaign by name in the current vault.
    
    Args:
        name: Campaign name
        config: Config object containing vault information
        
    Returns:
        Campaign object if found, None otherwise
    """
    if not config.current_vault:
        return None
    
    if config.current_vault not in config.vaults:
        return None
    
    vault_path = Path(config.vaults[config.current_vault])
    campaigns_dir = vault_path / "Campaigns"
    campaign_dir = campaigns_dir / name.strip()
    
    if campaign_dir.exists() and campaign_dir.is_dir():
        return Campaign(name=name.strip(), path=campaign_dir)
    
    return None


def _get_next_session_number(campaign: Campaign) -> int:
    """
    Get the next session number by scanning existing Session-XXX files.
    
    Scans the Sessions/ directory for files matching the pattern Session-XXX-*.md
    and returns the next number in sequence.
    
    Args:
        campaign: Campaign object
        
    Returns:
        Next session number (1 if no sessions exist)
    """
    sessions_dir = campaign.path / "Sessions"
    
    if not sessions_dir.exists():
        return 1
    
    # Pattern to match: Session-XXX-*.md where XXX is a number
    pattern = re.compile(r'^Session-(\d+)-')
    max_number = 0
    
    try:
        for file in sessions_dir.iterdir():
            if file.is_file() and file.name.endswith('.md'):
                match = pattern.match(file.name)
                if match:
                    session_num = int(match.group(1))
                    max_number = max(max_number, session_num)
    except (OSError, PermissionError):
        # If we can't read the directory, start at 1
        pass
    
    return max_number + 1


def _find_previous_session(campaign: Campaign) -> Optional[Path]:
    """
    Find the most recent previous session file.
    
    Args:
        campaign: Campaign object
        
    Returns:
        Path to the previous session file, or None if no sessions exist
    """
    sessions_dir = campaign.path / "Sessions"
    
    if not sessions_dir.exists():
        return None
    
    # Pattern to match: Session-XXX-*.md where XXX is a number
    pattern = re.compile(r'^Session-(\d+)-')
    sessions = []
    
    try:
        for file in sessions_dir.iterdir():
            if file.is_file() and file.name.endswith('.md'):
                match = pattern.match(file.name)
                if match:
                    session_num = int(match.group(1))
                    sessions.append((session_num, file))
    except (OSError, PermissionError):
        return None
    
    if not sessions:
        return None
    
    # Sort by session number (descending) and return the most recent
    sessions.sort(key=lambda x: x[0], reverse=True)
    return sessions[0][1]


def create_session(campaign: Campaign, title: str, config: "Config") -> Path:
    """
    Create a new session note in the campaign's Sessions/ directory.
    
    Creates a session note with automatic numbering, proper frontmatter, and
    automatic linking to the campaign and previous session.
    
    File naming: Session-XXX-<SanitizedTitle>.md
    Frontmatter includes: type, campaign, number, title, date
    
    Args:
        campaign: Campaign object
        title: Session title
        config: Config object containing vault information
        
    Returns:
        Path to the created session file
        
    Raises:
        ValueError: If session title is invalid or campaign doesn't have Sessions/ directory
        OSError: If file cannot be created
        PermissionError: If permissions are insufficient
    """
    safe_title = title.strip()
    if not safe_title:
        raise ValueError("Session title cannot be empty")
    
    session_number = _get_next_session_number(campaign)
    
    sanitized = re.sub(r'[<>:"/\\|?*]', '', safe_title)
    sanitized = sanitized.replace(" ", "-")[:50]
    
    note_title = f"Session-{session_number:03d}-{sanitized}"
    sessions_dir = campaign.path / "Sessions"
    
    if not sessions_dir.exists():
        try:
            sessions_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            raise OSError(f"Failed to create Sessions directory: {e}")
    
    session_file = sessions_dir / f"{note_title}.md"
    if session_file.exists():
        raise ValueError(f"Session file '{note_title}.md' already exists")
    
    today = datetime.now().strftime("%Y-%m-%d")
    previous_session = _find_previous_session(campaign)
    
    # Build body
    body = (
        f"# Session {session_number}: {safe_title}\n\n"
        f"**Campaign:** [[_campaign]]\n\n"
    )
    if previous_session:
        body += f"**Previous Session:** [[{previous_session.stem}]]\n\n"
    body += "## Attendees\n\n- \n\n## Summary\n\n\n## Notable NPCs\n\n- \n\n## Events & Notes\n\n"
    
    vault_path = Path(config.vaults[config.current_vault])
    folder = sessions_dir.relative_to(vault_path).as_posix()
    
    try:
        spec = NoteSpec(
            title=note_title,
            folder=folder,
            frontmatter={
                "type": "session",
                "campaign": campaign.name,
                "number": session_number,
                "title": safe_title,
                "date": today,
            },
            body=body,
        )
        result = create_note(spec, config)
        
        print(f"Session {session_number} '{safe_title}' created: {result.name}")
        return result
        
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating session '{safe_title}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create session '{safe_title}': {e}")

