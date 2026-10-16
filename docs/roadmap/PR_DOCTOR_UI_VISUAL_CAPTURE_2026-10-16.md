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
