"""Scoring functions: per-aspect sub-scores and aggregate day score.

This module contains the heart of the algorithm. Each ``score_*`` function
returns a value in [0, 100]; ``compute_day_score`` (added in step 3) combines
them with weights matching the specs.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from src.core.models import (
    HourlyWeather,
    ScoreBreakdown,
    SolunarDay,
    Species,
    Spot,
    WeatherData,
)

PRESSURE_OPTIMAL_MIN = 1013.0
PRESSURE_OPTIMAL_MAX = 1022.0
PRESSURE_OPTIMAL_CENTRE = 1017.0
PRESSURE_DECAY_PER_HPA = 5.0
PRESSURE_TREND_24H_BONUS_THRESHOLD = 2.0
PRESSURE_TREND_24H_BONUS = 10.0
PRESSURE_TREND_24H_PENALTY_THRESHOLD = -3.0
PRESSURE_TREND_24H_PENALTY = -20.0
PRESSURE_TREND_48H_BONUS_THRESHOLD = 4.0
PRESSURE_TREND_48H_BONUS = 5.0
PRESSURE_TREND_48H_PENALTY_THRESHOLD = -6.0
PRESSURE_TREND_48H_PENALTY = -10.0

# Penalty applied to the total when the species is biologically out of
# season (the calendar month isn't in species.season_active). Even if the
# weather looks ideal, fish are dormant outside their active months —
# winter pike, summer trout, etc.
OUT_OF_SEASON_MULTIPLIER = 0.6

SOLUNAR_MAJOR_SCORE = 100.0
SOLUNAR_MINOR_SCORE = 70.0
SOLUNAR_BASELINE_SCORE = 40.0

MOON_FLOOR_SCORE = 60.0
MOON_DECAY_FACTOR = 200.0

CLOUD_OPTIMAL = 50.0
CLOUD_DECAY_PER_PERCENT = 1.5
WIND_THRESHOLD_KMH = 15.0
WIND_DECAY_PER_KMH = 5.0
PRECIP_THRESHOLD_MM = 2.0
PRECIP_DECAY_PER_MM = 10.0

WEIGHT_THERMAL = 0.25
WEIGHT_PRESSURE = 0.25
WEIGHT_SOLUNAR = 0.20
WEIGHT_MOON = 0.10
WEIGHT_WEATHER = 0.20

REFERENCE_HOUR = 12  # noon — used to sample pressure and 24h trend

# Seasonal water-vs-air offsets, by month.
#
# Convention: ``water_temp = air_temp + seasonal_offset + spot_type_offset``.
# A negative seasonal offset means water is cooler than air, which matches
# physical reality in spring (air warms faster than water mass). The spec
# text writes a subtraction, but the parenthetical hints ("gros écart
# printemps" in May-June with offset -3) only make sense with addition;
# we follow the physically correct convention.
SEASONAL_WATER_OFFSET_BY_MONTH: dict[int, float] = {
    1: 0.0, 2: 0.0,        # mid-winter: water roughly tracks air, both low
    3: -2.0, 4: -2.0,      # early spring: air rises faster than water
    5: -3.0, 6: -3.0,      # late spring: largest air-water lag
    7: -2.0, 8: -2.0,      # summer: water catches up partially
    9: -1.0, 10: -1.0,     # autumn: smaller lag
    11: 0.0, 12: 0.0,      # early winter: convergence again
}

SPOT_TYPE_WATER_OFFSET: dict[str, float] = {
    "lac": 0.0,
    "fleuve": 1.0,    # larger volume, slower flow → slightly warmer
    "riviere": 0.0,
}


def estimate_water_temp(
    air_temp_avg: float, month: int, spot_type: str
) -> float:
    """Estimate average water temperature from average air temperature.

    Uses a simple seasonal-lag heuristic plus a small spot-type adjustment.
    A starter approximation, to refine with field measurements.
    """
    if month not in SEASONAL_WATER_OFFSET_BY_MONTH:
        raise ValueError(f"Invalid month: {month}")
    if spot_type not in SPOT_TYPE_WATER_OFFSET:
        raise ValueError(f"Unknown spot type: {spot_type}")
    return (
        air_temp_avg
        + SEASONAL_WATER_OFFSET_BY_MONTH[month]
        + SPOT_TYPE_WATER_OFFSET[spot_type]
    )


def score_thermal(water_temp: float, species: Species) -> float:
    """Score how favorable water temperature is for the species (0-100).

    100 inside the optimal band, 0 outside the critical band, linear
    interpolation in between.
    """
    if species.temp_optimal_min <= water_temp <= species.temp_optimal_max:
        return 100.0
    if (
        water_temp < species.temp_critical_min
        or water_temp > species.temp_critical_max
    ):
        return 0.0
    if water_temp < species.temp_optimal_min:
        span = species.temp_optimal_min - species.temp_critical_min
        return 100.0 * (water_temp - species.temp_critical_min) / span
    span = species.temp_critical_max - species.temp_optimal_max
    return 100.0 * (species.temp_critical_max - water_temp) / span


def score_pressure(
    pressure_now: float, trend_24h: float, trend_48h: float = 0.0
) -> float:
    """Score current barometric pressure plus 24h and 48h trends (0-100).

    High stable or rising pressure is generally favorable; a sharp drop
    over 24h indicates an incoming front and depresses activity. A
    sustained rise over 48h (post-front recovery) is also positive.
    """
    if PRESSURE_OPTIMAL_MIN <= pressure_now <= PRESSURE_OPTIMAL_MAX:
        score = 100.0
    else:
        score = max(
            0.0,
            100.0
            - abs(pressure_now - PRESSURE_OPTIMAL_CENTRE) * PRESSURE_DECAY_PER_HPA,
        )

    if trend_24h > PRESSURE_TREND_24H_BONUS_THRESHOLD:
        score += PRESSURE_TREND_24H_BONUS
    elif trend_24h < PRESSURE_TREND_24H_PENALTY_THRESHOLD:
        score += PRESSURE_TREND_24H_PENALTY

    if trend_48h > PRESSURE_TREND_48H_BONUS_THRESHOLD:
        score += PRESSURE_TREND_48H_BONUS
    elif trend_48h < PRESSURE_TREND_48H_PENALTY_THRESHOLD:
        score += PRESSURE_TREND_48H_PENALTY

    return max(0.0, min(100.0, score))


def score_solunar(
    solunar_day: SolunarDay,
    species_active_hours: list[tuple[int, int]],
) -> float:
    """Score how solunar windows overlap with species active hours.

    100 if any species active window overlaps a major lunar period,
    70 if it overlaps a minor period, 40 otherwise.
    """
    day_midnight = datetime.combine(solunar_day.date, time.min)
    active_intervals: list[tuple[datetime, datetime]] = [
        (
            day_midnight + timedelta(hours=h_start),
            day_midnight + timedelta(hours=h_end),
        )
        for h_start, h_end in species_active_hours
    ]

    def has_overlap(periods: list[tuple[datetime, datetime]]) -> bool:
        for period_start, period_end in periods:
            for active_start, active_end in active_intervals:
                if period_start < active_end and active_start < period_end:
                    return True
        return False

    if has_overlap(solunar_day.major_periods):
        return SOLUNAR_MAJOR_SCORE
    if has_overlap(solunar_day.minor_periods):
        return SOLUNAR_MINOR_SCORE
    return SOLUNAR_BASELINE_SCORE


def score_moon(phase: float) -> float:
    """Score moon phase: new and full moons score highest (0-100).

    Distance is measured to the nearest of {0, 0.5, 1}, so new and full
    moons get 100 and quarter moons hit the 60 floor.
    """
    distance = min(abs(phase), abs(phase - 0.5), abs(phase - 1.0))
    return max(MOON_FLOOR_SCORE, 100.0 - distance * MOON_DECAY_FACTOR)


def score_weather(
    cloud_cover: float,
    wind_speed: float,
    precipitation: float,
) -> float:
    """Score weather conditions on the average of three sub-scores.

    Inputs are daily aggregates (cloud %, wind km/h, precipitation mm).
    """
    cloud_score = max(
        0.0, 100.0 - abs(cloud_cover - CLOUD_OPTIMAL) * CLOUD_DECAY_PER_PERCENT
    )
    if wind_speed < WIND_THRESHOLD_KMH:
        wind_score = 100.0
    else:
        wind_score = max(
            0.0, 100.0 - (wind_speed - WIND_THRESHOLD_KMH) * WIND_DECAY_PER_KMH
        )
    if precipitation < PRECIP_THRESHOLD_MM:
        precip_score = 100.0
    else:
        precip_score = max(
            0.0,
            100.0 - (precipitation - PRECIP_THRESHOLD_MM) * PRECIP_DECAY_PER_MM,
        )
    return (cloud_score + wind_score + precip_score) / 3.0


def _hour_at(weather: WeatherData, day: date, hour: int) -> HourlyWeather | None:
    for h in weather.hourly:
        if h.time.date() == day and h.time.hour == hour:
            return h
    return None


def aggregate_day_weather(weather: WeatherData, day: date) -> dict[str, float]:
    """Compute the daily aggregates the scorer consumes."""
    day_hours = [h for h in weather.hourly if h.time.date() == day]
    if not day_hours:
        raise ValueError(f"No hourly weather data for {day}")

    noon = _hour_at(weather, day, REFERENCE_HOUR) or day_hours[len(day_hours) // 2]
    prev_24h = _hour_at(weather, day - timedelta(days=1), REFERENCE_HOUR)
    prev_48h = _hour_at(weather, day - timedelta(days=2), REFERENCE_HOUR)

    trend_24h = (
        noon.pressure_msl - prev_24h.pressure_msl
        if prev_24h is not None
        else 0.0
    )
    trend_48h = (
        noon.pressure_msl - prev_48h.pressure_msl
        if prev_48h is not None
        else 0.0
    )

    return {
        "air_temp_avg": sum(h.temperature_2m for h in day_hours) / len(day_hours),
        "cloud_avg": sum(h.cloud_cover for h in day_hours) / len(day_hours),
        "wind_max": max(h.wind_speed_10m for h in day_hours),
        "precip_total": sum(h.precipitation for h in day_hours),
        "pressure_now": noon.pressure_msl,
        "trend_24h": trend_24h,
        "trend_48h": trend_48h,
    }


def compute_day_score(
    spot: Spot,
    species: Species,
    weather: WeatherData,
    solunar_day: SolunarDay,
) -> ScoreBreakdown:
    """Compute the full sub-score breakdown for one (spot, species, day).

    Aggregates the hourly weather on ``solunar_day.date`` and combines all
    five sub-scores with the spec weights (0.25 / 0.25 / 0.20 / 0.10 / 0.20).
    """
    agg = aggregate_day_weather(weather, solunar_day.date)
    water_temp = estimate_water_temp(
        agg["air_temp_avg"], solunar_day.date.month, spot.type
    )

    thermal = score_thermal(water_temp, species)
    pressure = score_pressure(
        agg["pressure_now"], agg["trend_24h"], agg["trend_48h"]
    )
    solunar = score_solunar(solunar_day, species.active_hours)
    moon = score_moon(solunar_day.moon_phase)
    weather_score = score_weather(
        agg["cloud_avg"], agg["wind_max"], agg["precip_total"]
    )

    total = (
        thermal * WEIGHT_THERMAL
        + pressure * WEIGHT_PRESSURE
        + solunar * WEIGHT_SOLUNAR
        + moon * WEIGHT_MOON
        + weather_score * WEIGHT_WEATHER
    )

    # Biology overrides physics: dampen score when the species is dormant.
    if solunar_day.date.month not in species.season_active:
        total *= OUT_OF_SEASON_MULTIPLIER

    return ScoreBreakdown(
        thermal=round(thermal, 2),
        pressure=round(pressure, 2),
        solunar=round(solunar, 2),
        moon=round(moon, 2),
        weather=round(weather_score, 2),
        total=round(total, 2),
    )
