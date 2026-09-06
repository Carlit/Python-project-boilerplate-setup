-- Exemple de requête Oracle paramétrée par noms.
-- Attention : Oracle met les identifiants non quotés en MAJUSCULES.
-- Les colonnes remontent donc en majuscules dans les dictionnaires résultats,
-- sauf usage d'alias quotés comme ci-dessous.

SELECT
    t.id            AS "id",
    t.libelle       AS "libelle",
    t.date_creation AS "date_creation"
FROM  incident t
WHERE t.date_creation >= :date_debut
  AND ROWNUM <= :limite
ORDER BY t.date_creation DESC;
