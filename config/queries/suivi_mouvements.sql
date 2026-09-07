SELECT
    m.date_operation,
    c.libelle                                   AS compte,
    c.type_budget,
    COALESCE(m.libelle_suggere, m.libelle_brut) AS libelle,
    m.montant,
    m.categorie_parente,
    m.categorie,
    m.traitement
FROM  mouvements m
JOIN  comptes c ON c.id = m.compte_id
WHERE m.date_operation >= :date_debut
  AND m.date_operation <  :date_fin
  AND m.est_virement_interne = false
ORDER BY m.date_operation DESC, c.libelle
