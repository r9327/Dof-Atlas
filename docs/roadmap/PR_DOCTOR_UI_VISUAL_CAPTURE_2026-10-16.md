# Doctor Atlas — capture et diagnostic UI réel (outil réutilisable)

**Statut : spécification / à implémenter.** Cette PR ne doit pas toucher à la PR #202 (nouveautés non définies). C'est un outil de développement transversal, distinct des corrections du runtime des guides (#201).

## Problème réel confirmé dans le code actuel

`tools/atlas_doctor.py` expose `capture-ui` pour `qt`, `equipment`, `encyclopedia`, `webengine`. La commande exécute `run_traced_module` et écrit `.ai/runtime/atlas_doctor/traces/atlas_ui_<scenario>.json`.

Le scénario `encyclopedia` actuel (`tools/atlas_doctor_lib/encyclopedia_deferred_smoke.py`) teste une **interface différée légère**, sans catalogue réel ni afficheur `SharedGuideManualView`. Les tests `tests/test_atlas_doctor_capture_ui.py` vérifient cette API limitée.

**Ce qui manque :** une **capture PNG réellement rendue** du widget voulu, un **arbre de widgets Qt** avec géométries et états, et la possibilité de contrôler la non-duplication lors des changements de pages et des rafraîchissements. `doctor_graph_ui.py` affiche un graphe d'architecture, **pas l'interface réelle de l'application**.

## V1 — fonctionnalités demandées

1. **Réutiliser Doctor** : étendre son CLI et ses mécanismes opt-in, sans ajouter d'application ni de moteur de rendu alternatif. Conserver `capture-ui qt|equipment|encyclopedia|webengine` et leurs comportements existants ; enrichir avec un scénario explicitement nommé (ex. `guides`) et des options bornées. L'interface CLI finale doit être cohérente avec les contrats de Doctor.
2. **Sélection guidée et reproductible** : choisir un guide connu et une étape canonique/page valide, ex. Guide Succès (1, 3) ou Lanyel (1, 8) ; utiliser le service et le **vrai** `SharedGuideManualView`, avec un profil de progression factice **temporaire**, jamais les données utilisateur. Interdire les modules arbitraires et les données privées exportées.
3. **Screenshots authentiques** : créer PNG avec `QWidget.grab()` ou rendu Qt explicite, après stabilisation des événements et chargement du contenu sélectionné. Capturer au moins vue entière, contenu déroulant contrôlé, 2 résolutions, et états déterministes. Ne pas générer un dessin inventé ou réutiliser un ancien PNG.
4. **Squelette UI exploitable** : exporter une arborescence `JSON` des QWidgets/layouts (classe, `objectName`, parent, rang, visibles/masqués, rectangle/position, texte court si non sensible, état checkable/enabled, comptages), et option de surimpression des **limites de blocs** sur un PNG/HTML d'inspection, associées par ID au JSON. Le JSON n'est pas un remplacement de la capture écran.
5. **Contrôles objectifs** : détecter plusieurs `GuideManualSheet` visibles, section principale dupliquée, enfants détachés ou géométrie anormale, traces de lignes de l'étape précédente, duplication de boutons/cases, débordements/horizontal scroll et comportements différents lors de `render → next → previous → refresh × N → autre guide → retour`. Un doublon de chaîne à deux étapes pertinentes n'est pas automatiquement un défaut : associer des clés de ligne/provenance.
6. **Diagnostic ciblé** : relier rapport à l'ID du guide, stage/page, scénario, états des widgets, événements Qt et sources (fichiers/méthodes) **quand réellement observés** ; signaler `REVIEW` si la causalité ne peut pas être établie. Graphify peut guider les investigations mais ne doit pas être pris pour une preuve de rendu.
7. **Artefacts avec traçabilité** : écriture en répertoire runtime ignoré par Git (`.ai/runtime/atlas_doctor/ui/` ou équivalent conforme), avec PNG, arbre JSON, rapport JSON et manifeste SHA exact, état clean/dirty, version Python/PySide6/Qt, plateforme, DPI, taille, guide et étape, mode `offscreen` ou `desktop`, horodatage, erreurs et durée.
8. **Sécurité + stabilité** : opt-in seulement, traitement Qt dans le bon thread, pas de hooks permanents, pas de chargement réseau involontaire, suppression/désactivation des widgets après usage, pas de fuite mémoire, nombre de pages/temps/artefacts bornés, pas de secrets dans les captures, pas de profil utilisateur modifié. Réutiliser l'infrastructure Doctor plutôt que créer un framework neuf.

## Portée / réalisme

