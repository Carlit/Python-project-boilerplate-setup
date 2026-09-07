-- Critere 2 (le critere principal) : aucun marchand normalise apparaissant
-- 3 fois ou plus sur la periode ne doit rester non categorise. Un libelle
-- brut peut se decliner en plusieurs variantes (prefixe "Carte DD/MM/YY ",
-- "Avoir DD/MM/YY ", "Annul Carte DD/MM/YY ", "Rbt Carte DD/MM/YY ",
-- "Retrait Dab DD/MM/YY " ; suffixe " Cb*NNNN") : elles sont normalisees
-- avant regroupement, sinon un marchand frequent reste invisible sous le
-- seuil (ex. Superbuy : 4 libelles bruts, 1 marchand normalise).
-- Ne retourne que les marchands en infraction (compte >= 3 ET au moins
-- une operation encore non categorisee) : une liste vide = critere respecte.
WITH normalise AS (
    SELECT
        upper(trim(
            regexp_replace(
                regexp_replace(
                    COALESCE(m.libelle_suggere, m.libelle_brut),
                    '^(Carte|Avoir|Annul Carte|Rbt Carte|Retrait Dab) [0-9]{2}/[0-9]{2}/[0-9]{2}\s+',
                    '', 'i'
                ),
                '\s+Cb\*[0-9]+$', '', 'i'
            )
        ))                        AS marchand_normalise,
        m.categorie_parente
    FROM  mouvements m
    WHERE m.date_operation >= :date_debut
      AND m.est_virement_interne = false
)
SELECT
    marchand_normalise,
    COUNT(*)                                                     AS total_operations,
    COUNT(*) FILTER (WHERE categorie_parente = 'Non catégorisé') AS operations_non_categorisees
FROM normalise
GROUP BY marchand_normalise
HAVING COUNT(*) >= 3
   AND COUNT(*) FILTER (WHERE categorie_parente = 'Non catégorisé') > 0
ORDER BY operations_non_categorisees DESC, total_operations DESC
