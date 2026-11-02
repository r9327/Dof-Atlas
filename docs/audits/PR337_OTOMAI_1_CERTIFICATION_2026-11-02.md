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

## Correctifs locaux du lecteur — lot additionnel du 2 novembre

**Périmètre effectivement modifié :** consignes Otomaï 1 et composants
existants du lecteur de guides rédigés. Pas de nouveau guide, pas de
modification des deux guides optimisés, pas de restructuration
d'architecture ni de migration des sauvegardes.

| Problème | État après ce lot | Preuve |
| --- | --- | --- |
| Plusieurs positions à copier sur une étape | **CODE CORRIGÉ / TEST QT NOT_RUN** | Un lien `copy:<index>` par déplacement, chaque lien copie la commande `/travel x,y` depuis la seule étape affichée |
| PNJ et objets copiables distinctement | **CODE CORRIGÉ SUR #2219 / QT NOT_RUN** | `copy_values` explicites (20 libellés sur 13 actions) : PNJ distincts, ingrédients, montures et équipement ; palette suivant `talk`, `prepare`, `deliver` et `travel` |
| Source texte/clipboard sécurisé | **CONTRAT AJOUTÉ / QT NOT_RUN** | `html.escape`, liens uniquement internes `copy:<index>`, contrôle des bornes au clic, liste d'étiquettes bornée par le chargeur |
| Compatibilité du lecteur existant | **RÉGRESSION ÉVITÉE / QT NOT_RUN** | Le commit initial utilisait `QTextBrowser`, incompatible avec les tests historiques `QPlainTextEdit`. Correction en `07f682c` : `QPlainTextEdit` conservé, bande de liens `QLabel` séparée ; l'ancien bouton `GanymedeSourceCopyTravel` et la progression restent inchangés |
| En-tête partagé à 100 % avec le Guide optimisé | **FAIL / NON LIVRÉ** | `GanymedeSourceReader` est toujours un `QDialog` indépendant. Une modification structurelle exige Graphify exact-SHA et un test d'intégration, non disponibles ici |
| Clics dans le vrai Windows / DOFUS Unity | **NOT_RUN** | Environnement sans PySide6 ni DOFUS Unity, aucune preuve de fonctionnement réel |
| Parité source 2219, quantité de sésame | **NOT_VERIFIED / CONFLIT** | Toujours à comparer directement à la source et au jeu |

### Inventaire de commits de ce lot

- `e99216a` : ajout initial du moteur de liens `copy:<index>`
  dans une vue riche. **IMPROVEMENT REQUIRED** : rompait les
  consommateurs `QPlainTextEdit` préexistants, malgré sa logique de copie.
- `e2b1292` : annotations explicites de copie des noms dans la route
  Otomaï 1, sans inférence fragile depuis les textes.
- `9def252` : trois tests ajoutés sur HTML échappé, liens et 20 libellés ;
  ils restent **NOT_RUN**.
- `5c1416c` : validation du champ facultatif `copy_values`
  au chargement strict (32 valeurs maximum par action, 256 caractères).
- `2a15639` : test de refus des valeurs invalides/volumineuses.
- `07f682c` : correction de compatibilité Qt, conserve le
  `QPlainTextEdit` attendu et déplace les liens dans un
  `QLabel` séparé. **Correction obligatoire de la régression initiale**.
- `7e3d6d4` : quatrième test pour vérifier que la bande de liens
  ne répète pas les consignes du lecteur principal.

**Contrôle statique au SHA `7e3d6d41352ff3b53f43f5117b716782c76176bc` :**
7 étapes, 40 actions, 9/9 coordonnées présentes dans les observations
de la même étape, 20 noms explicitement copiables, 4 tests de copie
définis et un test du contrat de chargeur. Lecture des fichiers de
code/tests en GitHub : aucun écart à ces assertions statiques.
**Ce contrôle n'est PAS l'exécution des cinq tests Python.**

Le workflow « Guides / Focused Windows Proof » associé au SHA courant
est **SKIPPED**, et non PASS. Aucun Graphify exact-SHA utilisable n'a
été identifié parmi les runs de ce commit. Les tests Qt et le passage
réel en jeu sont donc toujours manquants.

**Verdict final du guide #2219 : NON CERTIFIÉ / CHANGES REQUIRED.**
Il reste à aligner l'en-tête commun après un diagnostic Graphify
exact-SHA, exécuter les tests Qt/Windows, résoudre la divergence des
ressources, vérifier les objectifs dans DOFUS Unity et produire les
preuves individuelles. Rester sur Otomaï 1 ; ne pas commencer #2220.
