"""
Session Scheduler module for Project Ceres.

Creates calendar invite files (.ics) for TTRPG sessions and generates
easy-to-share messages with clickable calendar links.
"""

import os
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None
        import time


@dataclass
class SessionInfo:
    """
    Information about a TTRPG session.
    
    Attributes:
        title: Session title/name
        start: Session start date and time
        end: Session end date and time
        description: Optional session description
    """
    title: str
    start: datetime
    end: datetime
    description: str = ""


def create_ics_file(info: SessionInfo, path: Path) -> Path:
    """
    Generate a valid ICS calendar file.
    
    Creates a VERSION:2.0 ICS file compatible with Android and iOS.
    
    Args:
        info: Session information
        path: File path where the ICS file should be created
        
    Returns:
        Path to the created ICS file
        
    Raises:
        OSError: If the file cannot be written
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Format datetimes for ICS (UTC format: YYYYMMDDTHHMMSSZ)
    def format_ics_datetime(dt: datetime) -> str:
        """Format datetime to ICS format."""
        return dt.strftime("%Y%m%dT%H%M%S")
    
    start_str = format_ics_datetime(info.start)
    end_str = format_ics_datetime(info.end)
    
    # Generate unique ID (using timestamp)
    uid = f"session-{int(info.start.timestamp())}@gm-assistant"
    
    # Escape special characters for ICS format
    def escape_ics_text(text: str) -> str:
        """Escape special characters in ICS text fields."""
        return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    
    # Create ICS content with proper line endings
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GM Assistant//Session Scheduler//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{format_ics_datetime(datetime.now())}",
        f"DTSTART:{start_str}",
        f"DTEND:{end_str}",
        f"SUMMARY:{escape_ics_text(info.title)}",
        f"DESCRIPTION:{escape_ics_text(info.description)}",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    ics_content = "\r\n".join(lines) + "\r\n"
    
    # Write file
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ics_content)
    except PermissionError as e:
        print(f"Error: Permission denied writing ICS file: {e}")
        print(f"Hint: Check that '{path.parent}' is writable.")
        raise
    except OSError as e:
        print(f"Error: Failed to write ICS file: {e}")
        print(f"Hint: Check that the directory exists and disk space is available.")
        raise
    except Exception as e:
        print(f"Error: Unexpected error writing ICS file: {e}")
        raise
    
    return path


def get_local_timezone():
    """
    Get the local system timezone.
    
    Returns:
        Timezone object (ZoneInfo or datetime.tzinfo), or None if unavailable
    """
    try:
        # Best method: use datetime.now() to get local timezone
        now = datetime.now()
        if now.tzinfo is not None:
            return now.tzinfo
        
        # If ZoneInfo is available, try to detect system timezone
        if ZoneInfo is not None:
            import time
            import os
            
            # Try TZ environment variable first (Unix-like)
            tz_env = os.environ.get('TZ')
            if tz_env:
                try:
                    return ZoneInfo(tz_env)
                except Exception:
                    pass
            
            # Try to get from system timezone name
            if hasattr(time, 'tzname'):
                tzname = time.tzname[0] if time.daylight == 0 else time.tzname[1]
                if tzname:
                    try:
                        return ZoneInfo(tzname)
                    except Exception:
                        pass
            
            # Windows fallback: use offset to create timezone
            if os.name == 'nt':
                offset_seconds = -time.timezone if not time.daylight else -time.altzone
                hours = offset_seconds // 3600
                # Create a simple timezone from offset
                from datetime import timezone, timedelta
                return timezone(timedelta(seconds=offset_seconds))
            
            # Unix-like: try /etc/timezone
            if os.path.exists('/etc/timezone'):
                try:
                    with open('/etc/timezone', 'r') as f:
                        tz_name = f.read().strip()
                        if tz_name:
                            return ZoneInfo(tz_name)
                except Exception:
                    pass
        
        # Final fallback: use system's local timezone via datetime
        # This creates a naive datetime, but we can work with it
        return None
    except Exception:
        return None


def format_pretty_datetime(dt: datetime, include_timezone: bool = True) -> str:
    """
    Format datetime in a pretty, human-readable format.
    
    Args:
        dt: Datetime to format
        include_timezone: Whether to include timezone information
        
    Returns:
        Formatted string like "Monday, March 25, 2025 at 7:00 PM (EST)"
    """
    # Format day of week and date
    day_name = dt.strftime("%A")
    date_str = dt.strftime("%B %d, %Y")
    
    # Format time (12-hour with AM/PM)
    time_str = dt.strftime("%I:%M %p").lstrip("0")
    
    # Format timezone if available
    tz_str = ""
    if include_timezone:
        if dt.tzinfo is not None:
            # Get timezone abbreviation
            tz_abbr = dt.strftime("%Z")
            if tz_abbr:
                tz_str = f" ({tz_abbr})"
            else:
                # Try to get offset
                offset = dt.utcoffset()
                if offset is not None:
                    hours = int(offset.total_seconds() / 3600)
                    sign = "+" if hours >= 0 else ""
                    tz_str = f" (UTC{sign}{hours})"
    
    return f"{day_name}, {date_str} at {time_str}{tz_str}"


def generate_share_message(info: SessionInfo, ics_path: Path) -> str:
    """
    Generate a formatted share message with calendar link.
    
    Uses pretty date/time formatting and includes timezone information.
    
    Args:
        info: Session information
        ics_path: Path to the ICS file
        
    Returns:
        Formatted message string with date, time, and calendar link
    """
    # Format date/time nicely with timezone
    datetime_str = format_pretty_datetime(info.start, include_timezone=True)
    
    # Format duration
    duration = info.end - info.start
    hours = int(duration.total_seconds() / 3600)
    minutes = int((duration.total_seconds() % 3600) / 60)
    if minutes == 0:
        duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        duration_str = f"{hours}h {minutes}m"
    
    # Create file:// URL (absolute path)
    abs_path = ics_path.resolve()
    if os.name == 'nt':  # Windows
        # Windows file:// URLs need triple slashes
        file_url = f"file:///{abs_path.as_posix()}"
    else:  # Unix-like
        file_url = f"file://{abs_path.as_posix()}"
    
    message = f"""Next Session: {info.title}

