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

Le workflow `.github/workflows/daily.yml` regénère `docs/` chaque matin à 5h UTC et commit le résultat sur `main`. GitHub Pages sert ensuite `docs/` en statique.

### Mise en place initiale (une seule fois)

1. **Créer le repo distant et pousser**
   ```bash
   gh repo create fishing-companion --public --source=. --remote=origin --push
   # ou via l'UI GitHub puis : git remote add origin git@github.com:<owner>/fishing-companion.git ; git push -u origin main
   ```

2. **Activer GitHub Pages**
   - Va dans `Settings > Pages`
   - Source : `Deploy from a branch`
   - Branch : `main`, Folder : `/docs`
   - Save

3. **Vérifier les permissions Actions**
   - `Settings > Actions > General > Workflow permissions` : "Read and write permissions" doit être coché
   - "Allow GitHub Actions to create and approve pull requests" peut rester décoché

4. **Premier run manuel pour tester**
   - `Actions > Daily forecast update > Run workflow` → branche `main` → Run
   - Le workflow checkoute, install deps, regen `docs/`, push si changements
   - Le commit `chore: daily forecast update` doit apparaître sur `main` dans la minute

5. **Accéder au dashboard**
   - URL : `https://<owner>.github.io/fishing-companion/`
   - Disponible 1-2 min après le 1er push réussi de `docs/`

## Gérer les spots et espèces

Toute la configuration vit dans `data/spots.json` et `data/species.json`. Pour ajouter / supprimer / modifier un spot ou une espèce :

### Méthode rapide depuis n'importe quel device (recommandée)

1. Ouvre `https://github.com/<owner>/<repo>/edit/main/data/spots.json` (ou `species.json`).
2. Modifie le JSON dans l'éditeur web.
3. Commit directement sur `main`.
4. Dans le dashboard, clique sur **🔄 Forcer la mise à jour** (en haut). Le workflow GHA tourne, regénère `docs/`, GitHub Pages se met à jour en 1-2 min.

Sinon attends le cron du lendemain matin.

### Méthode locale

```bash
# Édite data/spots.json puis valide la structure
python -c "from src.core.config import load_spots, load_species; \
           print(len(load_spots()), 'spots,', len(load_species()), 'species')"

git add data/spots.json
git commit -m "feat(data): add Annecy spot"
git push
```

### Schéma d'un spot

```json
{
  "id": "annecy",                         // identifiant unique (snake_case)
  "name": "Annecy (Lac)",                 // libellé affiché
  "latitude": 45.8992,                    // -90 à 90
  "longitude": 6.1294,                    // -180 à 180
  "type": "lac",                          // "fleuve" | "riviere" | "lac"
  "altitude": 447,                        // en mètres
  "notes": "Lac alpin, eaux claires"      // optionnel
}
```

Le chargement échoue avec un message explicite si le JSON ou les valeurs sont invalides — pas besoin de tester en aveugle.
