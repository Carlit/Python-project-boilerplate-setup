-- Exemple de requête paramétrée par noms.
-- Les paramètres sont fournis par le code via `:nom` — jamais par concaténation.
--
--   from src.database import DatabaseManager, DatabaseType
--   sql = (PROJECT_ROOT / "config/queries/exemple_postgres.sql").read_text("utf-8")
--   rows = db.fetch_all(DatabaseType.POSTGRES, sql, {"date_debut": "2026-01-01"})

SELECT
    id,
    libelle,
    date_creation
FROM  incident
WHERE date_creation >= :date_debut
ORDER BY date_creation DESC;
