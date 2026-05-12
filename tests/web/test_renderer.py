"""Tests for src.web.renderer."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

import pytest

from src.core.models import (
    DayScore,
    HourlyWeather,
    ScoreBreakdown,
    ScoresMatrix,
    SolunarDay,
    Species,
    Spot,
    WeatherData,
)
from src.web.renderer import (
    SCORE_TIER_GOOD,
    SCORE_TIER_MID,
    STATIC_ASSETS,
    _format_generated_at,
    _score_tier,
    render,
)


def _spot(spot_id="lyon", spot_type="fleuve") -> Spot:
    return Spot.model_validate(
        {
            "id": spot_id,
            "name": f"Spot {spot_id}",
            "latitude": 45.764,
            "longitude": 4.8357,
            "type": spot_type,
            "altitude": 170,
        }
    )


def _species(species_id="brochet") -> Species:
    return Species.model_validate(
        {
            "id": species_id,
            "name": f"Species {species_id}",
            "emoji": "🐟",
            "temp_optimal_min": 12,
            "temp_optimal_max": 18,
            "temp_critical_min": 4,
            "temp_critical_max": 21,
            "pressure_preference": "stable",
            "active_hours": [[5, 9]],
            "season_active": [5],
        }
    )


def _breakdown(total=72.5) -> ScoreBreakdown:
    return ScoreBreakdown(
        thermal=80, pressure=70, solunar=60, moon=50, weather=90, total=total
    )


def _build_matrix(days=2, total_values=None) -> ScoresMatrix:
    if total_values is None:
        total_values = [75.0, 35.0]
    spot = _spot()
    species = _species()
    base_day = date(2026, 5, 12)
    midnight = datetime.combine(base_day - timedelta(days=1), datetime.min.time())

    hourly = []
    for offset in range((days + 1) * 24):
        hourly.append(
            HourlyWeather(
                time=midnight + timedelta(hours=offset),
                temperature_2m=15.0,
                surface_pressure=1018.0,
                wind_speed_10m=6.0,
                wind_direction_10m=180.0,
                cloud_cover=55.0,
                precipitation=0.0,
            )
        )
    weather = WeatherData(
        latitude=45.764, longitude=4.8357, hourly=hourly, daily=[]
    )

    scores: list[DayScore] = []
    solunar_days: list[SolunarDay] = []
    for i in range(days):
        d = base_day + timedelta(days=i)
        sd_midnight = datetime.combine(d, datetime.min.time())
        solunar_days.append(
            SolunarDay(
                date=d,
                sunrise=sd_midnight + timedelta(hours=6, minutes=15),
                sunset=sd_midnight + timedelta(hours=21),
                moonrise=sd_midnight + timedelta(hours=4),
                moonset=sd_midnight + timedelta(hours=16),
                moon_phase=0.5,
                major_periods=[
                    (sd_midnight + timedelta(hours=8),
                     sd_midnight + timedelta(hours=10))
                ],
                minor_periods=[],
            )
        )
        scores.append(
            DayScore(
                spot_id=spot.id,
                species_id=species.id,
                date=d,
                breakdown=_breakdown(total=total_values[i]),
            )
        )

    return ScoresMatrix(
        generated_at=datetime(2026, 5, 12, 7, 30),
        spots=[spot],
        species=[species],
        scores=scores,
        weather_by_spot={spot.id: weather},
        solunar_by_spot={spot.id: solunar_days},
    )


class TestFormatGeneratedAt:
    def test_naive_assumed_utc_converted_to_paris_summer(self):
        # In May, Paris is CEST (UTC+2). 09:20 UTC → 11:20 local.
        result = _format_generated_at(datetime(2026, 5, 12, 9, 20))
        assert result == "2026-05-12 11:20"

    def test_naive_assumed_utc_converted_to_paris_winter(self):
        # In January, Paris is CET (UTC+1). 09:20 UTC → 10:20 local.
        result = _format_generated_at(datetime(2026, 1, 12, 9, 20))
        assert result == "2026-01-12 10:20"

    def test_tz_aware_utc_converted(self):
        from datetime import timezone as tz_module
        result = _format_generated_at(
            datetime(2026, 5, 12, 9, 20, tzinfo=tz_module.utc)
        )
        assert result == "2026-05-12 11:20"


class TestScoreTier:
    def test_good(self):
        assert _score_tier(SCORE_TIER_GOOD) == "good"
        assert _score_tier(100) == "good"

    def test_mid(self):
        assert _score_tier(SCORE_TIER_MID) == "mid"
        assert _score_tier(SCORE_TIER_GOOD - 1) == "mid"

    def test_bad(self):
        assert _score_tier(SCORE_TIER_MID - 1) == "bad"
        assert _score_tier(0) == "bad"

    def test_none(self):
        assert _score_tier(None) == "none"


class TestRender:
    def test_emits_full_file_set(self):
        files = render(_build_matrix())
        expected = {"index.html"} | set(STATIC_ASSETS)
        assert set(files.keys()) == expected

    def test_html_contains_spot_and_species(self):
        files = render(_build_matrix())
        html = files["index.html"]
        assert "Spot lyon" in html
        assert "Species brochet" in html
        assert '<link rel="stylesheet" href="style.css">' in html
        assert '<link rel="manifest" href="manifest.json">' in html

    def test_cells_get_correct_tier_class(self):
        # Day 0 total=75 → good, day 1 total=35 → bad.
        files = render(_build_matrix(days=2, total_values=[75.0, 35.0]))
        html = files["index.html"]
        # Two good cells across the matrix (1 spot × 1 species).
        good_count = len(re.findall(r"cell-good", html))
        bad_count = len(re.findall(r"cell-bad", html))
        assert good_count == 1
        assert bad_count == 1

    def test_clickable_cells_have_data_attributes(self):
        files = render(_build_matrix())
        html = files["index.html"]
        assert 'data-spot="lyon"' in html
        assert 'data-date="2026-05-12"' in html
        assert 'data-species="brochet"' in html

    def test_embedded_json_is_valid_and_well_shaped(self):
        files = render(_build_matrix())
        html = files["index.html"]
        match = re.search(
            r'<script id="dashboard-data" type="application/json">(.+?)</script>',
            html,
            re.DOTALL,
        )
        assert match is not None
        payload = json.loads(match.group(1))

        assert set(payload.keys()) == {"spots", "species_meta"}
        assert "brochet" in payload["species_meta"]
        assert payload["species_meta"]["brochet"]["name"] == "Species brochet"

        lyon = payload["spots"]["lyon"]
        assert lyon["type"] == "fleuve"
        day = lyon["days"]["2026-05-12"]
        assert day["weather"]["pressure_now"] == 1018.0
        assert day["solunar"]["sunrise"] == "06:15"
        assert day["solunar"]["moon_phase"] == 0.5
        assert day["scores"]["brochet"]["total"] == 75

    def test_embedded_json_escapes_script_close_sequences(self):
        # Build a matrix with a name that contains '</' to verify embedding safety.
        matrix = _build_matrix()
        matrix.spots[0] = Spot.model_validate(
            {
                "id": "lyon",
                "name": "Tricky </script> spot",
                "latitude": 45.764,
                "longitude": 4.8357,
                "type": "fleuve",
                "altitude": 170,
            }
        )
        files = render(matrix)
        html = files["index.html"]
        # The literal '</script>' must NOT appear inside the JSON block.
        match = re.search(
            r'<script id="dashboard-data" type="application/json">(.+?)</script>',
            html,
            re.DOTALL,
        )
        assert match is not None
        raw = match.group(1)
        assert "</script>" not in raw
        # And the data must still parse with the escape unwound.
        parsed = json.loads(raw.replace("<\\/", "</"))
        assert parsed["spots"]["lyon"]["name"] == "Tricky </script> spot"

    def test_manifest_is_valid_json(self):
        files = render(_build_matrix())
        manifest = json.loads(files["manifest.json"])
        assert manifest["display"] == "standalone"
        assert manifest["start_url"] == "./"
        assert manifest["icons"]

    def test_static_assets_are_non_empty(self):
        files = render(_build_matrix())
        for asset in STATIC_ASSETS:
            assert len(files[asset]) > 0, f"asset {asset} is empty"

    def test_force_update_link_present_when_repo_url_set(self):
        files = render(_build_matrix(), repo_url="https://github.com/maxime/fishing-companion")
        html = files["index.html"]
        assert "Forcer la mise à jour" in html
        assert (
            'href="https://github.com/maxime/fishing-companion/actions/workflows/daily.yml"'
            in html
        )

    def test_force_update_link_absent_without_repo_url(self):
        files = render(_build_matrix())
        html = files["index.html"]
        assert "Forcer la mise à jour" not in html

    def test_force_update_link_handles_trailing_slash(self):
        files = render(_build_matrix(), repo_url="https://github.com/maxime/fishing-companion/")
        html = files["index.html"]
        assert (
            'href="https://github.com/maxime/fishing-companion/actions/workflows/daily.yml"'
            in html
        )

    def test_null_score_renders_em_dash(self):
        """A cell with no score should render '–' with cell-none and no data-spot."""
        matrix = _build_matrix(days=1)
        # Add a second species but no score for it on this day — the cell
        # should render as a non-clickable em-dash.
        matrix.species.append(_species(species_id="perche"))
        files = render(matrix)
        html = files["index.html"]
        assert "cell-none" in html
        # Only the brochet cell should carry data-species; perche should not.
        assert 'data-species="brochet"' in html
        assert 'data-species="perche"' not in html
        assert "–" in html