"""Tests for src.core.weather using httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from src.core import weather as weather_module
from src.core.weather import API_URL, clear_cache, fetch_forecast


def _fake_payload(latitude: float = 45.764, longitude: float = 4.8357) -> dict:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": {
            "time": [
                "2026-05-12T00:00",
                "2026-05-12T01:00",
                "2026-05-12T02:00",
            ],
            "temperature_2m": [10.0, 9.8, 9.5],
            "surface_pressure": [1015.0, 1015.5, 1016.0],
            "wind_speed_10m": [5.0, 4.5, 4.0],
            "wind_direction_10m": [180.0, 190.0, 200.0],
            "cloud_cover": [50.0, 55.0, 60.0],
            "precipitation": [0.0, 0.1, 0.0],
        },
        "daily": {
            "time": ["2026-05-12", "2026-05-13"],
            "temperature_2m_min": [8.0, 9.0],
            "temperature_2m_max": [18.0, 20.0],
            "sunrise": ["2026-05-12T06:15", "2026-05-13T06:14"],
            "sunset": ["2026-05-12T21:05", "2026-05-13T21:06"],
        },
    }


def _make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _isolate_cache_and_skip_sleeps(monkeypatch):
    clear_cache()

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(weather_module.asyncio, "sleep", _instant)
    yield
    clear_cache()


async def test_fetch_returns_parsed_weather():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_fake_payload())

    async with _make_client(handler) as client:
        wd = await fetch_forecast(45.764, 4.8357, client=client)

    assert str(API_URL) in captured["url"]
    assert "latitude=45.764" in captured["url"]
    assert "longitude=4.8357" in captured["url"]
    assert "past_days=1" in captured["url"]
    assert "forecast_days=7" in captured["url"]
    assert "timezone=auto" in captured["url"]

    assert wd.latitude == 45.764
    assert len(wd.hourly) == 3
    assert wd.hourly[0].temperature_2m == 10.0
    assert wd.hourly[0].surface_pressure == 1015.0
    assert len(wd.daily) == 2
    assert wd.daily[0].temperature_2m_max == 18.0


async def test_cache_avoids_second_call():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=_fake_payload())

    async with _make_client(handler) as client:
        first = await fetch_forecast(45.764, 4.8357, client=client)
        second = await fetch_forecast(45.764, 4.8357, client=client)

    assert calls["count"] == 1
    assert first is second


async def test_cache_disabled_makes_two_calls():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=_fake_payload())

    async with _make_client(handler) as client:
        await fetch_forecast(45.764, 4.8357, client=client, use_cache=False)
        await fetch_forecast(45.764, 4.8357, client=client, use_cache=False)

    assert calls["count"] == 2


async def test_cache_keys_round_coordinates():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=_fake_payload())

    async with _make_client(handler) as client:
        await fetch_forecast(45.76401, 4.83571, client=client)
        await fetch_forecast(45.76402, 4.83573, client=client)

    assert calls["count"] == 1


async def test_retry_then_success():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.ConnectError("network down")
        return httpx.Response(200, json=_fake_payload())

    async with _make_client(handler) as client:
        wd = await fetch_forecast(45.764, 4.8357, client=client)

    assert calls["count"] == 3
    assert wd.latitude == 45.764


async def test_retry_exhausted_raises():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectError("network down")

    async with _make_client(handler) as client:
        with pytest.raises(httpx.ConnectError):
            await fetch_forecast(45.764, 4.8357, client=client)

    assert calls["count"] == 3


async def test_5xx_is_retried():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, text="service unavailable")

    async with _make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_forecast(45.764, 4.8357, client=client)

    assert calls["count"] == 3


async def test_4xx_fails_fast_without_retry():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, json={"reason": "bad params"})

    async with _make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_forecast(45.764, 4.8357, client=client)

    assert calls["count"] == 1


async def test_failure_does_not_pollute_cache():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] <= 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=_fake_payload())

    async with _make_client(handler) as client:
        with pytest.raises(httpx.ConnectError):
            await fetch_forecast(45.764, 4.8357, client=client)
        wd = await fetch_forecast(45.764, 4.8357, client=client)

    assert calls["count"] == 4
    assert wd.latitude == 45.764
