"""Render a ScoresMatrix into the static files served on GitHub Pages.

Returns a dict mapping output filename (relative to ``docs/``) to its
contents. The web facade writer (generate.py) is responsible for writing
those files to disk.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.core.models import ScoresMatrix, SolunarDay, WeatherData, spot_habitat
from src.core.scoring import aggregate_day_weather

DISPLAY_TIMEZONE = ZoneInfo("Europe/Paris")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

WEEKDAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

SCORE_TIER_GOOD = 70
SCORE_TIER_MID = 40

STATIC_ASSETS = ("style.css", "app.js", "manifest.json", "icon.svg")

WORKFLOW_PATH = "/actions/workflows/daily.yml"


def _format_generated_at(dt: datetime) -> str:
    """Format a generated-at datetime for display in Europe/Paris local time.

    Naive datetimes are assumed to be UTC (matches the pipeline convention
    and GitHub Actions runners).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def _score_tier(score: int | None) -> str:
    if score is None:
        return "none"
    if score >= SCORE_TIER_GOOD:
        return "good"
    if score >= SCORE_TIER_MID:
        return "mid"
    return "bad"


def _hhmm(dt) -> str | None:
    return dt.strftime("%H:%M") if dt is not None else None


def _solunar_to_dict(solunar: SolunarDay) -> dict[str, Any]:
    return {
        "sunrise": _hhmm(solunar.sunrise),
        "sunset": _hhmm(solunar.sunset),
        "moonrise": _hhmm(solunar.moonrise),
        "moonset": _hhmm(solunar.moonset),
        "moon_phase": round(solunar.moon_phase, 3),
        "major_periods": [
            [_hhmm(s), _hhmm(e)] for s, e in solunar.major_periods
        ],
        "minor_periods": [
            [_hhmm(s), _hhmm(e)] for s, e in solunar.minor_periods
        ],
    }


def _weather_aggregates_to_dict(
    weather: WeatherData, day
) -> dict[str, float] | None:
    try:
        agg = aggregate_day_weather(weather, day)
    except ValueError:
        return None
    return {
        "air_temp_avg": round(agg["air_temp_avg"], 1),
        "pressure_now": round(agg["pressure_now"], 1),
        "trend_24h": round(agg["trend_24h"], 1),
        "cloud_avg": round(agg["cloud_avg"], 1),
        "wind_max": round(agg["wind_max"], 1),
        "precip_total": round(agg["precip_total"], 1),
    }


def _day_label(d: date, today: date) -> str:
    """Return a short relative or weekday label for a date row."""
    delta = (d - today).days
    if delta == -1:
        return "Hier"
    if delta == 0:
        return "Auj."
    return WEEKDAYS_FR[d.weekday()]


def _build_view(matrix: ScoresMatrix) -> dict[str, Any]:
    """Project the matrix into a template-friendly nested structure."""
    dates = sorted({score.date for score in matrix.scores})
    today = (
        matrix.generated_at.astimezone(DISPLAY_TIMEZONE).date()
        if matrix.generated_at.tzinfo is not None
        else matrix.generated_at.date()
    )

    spots_view = []
    for spot in matrix.spots:
        habitat = spot_habitat(spot.type)
        spot_species = [s for s in matrix.species if s.habitat == habitat]
        rows = []
        for d in dates:
            cells = []
            for species in spot_species:
                score = matrix.get_score(spot.id, d, species.id)
                value = int(round(score.breakdown.total)) if score else None
                cells.append(
                    {
                        "species_id": species.id,
                        "species_name": species.name,
                        "score": value,
                        "tier": _score_tier(value),
                    }
                )
            rows.append(
                {
                    "date_iso": d.isoformat(),
                    "date_short": d.strftime("%d/%m"),
                    "weekday": _day_label(d, today),
                    "is_past": d < today,
                    "is_today": d == today,
                    "cells": cells,
                }
            )
        spots_view.append(
            {
                "id": spot.id,
                "name": spot.name,
                "species": [
                    {"id": s.id, "name": s.name, "emoji": s.emoji}
                    for s in spot_species
                ],
                "rows": rows,
            }
        )

    return {
        "generated_at": _format_generated_at(matrix.generated_at),
        "spots": spots_view,
        "species": [
            {"id": sp.id, "name": sp.name, "emoji": sp.emoji}
            for sp in matrix.species
        ],
    }


def _build_detail_payload(matrix: ScoresMatrix) -> dict[str, Any]:
    """Build the per-cell detail data embedded in the HTML for client-side use."""
    dates = sorted({score.date for score in matrix.scores})

    species_meta = {
        sp.id: {"name": sp.name, "emoji": sp.emoji} for sp in matrix.species
    }

    spots_payload: dict[str, Any] = {}
    for spot in matrix.spots:
        weather = matrix.weather_by_spot.get(spot.id)
        solunar_by_date = {
            sd.date: sd for sd in matrix.solunar_by_spot.get(spot.id, [])
        }
        days_payload: dict[str, Any] = {}
        for d in dates:
            scores_for_day: dict[str, Any] = {}
            for sp in matrix.species:
                ds = matrix.get_score(spot.id, d, sp.id)
                if ds is None:
                    continue
                b = ds.breakdown
                scores_for_day[sp.id] = {
                    "total": int(round(b.total)),
                    "thermal": round(b.thermal, 1),
                    "pressure": round(b.pressure, 1),
                    "solunar": round(b.solunar, 1),
                    "moon": round(b.moon, 1),
                    "weather": round(b.weather, 1),
                }
            days_payload[d.isoformat()] = {
                "weather": _weather_aggregates_to_dict(weather, d)
                if weather
                else None,
                "solunar": _solunar_to_dict(solunar_by_date[d])
                if d in solunar_by_date
                else None,
                "scores": scores_for_day,
            }
        spots_payload[spot.id] = {
            "name": spot.name,
            "type": spot.type,
            "days": days_payload,
        }

    return {"spots": spots_payload, "species_meta": species_meta}


def _embed_json(payload: dict[str, Any]) -> str:
    """Serialize payload safe for embedding in <script type=application/json>."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Prevent any '</script>' breakout if a string later contains it.
    return raw.replace("</", "<\\/")


def render(matrix: ScoresMatrix, *, repo_url: str | None = None) -> dict[str, str]:
    """Render the dashboard to a dict of {filename: content}.

    If ``repo_url`` (``https://github.com/<owner>/<repo>``) is given, a
    "force update" link is rendered pointing at the daily workflow's
    manual dispatch page.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "htm", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("index.html.j2")
    view = _build_view(matrix)
    view["embedded_json"] = _embed_json(_build_detail_payload(matrix))
    view["force_update_url"] = (
        f"{repo_url.rstrip('/')}{WORKFLOW_PATH}" if repo_url else None
    )

    files: dict[str, str] = {"index.html": template.render(view)}
    for asset in STATIC_ASSETS:
        files[asset] = (TEMPLATES_DIR / asset).read_text(encoding="utf-8")
    return files
