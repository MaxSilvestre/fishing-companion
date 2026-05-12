"""Pydantic models for the fishing-companion core domain.

This module defines the data shapes shared across the core pipeline:
configuration (spots, species), weather observations, solunar data,
and the final scoring matrix that any facade (web, telegram, ...) consumes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SpotType = Literal["fleuve", "riviere", "lac", "mer"]
Habitat = Literal["freshwater", "saltwater"]
PressurePreference = Literal["stable", "rising", "stable_or_rising"]

SALTWATER_SPOT_TYPES: frozenset[SpotType] = frozenset({"mer"})


def spot_habitat(spot_type: SpotType) -> Habitat:
    """Derive the habitat (freshwater/saltwater) from a spot type."""
    return "saltwater" if spot_type in SALTWATER_SPOT_TYPES else "freshwater"

MIN_HOUR = 0
MAX_HOUR = 24
MIN_MONTH = 1
MAX_MONTH = 12


class Spot(BaseModel):
    """A fishing location with geographic and structural attributes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    type: SpotType
    altitude: int = Field(..., ge=-500, le=9000)
    notes: str = ""


class Species(BaseModel):
    """A fish species with biological and environmental preferences."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    emoji: str = Field(..., min_length=1)
    temp_optimal_min: float
    temp_optimal_max: float
    temp_critical_min: float
    temp_critical_max: float
    pressure_preference: PressurePreference
    active_hours: list[tuple[int, int]]
    season_active: list[int]
    habitat: Habitat = "freshwater"
    weather_notes: str = ""

    @model_validator(mode="after")
    def _validate_temperature_band(self) -> Species:
        if not (
            self.temp_critical_min
            <= self.temp_optimal_min
            < self.temp_optimal_max
            <= self.temp_critical_max
        ):
            raise ValueError(
                "Species temperatures must satisfy "
                "temp_critical_min <= temp_optimal_min < temp_optimal_max <= temp_critical_max "
                f"(got crit_min={self.temp_critical_min}, opt_min={self.temp_optimal_min}, "
                f"opt_max={self.temp_optimal_max}, crit_max={self.temp_critical_max})"
            )
        return self

    @model_validator(mode="after")
    def _validate_active_hours(self) -> Species:
        for start, end in self.active_hours:
            if not (MIN_HOUR <= start < end <= MAX_HOUR):
                raise ValueError(
                    f"Active hour window must satisfy {MIN_HOUR} <= start < end <= {MAX_HOUR} "
                    f"(got [{start}, {end}])"
                )
        return self

    @model_validator(mode="after")
    def _validate_season_active(self) -> Species:
        for month in self.season_active:
            if not (MIN_MONTH <= month <= MAX_MONTH):
                raise ValueError(
                    f"Season month must be in [{MIN_MONTH}, {MAX_MONTH}] (got {month})"
                )
        if len(self.season_active) != len(set(self.season_active)):
            raise ValueError("Season months must be unique")
        return self


class HourlyWeather(BaseModel):
    """A single-hour weather observation from Open-Meteo."""

    model_config = ConfigDict(extra="forbid")

    time: datetime
    temperature_2m: float
    pressure_msl: float
    wind_speed_10m: float = Field(..., ge=0.0)
    wind_direction_10m: float = Field(..., ge=0.0, le=360.0)
    cloud_cover: float = Field(..., ge=0.0, le=100.0)
    precipitation: float = Field(..., ge=0.0)


class DailyWeather(BaseModel):
    """A single-day weather summary from Open-Meteo."""

    model_config = ConfigDict(extra="forbid")

    date: date
    temperature_2m_min: float
    temperature_2m_max: float
    sunrise: datetime
    sunset: datetime


class WeatherData(BaseModel):
    """Full weather payload for one spot: hourly and daily series."""

    model_config = ConfigDict(extra="forbid")

    latitude: float
    longitude: float
    hourly: list[HourlyWeather]
    daily: list[DailyWeather]


class SolunarDay(BaseModel):
    """Solunar computation for one location on one day."""

    model_config = ConfigDict(extra="forbid")

    date: date
    sunrise: datetime
    sunset: datetime
    moonrise: datetime | None
    moonset: datetime | None
    moon_phase: float = Field(..., ge=0.0, le=1.0)
    major_periods: list[tuple[datetime, datetime]]
    minor_periods: list[tuple[datetime, datetime]]


class ScoreBreakdown(BaseModel):
    """Sub-scores composing a day score, all in [0, 100]."""

    model_config = ConfigDict(extra="forbid")

    thermal: float = Field(..., ge=0.0, le=100.0)
    pressure: float = Field(..., ge=0.0, le=100.0)
    solunar: float = Field(..., ge=0.0, le=100.0)
    moon: float = Field(..., ge=0.0, le=100.0)
    weather: float = Field(..., ge=0.0, le=100.0)
    total: float = Field(..., ge=0.0, le=100.0)


class DayScore(BaseModel):
    """Activity score for a (spot, species, date) triple."""

    model_config = ConfigDict(extra="forbid")

    spot_id: str
    species_id: str
    date: date
    breakdown: ScoreBreakdown


class ScoresMatrix(BaseModel):
    """Top-level result returned by the core pipeline.

    Holds every DayScore for the forecast horizon, plus the underlying
    weather and solunar data so facades can render detail views.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    spots: list[Spot]
    species: list[Species]
    scores: list[DayScore]
    weather_by_spot: dict[str, WeatherData]
    solunar_by_spot: dict[str, list[SolunarDay]]

    def get_score(
        self, spot_id: str, day: date, species_id: str
    ) -> DayScore | None:
        """Return the DayScore for a (spot, day, species) triple, or None."""
        for entry in self.scores:
            if (
                entry.spot_id == spot_id
                and entry.date == day
                and entry.species_id == species_id
            ):
                return entry
        return None