- La capture offscreen avec Qt réelle peut prouver l'arbre et le rendu de widgets, mais **ne certifie pas à elle seule l'application Windows distribuée ni QtWebEngine** ; pour cela, prévoir un contrôle distinct sur EXE installé.
- Une comparaison pixel brute cross-OS peut être trompeuse (polices, DPI). Priorité aux **assertions structurelles/états** ; diff PNG optionnel sous environnement de référence et tolérance documentée.
- La V1 couvre prioritairement l'interface partagée des guides ; concevoir le harnais pour être extensible à Quêtes, Succès, Équipement, Organizer plus tard, sans développer ces scénarios d'avance.
- Ne pas lancer une FULL CI ou des benchmarks lourds à chaque capture ; tests ciblés adaptatifs conformes à la politique existante.
- Ne pas inclure la réparation des bugs observés : **c'est la PR #201**. Elle doit pouvoir être corrigée sans dépendance dure à cet outil.

## Plan d'intégration

1. Confirmer `HEAD`, règles `AGENTS.md`, `DEVELOPMENT_GUARDRAILS.md`, AI Context et Graphify exact-SHA pour les changements structurels.
2. Étendre `tools/atlas_doctor.py` et placer le scénario/harnas borné dans `tools/atlas_doctor_lib/` en réutilisant les services Qt/test existants. Vérifier Qt `grab()`, `QApplication.processEvents`, nettoyage `deleteLater` et prérequis platform plugin (Windows/offscreen).
3. Mettre à jour `tests/test_atlas_doctor_capture_ui.py` (allowlist/API compat) ; ajouter des tests Qt réels qui contrôlent la création d'artefacts, l'arbre UI, la structure de page, la persistance isolée, les retours/refresh, la protection des chemins et données.
4. Exécuter au minimum les scénarios Guide Succès pages 1/3 et Lanyel pages 1/8 et publier un exemple de paquet d'artefacts produits **effectivement** par le code du SHA candidat ; si blocage d'environnement, déclarer `BLOCKED`, sans fabriquer de captures.
5. Certification ciblée Doctor/Graphify/CI au SHA, puis revue. L'outil n'est pas certifié tant que les sorties PNG+JSON ne sont pas réelles et les scénarios ne passent pas.

## Conditions de sortie

- [ ] Commande Doctor opt-in qui sauvegarde PNG réel + JSON d'arbre du même rendu.
- [ ] Chemin d'artefacts relié au commit / identité de scène et stable sur Windows.
- [ ] Scénarios des deux guides reproduisibles sur pages courtes/longues et retours.
- [ ] Détection de feuille en double, UI détachée et débordement vérifiée sur cas positifs/négatifs.
- [ ] Zéro modification de progression utilisateur et aucun hook permanent.
- [ ] Compatibilité confirmée des anciens scénarios `capture-ui`.
- [ ] CI ciblée verte + limites des vérifications clairement déclarées.

**État du commit initial : uniquement ce cahier des charges, pas encore le code de l'outil.**

## Rectificatif prioritaire — VALIDATION FONCTIONNELLE, pas seulement capture

**Ce chapitre prévaut sur toute interprétation « PNG + arbre Qt = UI validée » dans le reste du document.** La mission est un **Doctor UI Validator** : exécuter des interactions réelles et comparer leurs résultats à des attentes vérifiables. Capture PNG/JSON uniquement comme preuves, pas comme critère de PASS.

### Architecture minimale ciblée

- Préserver `capture-ui` et ses contrats existants. Ajouter une entrée explicitement distincte de validation (proposition : `doctor verify-ui guides`, sous-commande exacte à fixer en conformité avec le CLI). Le module de scénario et les assertions doivent être réutilisables ; éviter un nouveau framework/runner général s'il existe déjà un exécuteur de scénarios Doctor.
- Utiliser **les vrais** `SharedGuideManualView`, `SharedGuideManualCard`, routeur/services existants et `QTest`/événements Qt. Pas de faux bouton sans lien avec la production. Fixtures injectées uniquement pour le stockage/profil, dans un répertoire temporaire. Certains contrôles de données peuvent utiliser un service stub déterministe en complément : indiquer précisément quelles preuves reposent sur données réelles vs fixture.
- En V1, inclure des scénarios connus des deux guides (succès page 1 / page ressources, Lanyel page 1 / transition vers Fécaline) et un **socle générique** sur les widgets Qt réels ; hors périmètre d'implémentation actuelle : toutes les autres vues de l'application.

### Assertions attendues, avec actions puis état vérifié

