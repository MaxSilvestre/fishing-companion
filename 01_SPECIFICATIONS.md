# 🎣 Fishing Companion — Spécifications

Projet personnel : dashboard web qui me dit quand pêcher quoi et où sur mes spots favoris.

> **Note d'architecture importante** : le projet est conçu pour accueillir d'autres façades (bot Telegram, app mobile, etc.) plus tard. C'est pourquoi le code métier est isolé dans `src/core/`. **Pour ce MVP on ne fait que la façade web**, mais l'architecture est prête pour étendre.

## 1. Vision du produit

Un dashboard web personnel qui affiche, pour mes 3 spots de pêche (Lyon, Vienne, Lozanne) et mes 5 espèces préférées (brochet, sandre, perche, black bass, truite), un score d'activité 0-100 par jour sur 7 jours.

Généré automatiquement chaque matin via GitHub Actions, publié sur GitHub Pages, accessible depuis n'importe quel navigateur.

## 2. Public cible

Usage personnel, single-user. Le dashboard est public (URL GitHub Pages) mais ne contient aucune donnée sensible : que des prévisions météo et calculs solunaires.

## 3. Périmètre fonctionnel

### 3.1 Inclus dans le MVP (façade web)

- Matrice colorée `7 jours × espèces` par spot
- Détail au clic sur une cellule (sous-scores, conditions complètes)
- Date de dernière mise à jour affichée
- Responsive mobile, ajoutable à l'écran d'accueil (PWA)
- Génération automatique chaque matin via GitHub Actions
- Bouton "régénérer" via workflow_dispatch GitHub (pour forcer manuellement)

### 3.2 Différé pour plus tard

- Façade Telegram (commandes interactives)
- Carnet de captures
- Notifications push
- Marées (eau douce only pour ce MVP)
- Reconnaissance d'espèce par photo

## 4. Architecture logique

```
┌─────────────────────────────────────────┐
│         CŒUR MÉTIER (src/core/)         │
│  modèles, weather, solunar, scoring     │
│  pipeline = compute_all_scores()        │
└─────────────────────────────────────────┘
                    │
                    ▼
        ┌──────────────────┐
        │  Façade Web      │
        │  src/web/        │
        │  génère docs/    │
        └──────────────────┘
                    │
                    ▼
              GitHub Pages
```

**Principe clé** : `src/core/` ne sait rien des façades. Elle expose `compute_all_scores(spots, species, days=7) -> ScoresMatrix` que `src/web/` consomme.

**Pourquoi cette séparation alors qu'on ne fait que le web ?**
Quand on voudra ajouter Telegram, mobile, ou autre, on ajoutera juste `src/telegram/` ou `src/mobile/` qui consommera le même `core` sans rien modifier.

## 5. Espèces ciblées

| Espèce       | Préférendum eau | Note                          |
|--------------|------------------|-------------------------------|
| Brochet      | 12-18°C          | Inactif > 21°C                |
| Sandre       | 14-20°C          | Crépusculaire et nocturne     |
| Perche       | 14-22°C          | Très actif en banc            |
| Black bass   | 18-26°C          | Aime la chaleur               |
| Truite fario | 8-16°C           | Surtout Lozanne (Azergues)    |

Configuration détaillée dans `data/species.json`.

## 6. Spots configurés

| Spot     | Coordonnées          | Type     |
|----------|----------------------|----------|
| Lyon     | 45.7640, 4.8357      | Fleuve   |
| Vienne   | 45.5256, 4.8743      | Fleuve   |
| Lozanne  | 45.8548, 4.6802      | Rivière  |

Configuration dans `data/spots.json`.

## 7. Sources de données

- **Météo** : Open-Meteo API (gratuit, sans clé, prévisions horaires 7 jours)
- **Solunaire** : lib Python `astral` (calculs locaux)

Pas de marées dans ce MVP (eau douce only).

## 8. Algorithme de scoring

```
score = thermique×0.25 + pression×0.25 + solunaire×0.20 + lune×0.10 + météo×0.20
```

Sous-scores détaillés en annexe.

Seuils couleur :
- 🟢 Vert : score ≥ 70 (excellent)
- 🟡 Orange : score 40-69 (correct)
- 🔴 Rouge : score < 40 (mauvais)

## 9. Stack technique

