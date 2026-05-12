# Project conventions — fishing-companion

## Architecture
Le projet est conçu avec une séparation cœur métier / façade :
- src/core/ : modèles, météo, solunaire, scoring, pipeline. CODE PUR, n'importe rien des façades.
- src/web/ : génération HTML pour GitHub Pages (la seule façade pour ce MVP)

Règle absolue : src/core/ ne dépend de RIEN d'autre dans src/.
L'inverse est OK : src/web/ peut tout importer de src/core/.

Cette séparation permettra d'ajouter une façade Telegram, mobile ou autre
sans rien refactorer.

## Stack
- Python 3.11+
- Type hints obligatoires partout
- Pydantic v2 pour les modèles
- httpx async pour HTTP (jamais requests)
- astral pour solunaire
- jinja2 pour les templates HTML
- pytest + pytest-asyncio pour les tests
- Pas de framework JS, CSS et JS vanilla

## Conventions
- Code (noms, commentaires, docstrings) en anglais
- UI / messages utilisateur en français
- Pas de print(), uniquement logging
- Pas de magic numbers : constantes nommées en haut du fichier
- Fonctions < 50 lignes, sinon refactor
- Tests : tests/core/ et tests/web/ miroir de src/

## Git
- Conventional commits : feat:, fix:, refactor:, test:, docs:, chore:
- Un commit minimum par phase
- Ne jamais commit : __pycache__/, .pytest_cache/, .venv/, *.pyc
- docs/ EST committé (servi par GitHub Pages, généré par le workflow)

## Async
- src/core/weather.py et src/core/pipeline.py sont async
- src/web/generate.py est sync mais utilise asyncio.run() pour appeler pipeline
- Tests : @pytest.mark.asyncio avec pytest-asyncio
