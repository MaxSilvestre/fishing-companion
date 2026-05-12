"""Integration tests for src.core.pipeline.

These tests stub Open-Meteo via ``httpx.MockTransport`` and verify that
``compute_all_scores`` orchestrates weather, solunar, and scoring
correctly across spots, days, and species.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from src.core.models import Species, Spot
from src.core.pipeline import compute_all_scores
from src.core.weather import clear_cache


def _spots() -> list[Spot]:
    return [
        Spot.model_validate(
            {"id": "lyon", "name": "Lyon", "latitude": 45.764,
             "longitude": 4.8357, "type": "fleuve", "altitude": 170}
        ),
        Spot.model_validate(
            {"id": "vienne", "name": "Vienne", "latitude": 45.5256,
             "longitude": 4.8743, "type": "fleuve", "altitude": 160}
        ),
        Spot.model_validate(
            {"id": "lozanne", "name": "Lozanne", "latitude": 45.8548,
             "longitude": 4.6802, "type": "riviere", "altitude": 230}
        ),
    ]


def _species() -> list[Species]:
    return [
        Species.model_validate({
            "id": "brochet", "name": "Brochet", "emoji": "🐊",
            "temp_optimal_min": 12, "temp_optimal_max": 18,
            "temp_critical_min": 4, "temp_critical_max": 21,
            "pressure_preference": "stable_or_rising",
            "active_hours": [[5, 9], [17, 21]],
            "season_active": [3, 4, 5, 9, 10, 11],
        }),
        Species.model_validate({
            "id": "perche", "name": "Perche", "emoji": "🐠",
            "temp_optimal_min": 14, "temp_optimal_max": 22,
            "temp_critical_min": 6, "temp_critical_max": 25,
            "pressure_preference": "stable_or_rising",
            "active_hours": [[7, 11], [15, 19]],
            "season_active": [4, 5, 6, 7, 8, 9, 10],
        }),
    ]


def _fake_payload(start: date, days_total: int = 8) -> dict:
    """Build a fake Open-Meteo response covering ``start - 1d`` to ``start + (days_total-2)d``."""
    base_day = start - timedelta(days=1)
    base_midnight = datetime.combine(base_day, datetime.min.time())
    n_hours = 24 * days_total
    return {
        "latitude": 45.764,
        "longitude": 4.8357,
        "hourly": {
            "time": [
                (base_midnight + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
                for i in range(n_hours)
            ],
            "temperature_2m": [18.0] * n_hours,
            "pressure_msl": [1018.0] * n_hours,
            "wind_speed_10m": [6.0] * n_hours,
            "wind_direction_10m": [180.0] * n_hours,
            "cloud_cover": [60.0] * n_hours,
            "precipitation": [0.0] * n_hours,
        },
        "daily": {
            "time": [(base_day + timedelta(days=i)).isoformat() for i in range(days_total)],
            "temperature_2m_min": [10.0] * days_total,
            "temperature_2m_max": [22.0] * days_total,
            "sunrise": [
                (base_midnight + timedelta(days=i, hours=6)).strftime("%Y-%m-%dT%H:%M")
                for i in range(days_total)
            ],
            "sunset": [
                (base_midnight + timedelta(days=i, hours=21)).strftime("%Y-%m-%dT%H:%M")
                for i in range(days_total)
            ],
        },
    }


@pytest.fixture(autouse=True)
def _isolate():
    # Pipeline tests don't trigger retry sleeps, so we only isolate the
    # weather cache between runs. (Patching asyncio.sleep globally would
    # break the concurrency-yielding behavior the parallel test needs.)
    clear_cache()
    yield
    clear_cache()


async def test_pipeline_produces_full_matrix():
    spots = _spots()
    species = _species()
    days = 7
    start = date(2026, 5, 12)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=_fake_payload(start))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        matrix = await compute_all_scores(
            spots, species, days=days, start_date=start, client=client
        )

    # One HTTP call per spot (concurrent fetch).
    assert len(calls) == len(spots)

    # Scores: spots × days × species.
    assert len(matrix.scores) == len(spots) * days * len(species)

    # Weather and solunar populated for every spot.
    assert set(matrix.weather_by_spot.keys()) == {s.id for s in spots}
    assert set(matrix.solunar_by_spot.keys()) == {s.id for s in spots}
    for spot_id, solunar_days in matrix.solunar_by_spot.items():
        assert len(solunar_days) == days

    # generated_at is recent (sanity check) — pipeline now returns tz-aware UTC.
    assert matrix.generated_at.tzinfo is not None
    assert (datetime.now(timezone.utc) - matrix.generated_at).total_seconds() < 60


async def test_pipeline_lookup_roundtrip():
    spots = _spots()
    species = _species()
    start = date(2026, 5, 12)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_fake_payload(start))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        matrix = await compute_all_scores(
            spots, species, days=3, start_date=start, client=client
        )

    score = matrix.get_score("lyon", start, "brochet")
    assert score is not None
    assert 0.0 <= score.breakdown.total <= 100.0

    # Missing combinations return None.
    assert matrix.get_score("unknown", start, "brochet") is None
    assert matrix.get_score("lyon", start + timedelta(days=99), "brochet") is None


async def test_pipeline_iterates_all_target_dates():
    spots = _spots()[:1]
    species = _species()[:1]
    start = date(2026, 5, 12)
    days = 5

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_fake_payload(start, days_total=days + 1))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        matrix = await compute_all_scores(
            spots, species, days=days, start_date=start, client=client
        )

    dates = {s.date for s in matrix.scores}
    expected = {start + timedelta(days=i) for i in range(days)}
    assert dates == expected


async def test_pipeline_propagates_weather_errors():
    spots = _spots()[:1]
    species = _species()[:1]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad params"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await compute_all_scores(
                spots, species, days=3,
                start_date=date(2026, 5, 12), client=client,
            )


async def test_pipeline_fetches_in_parallel():
    """All weather calls overlap — verified by tracking concurrent in-flight count."""
    import asyncio

    spots = _spots()
    species = _species()[:1]
    start = date(2026, 5, 12)

    in_flight = 0
    peak = 0

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json=_fake_payload(start))

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow_handler)) as client:
        await compute_all_scores(
            spots, species, days=3, start_date=start, client=client
        )

    assert peak >= 2, f"expected concurrent fetches, got peak={peak}"
