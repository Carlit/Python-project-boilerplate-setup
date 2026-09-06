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
| Qualité | flake8 |
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
├── .gitlab-ci.yml             Pipeline lint + tests
├── requirements.txt           Dépendances runtime
├── requirements-dev.txt       Dépendances de développement
├── pyproject.toml             Métadonnées, pytest, coverage
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
flake8 src tests
pytest
pytest --cov=src --cov-report=term-missing
```

Les tests ne nécessitent **aucune** base : les URL sont validées hors
connexion, et SQLite en mémoire sert de banc d'essai pour le requêtage.

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
