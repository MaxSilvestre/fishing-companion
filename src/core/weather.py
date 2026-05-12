"""Async client for the Open-Meteo forecast API.

Exposes ``fetch_forecast(latitude, longitude)`` which returns a fully
parsed ``WeatherData``. Includes a 30-minute in-memory cache and a
3-attempt exponential backoff retry policy on transient errors.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from src.core.models import DailyWeather, HourlyWeather, WeatherData

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_FIELDS = (
    "temperature_2m",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
    "precipitation",
)
DAILY_FIELDS = (
    "temperature_2m_min",
    "temperature_2m_max",
    "sunrise",
    "sunset",
)

FORECAST_DAYS = 7
# 3 past days lets us show yesterday in the dashboard AND compute a 48h
# pressure trend for it (needs day-before-yesterday and day-before-that).
PAST_DAYS = 3
CACHE_TTL_SECONDS = 30 * 60
MAX_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 15.0
LOCATION_PRECISION = 4

_cache: dict[tuple[float, float], tuple[float, WeatherData]] = {}


def clear_cache() -> None:
    """Empty the in-memory forecast cache. Useful for tests."""
    _cache.clear()


def _cache_key(latitude: float, longitude: float) -> tuple[float, float]:
    return (
        round(latitude, LOCATION_PRECISION),
        round(longitude, LOCATION_PRECISION),
    )


def _build_params(latitude: float, longitude: float) -> dict[str, Any]:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "timezone": "auto",
        "forecast_days": FORECAST_DAYS,
        "past_days": PAST_DAYS,
    }


def _parse_response(payload: dict[str, Any]) -> WeatherData:
    hourly_raw = payload["hourly"]
    hourly = [
        HourlyWeather(
            time=t,
            temperature_2m=temp,
            pressure_msl=pres,
            wind_speed_10m=ws,
            wind_direction_10m=wd,
            cloud_cover=cc,
            precipitation=p,
        )
        for t, temp, pres, ws, wd, cc, p in zip(
            hourly_raw["time"],
            hourly_raw["temperature_2m"],
            hourly_raw["pressure_msl"],
            hourly_raw["wind_speed_10m"],
            hourly_raw["wind_direction_10m"],
            hourly_raw["cloud_cover"],
            hourly_raw["precipitation"],
            strict=True,
        )
    ]

    daily_raw = payload["daily"]
    daily = [
        DailyWeather(
            date=d,
            temperature_2m_min=tmin,
            temperature_2m_max=tmax,
            sunrise=sr,
            sunset=ss,
        )
        for d, tmin, tmax, sr, ss in zip(
            daily_raw["time"],
            daily_raw["temperature_2m_min"],
            daily_raw["temperature_2m_max"],
            daily_raw["sunrise"],
            daily_raw["sunset"],
            strict=True,
        )
    ]

    return WeatherData(
        latitude=payload["latitude"],
        longitude=payload["longitude"],
        hourly=hourly,
        daily=daily,
    )


async def _fetch_with_retry(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    delay = INITIAL_BACKOFF_SECONDS
    last_exc: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.get(API_URL, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 400 <= status < 500:
                logger.error("Open-Meteo client error %s, not retrying", status)
                raise
            last_exc = exc
            logger.warning(
                "Open-Meteo server error %s on attempt %d/%d",
                status,
                attempt,
                MAX_ATTEMPTS,
            )
        except httpx.RequestError as exc:
            last_exc = exc
            logger.warning(
                "Open-Meteo network error on attempt %d/%d: %s",
                attempt,
                MAX_ATTEMPTS,
                exc,
            )

        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(delay)
            delay *= 2

    assert last_exc is not None
    raise last_exc


async def fetch_forecast(
    latitude: float,
    longitude: float,
    *,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> WeatherData:
    """Fetch a 7-day forecast (plus 1 past day) for the given coordinates.

    Results are cached in-memory for ``CACHE_TTL_SECONDS``. If ``client``
    is not provided, a short-lived AsyncClient is created and closed.
    """
    key = _cache_key(latitude, longitude)
    now = time.time()

    if use_cache:
        cached = _cache.get(key)
        if cached is not None and (now - cached[0]) < CACHE_TTL_SECONDS:
            logger.info("Weather cache hit for %s", key)
            return cached[1]

    params = _build_params(latitude, longitude)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)

    try:
        payload = await _fetch_with_retry(active_client, params)
    finally:
        if owns_client:
            await active_client.aclose()

    weather = _parse_response(payload)
    _cache[key] = (now, weather)
    logger.info(
        "Fetched weather for %s (%d hourly, %d daily)",
        key,
        len(weather.hourly),
        len(weather.daily),
    )
    return weather