📅 {datetime_str}
⏱️  Duration: {duration_str}

📎 Add to Calendar: {file_url}"""
    
    if info.description:
        message += f"\n\n{info.description}"
    
    return message


def generate_session_prompt(prompt_input_func: Callable[[str], str]) -> SessionInfo:
    """
    Interactively prompt user for session information.
    
    Args:
        prompt_input_func: Function to get user input (takes prompt string, returns response)
        
    Returns:
        SessionInfo instance with user-provided data
        
    Raises:
        ValueError: If date/time parsing fails
    """
    # Get session title
    title = prompt_input_func("Enter session title: ").strip()
    if not title:
        title = "TTRPG Session"
    
    # Get session date
    date_str = prompt_input_func("Enter session date (YYYY-MM-DD or MM/DD/YYYY): ").strip()
    try:
        # Try multiple date formats
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"]:
            try:
                session_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Could not parse date: {date_str}")
    except Exception as e:
        raise ValueError(f"Invalid date format: {e}")
    
    # Get start time
    time_str = prompt_input_func("Enter start time (HH:MM or HH:MM AM/PM): ").strip()
    try:
        # Try 24-hour format first
        try:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            # Try 12-hour format
            for fmt in ["%I:%M %p", "%I:%M%p", "%I %p"]:
                try:
                    time_obj = datetime.strptime(time_str, fmt).time()
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Could not parse time: {time_str}")
    except Exception as e:
        raise ValueError(f"Invalid time format: {e}")
    
    # Combine date and time
    start_datetime = datetime.combine(session_date, time_obj)
    
    # Make datetime timezone-aware using local timezone
    local_tz = get_local_timezone()
    if local_tz is not None:
        # If timezone is available, make datetime aware
        start_datetime = start_datetime.replace(tzinfo=local_tz)
    # Otherwise, keep as naive datetime (will be treated as local time)
    
    # Get duration
    duration_str = prompt_input_func("Enter duration in hours (default: 4): ").strip()
    if not duration_str:
        duration_hours = 4.0
    else:
        try:
            duration_hours = float(duration_str)
        except ValueError:
            raise ValueError(f"Invalid duration: {duration_str}")
    
    # Calculate end time
    end_datetime = start_datetime + timedelta(hours=duration_hours)
    
    # Get optional description
    description = prompt_input_func("Enter session description (optional, press Enter to skip): ").strip()
    
    return SessionInfo(
        title=title,
        start=start_datetime,
        end=end_datetime,
        description=description
    )


def schedule_next_session(prompt_input_func: Callable[[str], str]) -> Optional[str]:
    """
    Main function to schedule a session.
    
    Prompts user for session info, creates ICS file, and generates share message.
    
    Args:
        prompt_input_func: Function to get user input (takes prompt string, returns response)
        
    Returns:
        Share message string, or None if an error occurred
    """
    try:
        # Prompt for session information
        info = generate_session_prompt(prompt_input_func)
        
        # Create exports directory
        exports_dir = Path("exports")
        try:
            exports_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            print(f"Error: Failed to create exports directory: {e}")
            return None
        
        # Create ICS file
        ics_path = exports_dir / "next_session.ics"
        try:
            created_path = create_ics_file(info, ics_path)
        except Exception as e:
            print(f"Error: Failed to create ICS file: {e}")
            return None
        
        # Generate share message
        share_message = generate_share_message(info, created_path)
        
        # Save share message to file
        message_path = exports_dir / "session_share_message.txt"
        try:
            with open(message_path, "w", encoding="utf-8") as f:
                f.write(share_message)
        except PermissionError as e:
            print(f"Warning: Permission denied writing share message file: {e}")
            print(f"Hint: Check that '{exports_dir}' is writable.")
        except OSError as e:
            print(f"Warning: Failed to write share message file: {e}")
            print(f"Hint: Check that the directory exists and disk space is available.")
        except Exception as e:
            print(f"Warning: Unexpected error writing share message file: {e}")
        
        # Also save JSON metadata file for easier parsing
        json_path = exports_dir / "next_session.json"
        try:
            json_data = {
                "title": info.title,
                "start": info.start.isoformat(),
                "end": info.end.isoformat(),
                "description": info.description
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2)
        except (PermissionError, OSError):
            # Non-fatal error, continue
            pass
        
        # Print results
        print("\n" + "="*60)
        print("Session scheduled successfully!")
        print("="*60)
        print(f"\nICS file created: {created_path.resolve()}")
        print(f"\nShare message saved to: {message_path.resolve()}")
        print("\n" + "-"*60)
        print("SHARE MESSAGE:")
        print("-"*60)
        print(share_message)
        print("-"*60)
        
        return share_message
        
    except ValueError as e:
        print(f"\nError: {e}")
        print("Please try again with valid input.")
        return None
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return None


def get_next_session_info(config: "Config") -> Optional[SessionInfo]:
    """
    Return the next session information if available, otherwise None.
    
    Reads session information from the saved ICS file or JSON metadata file.
    If multiple files exist, returns the session with the earliest start time
    that is still in the future.
    
    Args:
        config: Config object (unused for now, but kept for future extensibility)
        
    Returns:
        SessionInfo object if a valid upcoming session is found, None otherwise
    """
    # First, try to read from JSON metadata file (if it exists)
    exports_dir = Path("exports")
    json_path = exports_dir / "next_session.json"
    
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Parse datetime strings
            start_str = data.get("start")
            end_str = data.get("end")
            if start_str and end_str:
                try:
                    # Try parsing ISO format
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    
                    # Check if session is in the future
                    if (start_dt > datetime.now(start_dt.tzinfo)) if start_dt.tzinfo else (start_dt > datetime.now()):
                        return SessionInfo(
                            title=data.get("title", "TTRPG Session"),
                            start=start_dt,
                            end=end_dt,
                            description=data.get("description", "")
                        )
                except (ValueError, AttributeError):
                    # If parsing fails, fall through to ICS parsing
                    pass
        except (json.JSONDecodeError, PermissionError, OSError):
            # If JSON read fails, fall through to ICS parsing
            pass
    
    # Fallback: parse ICS file
    ics_path = exports_dir / "next_session.ics"
    if not ics_path.exists():
        return None
    
    try:
        with open(ics_path, "r", encoding="utf-8") as f:
            ics_content = f.read()
        
        # Extract fields from ICS format
        # ICS format: SUMMARY:title, DTSTART:datetime, DTEND:datetime, DESCRIPTION:description
        title_match = re.search(r'SUMMARY:(.+?)(?:\r?\n|$)', ics_content)
        start_match = re.search(r'DTSTART[^:]*:(.+?)(?:\r?\n|$)', ics_content)
        end_match = re.search(r'DTEND[^:]*:(.+?)(?:\r?\n|$)', ics_content)
        desc_match = re.search(r'DESCRIPTION:(.+?)(?:\r?\n(?:[^\s]|DESCRIPTION)|END:VEVENT)', ics_content, re.DOTALL)
        
        if not start_match:
            return None
        
        # Parse datetime (ICS format: YYYYMMDDTHHMMSS or YYYYMMDDTHHMMSSZ)
        start_str = start_match.group(1).strip()
        try:
            # Parse ICS datetime format: YYYYMMDDTHHMMSS
            start_dt = datetime.strptime(start_str[:15], "%Y%m%dT%H%M%S")
        except ValueError:
            return None
        
        # Parse end time
        end_dt = None
        if end_match:
            end_str = end_match.group(1).strip()
            try:
                end_dt = datetime.strptime(end_str[:15], "%Y%m%dT%H%M%S")
            except ValueError:
                pass
        
        if not end_dt:
            # Default to 4 hours if end time not found
            end_dt = start_dt + timedelta(hours=4)
        
        # Check if session is in the future
        if start_dt <= datetime.now():
            return None
        
        # Extract title
        title = "TTRPG Session"
        if title_match:
            title = title_match.group(1).strip()
            # Unescape ICS text
            title = title.replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").replace("\\n", "\n")
        
        # Extract description
        description = ""
        if desc_match:
            description = desc_match.group(1).strip()
            # Unescape ICS text
            description = description.replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").replace("\\n", "\n")
        
        return SessionInfo(
            title=title,
            start=start_dt,
            end=end_dt,
            description=description
        )
    except (PermissionError, OSError, ValueError, AttributeError):
        return None

