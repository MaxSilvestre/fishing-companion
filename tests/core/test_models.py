"""Tests for src.core.models and src.core.config."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.config import (
    ConfigError,
    load_species,
    load_spots,
)
from src.core.models import (
    DailyWeather,
    DayScore,
    HourlyWeather,
    ScoreBreakdown,
    ScoresMatrix,
    SolunarDay,
    Species,
    Spot,
    WeatherData,
)


def _make_valid_spot(**overrides) -> dict:
    base = {
        "id": "lyon",
        "name": "Lyon",
        "latitude": 45.764,
        "longitude": 4.8357,
        "type": "fleuve",
        "altitude": 170,
        "notes": "test",
    }
    base.update(overrides)
    return base


def _make_valid_species(**overrides) -> dict:
    base = {
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
        "weather_notes": "test",
    }
    base.update(overrides)
    return base


class TestSpot:
    def test_valid(self):
        spot = Spot.model_validate(_make_valid_spot())
        assert spot.id == "lyon"
        assert spot.type == "fleuve"

    def test_invalid_latitude_too_high(self):
        with pytest.raises(ValidationError):
            Spot.model_validate(_make_valid_spot(latitude=91))

    def test_invalid_latitude_too_low(self):
        with pytest.raises(ValidationError):
            Spot.model_validate(_make_valid_spot(latitude=-91))

    def test_invalid_longitude(self):
        with pytest.raises(ValidationError):
            Spot.model_validate(_make_valid_spot(longitude=200))

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            Spot.model_validate(_make_valid_spot(type="ocean"))

    def test_empty_id_rejected(self):
        with pytest.raises(ValidationError):
            Spot.model_validate(_make_valid_spot(id=""))

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            Spot.model_validate(_make_valid_spot(extra_field="nope"))


class TestSpecies:
    def test_valid(self):
        species = Species.model_validate(_make_valid_species())
        assert species.id == "brochet"
        assert species.active_hours == [(5, 9), (17, 21)]

    def test_invalid_temperature_order_optimal_inverted(self):
        with pytest.raises(ValidationError):
            Species.model_validate(
                _make_valid_species(temp_optimal_min=20, temp_optimal_max=10)
            )

    def test_invalid_temperature_optimal_outside_critical(self):
        with pytest.raises(ValidationError):
            Species.model_validate(
                _make_valid_species(temp_critical_min=15, temp_optimal_min=10)
            )

    def test_invalid_active_hours_reversed(self):
        with pytest.raises(ValidationError):
            Species.model_validate(_make_valid_species(active_hours=[[9, 5]]))

    def test_invalid_active_hours_out_of_range(self):
        with pytest.raises(ValidationError):
            Species.model_validate(_make_valid_species(active_hours=[[20, 25]]))

    def test_invalid_pressure_preference(self):
        with pytest.raises(ValidationError):
            Species.model_validate(
                _make_valid_species(pressure_preference="falling")
            )

    def test_invalid_season_month(self):
        with pytest.raises(ValidationError):
            Species.model_validate(_make_valid_species(season_active=[0, 4]))

    def test_invalid_season_duplicate(self):
        with pytest.raises(ValidationError):
            Species.model_validate(_make_valid_species(season_active=[4, 4, 5]))


class TestScoreBreakdown:
    def test_valid(self):
        breakdown = ScoreBreakdown(
            thermal=80,
            pressure=70,
            solunar=60,
            moon=50,
            weather=90,
            total=72.5,
        )
        assert breakdown.total == 72.5

    def test_subscore_above_100_rejected(self):
        with pytest.raises(ValidationError):
            ScoreBreakdown(
                thermal=101, pressure=0, solunar=0, moon=0, weather=0, total=0
            )

    def test_negative_subscore_rejected(self):
        with pytest.raises(ValidationError):
            ScoreBreakdown(
                thermal=-1, pressure=0, solunar=0, moon=0, weather=0, total=0
            )


class TestWeatherModels:
    def test_hourly_weather_cloud_cover_clamped(self):
        with pytest.raises(ValidationError):
            HourlyWeather(
                time=datetime(2026, 5, 12, 10),
                temperature_2m=15.0,
                surface_pressure=1015.0,
                wind_speed_10m=5.0,
                wind_direction_10m=180.0,
                cloud_cover=110.0,
                precipitation=0.0,
            )

    def test_daily_weather_valid(self):
        d = DailyWeather(
            date=date(2026, 5, 12),
            temperature_2m_min=10.0,
            temperature_2m_max=22.0,
            sunrise=datetime(2026, 5, 12, 6, 15),
            sunset=datetime(2026, 5, 12, 21, 5),
        )
        assert d.date == date(2026, 5, 12)

    def test_weather_data_empty_series(self):
        wd = WeatherData(latitude=45.0, longitude=4.0, hourly=[], daily=[])
        assert wd.hourly == []


class TestSolunarAndScores:
    def test_solunar_day_valid(self):
        sd = SolunarDay(
            date=date(2026, 5, 12),
            sunrise=datetime(2026, 5, 12, 6, 15),
            sunset=datetime(2026, 5, 12, 21, 5),
            moonrise=datetime(2026, 5, 12, 22, 0),
            moonset=datetime(2026, 5, 12, 7, 30),
            moon_phase=0.5,
            major_periods=[],
            minor_periods=[],
        )
        assert sd.moon_phase == 0.5

    def test_solunar_moon_phase_above_one_rejected(self):
        with pytest.raises(ValidationError):
            SolunarDay(
                date=date(2026, 5, 12),
                sunrise=datetime(2026, 5, 12, 6, 15),
                sunset=datetime(2026, 5, 12, 21, 5),
                moonrise=None,
                moonset=None,
                moon_phase=1.5,
                major_periods=[],
                minor_periods=[],
            )

    def test_scores_matrix_get_score(self):
        breakdown = ScoreBreakdown(
            thermal=80, pressure=70, solunar=60, moon=50, weather=90, total=72.5
        )
        score = DayScore(
            spot_id="lyon",
            species_id="brochet",
            date=date(2026, 5, 12),
            breakdown=breakdown,
        )
        matrix = ScoresMatrix(
            generated_at=datetime(2026, 5, 12, 5, 0),
            spots=[],
            species=[],
            scores=[score],
            weather_by_spot={},
            solunar_by_spot={},
        )
        found = matrix.get_score("lyon", date(2026, 5, 12), "brochet")
        assert found is score
        assert matrix.get_score("vienne", date(2026, 5, 12), "brochet") is None


class TestConfigLoaders:
    def test_load_spots_returns_three(self):
        spots = load_spots()
        assert len(spots) == 3
        assert {s.id for s in spots} == {"lyon", "vienne", "lozanne"}

    def test_load_species_returns_five(self):
        species = load_species()
        ids = {s.id for s in species}
        assert ids == {"brochet", "sandre", "perche", "black_bass", "truite_fario"}

    def test_load_spots_missing_file(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="not found"):
            load_spots(tmp_path / "missing.json")

    def test_load_spots_invalid_json(self, tmp_path: Path):
        bad = tmp_path / "spots.json"
        bad.write_text("{not valid json")
        with pytest.raises(ConfigError, match="Invalid JSON"):
            load_spots(bad)

    def test_load_spots_wrong_shape(self, tmp_path: Path):
        bad = tmp_path / "spots.json"
        bad.write_text(json.dumps({"not": "a list"}))
        with pytest.raises(ConfigError, match="array"):
            load_spots(bad)

    def test_load_spots_validation_error(self, tmp_path: Path):
        bad = tmp_path / "spots.json"
        bad.write_text(
            json.dumps([{"id": "x", "name": "y", "latitude": 999,
                         "longitude": 0, "type": "lac", "altitude": 0}])
        )
        with pytest.raises(ConfigError, match="Invalid spots"):
            load_spots(bad)

    def test_load_species_validation_error(self, tmp_path: Path):
        bad = tmp_path / "species.json"
        bad.write_text(
            json.dumps([_make_valid_species(temp_optimal_min=99)])
        )
        with pytest.raises(ConfigError, match="Invalid species"):
            load_species(bad)
