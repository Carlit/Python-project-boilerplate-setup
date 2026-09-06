# scripts/userscripts/

User-scripts Tampermonkey / Violentmonkey versionnés avec le projet.

Ils servent à outiller des interfaces web internes (extraction d'un tableau,
ajout d'un bouton de copie, injection d'un raccourci) lorsqu'aucune API n'est
disponible.

## Convention

- Un fichier par script, extension `.user.js`.
- L'en-tête `==UserScript==` est obligatoire et versionné (`@version`), avec un
  `@match` aussi restrictif que possible.
- Aucun secret, identifiant, jeton ou URL interne sensible dans le code : ces
  fichiers sont lisibles par tout porteur du dépôt.
- Aucune donnée n'est envoyée vers un domaine tiers.

## Installation

1. Installer l'extension Tampermonkey dans le navigateur.
2. Tableau de bord → Utilitaires → *Importer depuis un fichier*, ou créer un
   nouveau script et coller le contenu.
3. Vérifier la ligne `@match` avant activation.
