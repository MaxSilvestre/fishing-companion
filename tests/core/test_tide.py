"""Tests for src.core.tide."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.core.models import SolunarDay
from src.core.tide import HALF_LUNAR_DAY, tide_multiplier, tide_phase_at


def _solunar_with_transit(day: date, transit_hour: int) -> SolunarDay:
    """Build a SolunarDay whose major periods centre on the given hours."""
    midnight = datetime.combine(day, datetime.min.time())
    transit = midnight + timedelta(hours=transit_hour)
    antitransit = transit + timedelta(hours=12)
    return SolunarDay(
        date=day,
        sunrise=midnight + timedelta(hours=6),
        sunset=midnight + timedelta(hours=21),
        moonrise=None,
        moonset=None,
        moon_phase=0.5,
        major_periods=[
            (transit - timedelta(hours=1), transit + timedelta(hours=1)),
            (antitransit - timedelta(hours=1), antitransit + timedelta(hours=1)),
        ],
        minor_periods=[],
    )


class TestTidePhaseAt:
    def test_at_high_tide_returns_high(self):
        sd = _solunar_with_transit(date(2026, 5, 12), 12)
        when = datetime(2026, 5, 12, 12, 0)
        assert tide_phase_at(when, sd) == "high"

    def test_at_low_tide_returns_low(self):
        # High at 12:00, low ~18:12.
        sd = _solunar_with_transit(date(2026, 5, 12), 12)
        when = datetime(2026, 5, 12, 18, 12)
        assert tide_phase_at(when, sd) == "low"

    def test_between_low_and_high_is_rising(self):
        # High at 12:00, previous low at ~05:48. 09:00 is rising.
        sd = _solunar_with_transit(date(2026, 5, 12), 12)
        when = datetime(2026, 5, 12, 9, 0)
        assert tide_phase_at(when, sd) == "rising"

    def test_between_high_and_low_is_falling(self):
        sd = _solunar_with_transit(date(2026, 5, 12), 12)
        when = datetime(2026, 5, 12, 15, 0)
        assert tide_phase_at(when, sd) == "falling"


class TestTideMultiplier:
    def test_rising_is_highest(self):
        assert tide_multiplier("rising") > tide_multiplier("high")
        assert tide_multiplier("high") > tide_multiplier("falling")
        assert tide_multiplier("falling") > tide_multiplier("low")

    def test_rising_boosts_score(self):
        assert tide_multiplier("rising") > 1.0

    def test_low_dampens_score(self):
        assert tide_multiplier("low") < 1.0
