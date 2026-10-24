# Atlas Guides — Plan d'exécution séquentiel et matrice de certification

> **CADRAGE UNIQUEMENT.** Ce document liste les règles d'exécution futures ; il ne lance aucun développement, test CI, déploiement, merge ni auto-remédiation. Base auditée : `5849fb05828d56b5b5a15fe762e762a71f6b913c` au 24 octobre 2026. Après changement de `main`, vérifier les chemins/contrats cités avant implémentation.

## Sources de vérité, ordre, couverture

| Ordre | PR de cadrage | Produit de sortie exigé | Entrées essentielles | Tests/évidence à la fin |
| --- | --- | --- | --- | --- |
| 1 | [#249 — Unity / Organizer / identité](https://github.com/r9327/Dof-Atlas/pull/249) | Registre d'identités vérifiées, sessions et portraits fiables, diagnostic fail-closed | Scanner Unity, Organizer, bindings, SHA client exact, capture Npcap | Scénarios Windows d'identité/connexion et tests réseau ciblés ; mentionner explicitement les preuves indisponibles |
| 2 | [#250 — Progression / Valider](https://github.com/r9327/Dof-Atlas/pull/250) | Écriture manuelle multi-personnages atomique, état de chaque fiche et progrès collectif exact | Identités sûres #249, GuideProgressService, snapshots Quêtes/Succès | Vrais clics Qt, JSON avant/après, 0/1/2/6 personnages, reprise après restart |
| 3 | [#251 — Préparation](https://github.com/r9327/Dof-Atlas/pull/251) | Exigences documentées, quantités/provenances, état Prêt individuel stable | Participants #249, progression #250, cartes Guide Succès/Sylvestre | Sources réelles, quantités, pierres d'âme, absence de participants, charge mémoire |
| 4 | [#252 — En-tête Opti](https://github.com/r9327/Dof-Atlas/pull/252) | Trois rangées compactes, un anneau global, trois barres en ligne, vrais panneaux et navigation fiche | Métriques cohérentes #250/#251, SharedGuideManualView | Mesures Qt, capture réelle **en-tête seulement**, clics, DPI / petites-grandes fenêtres |
| 5 | [#253 — Ergonomie + colonne droite](https://github.com/r9327/Dof-Atlas/pull/253) | Retour Quêtes/Guide, Sommaire sticky, commandes sûres, colonne rétractable | UI en-tête #252, contextes navigate_entity et splitter classique | Clics de navigation, état colonne/scroll, 3 captures utiles au maximum pour l'ensemble du chantier |
| 6 | [#254 — Accueil](https://github.com/r9327/Dof-Atlas/pull/254) | Deux cartes Opti, catégories alignées, grille Dofus, aucune recherche globale redondante | GuideCatalogView léger, signal guideRequested, libération rich runtime | Tests accueil, action carte entière, 3 largeurs, RAM accueil → guide → retour |
| 7 | [#255 — Ganymède](https://github.com/r9327/Dof-Atlas/pull/255) | Route continue unique par guide réellement certifié, suivis sûrs, statut explicite des non-certifiés | Moteur continu, données/manifestes source, #249–#254 | Parité manifeste/étapes, persistance, Doctor Ganymède ciblé, export Windows |

**Règle transversale :** ne pas toucher aux optimisations du Guide Succès en appliquant Ganymède. Ganymède apporte l'ordre source continu, pas une nouvelle route optimisée. Bonta/Brâkmar sont des catégories d'Alignement et ne passent pas le validateur actuel `ContinuousGuideNavigation` réservé à `category=dofus` ; leur activation exige un contrat réellement adapté.

## Séquence future pour CHAQUE PR — après autorisation explicite de développement

1. Vérifier `git rev-parse HEAD`, `git status --short`, `main` et l'état de la PR ; **un seul clone canonique**. Ne pas intégrer la branche accidentelle `fix/guide-opti-compact-controls-character-progress-20261024`.
2. Actualiser seulement **la PR active** depuis le `main` fusionné le plus récent. Une PR brouillon de planification n'est pas une PR terminée : ajouter l'implémentation au même lot, ne pas fusionner les documents seuls.
3. Relever pour chaque cas de réception le propriétaire du code, la donnée d'entrée, la sortie attendue, l'effet sur les sauvegardes, la preuve Qt/réseau nécessaire et le test le plus étroit disponible.
4. Implémenter toutes les exigences du lot, sans faire de petites PR supplémentaires par bouton. Des tests locaux rapides sont permis pendant le codage ; **pas de campagne CI complète intermédiaire**.
5. Comparer les résultats réels aux critères ; corriger les cas échoués et les tests obsolètes, sans suppressions opportunistes, sans faux providers non signalés, sans graphiques ou screenshots inventés.
6. Une fois le lot fonctionnel, préparer le **SHA candidat final**. L'événement `ready_for_review` déclenche `Phase Certification` : ne l'envoyer qu'au moment de certification. Les autres workflows `scoped-pr-ci` / `doctor-ui` sont majoritairement `workflow_dispatch` ou `workflow_call`, pas une preuve implicite de PASS sur chaque push.
7. Employer **l'impact réel** pour sélectionner Doctor, tests Windows, snapshots et performance. Si le planificateur `Phase Certification` indique `FULL_REQUIRED`, ne pas prétendre qu'un PASS scoped le remplace. Un `workflow_dispatch` manuel peut forcer FULL ; éviter ce déclenchement par réflexe. Ne pas désactiver les contrôles de sécurité juste pour gagner du temps.
8. Conserver un passeport de preuve : SHA candidat, base SHA, fichiers concernés, scénario réel, tests effectivement exécutés, captures utiles, métriques RAM, statut PASS/FAIL/BLOQUÉ, limites, rapport.
9. En cas de correction **après** une certification, toutes les preuves changées de SHA doivent être réévaluées. Merge uniquement si l'ensemble des contrats requis au SHA final est satisfait ; puis mise à jour de la PR suivante, **sans demander de nouvelle validation du découpage à chaque étape**.

## Points d'arrêt et résultats honnêtes

- **BLOQUÉ** = preuve indispensable manquante (Windows Dofus réel, mapping inconnu, donnée Ganymède incompréhensible, référence visuelle indisponible). Ne pas convertir BLOQUÉ en PASS ni remplacer la preuve par une fixture fictive.
- **PARTIEL** = chemins réparés mais scénarios de réception incomplets. Le lot reste brouillon et non fusionné.
- **TERMINÉ** = code, tests pertinents, preuves exact-SHA, absence de régression sur les dépendances et critères de réception complets ; passage en Ready/merge suivant les protections réelles.
- Les PR de cadrage #249–#255 ne contiennent actuellement que des spécifications. Leur numérotation ne mesure **aucun avancement fonctionnel**.

## Limites et non-régression

- La copie du cache `QuestCharacter` perd actuellement le champ `class_key` (PR #249) : diagnostic, **pas correctif** à ce stade.
- Le cercle et Route/Préparation/Succès reposent sur des sources distinctes ; ne pas inventer une métrique collective à partir du minimum des compteurs.
- Le bouton Valider d'une fiche rendue utilise aujourd'hui un seul `character_key` ; vérifier les destinataires avant toute mutation.
- Les sauvegardes Guide Succès, Sylvestre et Ganymède restent isolées et la migration ancienne `page:gps` est potentiellement écrite pendant une lecture.
- Les sources Ganymède indexent 95 guides, avec des drafts de cutover source-trusted pour 20 Dofus ; **aucune promesse de 95 parcours jouables**.
- La capture de référence de l'en-tête validée par l'utilisateur est externe à ce dépôt. Son absence interdit une certification de ressemblance exacte sans comparaison au moment de l'implémentation.
- L'EXE Windows doit rester autonome et inclure les ressources réellement utiles, sans Python utilisateur ni bibliothèque de développement.
