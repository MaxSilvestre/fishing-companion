# 🎣 Fishing Companion

Tableau de bord web personnel : pour chaque spot et espèce préférés, un score d'activité 0-100 sur 7 jours, mis à jour automatiquement chaque matin via GitHub Actions et publié sur GitHub Pages.

## Stack

Python 3.11+, httpx (async), astral, pydantic v2, jinja2 — front en HTML/CSS/JS vanilla.

## Architecture

- `src/core/` — cœur métier (modèles, météo, solunaire, scoring, pipeline). Indépendant des façades.
- `src/web/` — façade web : génère le HTML statique dans `docs/`.
- `data/` — configuration des spots et espèces.

Voir `CLAUDE.md` pour les conventions et `01_SPECIFICATIONS.md` pour les détails produit.

## Installation locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Utilisation

```bash
# Générer le dashboard dans docs/
python -m src.web.generate

# Servir localement
python -m http.server -d docs 8000
# puis ouvrir http://localhost:8000
```

## Tests

```bash
pytest -v
```

## Déploiement

Activer GitHub Pages : `Settings > Pages > Source: main branch, /docs folder`.
Le workflow `.github/workflows/daily.yml` regénère et commit `docs/` chaque matin.
