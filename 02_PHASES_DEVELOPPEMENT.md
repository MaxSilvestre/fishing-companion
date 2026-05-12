# 🛠️ Phases de développement — Fishing Companion (Web)

8 phases, ~8h de travail effectif, faisables sur 1 week-end.

> **Architecture extensible** : on garde `src/core/` séparé même si on ne fait que la façade web pour le moment. Cela permettra d'ajouter une façade Telegram (ou autre) plus tard sans rien refactorer.

## Vue d'ensemble

```
Phase 0  : Setup
Phase 1-5: ⭐ Cœur métier (commun, réutilisable)
Phase 6  : Façade Web (HTML + CSS + JS)
Phase 7  : GitHub Actions + GitHub Pages
```

---

## Phase 0 — Setup projet (30 min)

**Objectif** : base de projet propre.

**Livrables** :
- [ ] Repo Git initialisé
- [ ] `pyproject.toml` avec deps : httpx, astral, pydantic v2, jinja2, pytest, pytest-asyncio
- [ ] Structure : `src/core/`, `src/web/`, `src/web/templates/`, `data/`, `tests/core/`, `tests/web/`, `docs/`, `.github/workflows/`
- [ ] `.gitignore` Python complet (inclut `docs/` exclu seulement pour Pages — voir note)
- [ ] `CLAUDE.md` avec conventions
- [ ] `README.md` minimal

