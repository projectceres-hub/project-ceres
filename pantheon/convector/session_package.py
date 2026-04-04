"""
Session Event Package module for Project Ceres.

Provides data structures and utilities for packaging session scheduling data
into formats suitable for external systems (e.g., Discord bots, webhooks).

This module is part of the Convector domain in the Pantheon architecture,
responsible for data transport between Ceres and external systems.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class SessionEventPackage:
    """
    A structured package of session event data ready for external distribution.
    
    This dataclass contains all information needed to share a scheduled session
    with external systems like Discord bots, webhooks, or calendar services.
    
    Attributes:
        title: Session title/name
        description: Optional session description
        start_iso: ISO8601 datetime string in UTC or with timezone
        end_iso: ISO8601 datetime string, or None if using duration_minutes
        duration_minutes: Duration of the session in minutes
        timezone: Timezone identifier (e.g., "America/New_York")
        ics_path: Path to the .ics calendar file on disk
        ics_filename: Convenience field containing ics_path.name
        message_text: The full "Next Session" formatted message from Promitor
        google_calendar_url: Optional Google Calendar deep-link URL
    """
    title: str
    description: Optional[str]
    start_iso: str
    end_iso: Optional[str]
    duration_minutes: int
    timezone: str
    ics_path: Path
    ics_filename: str
    message_text: str
    google_calendar_url: Optional[str] = None


def build_session_event_package(
    *,
    title: str,
    description: Optional[str],
    start_dt: datetime,
    duration_minutes: int,
    timezone: str,
    ics_path: Path,
    message_text: str,
    google_calendar_url: Optional[str] = None,
) -> SessionEventPackage:
    """
    Construct a SessionEventPackage from raw session scheduling data.
    
    This function takes the output from Promitor's session scheduler and
    packages it into a structured format suitable for external systems.
    
    Args:
        title: Session title/name
        description: Optional session description
        start_dt: Session start datetime (timezone-aware or naive)
        duration_minutes: Duration of the session in minutes
        timezone: Timezone identifier (e.g., "America/New_York")
        ics_path: Path to the .ics calendar file
        message_text: The formatted "Next Session" message from Promitor
        google_calendar_url: Optional Google Calendar deep-link URL
        
    Returns:
        SessionEventPackage with all fields populated
        
    Note:
        - end_iso is computed from start_dt + duration_minutes
        - start_iso and end_iso are formatted as ISO8601 strings
        - ics_filename is automatically extracted from ics_path.name
    """
    # Calculate end datetime
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    
    # Format as ISO8601 strings
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()
    
    # Extract filename from path
    ics_filename = ics_path.name
    
    return SessionEventPackage(
        title=title,
        description=description,
        start_iso=start_iso,
        end_iso=end_iso,
        duration_minutes=duration_minutes,
        timezone=timezone,
        ics_path=ics_path,
        ics_filename=ics_filename,
        message_text=message_text,
        google_calendar_url=google_calendar_url,
    )


def session_event_to_dict(pkg: SessionEventPackage) -> dict[str, object]:
    """
    Convert a SessionEventPackage into a JSON-serializable dictionary.
    
    This function prepares the package for transmission to external systems
    via JSON APIs, webhooks, or other text-based protocols.
    
    Args:
        pkg: SessionEventPackage to convert
        
    Returns:
        Dictionary with all package fields, with Path objects converted to strings
        
    Note:
        - ics_path is serialized as a string (str(pkg.ics_path))
        - All field names are snake_case for consistency
        - None values are preserved in the dictionary
    """
    return {
        "title": pkg.title,
        "description": pkg.description,
        "start_iso": pkg.start_iso,
        "end_iso": pkg.end_iso,
        "duration_minutes": pkg.duration_minutes,
        "timezone": pkg.timezone,
        "ics_path": str(pkg.ics_path),
        "ics_filename": pkg.ics_filename,
        "message_text": pkg.message_text,
        "google_calendar_url": pkg.google_calendar_url,
    }


def write_session_event_json(pkg: SessionEventPackage, output_path: Path) -> None:
    """
    Write the given SessionEventPackage to a JSON file at output_path.
    
    This function serializes the package to JSON format suitable for external
    systems like Discord bots or webhooks to consume.
    
    Args:
        pkg: SessionEventPackage to serialize
        output_path: Path where the JSON file should be written
        
    Raises:
        OSError: If the file cannot be written (permission denied, disk full, etc.)
        
    Note:
        - Creates parent directories if they don't exist
        - Uses UTF-8 encoding
        - Pretty-prints JSON with 2-space indentation
    """
    data = session_event_to_dict(pkg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