- **Python 3.11+**
- **`httpx`** (async) — HTTP
- **`astral`** v3+ — calculs astronomiques
- **`pydantic`** v2 — modèles
- **`jinja2`** — templates HTML
- **`pytest`** + `pytest-asyncio` — tests

Pas de framework JS, pas de build step pour le front : CSS + JS vanilla.

## 10. Architecture des fichiers

```
fishing-companion/
├── README.md
├── pyproject.toml
├── .gitignore
├── CLAUDE.md                     # Conventions
│
├── data/
│   ├── spots.json
│   └── species.json
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                     # ⭐ CŒUR MÉTIER (extensible)
│   │   ├── __init__.py
│   │   ├── models.py             # Pydantic
│   │   ├── config.py             # Chargement JSON
│   │   ├── weather.py            # Client Open-Meteo
│   │   ├── solunar.py            # Calculs astral
│   │   ├── scoring.py            # Algo de score
│   │   └── pipeline.py           # compute_all_scores()
│   │
│   └── web/                      # Façade Web
│       ├── __init__.py
│       ├── generate.py           # Point d'entrée
│       ├── renderer.py
│       └── templates/
│           ├── index.html.j2
│           ├── style.css
│           └── app.js            # JS vanilla pour interactions
│
├── docs/                         # Sortie GitHub Pages (généré)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── manifest.json
│
├── tests/
│   ├── core/
│   │   ├── test_models.py
│   │   ├── test_weather.py
│   │   ├── test_solunar.py
│   │   ├── test_scoring.py
│   │   └── test_pipeline.py
│   └── web/
│       └── test_renderer.py
│
└── .github/
    └── workflows/
        └── daily.yml             # Cron + manuel
```

## 11. Déploiement

**GitHub Pages**, gratuit :

1. Le workflow GHA tourne chaque matin (`0 5 * * *`)
2. Exécute `python -m src.web.generate`
3. Commit auto du dossier `docs/`
4. GitHub Pages servi depuis `docs/` sur branche `main`
5. URL : `https://<user>.github.io/fishing-companion/`

Aucune infrastructure à maintenir, aucun coût.

## 12. Critères de succès MVP

- [ ] Dashboard visible sur GitHub Pages
- [ ] Mise à jour automatique chaque matin (cron GHA)
- [ ] Affichage correct sur mobile (responsive)
- [ ] Scores cohérents validés sur 2 semaines de pêche
- [ ] Le cœur `src/core/` n'importe rien de `src/web/`
- [ ] Couverture de tests > 70% sur `core/scoring.py`

## Annexe : détail des sous-scores

### Score thermique (25%)
```
si water_temp ∈ [opt_min, opt_max] : 100
sinon si hors [crit_min, crit_max] : 0
sinon : décroissance linéaire
```

### Score pression (25%)
```
si 1013 ≤ P ≤ 1022 hPa : base = 100
sinon : base = max(0, 100 - |P - 1017| × 5)
+10 si tendance 24h > +2 hPa
-20 si tendance 24h < -3 hPa
```

### Score solunaire (20%)
```
100 si période majeure (~2h autour transit lune) ∩ heures actives espèce
70 si période mineure (~1h lever/coucher lune) ∩ heures actives
40 sinon
```

### Score lunaire (10%)
```
distance = min(|phase|, |phase - 0.5|, |phase - 1|)
score = max(60, 100 - distance × 200)
```

### Score météo (20%)
```
cloud_score = max(0, 100 - |couverture - 50| × 1.5)
wind_score = 100 si vent < 15 km/h, sinon décroissance
prec_score = 100 si pluie < 2 mm, sinon décroissance
score = (cloud + wind + prec) / 3
```

### Estimation température eau
```
eau = air_temp_moy - offset_saisonnier - offset_type_spot

offset_saisonnier :
  jan-fév: 0    (eau ≈ air, basse partout)
  mar-avr: -2   (air monte plus vite que l'eau)
  mai-juin: -3  (gros écart printemps)
  juil-août: -2 (eau rattrape un peu)
  sep-oct: -1
  nov-déc: 0

offset_type_spot :
  lac: 0
  fleuve: +1 (légèrement plus chaud que rivière)
  rivière: 0
```

Heuristique de départ, à raffiner avec relevés terrain.
