"""
Utility functions for number handling, particularly for safe conversion between numeric types.
These functions are designed to handle edge cases like very large integers that might cause overflow
when converting to float
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_float(value: Any, default: float | None = None) -> float | None:
    """
    Safely convert a value to float, handling large integers and other edge cases.

    Args:
        value: The value to convert to float
        default: The default value to return if conversion fails (default: None)

    Returns:
        float value if conversion successful, default value otherwise
    """
    if value is None:
        return default

    try:
        return float(value)
    except (ValueError, TypeError, OverflowError) as e:
        logger.warning(f"Could not convert value '{value}' to float: {str(e)}")
        return default


def safe_float_list(
    values: list[Any], default_item: float | None = 0.0
) -> list[float | None]:
    """
    Safely convert a list of values to floats, handling large integers and other edge cases.

    Args:
        values: List of values to convert to floats
        default_item: The default value to use for items that fail conversion (default: 0.0)

    Returns:
        List of converted float values
    """
    if not values:
        return []

    result: list[float | None] = []
    for value in values:
        result.append(safe_float(value, default_item))
    return result


def safe_process_position(
    latitude_i: Any, longitude_i: Any, altitude: Any = None
) -> tuple[float | None, float | None, float | None]:
    """
    Safely process position data (latitude, longitude, altitude) from Meshtastic protocol.

    Args:
        latitude_i: Integer latitude value (needs to be divided by 1e7)
        longitude_i: Integer longitude value (needs to be divided by 1e7)
        altitude: Altitude value

    Returns:
        Tuple of (latitude, longitude, altitude) as floats
    """
    lat = None
    lon = None
    alt = None

    if latitude_i is not None and longitude_i is not None:
        lat = safe_float(latitude_i)
        lon = safe_float(longitude_i)

        if lat is not None and lon is not None:
            # Apply standard Meshtastic scaling
            lat = lat / 1e7
            lon = lon / 1e7

    if altitude is not None and altitude != 0:
        alt = safe_float(altitude)

    return (lat, lon, alt)
