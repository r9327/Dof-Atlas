# PR #337 — Otomaï 1 (source 2219) : contrôle avant certification individuelle

**Date :** 2026-11-02  
**SHA des données et tests examinés :** `9df839b6f809e750307ba7d138e2c3844de9b641`  
**STATUT : `NOT_CERTIFIED` — guide non terminé.**  
**Ordre de travail :** ne pas poursuivre le guide suivant avant la preuve de
certification intégrale de ce parcours. Une correction d'un guide préexistant ne
vaut pas certif.

## Contrôles réellement effectués

| Contrôle | Résultat | Preuve / limite |
| --- | --- | --- |
| JSON lu depuis le HEAD de la PR | PASS_STATIC | 7 étapes numérotées 1–7, 41 actions typées, toutes avec texte |
| Coordonnées par étape | PASS_STATIC | 11/11 déplacements présents dans le relevé `ganymede_otomai_1_observed_links.json` de même étape |
| Trois combats de traversée | PASS_STATIC | 3 actions de combat à l'étape 4 ; aucune à l'étape 3 |
| Succès / niveaux / préparations | PASS_STATIC | Niveau 40 recommandé, « La grande kradoc » et « Haute voltige », graines de sésame, objets de la traversée |
| Détour facultatif source | PASS_STATIC | « Le secret des Flaqueux » en [-43,-1], parasol, Parchemin des Flaqueux ; jamais une validation forcée |
| Les deux quêtes de scaéroplane | PASS_STATIC | Flip Flap [-56,22], Spitte Fayeur [-54,19], actions typées de remise |
| Format des dragodindes | NEEDS_GAME_CHECK | Le guide officiel numérote Rousse/Amande sans format ; de vieux guides demandent des certificats sauvages, des sources modernes parlent des dragodindes. La consigne demande de vérifier le format réellement accepté dans Unity |
| Test de régression Python dédié | NOT_RUN | Test ajouté dans `tests/test_ganymede_local_instructions.py`, mais non exécuté dans un checkout du dépôt. Ancienne assertion devenue contradictoire (1 bloc de 3 combats) corrigée pour trois actions `fight` |
| Comparaison Ganymède **2219** de bout en bout | NOT_PROVEN | La source cible [MG6] est consultable à l'étape 1 ; les étapes complètes 2–7 ont été rapprochées de [GP6] 183, parcours public parallèle du même sujet, **non preuve 1:1 de MG6** |
| Rendu dans l'entête universel, positions/objets copiables, couleurs PNJ et progression par `character:<id_dofus>` | NOT_RUN | Pas d'essai PySide6/Qt sous Windows |
| Réalité des combats, PNJ, objets, quêtes, déblocage et reprise sous DOFUS Unity | NOT_RUN | Pas de session Windows/Unity disponible |
| Doctor ciblé, vérifications de régression sur guide optimisé et benchmark | NOT_RUN | Sans checkout, commandes locales inaccessibles ; aucune FULL CI lancée sur une PR Draft |

## Sources de recoupement

- Route cible : https://ganymede-app.com/guides/2219?page=1&stepsPerPage=1
- Parcours public parallèle 7 étapes : https://ganymede-app.com/guides/183
- Quête accessoire : https://www.dofuspourlesnoobs.com/le-secret-des-flaqueux.html
- Accès et fournitures : https://www.dofuserie.com/quetes/le-nouveau-monde/
- Succès/équipements : https://www.dofuspourlesnoobs.com/haute-voltige.html
- Flip Flap : https://www.dofuserie.com/quetes/un-autre-moyen-de-transport/
- Spitte Fayeur : https://www.dofuserie.com/quetes/scaeroplane-a-tres-grande-vitesse/

Toutes les instructions locales restent rédigées en propres termes ;
aucune source tierce n'est importée en texte brut.

## Corrections et audit des commits du lot

1. `80b0620` : révision des sept étapes, actions de combats détaillées,
   statut `source_parity_certified=false` et `gameplay_certified=false`.
   **REVIEW OK** sur la structure, mais condition trop affirmative
   de certificat sauvage corrigée par `8b1c8c5`.
2. `f8066f8` : test de non-régression dédié.
   **IMPROVEMENTS REQUIRED** à cet état : ancien test attendant une
   unique action de combat ; corrigé par `9df839b`.
3. `8b1c8c5` : retire la certitude des seuls certificats sauvages,
   rétablit les objets indiqués dans la version actuelle.
   **REVIEW OK** ; test mis à jour dans `e4fd991`.
4. `e4fd991` : assertions sur les deux montures et le format Unity.
   **REVIEW OK**, tests non exécutés.
5. `9df839b` : ancienne assertion modifiée de 1 à 3 actions de combat.
   **REVIEW OK** en lecture statique, tests non exécutés.

**Verdict logique actuel : REVIEW OK pour ces changements documentaires
et le code test corrigé ; verdict métier : NOT_CERTIFIED.**
La parité intégrale du guide cible et les essais Windows/Unity sont
obligatoires avant toute signature `CERTIFIED` et avant de passer au
parcours suivant. La Phase Certification finale de la PR reste séparée.
