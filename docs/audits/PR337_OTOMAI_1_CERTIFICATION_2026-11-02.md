# PR #337 — Otomaï 1 (#2219) : vérification individuelle avant certificat

**Périmètre : un seul parcours #2219 (7 étapes). Règle : ne pas commencer
le suivant avant certification complète du présent.**

## État réel : BLOCKED / NON CERTIFIÉ

| Épreuve | Résultat | Preuve et limites |
| --- | --- | --- |
| Catalogue local et ordre | PASS statique | 7/7 étapes consécutives, ID 2219, `source_url` cohérente |
| Contenu structuré | PASS statique | 40 actions explicites, dont 3 combats de traversée indépendants et l'option « Le secret des Flaqueux » |
| Coordonnées locales | PASS statique | 9/9 actions de déplacement situées sur les cartes observées à la même étape |
| Régression du contenu attendu | PASS statique JS | Relecture des assertions du test `tests/test_ganymede_local_instructions.py` sur le JSON courant : combats 3 uniquement à l'étape 4, ressources, deux succès, GPS, 2 scaéroplanes et flags NON CERTIFIÉ |
| Source Ganymède exacte | **NOT_VERIFIED** | La page catalogue source `https://ganymede-app.com/guides/2219` n'expose pas son texte complet ici ; le parcours public `https://ganymede-app.com/guides/183` correspond à 7 étapes et aux positions du relevé, mais le rattachement exact des deux IDs reste à prouver |
| Sources de quêtes indépendantes | PARTIAL | `dofuspourlesnoobs.com` : « Le nouveau monde », « L'île des naufragés », « Un autre moyen de transport », « Scaéroplane à très grande vitesse » ; vérification DOFUS Unity manquante |
| Quantité Graines de Sésame | **CONFLICT** | La route GP6/183 mentionne 3 Graines de Sésame, un guide de quête indépendant en mentionne 10. Le texte conserve la variante source et impose une vérification en jeu avant validation |
| Tests Python ciblés (`unittest`) | **NOT_RUN** | Pas de checkout intégral + dépendances Python/Qt de la PR disponibles dans cette session |
| En-tête universel des guides optimisés | **FAIL vérifié par lecture de code** | `app/modules/encyclopedia/views/guide_catalog_view.py` ouvre `GanymedeSourceReader` (`QDialog`) et affiche les actions dans un `QPlainTextEdit`, pas dans le composant d'en-tête du lecteur optimisé |
| Positions copiables individuellement | **FAIL vérifié par lecture de code** | `copy_travel()` copie uniquement `positions[0]` : les autres positions d'une étape ne sont pas sélectionnables via leur propre action |
| Objets copiables/couleurs PNJ/ressources | **FAIL vérifié par lecture de code** | `_format_offline_instruction()` concatène du texte brut ; aucune interaction ni style de couleur différent pour les objets et les PNJ |
| Progression et validation propres au guide | PARTIAL | `toggle_step` persiste manuellement les étapes par `character:<id_dofus>`; pas de validation vérifiée des objectifs/combats réels ni de test de reprise sous Windows |
| Test application Windows, DOFUS Unity, sauvegarde/reprise | **NOT_RUN** | Essais natifs et validation de gameplay absents ; aucune preuve d'acceptation 100 % |

**Résultat global : BLOCKED / NON CERTIFIÉ.** Même un PASS des
contrôles documentaires n'équivaut pas à la certification du guide.
Les champs `source_parity_certified=false` et
`gameplay_certified=false` restent explicites.

## Correctifs de ce lot

- `506dd742` : les 7 étapes du guide ont été réécrites pour détailler
  3 combats distincts (Boomba, Nakumbra, Canon Dorf rachitiques),
  les dialogues, les ressources/quantités, le détour facultatif des
  Flaqueux, les deux dragodindes et les deux quêtes des scaéroplanes ;
  aucune transition ou quête n'est auto-cochée dans le fichier.
- `01e562ed` : correction des positions et mentions manquantes
  dans le fichier, alignement avec les assertions déjà présentes dans
  `tests/test_ganymede_local_instructions.py`, et ajout des deux
  marqueurs `false` pour éviter toute certification implicite.
- Lecture statique directe GitHub au SHA `01e562ed26bdfaac12f8880f936eccd1d36fe0f3` :
  7 étapes, 40 actions, 9 coordonnées du relevé,
  évaluation JS des contraintes de régression **PASS_STATIC_JS**
  (aucun échec). Ce n'est **pas** un `unittest` Python.

## Avant de passer au guide suivant

1. Comparer `/guides/2219` à `/guides/183` et vérifier les 7 étapes
   d'origine, les quantités, le droit de reprise et tous les objectifs.
2. Conformément à `AGENTS.md`, produire le rapport Graphify
   du SHA exact **avant de modifier structurellement la navigation**
   et réutiliser un seul en-tête/lecteur partagé pour tous les guides.
   Les coordonnées de chaque déplacement, objets de préparation et
   PNJ doivent avoir leurs interactions et couleurs communes au
   Guide optimisé. La validation reste propre à chaque parcours.
3. Exécuter et corriger les tests du contrat de contenu, du lecteur Qt,
   des sauvegardes et de la sélection de personnages.
4. Vérifier sur un PC Windows avec DOFUS Unity : 7/7 étapes,
   trois combats, itinéraires facultatifs et obligatoires,
   prérequis/récompenses, copies, sauvegarde et retour.
5. Enregistrer la preuve complète au SHA du guide, puis seulement
   déclarer `CERTIFIED` et travailler sur #2220 (ou l'autre guide
   suivant). Pas de FULL CI de PR avant fin d'implémentation.

**Aucun guide suivant entamé dans ce lot. PR #337 reste Draft,
CHANGES REQUIRED.**