1. **Ouverture et identité** : ouvrir le guide via l'entrée réellement utilisée par l'app ; vérifier bon guide, bon `stage_id` canonique, bon titre, bonnes sections/row IDs. Le texte affiché doit être attribuable à la carte active ; aucun texte d'ancienne page sauf s'il est aussi attendu sur la nouvelle.
2. **Navigation effective** : cliquer vraiment Précédent/Suivant/Guide ; contrôler la page obtenue et sa progression, enchaîner des aller-retours rapides, changement de guide puis retour, Home puis réouverture, pages longues et courtes. Faire les assertions **après livraison des événements Qt**, et après traitement des destructions différées.
3. **Arbre et cycle de vie Qt** : compter les `GuideManualSheet` et sections réellement montées/visibles, leurs parents, ordre des layouts, objets en attente de destruction, signaux/callbacks répétitifs ; montrer que les anciens widgets ne restent pas affichés ou connectés. `rendered_card_count=1` seul est insuffisant.
4. **Action réelle des contrôles** : déclencher boutons et cases avec QTest ; vérifier le bon identifiant/cible, l'état du service et l'état visuel après action, puis réouverture. Vérifier verrouillage/déverrouillage, navigation autorisée/interdite selon le contrat existant, labels/icônes/accessibilityName cohérents.
5. **Progression / isolation** : valider manuellement une page et un combat sur un profil temporaire, naviguer, changer de personnage fictif, recharger les services ; vérifier persistance et absence de contamination entre personnages. Tester explicitement que les validations automatiques n'acceptent pas d'étape sans preuve ; ne jamais simuler comme vérifié un signal DOFUS réel indisponible.
6. **Interactions spécifiques** : clics sur liens de quête/PNJ/objet, copie /travel/coordonnées quand la fonctionnalité existe, noms et quantités de combats ; vérifier callbacks/arguments ou effets observables avec espion isolé, sans déclencher d'action externe ou macro réelle.
7. **Géométrie et accessibilité** : sous deux dimensions, vérifier widget contenu dans le viewport, absence de scroll horizontal involontaire, aucun chevauchement de composants interactifs, contrôle toujours accessible après scroll, textes importants non masqués ; contrôle visuel/PNG *en complément* pour les défauts impossibles à conclure par la géométrie seule.
8. **Robustesse** : N répétitions bornées de render/navigation/resize/refresh et ouverture/fermeture, vérifier que le nombre de widgets vivants, connexions et références utiles revient à la normale ; surveiller exceptions Qt, timeout, latence grossière et destruction. Pas de bench RAM/FULL systématique.
9. **Provenance et contenu** : distinguer doublon de QWidget, doublon de ligne et consigne répétée légitimement à deux moments distincts ; signaler comme `REVIEW` une anomalie sémantique sans oracle fiable, jamais supprimer des données sur simple similitude de texte.

### Véritable oracle / statuts — aucun faux vert

- Chaque contrôle doit contenir : `scenario_id`, `action`, `expected`, `observed`, `status`, `evidence_path` et identifiant de guide/carte. Ne pas confondre `test_executed` avec `test_passed`.
- Statuts individuels : `PASS` (assertion exécutée et vérifiée), `FAIL` (comportement observé contraire au contrat), `BLOCKED` (impossible à exécuter), `REVIEW` (preuve insuffisante, notamment jugement sémantique), `NOT_COVERED` (périmètre non testé).
- Verdict global `PASS` **uniquement** lorsque toutes les assertions obligatoires applicables sont réellement exécutées, que zéro `FAIL/BLOCKED/REVIEW` obligatoire subsiste et que le rapport porte sur le SHA contrôlé. Sinon `FAIL`, `BLOCKED` ou `REVIEW`, avec couverture exacte (nombre passé/échoué/non couvert). Une capture réussie ne peut jamais émettre `PASS` de validation.
- Différencier **Qt offscreen test** du **binaire Windows installé avec parcours utilisateur réel** : fournir deux niveaux de preuve et une limite explicite. Le PASS offscreen ne prétend pas prouver l'affichage ni l'intégration EXE Windows.
- Artefacts : `verdict.json` lisible par machine, journal chronologique actions/assertions avec IDs, arbre Qt avant/après, traces/exceptions, captures optionnelles, manifeste exact-SHA + environnement. Un rapport doit être suffisant pour retrouver le widget, la page et la première assertion en échec.

### Tests du validateur lui-même (preuve qu'il détecte un bug)

- **Cas sains** : pages courtes/longues réelles, transitions, clics/persistance, retour à l'état attendu.
- **Cas volontairement cassés** (fixtures ou injection isolée hors production) : seconde feuille visible, ancienne ligne rémanente, mauvais lien/checkbox → objectif, bouton qui ne change pas la page, non-persistance, débordement et statut de verrouillage incohérent. Chacun doit conduire à `FAIL` avec raison ciblée ; pas de `PASS` si une assertion obligatoire ne tourne pas.
- **Cas empêchés** : PySide6 indisponible, service impossible à charger, timeout, environnement Qt non compatible, artefact manquant → `BLOCKED` ou `REVIEW` ; jamais `PASS`.
- **Compatibilité** : conserver tous les anciens tests Doctor (`capture-ui`, runtime-trace, Qt scenarios), pas de migration destructive.
- **Certification** : CI ciblée au SHA, et validation Windows installée séparée si disponible. **Aucune auto-fusion basée sur une image.**

### Articulation des PR

- **#203** : construire le validateur réutilisable et prouver que ses contrôles détectent des défauts, *sans corriger le guide lui-même*.
- **#201** : corriger les guides, utiliser les tests Qt comportementaux dès maintenant ; exploiter le validateur #203 quand disponible, mais ne pas rendre #201 artificiellement bloquée par une PR externe.
- **#202** : nouveautés non spécifiées, inchangée.

**État actuel : exigences documentées, pas encore d'implémentation de vérification fonctionnelle.**
