"""Configuration loaders for spots and species from JSON files."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from src.core.models import Species, Spot

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SPOTS_PATH = DEFAULT_DATA_DIR / "spots.json"
DEFAULT_SPECIES_PATH = DEFAULT_DATA_DIR / "species.json"

_SpotsAdapter = TypeAdapter(list[Spot])
_SpeciesAdapter = TypeAdapter(list[Species])


class ConfigError(Exception):
    """Raised when configuration files are missing or malformed."""


def _load_json_list(path: Path) -> list:
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ConfigError(f"Expected a JSON array at top level of {path}")
    return data


def load_spots(path: Path | None = None) -> list[Spot]:
    """Load and validate the list of spots from JSON.

    Raises ConfigError if the file is missing, not valid JSON, or fails
    Pydantic validation.
    """
    spots_path = path or DEFAULT_SPOTS_PATH
    logger.info("Loading spots from %s", spots_path)
    data = _load_json_list(spots_path)
    try:
        return _SpotsAdapter.validate_python(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid spots in {spots_path}: {exc}") from exc


def load_species(path: Path | None = None) -> list[Species]:
    """Load and validate the list of species from JSON.

    Raises ConfigError if the file is missing, not valid JSON, or fails
    Pydantic validation.
    """
    species_path = path or DEFAULT_SPECIES_PATH
    logger.info("Loading species from %s", species_path)
    data = _load_json_list(species_path)
    try:
        return _SpeciesAdapter.validate_python(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid species in {species_path}: {exc}") from exc
