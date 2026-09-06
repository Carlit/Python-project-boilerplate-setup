# Architecture

## Vue d'ensemble

Le socle sépare quatre responsabilités, une par module, sans dépendance
circulaire :

```
main.py  ──►  database.py  ──►  settings.py  ──►  exceptions.py
   │               │                  │
   └──────► logging_config.py ────────┘
```

| Module | Responsabilité | Ne fait pas |
| --- | --- | --- |
| `settings.py` | Lire et valider l'environnement, exposer des dataclasses typées | Aucun accès réseau |
| `logging_config.py` | Configurer les handlers une seule fois | Aucune logique métier |
| `database.py` | Créer les engines, ouvrir des connexions, exécuter du SQL | Aucune règle métier |
| `exceptions.py` | Typer les erreurs applicatives | Aucun effet de bord |
| `main.py` | Orchestrer le démarrage et la vérification | Aucun accès direct aux drivers |

## Configuration

Toute la configuration provient de variables d'environnement, chargées depuis
`.env` par `python-dotenv` en développement et injectées par la plateforme en
recette et production.

`DatabaseManager.from_env()` est volontairement tolérant : si seule la
configuration PostgreSQL est présente, l'objet est créé et seul l'appel
effectif au moteur Oracle lèvera une `ConfigurationError`. Un projet
n'utilisant qu'un moteur n'a donc pas à renseigner l'autre.

## Cycle de vie des connexions

1. `get_engine(db_type)` crée l'engine à la première demande puis le met en
   cache. Un engine porte un pool : il ne doit jamais être recréé par requête.
2. `connect(db_type)` ouvre une connexion **dans une transaction**
   (`engine.begin()`) : commit à la sortie du bloc, rollback sur exception.
3. En cas d'échec de connexion, trois tentatives sont effectuées avec un
   backoff exponentiel (1 s, 2 s). L'échec final lève `ConnectionFailedError`.
4. `dispose()` — appelé automatiquement par le `with` sur le manager — ferme
   tous les pools.

`pool_pre_ping=True` teste la connexion avant de la sortir du pool : c'est ce
qui évite les erreurs « server closed the connection unexpectedly » après une
coupure firewall ou un timeout d'inactivité côté serveur.

## Spécificités par moteur

### PostgreSQL

- Dialecte `postgresql+psycopg` (psycopg 3).
- `PG_SCHEMA` est appliqué via `options=-csearch_path=<schema>` dans les
  `connect_args` : les requêtes n'ont pas à préfixer les tables.
- `PG_SSLMODE` est transmis tel quel au driver.

### Oracle

- Dialecte `oracle+oracledb`, mode **thin** par défaut : aucun Oracle Instant
  Client à installer sur le poste.
- Le *service name* est privilégié ; le SID reste disponible pour les bases
  anciennes (`ORACLE_SID`).
- Le mode **thick** n'est nécessaire que pour certaines fonctionnalités
  avancées (authentification externe, jeux de caractères anciens). Il s'active
  par `ORACLE_CLIENT_MODE=thick` et `ORACLE_CLIENT_LIB_DIR`.
- Oracle met les identifiants non quotés en MAJUSCULES : les clés des
  dictionnaires retournés le sont aussi, sauf alias quotés dans la requête
  (voir `config/queries/exemple_oracle.sql`).

## Gestion des erreurs

Le code appelant ne manipule jamais d'exception de driver. Toute
`SQLAlchemyError` est interceptée et convertie :

| Situation | Exception levée |
| --- | --- |
| Variable d'environnement manquante ou invalide | `ConfigurationError` |
| Connexion impossible après réessais | `ConnectionFailedError` |
| Échec d'exécution d'une requête | `QueryError` |

Toutes dérivent de `AppError`, ce qui permet un `except AppError` unique au
niveau du point d'entrée.

## Stratégie de test

Aucun test ne requiert de serveur de base de données :

- la construction des URL est vérifiée hors connexion (dialecte, échappement du
  mot de passe, arbitrage service name / SID) ;
- le requêtage (`fetch_all`, `fetch_one`, `execute`, `read_dataframe`) est
  exercé sur SQLite en mémoire, en injectant l'engine dans le cache du manager ;
- l'environnement est isolé par une fixture `autouse` qui purge les variables
  du poste, garantissant des tests reproductibles en CI comme en local.
