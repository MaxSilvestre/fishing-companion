# 🤖 Prompt initial pour Claude Code — Fishing Companion (Web MVP)

## Préparation (5 min)

### 1. Créer le repo

```bash
mkdir fishing-companion && cd fishing-companion
git init
```

### 2. Placer les fichiers

À la racine :
- `01_SPECIFICATIONS.md`
- `02_PHASES_DEVELOPPEMENT.md`
- `03_CLAUDE_CODE_PROMPT.md` (ce fichier)
- `CLAUDE.md` (template ci-dessous)

Dans `data/` :
- `spots.json`
- `species.json`

Pas de `.env` cette fois : aucun secret nécessaire pour la façade web.

### 3. Créer le repo distant (à n'importe quel moment, idéalement après Phase 0)

```bash
gh repo create fishing-companion --public --source=. --remote=origin
# ou via l'interface GitHub
```

---

## Prompt à coller dans Claude Code

```
Bonjour Claude. Je veux développer le projet "fishing-companion" décrit dans 01_SPECIFICATIONS.md.

C'est un dashboard web personnel pour la pêche, hébergé sur GitHub Pages, mis à jour automatiquement chaque matin.

IMPORTANT : l'architecture sépare le CŒUR MÉTIER (src/core/) de la FAÇADE WEB (src/web/). Pour ce MVP on ne fait QUE la façade web, mais le cœur doit rester indépendant pour qu'on puisse ajouter d'autres façades plus tard (bot Telegram, app mobile, etc.).

Lis d'abord ces 3 fichiers :
- 01_SPECIFICATIONS.md : produit, archi, règles métier
- 02_PHASES_DEVELOPPEMENT.md : 8 phases avec critères de validation
- CLAUDE.md : conventions du projet

Mon contexte :
- Je suis développeur, à l'aise avec Python async
- data/spots.json et data/species.json sont déjà remplis
- Objectif : MVP fonctionnel en 1 long week-end (~8h30)

Règles de travail :
1. Une phase à la fois. Fin de phase = tu montres le résultat, on valide ensemble, on commit, on passe.
2. RÈGLE D'OR : src/core/ ne doit JAMAIS importer quoi que ce soit de src/web/. L'inverse est OK. Je vérifierai.
3. Code Python 3.11+ propre, type hints partout, docstrings concises.
4. Async là où Open-Meteo l'impose.
5. Tests pytest AU FUR ET À MESURE, pas à la fin.
6. Commits conventional (feat:, fix:, test:, docs:, chore:) en fin de phase.
7. Pas de print(), uniquement logging.
8. Si une décision technique mérite débat, signale-la AVANT de coder.

ATTENTION pour les phases 4 (scoring) et 6 (HTML/CSS/JS) : à découper en plusieurs sous-prompts comme indiqué dans 02_PHASES_DEVELOPPEMENT.md. Ne pas tout générer en un seul gros bloc.

On commence par la Phase 0. Liste-moi ce que tu vas faire, puis exécute.
```

---

## Fichier `CLAUDE.md` à placer à la racine

```markdown
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
```

---

## Workflow pendant le développement

### Démarrage de session
À chaque reprise :
> "On reprend fishing-companion. On en est à la Phase X. État actuel : [résumé court]. Continue."

### Vérifier l'isolation du cœur
Régulièrement, vérifie que `src/core/` reste pur :
```bash
grep -r "from src.web" src/core/ && echo "❌ violation" || echo "✅ core est pur"
grep -r "import src.web" src/core/ && echo "❌ violation" || echo "✅ core est pur"
```

### Test continu du dashboard
Garde un terminal avec un serveur local :
```bash
python -m http.server -d docs 8000
```
Puis ouvre `http://localhost:8000` dans le navigateur. Après chaque `python -m src.web.generate`, F5 dans le navigateur.

### Test mobile réaliste
Phase 6 : sers depuis ton PC sur le réseau local, accède depuis ton tél :
```bash
# Trouve ton IP locale
ip a  # ou ipconfig getifaddr en0 sur macOS

# Sers
python -m http.server -d docs 8000

# Sur ton tél : http://<ton-ip>:8000
```

### Si Claude Code dérive
- Coupe-le tôt si la direction part en vrille
- `/clear` entre les phases denses (4, 6) pour repartir propre
- Rappel court : "Voici les specs [pointer le bon .md], reprends depuis ici."

### Découpe de la Phase 4 (scoring)
**Ne pas faire** : "Implémente tout scoring.py."

**Faire** (3 prompts) :
1. "Implémente estimate_water_temp et score_thermal + tests."
2. "Ajoute score_pressure, score_solunar, score_moon, score_weather + tests."
3. "Ajoute compute_day_score qui agrège tout + 3 tests d'intégration."

### Découpe de la Phase 6 (façade web)
**Ne pas faire** : "Fais le dashboard complet."

**Faire** (3 prompts) :
1. "Template Jinja2 minimal sans CSS + renderer + generate, qui produit un HTML brut fonctionnel."
2. "Ajoute le CSS responsive mobile-first avec cellules colorées."
3. "Ajoute le JS vanilla pour les détails au clic + manifest PWA."

---

## Checklist de fin de MVP

### Avant de claim "MVP terminé"

- [ ] `pytest` : tous verts, couverture > 70% sur `src/core/scoring.py`
- [ ] `python -m src.web.generate` : crée `docs/` sans erreur
- [ ] `python -m http.server -d docs 8000` : dashboard s'affiche correctement
- [ ] Test sur mobile réel : responsive OK, lisible, clic sur cellule fonctionne
- [ ] GitHub Pages activé, l'URL publique fonctionne
- [ ] Workflow GHA exécuté manuellement avec succès au moins une fois
- [ ] README à jour avec instructions complètes et URL du dashboard
- [ ] Vérifié : `src/core/` ne contient aucun import de `src/web/`

### Validation terrain (semaines 1-3)

Tiens un journal :

| Date | Spot | Espèce | Score prédit | Heure pêchée | Prises | Notes |
|------|------|--------|--------------|--------------|--------|-------|
| 12/05 | Lyon | Perche | 89 | 18-20h | 4 | Pression 1018 stable |
| 14/05 | Vienne | Brochet | 32 | 16-19h | 0 | Pluie + vent |

Au bout de 20-30 sessions, regarde si scores élevés = belles pêches. Si non, ajuste `scoring.py` ou `species.json`.

---

## Pour plus tard : ajouter la façade Telegram

Quand le dashboard tourne depuis 1+ mois et que tu valides l'algo, tu pourras ajouter Telegram :

1. Créer le bot via `@BotFather`, ajouter `.env` avec token + chat_id
2. Créer `src/telegram/` (bot.py, handlers.py, formatter.py, resolver.py)
3. Implémenter les commandes `/score`, `/week`, `/all`, etc.
4. Déployer le bot (Fly.io, Oracle Cloud, ou Raspberry Pi)

**Aucune modification de `src/core/` ni de `src/web/`.** C'est tout l'intérêt de l'archi.

Tight lines 🎣
