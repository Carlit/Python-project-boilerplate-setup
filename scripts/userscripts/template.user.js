// ==UserScript==
// @name         Modèle - outil interne
// @namespace    python-db-boilerplate
// @version      0.1.0
// @description  Modèle de user-script : à dupliquer et adapter.
// @author       Charly
// @match        https://exemple.interne.local/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const PREFIX = '[boilerplate]';

    /**
     * Journalise un message préfixé.
     * @param {string} message
     * @param {...unknown} args
     */
    function log(message, ...args) {
        console.info(`${PREFIX} ${message}`, ...args);
    }

    /**
     * Attend l'apparition d'un élément dans le DOM.
     * @param {string} selector Sélecteur CSS.
     * @param {number} timeoutMs Délai maximal d'attente.
     * @returns {Promise<Element>}
     */
    function waitFor(selector, timeoutMs = 10000) {
        return new Promise((resolve, reject) => {
            const existing = document.querySelector(selector);
            if (existing) {
                resolve(existing);
                return;
            }

            const observer = new MutationObserver(() => {
                const found = document.querySelector(selector);
                if (found) {
                    observer.disconnect();
                    clearTimeout(timer);
                    resolve(found);
                }
            });

            const timer = setTimeout(() => {
                observer.disconnect();
                reject(new Error(`Élément introuvable : ${selector}`));
            }, timeoutMs);

            observer.observe(document.body, { childList: true, subtree: true });
        });
    }

    /**
     * Point d'entrée du script.
     * @returns {Promise<void>}
     */
    async function main() {
        try {
            const target = await waitFor('#zone-cible');
            log('Élément cible trouvé', target);
            // ... traitement ...
        } catch (error) {
            console.error(`${PREFIX} échec :`, error);
        }
    }

    main();
})();
