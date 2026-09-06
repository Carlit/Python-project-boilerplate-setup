# config/

Configurations **non secrètes** et versionnées : paramètres par environnement,
requêtes SQL de référence, mappings.

Ce dossier ne doit contenir aucun identifiant, mot de passe ou chaîne de
connexion. Les secrets vivent exclusivement dans le fichier `.env` à la racine,
ignoré par Git (modèle : `.env.example`).

## Contenu

| Fichier | Rôle |
| --- | --- |
| `environments.example.toml` | Modèle de paramétrage par environnement (local / recette / production) |
| `queries/` | Requêtes SQL réutilisables, une par fichier |

Tout fichier nommé `*.local.*` est ignoré par Git : c'est l'emplacement prévu
pour une surcharge propre au poste.
