"""Process matcher — deterministic evaluation of numeric process requirements.

Handles: capacity, flow rate, pressure, temperature, oil content (ppm),
voltage, power, and other numeric specs.
"""

from __future__ import annotations

import logging
import re

from src.compliance.matchers.base import BaseMatcher, MatchResult
from src.compliance.unit_converter import normalize_to, parse_value
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus, MeasuredValue

logger = logging.getLogger(__name__)


# Keywords that indicate this matcher can handle the requirement.
# Organized by comparison type.
_GTE_KEYWORDS = {
    # Product value must be >= tender value
    "capacity",
    "flow rate",
    "flow capacity",
    "throughput",
    "design pressure",
    "working pressure",
    "test pressure",
    "max pressure",
    "voltage",
    "power",
    "power supply",
    "service life",
    "design life",
    "minimum service life",
}

_LTE_KEYWORDS = {
    # Product value must be <= tender value
    "oil content",
    "oil in water",
    "remaining oil",
    "ppm",
    "noise level",
    "noise",
    "vibration",
}

_RANGE_KEYWORDS = {
    # Product value must be within range
    "temperature",
    "ambient temperature",
    "design temperature",
    "operating temperature",
}

_ALL_KEYWORDS = _GTE_KEYWORDS | _LTE_KEYWORDS | _RANGE_KEYWORDS


