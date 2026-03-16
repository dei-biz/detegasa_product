"""Tests for the unit converter module."""

import pytest

from src.compliance.unit_converter import (
    can_convert,
    convert,
    normalize_to,
    parse_value,
)
from src.schemas.common import MeasuredValue


# ── convert() ─────────────────────────────────────────────────────────────────


class TestConvert:
    """Test unit conversion accuracy."""

    def test_bar_to_psi(self):
        result = convert(MeasuredValue(value=1.0, unit="bar"), "psi")
        assert abs(result.value - 14.5038) < 0.01
        assert result.unit == "psi"

    def test_psi_to_bar(self):
        result = convert(MeasuredValue(value=14.5038, unit="psi"), "bar")
        assert abs(result.value - 1.0) < 0.01

    def test_bar_to_kpa(self):
        result = convert(MeasuredValue(value=3.5, unit="bar"), "kPa")
        assert abs(result.value - 350.0) < 0.1

    def test_bar_to_mpa(self):
        result = convert(MeasuredValue(value=10.0, unit="bar"), "MPa")
        assert abs(result.value - 1.0) < 0.01

    def test_barg_to_psig(self):
        result = convert(MeasuredValue(value=4.0, unit="barg"), "psig")
        assert abs(result.value - 58.015) < 0.1

    def test_kgf_cm2_to_bar(self):
        result = convert(MeasuredValue(value=1.0, unit="kgf/cm2"), "bar")
        assert abs(result.value - 0.9807) < 0.01

    def test_celsius_to_fahrenheit(self):
        result = convert(MeasuredValue(value=100.0, unit="C"), "F")
        assert abs(result.value - 212.0) < 0.1

    def test_fahrenheit_to_celsius(self):
        result = convert(MeasuredValue(value=32.0, unit="F"), "C")
        assert abs(result.value - 0.0) < 0.1

    def test_celsius_zero_to_fahrenheit(self):
        result = convert(MeasuredValue(value=0.0, unit="C"), "F")
        assert abs(result.value - 32.0) < 0.1

    def test_m3h_to_gpm(self):
        result = convert(MeasuredValue(value=5.0, unit="m3/h"), "gpm")
        assert abs(result.value - 22.014) < 0.1

    def test_gpm_to_m3h(self):
        result = convert(MeasuredValue(value=22.014, unit="gpm"), "m3/h")
        assert abs(result.value - 5.0) < 0.1

    def test_m3h_to_lmin(self):
        result = convert(MeasuredValue(value=1.0, unit="m3/h"), "l/min")
        assert abs(result.value - 16.6667) < 0.1

    def test_mm_to_inch(self):
        result = convert(MeasuredValue(value=25.4, unit="mm"), "inch")
        assert abs(result.value - 1.0) < 0.01

    def test_inch_to_mm(self):
        result = convert(MeasuredValue(value=2.0, unit="inch"), "mm")
        assert abs(result.value - 50.8) < 0.1

    def test_kw_to_hp(self):
        result = convert(MeasuredValue(value=1.0, unit="kW"), "HP")
        assert abs(result.value - 1.341) < 0.01

    def test_hp_to_kw(self):
        result = convert(MeasuredValue(value=1.341, unit="HP"), "kW")
        assert abs(result.value - 1.0) < 0.01

    def test_w_to_kw(self):
        result = convert(MeasuredValue(value=1500.0, unit="W"), "kW")
        assert abs(result.value - 1.5) < 0.01

    def test_same_unit_noop(self):
        """Converting to the same unit should return the original."""
        val = MeasuredValue(value=42.0, unit="bar")
        result = convert(val, "bar")
        assert result.value == 42.0
        assert result.unit == "bar"

    def test_unsupported_conversion_raises(self):
        """Unsupported conversion should raise ValueError."""
        with pytest.raises(ValueError, match="No conversion available"):
            convert(MeasuredValue(value=1.0, unit="bar"), "m3/h")


# ── can_convert() ─────────────────────────────────────────────────────────────


class TestCanConvert:
    def test_bar_to_psi_available(self):
        assert can_convert("bar", "psi") is True

    def test_same_unit(self):
        assert can_convert("bar", "bar") is True

    def test_unsupported(self):
        assert can_convert("bar", "m3/h") is False

    def test_aliases(self):
        """Unit aliases should be recognized."""
        assert can_convert("°C", "F") is True
        assert can_convert("m³/h", "gpm") is True


# ── normalize_to() ────────────────────────────────────────────────────────────


class TestNormalizeTo:
    def test_successful_conversion(self):
        result = normalize_to(MeasuredValue(value=1.0, unit="bar"), "psi")
        assert abs(result.value - 14.5038) < 0.01

    def test_unsupported_returns_original(self):
        """normalize_to should silently return original on unsupported conversion."""
        val = MeasuredValue(value=42.0, unit="bar")
        result = normalize_to(val, "m3/h")
        assert result.value == 42.0
        assert result.unit == "bar"


# ── parse_value() ─────────────────────────────────────────────────────────────


class TestParseValue:
    def test_simple_value(self):
        result = parse_value("5 m3/h")
        assert result is not None
        assert result.value == 5.0
        assert result.unit == "m3/h"

    def test_decimal_value(self):
        result = parse_value("3.5 barg")
        assert result is not None
        assert result.value == 3.5
        assert result.unit == "barg"

    def test_ppm(self):
        result = parse_value("15 ppm")
        assert result is not None
        assert result.value == 15.0
        assert result.unit == "ppm"

    def test_with_comparator(self):
        """Comparators like ≤ should be stripped from the numeric value."""
        result = parse_value("≤15 ppm")
        assert result is not None
        assert result.value == 15.0
        assert result.unit == "ppm"

    def test_greater_than(self):
        result = parse_value(">=100 mm")
        assert result is not None
        assert result.value == 100.0

    def test_comma_decimal(self):
        result = parse_value("3,5 barg")
        assert result is not None
        assert result.value == 3.5

    def test_large_value(self):
        result = parse_value("500 mm")
        assert result is not None
        assert result.value == 500.0
        assert result.unit == "mm"

    def test_empty_string(self):
        assert parse_value("") is None

    def test_no_unit(self):
        """Text with number but no recognizable unit should return None."""
        assert parse_value("just 42") is None

    def test_no_number(self):
        assert parse_value("no numbers here") is None

    def test_embedded_in_sentence(self):
        result = parse_value("Minimum capacity of 5 m3/h required")
        assert result is not None
        assert result.value == 5.0
        assert result.unit == "m3/h"
