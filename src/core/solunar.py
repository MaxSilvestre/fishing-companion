"""Solunar computations: sun/moon rise and set, moon phase, fishing periods.

Solunar theory in brief:
- Major periods (~2h) span lunar transit and antitransit (when the moon
  is at the local meridian and its opposite point). These are traditionally
  the best fishing windows.
- Minor periods (~1h) span moonrise and moonset.

astral exposes sun and moon rise/set plus moon phase, but not lunar transit.
We approximate transit as ``solar_noon + 24h * moon_phase`` (in [0, 24)),
which is exact at new moon (transit = noon) and full moon (transit = midnight)
and within ~30 minutes of the true transit at intermediate phases. That
accuracy is sufficient for fishing windows of ±1 hour.

All datetimes are naive and expressed in the spot's local time, matching
the convention used by ``src.core.weather`` (Open-Meteo with timezone=auto).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.moon import moonrise as astral_moonrise
from astral.moon import moonset as astral_moonset
from astral.moon import phase as astral_phase
from astral.sun import sun as astral_sun

from src.core.models import SolunarDay

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Europe/Paris"
ASTRAL_PHASE_MAX = 28.0
MAJOR_HALF_WINDOW = timedelta(hours=1)
MINOR_HALF_WINDOW = timedelta(minutes=30)


def _strip_tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


def compute_solunar(
    day: date,
    latitude: float,
    longitude: float,
    *,
    tz_name: str = DEFAULT_TIMEZONE,
) -> SolunarDay:
    """Compute sun/moon events and fishing periods for one day at one location."""
    tz = ZoneInfo(tz_name)
    location = LocationInfo(
        name="spot",
        region="",
        timezone=tz_name,
        latitude=latitude,
        longitude=longitude,
    )
    observer = location.observer

    sun_events = astral_sun(observer, date=day, tzinfo=tz)
    sunrise = _strip_tz(sun_events["sunrise"])
    sunset = _strip_tz(sun_events["sunset"])

    try:
        moonrise = _strip_tz(astral_moonrise(observer, day, tzinfo=tz))
    except ValueError:
        logger.debug("No moonrise on %s at (%s, %s)", day, latitude, longitude)
        moonrise = None
    try:
        moonset = _strip_tz(astral_moonset(observer, day, tzinfo=tz))
    except ValueError:
        logger.debug("No moonset on %s at (%s, %s)", day, latitude, longitude)
        moonset = None

    raw_phase = astral_phase(day)
    moon_phase = (raw_phase % ASTRAL_PHASE_MAX) / ASTRAL_PHASE_MAX

    solar_noon = sunrise + (sunset - sunrise) / 2
    transit = solar_noon + timedelta(hours=moon_phase * 24)
    antitransit = transit + timedelta(hours=12)
    major_periods = [
        (transit - MAJOR_HALF_WINDOW, transit + MAJOR_HALF_WINDOW),
        (antitransit - MAJOR_HALF_WINDOW, antitransit + MAJOR_HALF_WINDOW),
    ]

    minor_periods: list[tuple[datetime, datetime]] = []
    if moonrise is not None:
        minor_periods.append(
            (moonrise - MINOR_HALF_WINDOW, moonrise + MINOR_HALF_WINDOW)
        )
    if moonset is not None:
        minor_periods.append(
            (moonset - MINOR_HALF_WINDOW, moonset + MINOR_HALF_WINDOW)
        )

    return SolunarDay(
        date=day,
        sunrise=sunrise,
        sunset=sunset,
        moonrise=moonrise,
        moonset=moonset,
        moon_phase=moon_phase,
        major_periods=major_periods,
        minor_periods=minor_periods,
    )
