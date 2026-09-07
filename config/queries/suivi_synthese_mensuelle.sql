SELECT
    date_trunc('month', m.date_operation)::date     AS mois,
    COALESCE(m.categorie_parente, 'Non categorise') AS categorie_parente,
    SUM(m.montant)                                  AS total,
    COUNT(*)                                        AS nb_operations
FROM  mouvements m
WHERE m.date_operation >= :date_debut
  AND m.est_virement_interne = false
GROUP BY 1, 2
ORDER BY 1 DESC, 3 ASC
