# python-db-boilerplate

Socle technique Python pour les traitements et extractions sur bases
**PostgreSQL** et **Oracle**, via SQLAlchemy 2.

## Stack

| Élément | Choix |
| --- | --- |
| Langage | Python 3.11+ |
| ORM / accès données | SQLAlchemy 2.x |
| Driver PostgreSQL | `psycopg` 3 (binaire) |
| Driver Oracle | `python-oracledb` (mode *thin* par défaut) |
| Manipulation de données | pandas |
| Configuration | `python-dotenv` + variables d'environnement |
| Qualité | flake8 + mypy (strict) + pre-commit |
| Tests | pytest + pytest-cov |
| CI | GitLab CI (`.gitlab-ci.yml`) |
| IDE | Visual Studio Code (`.vscode/` fourni) |

## Arborescence

```
python-db-boilerplate/
├── src/                       Code applicatif
│   ├── database.py            Connexions PostgreSQL / Oracle (DatabaseManager)
│   ├── settings.py            Configuration typée depuis l'environnement
│   ├── logging_config.py      Journalisation centralisée
│   ├── exceptions.py          Hiérarchie d'exceptions applicatives
│   └── main.py                Point d'entrée / vérification de connectivité
├── tests/                     Tests unitaires (aucune base requise)
├── config/                    Configurations non secrètes, requêtes SQL
│   └── queries/
├── scripts/                   Outils utilitaires
│   └── userscripts/           User-scripts Tampermonkey
├── docs/                      Documentation
├── .vscode/                   Configuration VS Code partagée
├── .env.example               Modèle de configuration (à copier en .env)
├── .cursorrules               Règles de développement contraignantes
├── .pre-commit-config.yaml    Hooks locaux : flake8 + mypy avant commit
├── .gitlab-ci.yml             Pipeline lint (flake8 + mypy) + tests
├── requirements.txt           Dépendances runtime
├── requirements-dev.txt       Dépendances de développement
├── pyproject.toml             Métadonnées, pytest, coverage, mypy
└── setup.cfg                  Configuration flake8
```

## Démarrage

### Windows (PowerShell)

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS / WSL

```bash
./scripts/bootstrap.sh
source .venv/bin/activate
```

### Manuellement

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env            # puis renseigner les valeurs
```

## Vérifier la configuration et les connexions

```bash
python scripts/check_config.py          # complétude du .env, sans connexion
python -m src.main --check postgres     # test de connexion PostgreSQL
python -m src.main --check oracle       # test de connexion Oracle
python -m src.main --check all
```

## Utilisation

```python
from src.database import DatabaseManager, DatabaseType
from src.logging_config import setup_logging

setup_logging("INFO")

with DatabaseManager.from_env() as db:
    # Lecture simple
    lignes = db.fetch_all(
        DatabaseType.POSTGRES,
        "SELECT id, libelle FROM incident WHERE date_creation >= :debut",
        {"debut": "2026-01-01"},
    )

    # Chargement direct en DataFrame
    df = db.read_dataframe(DatabaseType.ORACLE, "SELECT * FROM v_incidents")

    # Écriture transactionnelle
    db.execute(
        DatabaseType.POSTGRES,
        "UPDATE incident SET statut = :statut WHERE id = :id",
        {"statut": "CLOS", "id": 42},
    )
```

Points notables du `DatabaseManager` :

- engines créés paresseusement et mis en cache, un par moteur ;
- `pool_pre_ping` activé et recyclage des connexions : résiste aux coupures
  réseau et aux fermetures de session côté serveur ;
- réessais avec backoff exponentiel sur échec de connexion ;
- mots de passe échappés par `URL.create` et jamais journalisés ;
- erreurs des drivers converties en exceptions applicatives (`src/exceptions.py`).

## Qualité et tests

```bash
flake8 src tests scripts
mypy
pytest
pytest --cov=src --cov-report=term-missing
```

Les tests ne nécessitent **aucune** base : les URL sont validées hors
connexion, et SQLite en mémoire sert de banc d'essai pour le requêtage.

`mypy` tourne en mode strict (`[tool.mypy]` dans `pyproject.toml`) sur
`src`, `scripts` et `tests`.

### pre-commit

Un hook local (`.pre-commit-config.yaml`) exécute flake8 puis mypy avant
chaque commit, en réutilisant l'outillage déjà installé dans le venv du
projet — pas d'environnement isolé supplémentaire à maintenir.

```bash
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

Le venv doit être **activé** au moment du commit (`flake8`/`mypy` doivent
être sur le PATH) ; c'est le cas par défaut dans un terminal VS Code
intégré (`python.terminal.activateEnvironment` est déjà à `true`).

### Tâches VS Code

`Terminal > Exécuter une tâche` (ou `Ctrl+Maj+P` → *Tasks: Run Task*)
expose « Lint (flake8) », « Typage (mypy) », « Tests (pytest) », et une
tâche combinée « Qualité (flake8 + mypy + pytest) » qui enchaîne les
trois dans l'ordre.

## Sécurité

- Aucun secret n'est versionné : `.env` est ignoré par Git, seul `.env.example`
  est committé.
- Tout SQL est paramétré par noms (`:param`) — la concaténation de chaînes pour
  construire une requête est interdite (voir `.cursorrules`).
- Les URL de connexion sont journalisées mot de passe masqué.

## Règles de développement

Voir [`.cursorrules`](.cursorrules) : typage statique obligatoire, gestion
stricte des erreurs et des logs, code concis et modulaire. Ces règles
s'appliquent à toute contribution, humaine ou assistée.
