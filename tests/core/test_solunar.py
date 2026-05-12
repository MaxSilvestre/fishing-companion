"""Tests for src.core.solunar."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.core.solunar import (
    MAJOR_HALF_WINDOW,
    MINOR_HALF_WINDOW,
    compute_solunar,
)

LYON = (45.764, 4.8357)


def test_summer_solstice_in_lyon_has_long_day():
    sd = compute_solunar(date(2026, 6, 21), *LYON)
    # Around summer solstice in Lyon, sunrise ~ 05:50, sunset ~ 21:30 local.
    assert sd.sunrise.hour == 5
    assert 45 <= sd.sunrise.minute <= 59
    assert sd.sunset.hour == 21
    assert 15 <= sd.sunset.minute <= 35
    day_length = sd.sunset - sd.sunrise
    assert day_length > timedelta(hours=15)


def test_winter_solstice_in_lyon_has_short_day():
    sd = compute_solunar(date(2026, 12, 21), *LYON)
    # Around winter solstice in Lyon, sunrise ~ 08:00, sunset ~ 16:55 local.
    assert sd.sunrise.hour == 8
    assert sd.sunset.hour == 16
    day_length = sd.sunset - sd.sunrise
    assert day_length < timedelta(hours=9)


def test_spring_day_in_lyon_is_intermediate():
    sd = compute_solunar(date(2026, 5, 12), *LYON)
    assert 5 <= sd.sunrise.hour <= 7
    assert 20 <= sd.sunset.hour <= 22
    day_length = sd.sunset - sd.sunrise
    assert timedelta(hours=13) < day_length < timedelta(hours=15)


def test_moon_phase_in_valid_range():
    for d in [date(2026, 1, 1), date(2026, 5, 12), date(2026, 12, 31)]:
        sd = compute_solunar(d, *LYON)
        assert 0.0 <= sd.moon_phase < 1.0


def test_moon_phase_progresses_through_cycle():
    # Sample 4 dates one week apart: phases should differ noticeably.
    phases = [
        compute_solunar(date(2026, 5, 1) + timedelta(days=7 * i), *LYON).moon_phase
        for i in range(4)
    ]
    distinct = {round(p, 2) for p in phases}
    assert len(distinct) >= 3


def test_major_periods_structure():
    sd = compute_solunar(date(2026, 5, 12), *LYON)
    assert len(sd.major_periods) == 2

    transit_start, transit_end = sd.major_periods[0]
    antitransit_start, antitransit_end = sd.major_periods[1]

    # Each window is 2*MAJOR_HALF_WINDOW long.
    assert transit_end - transit_start == 2 * MAJOR_HALF_WINDOW
    assert antitransit_end - antitransit_start == 2 * MAJOR_HALF_WINDOW

    # Antitransit centre = transit centre + 12h.
    transit_centre = transit_start + MAJOR_HALF_WINDOW
    antitransit_centre = antitransit_start + MAJOR_HALF_WINDOW
    assert antitransit_centre - transit_centre == timedelta(hours=12)


def test_minor_periods_centered_on_moon_events():
    sd = compute_solunar(date(2026, 5, 12), *LYON)
    # At least one of moonrise/moonset should exist most days.
    assert sd.moonrise is not None or sd.moonset is not None

    expected_periods = []
    if sd.moonrise is not None:
        expected_periods.append(sd.moonrise)
    if sd.moonset is not None:
        expected_periods.append(sd.moonset)

    assert len(sd.minor_periods) == len(expected_periods)
    for centre, (start, end) in zip(expected_periods, sd.minor_periods):
        assert end - start == 2 * MINOR_HALF_WINDOW
        assert start + MINOR_HALF_WINDOW == centre


def test_different_latitudes_yield_different_day_length():
    # Same longitude (Europe/Paris tz), different latitudes: higher latitude
    # should give a longer day in May.
    lyon = compute_solunar(date(2026, 5, 12), 45.764, 4.836)
    further_north = compute_solunar(date(2026, 5, 12), 55.0, 4.836)
    assert (further_north.sunset - further_north.sunrise) > (
        lyon.sunset - lyon.sunrise
    )


def test_returned_datetimes_are_naive():
    sd = compute_solunar(date(2026, 5, 12), *LYON)
    assert sd.sunrise.tzinfo is None
    assert sd.sunset.tzinfo is None
    if sd.moonrise is not None:
        assert sd.moonrise.tzinfo is None
    if sd.moonset is not None:
        assert sd.moonset.tzinfo is None
    for start, end in sd.major_periods + sd.minor_periods:
        assert isinstance(start, datetime) and start.tzinfo is None
        assert isinstance(end, datetime) and end.tzinfo is None


def test_solunar_is_deterministic():
    a = compute_solunar(date(2026, 5, 12), *LYON)
    b = compute_solunar(date(2026, 5, 12), *LYON)
    assert a.model_dump() == b.model_dump()
