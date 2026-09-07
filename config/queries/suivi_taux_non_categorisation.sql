-- Critere 1 : part des operations non categorisees sur la periode.
-- Cible : < 5 %. Baseline mesuree le 07/09/2026 : 66 sur 530 mouvements
-- hors virements internes, du 01/05 au 07/09/2026 (soit 12,5 %).
SELECT
    COUNT(*)                                                       AS total_operations,
    COUNT(*) FILTER (WHERE m.categorie_parente = 'Non catégorisé') AS operations_non_categorisees,
    round(
        100.0 * COUNT(*) FILTER (WHERE m.categorie_parente = 'Non catégorisé')
        / COUNT(*),
        1
    )                                                               AS pct_non_categorise
FROM  mouvements m
WHERE m.date_operation >= :date_debut
  AND m.est_virement_interne = false