class ProcessMatcher(BaseMatcher):
    """Evaluate numeric process requirements deterministically."""

    @property
    def name(self) -> str:
        return "process"

    def can_handle(self, tbt_item: TBTItem) -> bool:
        """Check if the TBT item contains a numeric process requirement."""
        text = f"{tbt_item.description} {tbt_item.spec_requirement}".lower()

        # Must have a keyword AND a numeric value in spec_requirement
        has_keyword = any(kw in text for kw in _ALL_KEYWORDS)
        has_number = bool(re.search(r"\d+(?:[.,]\d+)?", tbt_item.spec_requirement))

        return has_keyword and has_number

    def evaluate(self, tbt_item: TBTItem, product_data: dict) -> MatchResult:
        """Compare a numeric process requirement against product data."""
        text = f"{tbt_item.description} {tbt_item.spec_requirement}".lower()
        spec = tbt_item.spec_requirement

        # Parse the required value from the TBT spec
        required = parse_value(spec)
        if not required:
            return MatchResult(
                status=ComplianceStatus.CLARIFICATION_NEEDED,
                tender_value=spec,
                gap_description="Could not parse numeric value from specification",
                confidence=0.3,
            )

        # Try to find matching product value
        product_value = self._find_product_value(text, product_data, required)

        if product_value is None:
            return MatchResult(
                status=ComplianceStatus.CLARIFICATION_NEEDED,
                tender_value=str(required),
                gap_description="No matching product value found for this requirement",
                confidence=0.3,
            )

        # Normalize units if needed
        product_norm = normalize_to(product_value, required.unit)

        # Determine comparison type and evaluate
        if any(kw in text for kw in _LTE_KEYWORDS):
            return self._compare_lte(product_norm, required, spec)
        elif any(kw in text for kw in _RANGE_KEYWORDS):
            return self._compare_range(product_norm, required, spec)
        else:
            # Default: product >= required
            return self._compare_gte(product_norm, required, spec)

    def _find_product_value(
        self, text: str, product_data: dict, required: MeasuredValue
    ) -> MeasuredValue | None:
        """Find the relevant product value for a given requirement."""
        perf = product_data.get("performance", {})

        # Capacity / flow rate
        if any(kw in text for kw in ("capacity", "flow rate", "flow capacity", "throughput")):
            cap = perf.get("capacity")
            if cap:
                return MeasuredValue(value=cap["value"], unit=cap["unit"])

        # Design pressure
        if any(kw in text for kw in ("design pressure", "working pressure", "max pressure")):
            dp = perf.get("design_pressure")
            if dp:
                return MeasuredValue(value=dp["value"], unit=dp["unit"])

        # Design temperature
        if any(kw in text for kw in ("design temperature", "operating temperature", "temperature")):
            dt = perf.get("design_temperature")
            if dt:
                return MeasuredValue(value=dt["value"], unit=dt["unit"])

        # Oil content / ppm
        if any(kw in text for kw in ("oil content", "oil in water", "remaining oil", "ppm")):
            ppm = perf.get("oil_output_max_ppm")
            if ppm is not None:
                return MeasuredValue(value=float(ppm), unit="ppm")

        # Service life
        if any(kw in text for kw in ("service life", "design life", "minimum service life")):
            # Look for service_life in performance or package_level
            pkg = product_data.get("package_level") or {}
            life = pkg.get("service_life_years")
            if life is not None:
                return MeasuredValue(value=float(life), unit="years")

        # Noise
        if any(kw in text for kw in ("noise level", "noise")):
            pkg = product_data.get("package_level") or {}
            noise = pkg.get("noise_level_dba")
            if noise is not None:
                return MeasuredValue(value=float(noise), unit="dB(A)")

        # Voltage / power from electrical specs of any component
        if any(kw in text for kw in ("voltage", "power", "power supply")):
            return self._find_electrical_value(text, product_data)

        return None

    def _find_electrical_value(
        self, text: str, product_data: dict
    ) -> MeasuredValue | None:
        """Search component electrical specs for voltage or power."""
        components = product_data.get("components", [])
        for comp in components:
            elec = comp.get("electrical") or {}
            if "voltage" in text:
                for key in ("voltage", "supply_voltage", "supply_voltage_rated"):
                    val = elec.get(key)
                    if val:
                        parsed = parse_value(str(val))
                        if parsed:
                            return parsed
            if "power" in text:
                for key in ("power", "rated_power", "power_consumption"):
                    val = elec.get(key)
                    if val:
                        parsed = parse_value(str(val))
                        if parsed:
                            return parsed
        return None

    @staticmethod
    def _compare_gte(
        product: MeasuredValue, required: MeasuredValue, spec: str
    ) -> MatchResult:
        """Product value must be >= required value."""
        if product.value >= required.value:
            return MatchResult(
                status=ComplianceStatus.COMPLIANT,
                product_value=str(product),
                tender_value=spec,
                confidence=0.95,
            )
        else:
            gap = required.value - product.value
            return MatchResult(
                status=ComplianceStatus.NON_COMPLIANT,
                product_value=str(product),
                tender_value=spec,
                gap_description=(
                    f"Product offers {product} but {spec} is required "
                    f"(gap: {gap:.2f} {required.unit})"
                ),
                confidence=0.90,
            )

    @staticmethod
    def _compare_lte(
        product: MeasuredValue, required: MeasuredValue, spec: str
    ) -> MatchResult:
        """Product value must be <= required value (e.g. oil output ppm)."""
        if product.value <= required.value:
            return MatchResult(
                status=ComplianceStatus.COMPLIANT,
                product_value=str(product),
                tender_value=spec,
                confidence=0.95,
            )
        else:
            excess = product.value - required.value
            return MatchResult(
                status=ComplianceStatus.NON_COMPLIANT,
                product_value=str(product),
                tender_value=spec,
                gap_description=(
                    f"Product value {product} exceeds requirement {spec} "
                    f"(excess: {excess:.2f} {required.unit})"
                ),
                confidence=0.90,
            )

    @staticmethod
    def _compare_range(
        product: MeasuredValue, required: MeasuredValue, spec: str
    ) -> MatchResult:
        """Product temperature range must cover required temperature."""
        # For temperature, compliance is less deterministic —
        # we can't always tell if it's min, max, or range.
        # Return partial confidence and let LLM refine if needed.
        return MatchResult(
            status=ComplianceStatus.COMPLIANT if product.value >= required.value
            else ComplianceStatus.CLARIFICATION_NEEDED,
            product_value=str(product),
            tender_value=spec,
            gap_description=None if product.value >= required.value
            else f"Product design temperature {product} vs required {spec} — verify range",
            confidence=0.6,
        )
