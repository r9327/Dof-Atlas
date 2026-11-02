# PR #337 — Audit des 15 parcours à consignes locales

**Date :** 2026-11-02  
**Commit de code audité :** `ac449ddd369cbc243f6144d991e2386d0291ba7b`  
**Verdict :** **CHANGES REQUIRED — 0/15 parcours certifiés à 100 %**  
**Périmètre :** les 15 fichiers `data/encyclopedia/guides/ganymede_<id>_instructions.json` présents à ce HEAD. Aucun nouveau guide n'est créé dans cet audit.

## Résultat vérifiable

- **15 fichiers rédigés**, **212 étapes numérotées**, **645 actions structurées**.
- **15/15** ont des snapshots de liens factuels locaux. Ces snapshots déclarent `quest_objective_mapping_verified: 0` et `route_order_certified: false` : ils ne contiennent **pas** les objectifs de jeu complets ni l'ordre éditorial certifié de la source.
- **231 actions avec coordonnées** : **229** portent une position également mentionnée dans le relevé de leur étape ; **2** ne correspondent pas à ce critère. Ce critère ne garantit pas qu'une coordonnée présente soit correcte en jeu.
- Les 15 fichiers passent le contrôle **statique de structure** (étapes numérotées, textes/actions présents, types admissibles). Cela ne valide ni les PNJ, dialogues, quantités, embranchements, optimisations, prérequis ni combats réels.
- L'accès web direct à des guides `ganymede-app.com/guides/<id>` a renvoyé un document HTML sans texte lisible exploitable pour une confrontation éditoriale intégrale dans cet environnement. **Aucune comparaison exhaustive 1:1 avec les pages originales n'est démontrée.**
- Aucun **test PySide6/Qt/Windows**, essai sur jeu réel, exécution de Doctor/benchmark ni certification exacte-SHA n'a été produit pour ces 15 parcours durant cet audit.

## Inventaire par guide

| Source | Parcours Atlas (nom courant) | Étapes | Actions | Actions GPS | GPS à examiner | Conformité 100 % |
|---|---|---:|---:|---:|---|---|
| 2219 | Otomaï 1 | 7 | 21 | 5 | Aucun écart de relevé | NON PROUVÉE |
| 2220 | Otomaï 2 | 7 | 19 | 6 | Aucun écart de relevé | NON PROUVÉE |
| 2224 | Sidimote 1 | 25 | 79 | 34 | Aucun écart de relevé | NON PROUVÉE |
| 2227 | Koalaks | 9 | 33 | 10 | Aucun écart de relevé | NON PROUVÉE |
| 2240 | Xélorium 1 | 27 | 71 | 29 | Aucun écart de relevé | NON PROUVÉE |
| 2247 | Dofus Nébuleux | 6 | 22 | 5 | Aucun écart de relevé | NON PROUVÉE |
| 2248 | Dolmanax | 9 | 30 | 1 | Aucun écart de relevé | NON PROUVÉE |
| 2252 | Otomaï 3 | 13 | 37 | 12 | **Étape 1 [-48,19]** | NON PROUVÉE |
| 2259 | Sidimote 5 | 25 | 71 | 44 | Aucun écart de relevé | NON PROUVÉE |
| 2273 | Argenté Scintillant | 15 | 47 | 15 | **Étape 8 [-71,-78]** | NON PROUVÉE |
| 2274 | Roc des Salbatroces | 26 | 62 | 21 | Aucun écart de relevé | NON PROUVÉE |
| 2284 | Le secret des Dofus : Prologue | 21 | 75 | 27 | Aucun écart de relevé | NON PROUVÉE |
| 2285 | Dom de Pin | 4 | 15 | 3 | Aucun écart de relevé | NON PROUVÉE |
| 2290 | Dofus Sylvestre (source) | 2 | 9 | 1 | Aucun écart de relevé | NON PROUVÉE |
| 2590 | Halouine | 16 | 54 | 18 | Aucun écart de relevé | NON PROUVÉE |
| **TOTAL** | | **212** | **645** | **231** | **2** | **0/15 certifié** |

**Interprétation des écarts GPS :**

1. `ganymede_2252_instructions.json` (Otomaï 3), étape 1, indique `[-48,19]` pour le professeur Fournesol. L'observation associée à l'étape 1 ne mentionne aucune coordonnée ; `[-48,19]` apparaît à l'étape 2. Cela peut être un trajet introduit trop tôt, **pas une preuve de fausse position en jeu**.
2. `ganymede_2273_instructions.json` (Argenté Scintillant), étape 8, indique l'entrée d'Externam en `[-71,-78]`, tandis que le relevé local mentionne `[-74,-83]` à cette même étape. Une vérification de destination et de contexte est requise. **Ne pas corriger automatiquement en recopiant le relevé.**

## Écart fonctionnel majeur : présentation actuelle

`app/modules/encyclopedia/views/guide_catalog_view.py` crée `GanymedeSourceReader`, un dialogue `QDialog` de 950×700 pixels et affiche `_format_offline_instruction()` via un **`QPlainTextEdit` en lecture seule**. Il fournit Précédent / Actuelle / Suivant, Valider l'étape, copie du premier `/travel`, et progression manuelle par personnage.

**Ce n'est pas le rendu du grand Guide Succès optimisé** : aucune preuve de cartes avec icônes d'objets, combats cochables individuellement, préparations fusionnées, sections riches de navigation ou fiche stylisée équivalente. Le JSON contient des phrases et des types d'action, **mais pas nécessairement toutes les données structurées nécessaires à cette UX**. L'import des consignes n'établit pas la parité de l'interface.

## Faux positif de certification à éviter

`tools/audit_ganymede_instruction_coverage.py` compte une route comme `complete_offline_instruction_routes` si le fichier et ses étapes respectent le contrat de **structure**. Même si ce compteur atteignait 95/95, `PASS_INSTRUCTION_COVERAGE` ne certifierait **ni conformité à l'intégralité des étapes source ni vérification dans le jeu**. Toujours séparer :
- **rédigé / parseable** ;
- **correspondance source vérifiée étape par étape** ;
- **tests runtime/jeu/UX validés** ;
- **certifié à 100 % sur SHA exact**.

## Conditions nécessaires avant toute nouvelle route

1. Pour **chacun des 15**, disposer d'une référence exhaustive et fiable du chemin réellement attendu, puis rapprocher chaque étape et chaque action (pré-requis, destination, dialogue, collecte, combat, quantité, embranchement, objectifs parallèles et fin de quête) ; relever chaque ajout/manque.
2. Résoudre les deux positions litigieuses sur preuve externe ou en jeu, plutôt que substituer une coordonnée non vérifiée.
3. Tester le lecteur réel et le rendu demandé (y compris états de progression, commande /travel, images d'objets, préparation et combat), vérifier que les deux gros guides optimisés ne changent pas.
4. Exécuter les tests ciblés, Doctor et les validations Windows appropriées. Puis documenter **pour chaque guide** un état `CERTIFIÉ` uniquement lorsque la preuve de parité complète et d'exécution est disponible.
5. **Blocage de production du contenu : pas de nouveaux parcours tant que la conformité des parcours déjà rédigés n'est pas vérifiée**, conformément à la demande du propriétaire de l'application. Conserver PR Draft et ne lancer ni fusion ni release avant résolution.

**Note de méthode :** cette revue est un **audit statique factuel des fichiers réellement présents à GitHub**, et non un audit de contenu complet de Ganymède ou une capture Windows authentique. Elle n'apporte aucune preuve de réussite en jeu.
