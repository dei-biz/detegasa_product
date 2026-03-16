"""Unit conversion for maritime engineering measurements.

Supports the units commonly found in DETEGASA data sheets and client tenders:
pressure, temperature, flow rate, length, power.
"""

from __future__ import annotations

import logging
import re

from src.schemas.common import MeasuredValue

logger = logging.getLogger(__name__)


# ── Conversion tables ────────────────────────────────────────────────────────
# Each entry: (from_unit, to_unit) -> multiplier or callable
# Units are normalized to lowercase for lookup.

_CONVERSIONS: dict[tuple[str, str], float | callable] = {
    # Pressure
    ("bar", "psi"): 14.5038,
    ("bar", "kpa"): 100.0,
    ("bar", "mpa"): 0.1,
    ("bar", "kgf/cm2"): 1.01972,
    ("barg", "psig"): 14.5038,
    ("barg", "bar"): 1.0,  # gauge = absolute for comparison purposes
    ("psi", "bar"): 1 / 14.5038,
    ("psig", "barg"): 1 / 14.5038,
    ("kpa", "bar"): 0.01,
    ("mpa", "bar"): 10.0,
    ("kgf/cm2", "bar"): 1 / 1.01972,
    # Temperature
    ("c", "f"): lambda c: c * 9 / 5 + 32,
    ("f", "c"): lambda f: (f - 32) * 5 / 9,
    # Flow rate
    ("m3/h", "l/min"): 16.6667,
    ("m3/h", "gpm"): 4.40287,
    ("l/min", "m3/h"): 1 / 16.6667,
    ("gpm", "m3/h"): 1 / 4.40287,
    # Length
    ("mm", "inch"): 0.0393701,
    ("mm", "m"): 0.001,
    ("inch", "mm"): 25.4,
    ("m", "mm"): 1000.0,
    # Power
    ("w", "kw"): 0.001,
    ("kw", "w"): 1000.0,
    ("kw", "hp"): 1.34102,
    ("hp", "kw"): 1 / 1.34102,
}

# Unit aliases — map common variants to canonical form
_ALIASES: dict[str, str] = {
    "°c": "c",
    "ºc": "c",
    "deg c": "c",
    "degc": "c",
    "celsius": "c",
    "°f": "f",
    "ºf": "f",
    "deg f": "f",
    "degf": "f",
    "fahrenheit": "f",
    "m³/h": "m3/h",
    "m3/hr": "m3/h",
    "m³/hr": "m3/h",
    "cbm/h": "m3/h",
    "l/m": "l/min",
    "lpm": "l/min",
    "in": "inch",
    "inches": "inch",
    "\"": "inch",
    "watts": "w",
    "watt": "w",
    "kilowatt": "kw",
    "kilowatts": "kw",
    "horsepower": "hp",
}


def _normalize_unit(unit: str) -> str:
    """Normalize a unit string to its canonical lowercase form."""
    lower = unit.lower().strip()
    return _ALIASES.get(lower, lower)


def convert(value: MeasuredValue, target_unit: str) -> MeasuredValue:
    """Convert a MeasuredValue to a different unit.

    Parameters
    ----------
    value:
        The value to convert.
    target_unit:
        The desired unit.

    Returns
    -------
    MeasuredValue
        Converted value, or the original if no conversion is available.

    Raises
    ------
    ValueError
        If the conversion is not supported.
    """
    src = _normalize_unit(value.unit)
    dst = _normalize_unit(target_unit)

    if src == dst:
        return value

    key = (src, dst)
    factor = _CONVERSIONS.get(key)

    if factor is None:
        raise ValueError(
            f"No conversion available: {value.unit!r} -> {target_unit!r}"
        )

    if callable(factor):
        converted = factor(value.value)
    else:
        converted = value.value * factor

    return MeasuredValue(value=round(converted, 4), unit=target_unit)


def can_convert(from_unit: str, to_unit: str) -> bool:
    """Check if a conversion is available between two units."""
    src = _normalize_unit(from_unit)
    dst = _normalize_unit(to_unit)
    return src == dst or (src, dst) in _CONVERSIONS


def normalize_to(value: MeasuredValue, target_unit: str) -> MeasuredValue:
    """Convert if possible, otherwise return the original value unchanged."""
    try:
        return convert(value, target_unit)
    except ValueError:
        return value


# ── Value parsing ────────────────────────────────────────────────────────────

_VALUE_UNIT_PATTERN = re.compile(
    r"([<>=≤≥]*\s*\d+(?:[.,]\d+)?)\s+"  # number with optional comparator(s) + whitespace
    r"([a-zA-Z°º³²%][a-zA-Z0-9°º³/²%()\-]*)",  # unit (starts with letter, may contain digits/slashes)
)


def parse_value(text: str) -> MeasuredValue | None:
    """Try to parse a numeric value with unit from free text.

    Examples:
        "5 m3/h"     -> MeasuredValue(5.0, "m3/h")
        "15 ppm"     -> MeasuredValue(15.0, "ppm")
        "3.5 barg"   -> MeasuredValue(3.5, "barg")
        "≤15 ppm"    -> MeasuredValue(15.0, "ppm")
        "500 mm"     -> MeasuredValue(500.0, "mm")
    """
    if not text or not text.strip():
        return None

    match = _VALUE_UNIT_PATTERN.search(text)
    if not match:
        return None

    num_str = match.group(1).strip().lstrip("<>=≤≥").strip()
    num_str = num_str.replace(",", ".")
    unit = match.group(2).strip()

    try:
        return MeasuredValue(value=float(num_str), unit=unit)
    except (ValueError, TypeError):
        return None
