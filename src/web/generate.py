"""Entry point: load config, run the core pipeline, write static dashboard.

Run with ``python -m src.web.generate``. Outputs everything into ``docs/``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path

from src.core.config import load_species, load_spots
from src.core.pipeline import compute_all_scores
from src.web.renderer import render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "docs"

_GITHUB_REMOTE_RE = re.compile(
    r"^(?:git@github\.com:|https://github\.com/)(?P<slug>[^/]+/[^/.]+?)(?:\.git)?$"
)


def detect_repo_url() -> str | None:
    """Detect the GitHub repo URL from CI env or local git remote.

    Returns ``https://github.com/<owner>/<repo>`` or None if detection fails.
    """
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return f"https://github.com/{env_repo}"

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            cwd=PROJECT_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    match = _GITHUB_REMOTE_RE.match(result.stdout.strip())
    if not match:
        return None
    return f"https://github.com/{match.group('slug')}"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    spots = load_spots()
    species = load_species()
    matrix = asyncio.run(compute_all_scores(spots, species))

    repo_url = detect_repo_url()
    if repo_url:
        logger.info("Detected repo URL: %s", repo_url)
    else:
        logger.info("No repo URL detected — force-update link will be hidden")

    files = render(matrix, repo_url=repo_url)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        path = OUTPUT_DIR / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote %s (%d bytes)", path, len(content))


if __name__ == "__main__":
    main()
