# [PLAN 15] Validation native Windows de bout en bout après correctifs

> **PLAN / DRAFT : scénario d'intégration produit à écrire et exécuter après correctifs, pas une certification déjà obtenue.**

Code audit source : `main@ac07be9b894718f5e68e7c3a91016d7651e3065b`. Rapport/probes : [PR #160](https://github.com/r9327/Dof-Atlas/pull/160).

## Pourquoi ce lot est distinct
Doctor/Graphify/AI Context attestent la structure, pas les parcours natifs de bout en bout. #168 vérifie la **politique** de certification et #159 prépare la **distribution**. Ce lot vérifie le **produit réel**, sans redévelopper les autres lots.

## Travail prévu
1. Créer des scénarios de validation representatifs sur Windows/Python/PySide réel, sans assimiler une trace Qt synthétique à l'application complète.
2. Tester le parcours source DOFUS.bat → Home → Quêtes → Guide compact et Guide manuel → Succès, avec identité personnage réelle et propagation/décochage.
3. Tester Craft avec recettes/dataset complet, Organizer avec profils/ordre, Zaap navigation et retours Home, Scan Monde avec persistance, Équipement externe et ses échecs contrôlés.
4. Capturer flux UI réels, destruction des vues différées et workers aux frontières Home ; quantifier mémoire et latence après stabilisation des modules, sans remettre un gate artificiel Home<100 Mo.
5. Pour réseau/capture Npcap et EXE, exécuter scénarios Win32/UAC seulement en environnement autorisé ; worker IPC et stdout --windowed sont propriétaires #159, pas de modification doublonnée.
6. Tester un build indépendant du checkout et une installation propre + mise à niveau + rollback uniquement une fois #159 prête ; journaliser présence des datasets et provenance exact-SHA.
7. Exécuter validation Guide/Quêtes/Succès/Craft avec les données brutes exactes et versionnées ; faute de dataset, marquer BLOCKED et ne pas annoncer PASS.
8. Rendre publiquement lisibles la matrice des scénarios, tests réellement joués, skipped, erreurs, limitations natives et preuves re-lançables ; pas de FULL en boucle.
9. Réaliser une certification cumulative unique uniquement lorsque les patchs préalables sont stabilisés et que la policy la justifie.

## Critères de sortie
- [ ] Un scénario produit réel par flux majeur (Quêtes/Guide/Succès, Craft, Scan, Organizer, Zaap, Equipment) avec résultat et preuve.
- [ ] Quitter chaque écran pour Home sans objet/thread permanent non expliqué ; comparer valeurs plutôt que supposer un budget arbitraire.
- [ ] Chaque blocage Windows/Npcap/données externes est affiché, pas transformé en certificat vert.
- [ ] EXE install/rollback, binaire compilé et Qt lock restent explicitement sous responsabilité #159 et #138, avec preuves consommées, pas dupliquées.
- [ ] Preuves rattachées au SHA de code et au fingerprint des données ; aucun merge de cette PR de plan comme si produit certifié.

## Dépendances
Après code des PR #161/#162/#163/#164 et #159 ; coordination #138 Qt et #168 gate ; preuves complémentaires #170/#171/#172/#173/#174. Aucun test de production ne peut être déclaré PASS sans installation/autorisation/dataset correspondants.

**Aucun code applicatif modifié par ce plan.** Commencer au HEAD réel après les merges, puis tests ciblés et certification adaptée.