**Note `.gitignore`** : `docs/` SERA committé (c'est ce que GitHub Pages sert), mais le workflow le génère. En local, on peut le mettre dans `.gitignore` initialement, puis l'enlever quand on push.

**Commande Claude Code** :
> "Crée la structure du projet fishing-companion selon les specs : pyproject.toml avec httpx, astral, pydantic v2, jinja2, pytest, pytest-asyncio. Structure src/core, src/web/templates, data, tests/core, tests/web, docs, .github/workflows. CLAUDE.md avec conventions, README minimal, .gitignore Python. Pas de logique métier encore, juste l'arborescence et la config."

**Validation** :
```bash
python -c "import httpx, astral, pydantic, jinja2; print('OK')"
tree -L 3 -a -I '.git|__pycache__|.venv'
```

---

## Phase 1 — Modèles et config (45 min)

**Objectif** : modèles Pydantic + chargement validé des JSON.

**Livrables** :
- [ ] `src/core/models.py` : `Spot`, `Species`, `HourlyWeather`, `DailyWeather`, `WeatherData`, `SolunarDay`, `ScoreBreakdown`, `DayScore`, `ScoresMatrix`
- [ ] `src/core/config.py` : `load_spots()`, `load_species()`
- [ ] `data/spots.json` et `data/species.json` (fournis)
- [ ] Tests dans `tests/core/test_models.py`

**Commande Claude Code** :
> "Implémente src/core/models.py avec les modèles Pydantic v2 selon les specs. Utilise Field() pour les validateurs (min/max, ge/le). src/core/config.py charge spots.json et species.json avec validation, lève une erreur claire si invalide. Tests pytest dans tests/core/test_models.py avec cas valides et invalides."

**Validation** :
```bash
pytest tests/core/test_models.py -v
python -c "from src.core.config import load_spots, load_species; print(load_spots()); print(load_species())"
```

---

## Phase 2 — Client météo (1h)

**Objectif** : `fetch_forecast(lat, lon) -> WeatherData` async et robuste.

**Livrables** :
- [ ] `src/core/weather.py` :
  - `async fetch_forecast(latitude, longitude) -> WeatherData`
  - Cache mémoire TTL 30 min (clé : lat,lon)
  - Retry 3x backoff exponentiel
- [ ] Champs : `temperature_2m`, `surface_pressure`, `wind_speed_10m`, `wind_direction_10m`, `cloud_cover`, `precipitation` (horaires) + `temperature_2m_min/max`, `sunrise`, `sunset` (daily)
- [ ] `past_days=1` pour avoir la tendance pression
- [ ] Tests avec mock httpx

**Commande Claude Code** :
> "Implémente src/core/weather.py en async avec httpx.AsyncClient. fetch_forecast appelle l'API Open-Meteo avec les champs listés sur forecast_days=7 et past_days=1 (pour la tendance pression). Cache mémoire dict avec timestamp, TTL 30 min. Retry 3x exponential backoff sur erreur réseau. Tests dans tests/core/test_weather.py avec httpx.MockTransport, cas succès + erreurs."

**Validation** :
```bash
pytest tests/core/test_weather.py -v
python -c "import asyncio; from src.core.weather import fetch_forecast; r = asyncio.run(fetch_forecast(45.764, 4.836)); print(r.hourly[:3])"
```

---

## Phase 3 — Calculs solunaires (1h)

**Objectif** : `compute_solunar(date, lat, lon) -> SolunarDay`.

**Livrables** :
- [ ] `src/core/solunar.py` :
  - Lever/coucher soleil et lune
  - Phase lune normalisée 0-1
  - Périodes majeures (~2h autour transit et antitransit lunaires)
  - Périodes mineures (~1h autour moonrise et moonset)
- [ ] Tests sur dates de référence

**Commande Claude Code** :
> "Implémente src/core/solunar.py avec la lib astral. compute_solunar retourne un SolunarDay avec : sunrise, sunset, moonrise, moonset, moon_phase (0-1, normalisé depuis astral.moon.phase), major_periods (transit lunaire ±1h ET antitransit ±1h — antitransit = transit + 12h), minor_periods (moonrise ±30min, moonset ±30min). Tests sur des dates avec valeurs vérifiables (au moins 3 dates différentes)."

**Validation** :
```bash
pytest tests/core/test_solunar.py -v
```

---

## Phase 4 — Algorithme de scoring (2h) ⭐ phase critique

**Objectif** : score 0-100 par espèce/spot/jour.

⚠️ **À découper en plusieurs prompts** au lieu d'un seul.

**Livrables** :
- [ ] `src/core/scoring.py` :
  - `estimate_water_temp(air_temp_avg, month, spot_type) -> float`
  - `score_thermal(water_temp, species) -> float`
  - `score_pressure(pressure_now, trend_24h) -> float`
  - `score_solunar(solunar_day, species_active_hours) -> float`
  - `score_moon(phase) -> float`
  - `score_weather(cloud, wind, precipitation) -> float`
  - `compute_day_score(spot, species, weather_day, solunar_day) -> ScoreBreakdown`
- [ ] Tests par fonction + tests d'intégration

**Commandes Claude Code (à enchaîner)** :

> "Étape 1/3 : implémente estimate_water_temp et score_thermal dans src/core/scoring.py selon les formules des specs. Tests dans tests/core/test_scoring.py."

> "Étape 2/3 : ajoute score_pressure, score_solunar, score_moon, score_weather dans src/core/scoring.py. Tests pour chaque."

> "Étape 3/3 : ajoute compute_day_score qui agrège tout avec les pondérations. 3 tests d'intégration : journée idéale brochet mai (score > 75 attendu), journée mauvaise truite été (score < 30), cas limite chute brutale de pression."

**Validation** :
```bash
pytest tests/core/test_scoring.py -v
```

---

## Phase 5 — Pipeline (45 min)

**Objectif** : orchestrer tout le cœur.

**Livrables** :
- [ ] `src/core/pipeline.py` :
  - `async compute_all_scores(spots, species, days=7) -> ScoresMatrix`
  - Fetch météo en parallèle (asyncio.gather)
  - Compute solunaire pour chaque jour
  - Compute score pour chaque (spot, jour, espèce)
- [ ] Logging clair
- [ ] Tests d'intégration légers

**Commande Claude Code** :
> "Implémente src/core/pipeline.py. compute_all_scores prend les listes spots et species, lance asyncio.gather pour fetch toutes les météos en parallèle, puis loop sur jours et espèces pour calculer les scores. Retourne ScoresMatrix indexée par (spot_id, date, species_id) avec aussi les WeatherData et SolunarDay associés. Logging INFO sur les étapes principales. Test d'intégration avec mocks weather."

**Validation** :
```bash
python -c "
import asyncio
from src.core.config import load_spots, load_species
from src.core.pipeline import compute_all_scores
result = asyncio.run(compute_all_scores(load_spots(), load_species()))
print(f'{len(result.scores)} entries computed')
"
```

🎯 **Le cœur est terminé à ce stade.** Tu peux déjà afficher des scores en console.

---

## Phase 6 — Façade Web : HTML + CSS + JS (2h)

**Objectif** : dashboard responsive depuis la matrice de scores.

⚠️ **À découper en plusieurs prompts**.

**Livrables** :
- [ ] `src/web/templates/index.html.j2` : template Jinja2 (structure du dashboard)
- [ ] `src/web/templates/style.css` : CSS responsive mobile-first
- [ ] `src/web/templates/app.js` : JS vanilla pour interactions
- [ ] `src/web/renderer.py` : `render(scores_matrix) -> dict[filename, content]`
- [ ] `src/web/generate.py` : point d'entrée qui charge config → pipeline → renderer → écrit `docs/`
- [ ] `docs/manifest.json` PWA basique
- [ ] Une matrice colorée par spot (7 jours × 5 espèces), clic = détails

**Commandes Claude Code (à enchaîner)** :

> "Étape 1/3 : crée src/web/templates/index.html.j2 minimal qui affiche pour chaque spot un tableau brut (lignes = jours, colonnes = espèces, cellules = score). Pas encore de CSS ni JS. src/web/renderer.py utilise Jinja2 pour générer le HTML. src/web/generate.py orchestre tout et écrit docs/index.html."

> "Étape 2/3 : ajoute src/web/templates/style.css responsive (mobile-first, CSS Grid). Style des cellules selon score (vert/orange/rouge). Header avec date de mise à jour. Design sobre et lisible."

> "Étape 3/3 : ajoute src/web/templates/app.js. Au clic sur une cellule, afficher une modale ou section avec sous-scores, conditions météo, périodes solunaires. Ajoute docs/manifest.json PWA basique pour ajout à l'écran d'accueil iOS/Android."

**Validation** :
```bash
python -m src.web.generate
open docs/index.html  # macOS
# ou xdg-open sur Linux
# Tester aussi sur mobile en servant localement :
python -m http.server -d docs 8000
# puis depuis ton tél : http://<ip-locale>:8000
```

---

## Phase 7 — GitHub Actions + Pages (30 min)

**Objectif** : mise à jour automatique + hébergement.

**Livrables** :
- [ ] `.github/workflows/daily.yml` :
  - Trigger : cron `0 5 * * *` (5h UTC) + workflow_dispatch
  - Setup Python 3.11, install deps
  - Run `python -m src.web.generate`
  - Commit auto de `docs/` avec message clair
  - Push sur main
  - Permissions `contents: write`
- [ ] README documenté pour activer GitHub Pages
- [ ] Premier test du workflow en manuel

**Commande Claude Code** :
> "Crée .github/workflows/daily.yml. Cron quotidien à 5h UTC + workflow_dispatch pour run manuel. Steps : checkout (avec token write), setup-python 3.11, install via pip install -e . (ou cache pip si possible), run python -m src.web.generate, git add docs/, commit avec message 'chore: daily forecast update' SI changements (utilise git diff --quiet), push. Permissions contents: write. Documente dans README : Settings > Pages > Source: main branch /docs folder."

**Étapes manuelles après création** :
1. Push tout le repo sur GitHub
2. Settings > Pages > Source : `main` branch, `/docs` folder, Save
3. Actions > daily.yml > Run workflow (manual dispatch) pour test
4. Vérifier que `docs/` est mis à jour par le workflow
5. Attendre 1-2 min, accéder à `https://<user>.github.io/fishing-companion/`

**Validation** :
- L'URL GitHub Pages affiche le dashboard
- Le cron s'est exécuté avec succès une fois manuellement
- Le commit auto a bien eu lieu sur main

🎉 **MVP terminé à ce stade.** Ton dashboard est en production, gratuit, automatique.

---

## Estimation totale

| Phase | Durée | Cumul |
|-------|-------|-------|
| 0 Setup | 30 min | 30 min |
| 1 Modèles | 45 min | 1h15 |
| 2 Météo | 1h | 2h15 |
| 3 Solunaire | 1h | 3h15 |
| 4 Scoring | 2h | 5h15 |
| 5 Pipeline | 45 min | 6h |
| 6 Façade Web | 2h | 8h |
| 7 GitHub Actions | 30 min | 8h30 |

**Total : ~8h30** sur 1 long week-end ou 3-4 soirées.

## Points de vigilance

### Le cœur d'abord
Tentation : aller direct au visuel. **Discipline** : finir solidement les phases 0-5 avant de toucher au HTML. Si le scoring est buggé, ton beau dashboard sera faux.

### Découper la phase 4
La plus dense. Trois prompts séparés au lieu d'un seul (voir détail ci-dessus). Sinon Claude Code génère 300 lignes médiocres au lieu de 100 lignes propres.

### Tester sur vrai mobile
Phase 6 : ouvre le dashboard sur ton vrai téléphone via `python -m http.server` et l'IP locale. C'est le seul vrai test du responsive.

### Workflow GHA : test manuel d'abord
Phase 7 : avant d'attendre le cron, lance toujours `workflow_dispatch` une fois manuellement pour vérifier que tout marche.

### Validation terrain
Une fois le dashboard en prod, tiens un journal :

| Date | Spot | Espèce | Score prédit | Prises réelles |
|------|------|--------|--------------|----------------|
| 12/05 | Lyon | Perche | 89 | 4 en 2h |

Au bout de 20-30 sessions, ajuste les poids et seuils dans `scoring.py` ou `species.json`.

## Quand ajouter Telegram plus tard

Quand tu voudras ajouter la façade bot :
1. Phase Telegram-0 : créer bot via @BotFather
2. Phase Telegram-1 : ajouter `src/telegram/` (bot.py, handlers.py, formatter.py, resolver.py)
3. Phase Telegram-2 : enrichir les commandes
4. Phase Telegram-3 : déploiement (Fly.io ou Oracle Cloud)

**Aucune modification de `src/core/` ou `src/web/`.** C'est tout l'intérêt d'avoir séparé dès le début.
