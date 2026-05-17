"""Time tools for LLM function calling - timezone and time conversion utilities."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel


class TimeResult(BaseModel):
    """Result model for time queries."""

    timezone: str
    datetime: str
    is_dst: bool


class TimeConversionResult(BaseModel):
    """Result model for time conversions."""

    source: TimeResult
    target: TimeResult
    time_difference: str


def get_local_timezone(local_tz_override: Optional[str] = None) -> str:
    """
    Get the local timezone name using system timezone.
    Falls back to UTC if cannot determine.
    """
    if local_tz_override:
        return local_tz_override

    try:
        # Try to get timezone from datetime
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, "key"):
            return local_tz.key

        # Try to parse from string representation
        tz_str = str(local_tz)
        if tz_str and not tz_str.startswith("UTC"):
            return tz_str

        # Default to UTC
        return "UTC"
    except:
        return "UTC"


def get_current_time(timezone: str) -> Dict[str, Any]:
    """
    Get current time in specified timezone.

    Args:
        timezone: IANA timezone name (e.g., 'America/New_York', 'Europe/London')

    Returns:
        Dict containing timezone, datetime, and DST status
    """
    try:
        tz = ZoneInfo(timezone)
        current_time = datetime.now(tz)

        result = TimeResult(
            timezone=timezone,
            datetime=current_time.isoformat(timespec="seconds"),
            is_dst=bool(current_time.dst()),
        )
        return result.model_dump()
    except Exception as e:
        raise ValueError(f"Invalid timezone '{timezone}': {str(e)}")


def convert_time(
    source_timezone: str, time: str, target_timezone: str
) -> Dict[str, Any]:
    """
    Convert time between timezones.

    Args:
        source_timezone: Source IANA timezone name
        time: Time to convert in 24-hour format (HH:MM)
        target_timezone: Target IANA timezone name

    Returns:
        Dict containing source time, target time, and time difference
    """
    try:
        source_tz = ZoneInfo(source_timezone)
        target_tz = ZoneInfo(target_timezone)
    except Exception as e:
        raise ValueError(f"Invalid timezone: {str(e)}")

    # Parse time
    try:
        parsed_time = datetime.strptime(time, "%H:%M").time()
    except ValueError:
        raise ValueError("Invalid time format. Expected HH:MM in 24-hour format")

    # Create datetime objects
    now = datetime.now(source_tz)
    source_time = datetime(
        now.year,
        now.month,
        now.day,
        parsed_time.hour,
        parsed_time.minute,
        tzinfo=source_tz,
    )

    # Convert to target timezone
    target_time = source_time.astimezone(target_tz)

    # Calculate time difference
    source_offset = source_time.utcoffset() or timedelta()
    target_offset = target_time.utcoffset() or timedelta()
    hours_difference = (target_offset - source_offset).total_seconds() / 3600

    # Format time difference
    if hours_difference.is_integer():
        time_diff_str = f"{int(hours_difference):+d}h"
    else:
        # For fractional hours like Nepal's UTC+5:45
        hours = int(hours_difference)
        minutes = int(abs(hours_difference - hours) * 60)
        if hours_difference >= 0:
            time_diff_str = f"+{hours}h{minutes:02d}m"
        else:
            time_diff_str = f"{hours}h{minutes:02d}m"

    result = TimeConversionResult(
        source=TimeResult(
            timezone=source_timezone,
            datetime=source_time.isoformat(timespec="seconds"),
            is_dst=bool(source_time.dst()),
        ),
        target=TimeResult(
            timezone=target_timezone,
            datetime=target_time.isoformat(timespec="seconds"),
            is_dst=bool(target_time.dst()),
        ),
        time_difference=time_diff_str,
    )
    return result.model_dump()


# Tool definitions for LLM function calling
def get_time_tools(local_tz_override: Optional[str] = None) -> list[Dict[str, Any]]:
    """Get tool definitions with dynamic local timezone."""
    local_tz = local_tz_override or get_local_timezone()

    return [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get current time in a specific timezone",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": f"IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Use '{local_tz}' as local timezone if no timezone provided by the user.",
                        }
                    },
                    "required": ["timezone"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "convert_time",
                "description": "Convert time between timezones",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_timezone": {
                            "type": "string",
                            "description": f"Source IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Use '{local_tz}' as local timezone if no source timezone provided by the user.",
                        },
                        "time": {
                            "type": "string",
                            "description": "Time to convert in 24-hour format (HH:MM)",
                        },
                        "target_timezone": {
                            "type": "string",
                            "description": f"Target IANA timezone name (e.g., 'Asia/Tokyo', 'America/San_Francisco'). Use '{local_tz}' as local timezone if no target timezone provided by the user.",
                        },
                    },
                    "required": ["source_timezone", "time", "target_timezone"],
                },
            },
        },
    ]
