"""End-to-end orchestration of the core: weather + solunar + scoring.

``compute_all_scores`` is the single entry point a facade (web, telegram,
...) needs to call. It fetches all weather forecasts concurrently, then
computes solunar and scores for every (spot, day, species) triple.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from src.core.models import (
    DayScore,
    ScoresMatrix,
    SolunarDay,
    Species,
    Spot,
)
from src.core.scoring import compute_day_score
from src.core.solunar import compute_solunar
from src.core.weather import HTTP_TIMEOUT_SECONDS, fetch_forecast

logger = logging.getLogger(__name__)

DEFAULT_FORECAST_DAYS = 7


async def compute_all_scores(
    spots: list[Spot],
    species: list[Species],
    *,
    days: int = DEFAULT_FORECAST_DAYS,
    start_date: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> ScoresMatrix:
    """Compute the full ScoresMatrix for every (spot, day, species) triple.

    Fetches all weather forecasts concurrently using a single
    ``httpx.AsyncClient``, then computes solunar and scoring sequentially
    (both CPU-bound and fast).
    """
    start = start_date or date.today()
    target_dates = [start + timedelta(days=i) for i in range(days)]

    logger.info(
        "Computing scores for %d spots × %d species × %d days",
        len(spots),
        len(species),
        days,
    )

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)

    try:
        weather_results = await asyncio.gather(
            *[
                fetch_forecast(spot.latitude, spot.longitude, client=active_client)
                for spot in spots
            ]
        )
    finally:
        if owns_client:
            await active_client.aclose()

    weather_by_spot = {spot.id: w for spot, w in zip(spots, weather_results)}
    logger.info("Fetched weather for %d spots", len(spots))

    solunar_by_spot: dict[str, list[SolunarDay]] = {}
    scores: list[DayScore] = []

    for spot in spots:
        weather = weather_by_spot[spot.id]
        spot_solunar: list[SolunarDay] = []
        for target in target_dates:
            solunar = compute_solunar(target, spot.latitude, spot.longitude)
            spot_solunar.append(solunar)
            for sp in species:
                breakdown = compute_day_score(spot, sp, weather, solunar)
                scores.append(
                    DayScore(
                        spot_id=spot.id,
                        species_id=sp.id,
                        date=target,
                        breakdown=breakdown,
                    )
                )
        solunar_by_spot[spot.id] = spot_solunar

    logger.info("Computed %d day scores", len(scores))

    return ScoresMatrix(
        generated_at=datetime.now(timezone.utc),
        spots=spots,
        species=species,
        scores=scores,
        weather_by_spot=weather_by_spot,
        solunar_by_spot=solunar_by_spot,
    )
