"""Approximate tide phase derived from solunar data.

The Mediterranean and most coastal locations have a semi-diurnal tide
that aligns roughly with lunar transit: high tide occurs near the moon's
highest point overhead and at its antitransit (12h later). Low tides
sit ~6h12min after each high tide (half a lunar day).

This is a coarse approximation — real harbor predictions need
location-specific harmonic constants and have a few-hour "harbor lag".
For the Med (tidal range ~30-40 cm) the approximation is acceptable for
fishing-window scoring; it will be less accurate on Atlantic coasts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from src.core.models import SolunarDay, TidePhase

# Tidal cycle: high → low → next high takes ~12h25min (half lunar day = period).
TIDAL_CYCLE = timedelta(hours=12, minutes=25)
TIDAL_CYCLE_SECONDS = TIDAL_CYCLE.total_seconds()
# Time between a high and the following low.
HALF_LUNAR_DAY = TIDAL_CYCLE / 2

# Phase fractions within one tidal cycle (0 = high tide, 0.5 = low tide).
# Slack windows are narrow; rising/falling fill the rest.
SLACK_FRACTION = 1.0 / 12.0  # ±~62 min around high/low

# Multiplier applied to a saltwater slot score by tide phase.
# Calibration is rough; refine after field validation.
TIDE_MULTIPLIERS: dict[TidePhase, float] = {
    "rising": 1.15,
    "high": 1.05,
    "falling": 0.95,
    "low": 0.80,
}


def _high_tide_times(solunar_day: SolunarDay) -> list[datetime]:
    """Use major-period centres as a proxy for high-tide times."""
    return [s + (e - s) / 2 for s, e in solunar_day.major_periods]


def tide_phase_at(when: datetime, solunar_day: SolunarDay) -> TidePhase:
    """Classify the tide phase at a given moment.

    Anchors on one high-tide reference (lunar transit) and computes the
    phase position within the 12h25 tidal cycle, modulo. This is robust to
    cases where the literal transit time lies on a different calendar day
    than ``when``.
    """
    high_tides = _high_tide_times(solunar_day)
    if not high_tides:
        return "rising"

    # Any high tide works as a reference; the modulo collapses them.
    high_ref = high_tides[0]
    delta_seconds = (when - high_ref).total_seconds()
    phase = (delta_seconds % TIDAL_CYCLE_SECONDS) / TIDAL_CYCLE_SECONDS

    # phase ∈ [0, 1): 0 = high, 0.5 = low.
    if phase < SLACK_FRACTION or phase > 1.0 - SLACK_FRACTION:
        return "high"
    if 0.5 - SLACK_FRACTION < phase < 0.5 + SLACK_FRACTION:
        return "low"
    if phase < 0.5:
        return "falling"
    return "rising"


def tide_multiplier(phase: TidePhase) -> float:
    return TIDE_MULTIPLIERS[phase]
