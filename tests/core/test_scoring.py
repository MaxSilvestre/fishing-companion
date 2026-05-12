"""Tests for src.core.scoring (built up across Phase 4 sub-steps)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.core.models import (
    HourlyWeather,
    SolunarDay,
    Species,
    Spot,
    WeatherData,
)
from src.core.scoring import (
    SEASONAL_WATER_OFFSET_BY_MONTH,
    SPOT_TYPE_WATER_OFFSET,
    compute_day_score,
    estimate_water_temp,
    score_moon,
    score_pressure,
    score_solunar,
    score_thermal,
    score_weather,
)


def _brochet() -> Species:
    return Species.model_validate(
        {
            "id": "brochet",
            "name": "Brochet",
            "emoji": "🐊",
            "temp_optimal_min": 12,
            "temp_optimal_max": 18,
            "temp_critical_min": 4,
            "temp_critical_max": 21,
            "pressure_preference": "stable_or_rising",
            "active_hours": [[5, 9], [17, 21]],
            "season_active": [3, 4, 5, 9, 10, 11],
            "weather_notes": "",
        }
    )


class TestEstimateWaterTemp:
    def test_may_fleuve(self):
        # May: -3, fleuve: +1 → water = 20 - 3 + 1 = 18
        assert estimate_water_temp(20.0, 5, "fleuve") == 18.0

    def test_may_riviere(self):
        # May: -3, riviere: 0 → water = 20 - 3 = 17
        assert estimate_water_temp(20.0, 5, "riviere") == 17.0

    def test_january_riviere(self):
        # January: 0, riviere: 0 → water = air
        assert estimate_water_temp(5.0, 1, "riviere") == 5.0

    def test_august_fleuve(self):
        # August: -2, fleuve: +1 → water = 25 - 2 + 1 = 24
        assert estimate_water_temp(25.0, 8, "fleuve") == 24.0

    def test_water_warmer_in_fleuve_than_riviere(self):
        # Same month, fleuve always >= riviere.
        for month in range(1, 13):
            fleuve = estimate_water_temp(15.0, month, "fleuve")
            riviere = estimate_water_temp(15.0, month, "riviere")
            assert fleuve >= riviere

    def test_water_cooler_than_air_in_spring(self):
        # In May the seasonal offset is negative, so water < air everywhere.
        for spot in ("lac", "fleuve", "riviere"):
            assert estimate_water_temp(20.0, 5, spot) < 20.0

    def test_invalid_month(self):
        with pytest.raises(ValueError, match="month"):
            estimate_water_temp(15.0, 13, "fleuve")

    def test_invalid_spot_type(self):
        with pytest.raises(ValueError, match="spot type"):
            estimate_water_temp(15.0, 5, "ocean")

    def test_all_months_present(self):
        assert set(SEASONAL_WATER_OFFSET_BY_MONTH.keys()) == set(range(1, 13))

    def test_all_spot_types_present(self):
        assert set(SPOT_TYPE_WATER_OFFSET.keys()) == {"lac", "fleuve", "riviere"}


class TestScoreThermal:
    def test_inside_optimal_band(self):
        species = _brochet()  # opt 12-18
        for w in (12.0, 14.0, 15.0, 18.0):
            assert score_thermal(w, species) == 100.0

    def test_at_optimal_boundaries_is_100(self):
        species = _brochet()
        assert score_thermal(12.0, species) == 100.0
        assert score_thermal(18.0, species) == 100.0

    def test_at_critical_boundaries_is_0(self):
        species = _brochet()  # crit 4-21
        assert score_thermal(4.0, species) == 0.0
        assert score_thermal(21.0, species) == 0.0

    def test_below_critical_is_0(self):
        species = _brochet()
        assert score_thermal(3.0, species) == 0.0
        assert score_thermal(-5.0, species) == 0.0

    def test_above_critical_is_0(self):
        species = _brochet()
        assert score_thermal(22.0, species) == 0.0
        assert score_thermal(30.0, species) == 0.0

    def test_below_optimal_linear_midpoint(self):
        # crit_min=4, opt_min=12. Midpoint w=8 should give 50.
        species = _brochet()
        assert score_thermal(8.0, species) == 50.0

    def test_above_optimal_linear_midpoint(self):
        # opt_max=18, crit_max=21. Midpoint w=19.5 should give 50.
        species = _brochet()
        assert score_thermal(19.5, species) == 50.0

    def test_below_optimal_three_quarters(self):
        # crit_min=4, opt_min=12. w=10 → 75% of span → score = 75.
        species = _brochet()
        assert score_thermal(10.0, species) == 75.0

    def test_score_is_continuous(self):
        # The piecewise function should not jump at the boundaries.
        species = _brochet()
        eps = 1e-9
        assert score_thermal(species.temp_optimal_min - eps, species) == pytest.approx(100.0)
        assert score_thermal(species.temp_critical_min + eps, species) == pytest.approx(0.0, abs=1e-7)


class TestScorePressure:
    def test_stable_in_optimal_band(self):
        assert score_pressure(1015.0, 0.0) == 100.0
        assert score_pressure(1013.0, 0.0) == 100.0
        assert score_pressure(1022.0, 0.0) == 100.0

    def test_below_optimal_linear_decay(self):
        # 1010: |1010 - 1017| = 7, decay 7*5 = 35 → score 65.
        assert score_pressure(1010.0, 0.0) == 65.0

    def test_far_from_optimal_floors_at_zero(self):
        # 997: |997 - 1017| = 20, decay 100 → score 0.
        assert score_pressure(997.0, 0.0) == 0.0

    def test_rising_trend_bonus(self):
        # Optimal pressure + rising trend: 100 + 10, clamped to 100.
        assert score_pressure(1015.0, 3.0) == 100.0
        # Below optimal: 1010 → base 65, +10 = 75.
        assert score_pressure(1010.0, 3.0) == 75.0

    def test_falling_trend_penalty(self):
        # Optimal pressure - 20 (penalty for sharp drop) → 80.
        assert score_pressure(1015.0, -5.0) == 80.0
        # Below optimal: 1010 base 65 -20 = 45.
        assert score_pressure(1010.0, -5.0) == 45.0

    def test_minor_trend_no_effect(self):
        # Trend within (-3, +2] → no bonus/penalty.
        assert score_pressure(1015.0, 1.0) == 100.0
        assert score_pressure(1015.0, -2.0) == 100.0
        assert score_pressure(1015.0, 2.0) == 100.0

    def test_falling_trend_cannot_go_negative(self):
        # 1000 base = 15, -20 penalty would give -5, clamped to 0.
        assert score_pressure(1000.0, -5.0) == 0.0

    def test_48h_trend_rising_adds_small_bonus(self):
        # Optimal pressure (100) with 48h rise > 4 hPa: + 5, clamped to 100.
        assert score_pressure(1015.0, 0.0, 5.0) == 100.0
        # Below optimal: 1010 → base 65, no 24h trend, 48h +5 → 70.
        assert score_pressure(1010.0, 0.0, 5.0) == 70.0

    def test_48h_trend_falling_adds_penalty(self):
        # Optimal pressure, 48h drop < -6 → -10 → 90.
        assert score_pressure(1015.0, 0.0, -7.0) == 90.0

    def test_24h_and_48h_trends_stack(self):
        # 1010 → base 65; 24h rise (+10) and 48h rise (+5) → 80.
        assert score_pressure(1010.0, 3.0, 5.0) == 80.0
        # 1010 → base 65; 24h drop (-20) and 48h drop (-10) → 35.
        assert score_pressure(1010.0, -5.0, -8.0) == 35.0

    def test_48h_trend_within_threshold_no_effect(self):
        # 48h trend in (-6, +4]: no change.
        assert score_pressure(1015.0, 0.0, 3.0) == 100.0
        assert score_pressure(1015.0, 0.0, -5.0) == 100.0


class TestScoreSolunar:
    @staticmethod
    def _solunar_with_periods(
        major: list[tuple[int, int]], minor: list[tuple[int, int]]
    ) -> SolunarDay:
        day = date(2026, 5, 12)
        midnight = datetime.combine(day, datetime.min.time())
        return SolunarDay(
            date=day,
            sunrise=midnight + timedelta(hours=6),
            sunset=midnight + timedelta(hours=21),
            moonrise=None,
            moonset=None,
            moon_phase=0.5,
            major_periods=[
                (midnight + timedelta(hours=s), midnight + timedelta(hours=e))
                for s, e in major
            ],
            minor_periods=[
                (midnight + timedelta(hours=s), midnight + timedelta(hours=e))
                for s, e in minor
            ],
        )

    def test_overlap_with_major_window(self):
        sd = self._solunar_with_periods(major=[(5, 7)], minor=[(11, 12)])
        # Species active 4-9: overlaps major (5-7).
        assert score_solunar(sd, [(4, 9)]) == 100.0

    def test_overlap_with_minor_window_only(self):
        sd = self._solunar_with_periods(major=[(11, 13)], minor=[(5, 7)])
        # Species active 4-9: overlaps minor (5-7) but not major (11-13).
        assert score_solunar(sd, [(4, 9)]) == 70.0

    def test_no_overlap_baseline(self):
        sd = self._solunar_with_periods(major=[(11, 13)], minor=[(14, 15)])
        # Species active 4-9 and 18-22, no overlap with either window.
        assert score_solunar(sd, [(4, 9), (18, 22)]) == 40.0

    def test_major_wins_over_minor(self):
        sd = self._solunar_with_periods(major=[(5, 7)], minor=[(5, 7)])
        assert score_solunar(sd, [(4, 9)]) == 100.0

    def test_active_hour_ending_at_24(self):
        # Active 22:00 → 24:00 should be representable.
        sd = self._solunar_with_periods(major=[(22, 23)], minor=[])
        assert score_solunar(sd, [(22, 24)]) == 100.0


class TestScoreMoon:
    def test_new_moon_is_100(self):
        assert score_moon(0.0) == 100.0

    def test_full_moon_is_100(self):
        assert score_moon(0.5) == 100.0

    def test_close_to_new_moon_is_100(self):
        assert score_moon(1.0) == 100.0

    def test_first_quarter_hits_floor(self):
        assert score_moon(0.25) == 60.0

    def test_last_quarter_hits_floor(self):
        assert score_moon(0.75) == 60.0

    def test_near_full_moon(self):
        # phase 0.4: distance = 0.1, score = 100 - 20 = 80.
        assert score_moon(0.4) == 80.0

    def test_near_new_moon(self):
        # phase 0.1: distance = 0.1, score = 80.
        assert score_moon(0.1) == 80.0

    def test_score_never_below_floor(self):
        for p in (0.2, 0.25, 0.3, 0.7, 0.75, 0.8):
            assert score_moon(p) >= 60.0


class TestScoreWeather:
    def test_perfect_conditions(self):
        # Cloud 50, wind 5, precip 0 → 100, 100, 100 → 100.
        assert score_weather(50.0, 5.0, 0.0) == 100.0

    def test_clear_sky(self):
        # Cloud 0, wind 5, precip 0 → cloud=25, wind=100, prec=100 → 75.
        assert score_weather(0.0, 5.0, 0.0) == 75.0

    def test_overcast(self):
        # Cloud 100, wind 5, precip 0 → cloud=25, wind=100, prec=100 → 75.
        assert score_weather(100.0, 5.0, 0.0) == 75.0

    def test_strong_wind(self):
        # Wind 25 → wind score = 100 - 10*5 = 50.
        # Cloud 50 → 100, precip 0 → 100. Avg = (100+50+100)/3 ≈ 83.33.
        assert score_weather(50.0, 25.0, 0.0) == pytest.approx(83.333, rel=1e-3)

    def test_heavy_rain(self):
        # Precip 7 → prec score = 100 - 5*10 = 50. Cloud 50 → 100. Wind 5 → 100.
        assert score_weather(50.0, 5.0, 7.0) == pytest.approx(83.333, rel=1e-3)

    def test_storm_conditions(self):
        # Wind 40 (>35), precip 15 (>12), cloud 100 → all sub-scores hit 0 or low.
        # wind: max(0, 100-(40-15)*5) = max(0, -25) = 0
        # precip: max(0, 100-(15-2)*10) = max(0, -30) = 0
        # cloud: max(0, 100-|100-50|*1.5) = max(0, 25) = 25
        assert score_weather(100.0, 40.0, 15.0) == pytest.approx(25.0 / 3.0, rel=1e-3)

    def test_threshold_boundaries(self):
        # Right at wind threshold: 15 km/h → wind score still 100? With strict <.
        # 15 km/h: decay (15-15)*5 = 0, score 100. Same value either way.
        assert score_weather(50.0, 14.9, 1.9) == 100.0
        # Just above thresholds: wind 16, precip 3 should be slightly lower.
        result = score_weather(50.0, 16.0, 3.0)
        assert result < 100.0


def _truite_fario() -> Species:
    return Species.model_validate(
        {
            "id": "truite_fario",
            "name": "Truite fario",
            "emoji": "🎣",
            "temp_optimal_min": 8,
            "temp_optimal_max": 16,
            "temp_critical_min": 2,
            "temp_critical_max": 19,
            "pressure_preference": "stable_or_rising",
            "active_hours": [[6, 10], [17, 21]],
            "season_active": [3, 4, 5, 6, 9],
            "weather_notes": "",
        }
    )


def _lyon_fleuve() -> Spot:
    return Spot.model_validate(
        {
            "id": "lyon",
            "name": "Lyon",
            "latitude": 45.764,
            "longitude": 4.8357,
            "type": "fleuve",
            "altitude": 170,
            "notes": "",
        }
    )


def _build_weather(
    day: date,
    *,
    air_temp: float = 20.0,
    cloud: float = 60.0,
    wind: float = 8.0,
    precip: float = 0.0,
    pressure_now: float = 1018.0,
    pressure_prev: float | None = None,
) -> WeatherData:
    """Build a WeatherData covering ``day - 1`` and ``day`` with uniform values."""
    if pressure_prev is None:
        pressure_prev = pressure_now
    midnight_prev = datetime.combine(day - timedelta(days=1), datetime.min.time())
    midnight_day = datetime.combine(day, datetime.min.time())
    hourly: list[HourlyWeather] = []
    for offset, pressure in ((midnight_prev, pressure_prev), (midnight_day, pressure_now)):
        for h in range(24):
            hourly.append(
                HourlyWeather(
                    time=offset + timedelta(hours=h),
                    temperature_2m=air_temp,
                    pressure_msl=pressure,
                    wind_speed_10m=wind,
                    wind_direction_10m=180.0,
                    cloud_cover=cloud,
                    precipitation=precip,
                )
            )
    return WeatherData(latitude=45.764, longitude=4.8357, hourly=hourly, daily=[])


def _build_solunar(
    day: date,
    *,
    moon_phase: float,
    major: list[tuple[int, int]],
    minor: list[tuple[int, int]] | None = None,
) -> SolunarDay:
    midnight = datetime.combine(day, datetime.min.time())
    return SolunarDay(
        date=day,
        sunrise=midnight + timedelta(hours=6),
        sunset=midnight + timedelta(hours=21),
        moonrise=None,
        moonset=None,
        moon_phase=moon_phase,
        major_periods=[
            (midnight + timedelta(hours=s), midnight + timedelta(hours=e))
            for s, e in major
        ],
        minor_periods=[
            (midnight + timedelta(hours=s), midnight + timedelta(hours=e))
            for s, e in (minor or [])
        ],
    )


class TestComputeDayScore:
    def test_ideal_pike_day_in_may(self):
        # Brochet, May, Lyon (fleuve). Air 20°C → water 18°C (top of optimal).
        # Pressure 1018 stable. Major period overlaps active 5-9.
        # Full moon, calm overcast.
        day = date(2026, 5, 12)
        breakdown = compute_day_score(
            _lyon_fleuve(),
            _brochet(),
            _build_weather(day, air_temp=20.0, cloud=60.0, wind=8.0, precip=0.0,
                           pressure_now=1018.0),
            _build_solunar(day, moon_phase=0.5, major=[(6, 8)], minor=[]),
        )

        assert breakdown.thermal == 100.0
        assert breakdown.pressure == 100.0
        assert breakdown.solunar == 100.0
        assert breakdown.moon == 100.0
        assert breakdown.weather > 80.0
        assert breakdown.total > 75.0

    def test_bad_trout_day_in_summer(self):
        # Trout in August — way too hot. Air 30°C → water 29°C (above critical 19).
        # Pressure 1005 with -5/24h drop. No solunar overlap. Quarter moon.
        # Windy with rain.
        day = date(2026, 8, 15)
        breakdown = compute_day_score(
            _lyon_fleuve(),
            _truite_fario(),
            _build_weather(
                day,
                air_temp=30.0,
                cloud=0.0,
                wind=35.0,
                precip=5.0,
                pressure_now=1005.0,
                pressure_prev=1010.0,
            ),
            _build_solunar(day, moon_phase=0.25, major=[(12, 14)], minor=[(15, 16)]),
        )

        assert breakdown.thermal == 0.0
        assert breakdown.pressure < 30.0  # 40 base - 20 trend penalty = 20
        assert breakdown.solunar == 40.0
        assert breakdown.moon == 60.0
        assert breakdown.total < 30.0

    def test_sharp_pressure_drop_significantly_lowers_score(self):
        # Same excellent baseline as the pike test, but pressure 1010 with
        # a 5 hPa drop in 24h. Expect a noticeably lower total and a
        # pressure sub-score well below 50.
        day = date(2026, 5, 12)
        spot = _lyon_fleuve()
        species = _brochet()
        solunar = _build_solunar(day, moon_phase=0.5, major=[(6, 8)], minor=[])

        baseline = compute_day_score(
            spot, species,
            _build_weather(day, pressure_now=1018.0),
            solunar,
        )
        dropping = compute_day_score(
            spot, species,
            _build_weather(day, pressure_now=1010.0, pressure_prev=1015.0),
            solunar,
        )

        assert dropping.pressure < 50.0
        assert dropping.pressure < baseline.pressure
        assert baseline.total - dropping.total >= 10.0

    def test_total_is_weighted_sum(self):
        # Sanity check: total = sum(sub_i × weight_i) within rounding.
        day = date(2026, 5, 12)
        breakdown = compute_day_score(
            _lyon_fleuve(),
            _brochet(),
            _build_weather(day, air_temp=20.0, cloud=60.0, wind=8.0,
                           pressure_now=1018.0),
            _build_solunar(day, moon_phase=0.5, major=[(6, 8)], minor=[]),
        )
        expected = (
            breakdown.thermal * 0.25
            + breakdown.pressure * 0.25
            + breakdown.solunar * 0.20
            + breakdown.moon * 0.10
            + breakdown.weather * 0.20
        )
        assert breakdown.total == pytest.approx(expected, abs=0.05)

    def test_out_of_season_total_is_dampened(self):
        # Brochet season_active = [3,4,5,9,10,11]. In July (month 7) the
        # species is biologically out of season, so the total is multiplied
        # by 0.6 even with ideal conditions.
        july_day = date(2026, 7, 12)
        spot = _lyon_fleuve()
        species = _brochet()
        solunar = _build_solunar(
            july_day, moon_phase=0.5, major=[(6, 8)], minor=[]
        )
        # In July, water temp will be 20-2+1=19°C (just above brochet optimal max 18 → near critical),
        # so thermal won't be ideal. Use a lower air temp to keep thermal high.
        weather = _build_weather(
            july_day, air_temp=18.0, cloud=60.0, wind=8.0, pressure_now=1018.0
        )
        in_season_solunar = _build_solunar(
            date(2026, 5, 12), moon_phase=0.5, major=[(6, 8)], minor=[]
        )
        in_season_weather = _build_weather(
            date(2026, 5, 12), air_temp=20.0, cloud=60.0, wind=8.0, pressure_now=1018.0
        )

        in_season_score = compute_day_score(
            spot, species, in_season_weather, in_season_solunar
        )
        out_of_season_score = compute_day_score(
            spot, species, weather, solunar
        )

        assert in_season_score.total > 70
        # Out-of-season total ≈ in_season × 0.6 (with similar sub-scores).
        assert out_of_season_score.total <= in_season_score.total * 0.65

    def test_in_season_total_not_dampened(self):
        # May is in brochet's season_active.
        day = date(2026, 5, 12)
        spot = _lyon_fleuve()
        species = _brochet()
        breakdown = compute_day_score(
            spot, species,
            _build_weather(day, air_temp=20.0, pressure_now=1018.0),
            _build_solunar(day, moon_phase=0.5, major=[(6, 8)], minor=[]),
        )
        expected_raw = (
            breakdown.thermal * 0.25
            + breakdown.pressure * 0.25
            + breakdown.solunar * 0.20
            + breakdown.moon * 0.10
            + breakdown.weather * 0.20
        )
        # In-season: total == weighted sum (no dampening).
        assert breakdown.total == pytest.approx(expected_raw, abs=0.05)

    def test_missing_target_day_raises(self):
        # Weather only covers 2026-05-11 and 2026-05-12 — asking for 13 fails.
        day = date(2026, 5, 13)
        with pytest.raises(ValueError, match="No hourly"):
            compute_day_score(
                _lyon_fleuve(),
                _brochet(),
                _build_weather(date(2026, 5, 12)),
                _build_solunar(day, moon_phase=0.5, major=[(6, 8)], minor=[]),
            )
