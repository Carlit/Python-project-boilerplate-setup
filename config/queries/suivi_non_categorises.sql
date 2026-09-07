SELECT
    COALESCE(m.libelle_suggere, m.libelle_brut) AS marchand,
    COUNT(*)                                    AS nb_operations
FROM  mouvements m
WHERE m.categorie_parente = 'Non catégorisé'
  AND m.date_operation >= :date_debut
GROUP BY 1
ORDER BY 2 DESC, 1
