# Dofus Atlas — Audit intégral du code après optimisation

**État : PREPARED / BLOCKED.** Cette feuille prépare un futur audit : elle **ne prouve pas** que le dépôt a déjà été audité ou corrigé.
**Dépôt canonique :** `r9327/Dof-Atlas`. **Point de départ :** le `main` final réellement certifié, et non un ancien SHA.
**Principe :** auditer 100 % de la surface pertinente, corriger seulement les problèmes prouvés, sans perdre les gains mémoire, performance et Graphify.

## 0. Conditions pour démarrer (bloquantes)

- [ ] Phase 8 RAM + temps + preload achevée et certifiée sur le SHA final : mémoire stabilisée <100 Mo après Home pour chaque module lourd, pic process-tree <=220 Mo, jamais >250 Mo, pas de trim artificiel ni de coût reporté au preload.
- [ ] Travaux Graphify de la PR #123 (ou leur successeur) terminés, certifiés et intégrés ; résultats par communautés, connexions, hubs et cycles conservés.
- [ ] Intégration Context7 de la PR #124 terminée ; **tester réellement Context7 dans l'environnement de l'agent**, car config Git et accès MCP sont deux choses distinctes.
- [ ] Relever le HEAD réel `main`, l'état Git propre, les tests, la CI, les budgets, Doctor, Atlas Integrity FULL/DEEP approprié, et les artefacts Graphify de **ce SHA exact**.
- [ ] Figer une baseline reproductible RAM / CPU / ouverture / retour Home / preload froid et chaud, sur le même runner/environnement pour tout avant-après.

Tant qu'une condition manque : **BLOCKED**. L'audit ne démarre pas silencieusement et aucune optimisation actuelle n'est déclarée défectueuse sans preuve.

## 1. Préflight et ordre obligatoire des preuves

```powershell
git rev-parse HEAD
git status --short
git branch --show-current
git remote get-url origin
py -3.13 -m tools.ai_context status
py -3.13 -m tools.agent_task_profiles --task structural --quality best --structural --json
py -3.13 -m tools.atlas_doctor graph --json
```

Lire et appliquer `AGENTS.md`, `AI_CONTEXT.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, `GRAPHIFY.md` et `PHASE_CERTIFICATION.md`. Employer `tools.work_spec`, Agent et Doctor existants ; ne pas inventer de second moteur d'audit ou de cache de verdicts.

Cartographie initiale exhaustive : code applicatif, scripts, tests, CI, hooks, dépendances, ressources et données, runtime Windows, code natif/FFI, modules optionnels, compatibilité, documentation contractuelle. Séparer explicitement les fichiers générés/ignorés et l'état utilisateur de la base de code source.

## 2. Context7 : documentation vivante, jamais autorité sur le dépôt

Utiliser **Context7** pour consulter la documentation officielle **des versions réellement présentes** dans le projet, d'abord **PySide6 / Qt6 / QtWebEngine / QtCore**, puis les bibliothèques tierces réellement utilisées lorsqu'une question de compatibilité ou de bonnes pratiques le justifie.

Par famille de vérifications :
- API supportées / dépréciées, contrats de version et comportements documentés ;
- ownership `QObject`, parentage, `deleteLater`, destruction après event loop, thread affinity, signal/slot, `QThread`, `QProcess`, timers, connexions ;
- `QWebEngineView`, processus Chromium, libération des vues, surfaces cachées et cache ;
- lecture/écriture sûre de fichiers, concurrence et persistance selon les API réelles.

Consigner pour chaque conclusion : paquet + version, API, URL de la documentation Context7 / éditeur, chemin/ligne du code actuel, preuve runtime/test, verdict (applicable / non applicable / incertain). **Context7 ne peut pas démontrer qu'un morceau de code est mort, qu'un comportement applicatif est correct, ni qu'une optimisation améliore la RAM.** En cas d'indisponibilité MCP, marquer la vérification `NOT RUN` et ne pas la déclarer PASS.

## 3. Audit complet — investigations obligatoires

### A. Architecture et branchements
- Graphify du HEAD exact : imports, appels, dépendances inversées, cycles, communautés minces, symboles isolés, hubs, frontières de domaines, imports paresseux.
- Identifier imports morts, fonctions/classes jamais utilisées, code inatteignable, scripts obsolètes, wrappers de compatibilité, doublons métier, façades superflues, anciennes voies Guide/Quêtes/Succès, traitements concurrents d'une même donnée.
- Pour toute suppression : corréler **Graphify + recherche source + imports dynamiques + reflection + tests + entrées CLI + UI + workflows + FFI + usages Windows**. Zéro arête Graphify ne signifie jamais « code mort » à lui seul.
- Revoir les communautés encore artificiellement fragmentées et celles qui doivent rester isolées ; refuser les fusions purement cosmétiques.
- Examiner dépendances cycliques, effets de bord d'import, import eager caché, singletons, références globales et responsabilités mélangées.

### B. Relecture critique de TOUTES les optimisations passées
- Pour chaque optimisation récente : **intention -> implémentation actuelle -> contrat protégé -> mesures d'origine -> contre-effets -> verdict garder / améliorer / annuler**.
- Rechercher la dette introduite par lazy loading, préchargement, cache, worker temporaire, virtualisation, découpage/sharding JSON, index disque, imports différés, destruction/recréation des écrans.
- Contrôler que les gains RAM ne masquent ni surcharge CPU, ni latence, ni allocations déplacées, ni fuite au fil des cycles, ni perte de fonctionnalité.
- Ne revenir sur une optimisation que si preuve de bug/régression/surcomplexité et alternative mesurée ; **ne pas restaurer du code lourd par confort**.

### C. Ressources, performance, durée de vie
- RAM processus **et arbre de processus**, RSS stabilisé, pics fugitifs, CPU repos et en charge, temps startup / preload / ouverture / détail / navigation / Home ; scénarios froid et chaud séparés.
- Tester première visite, retour, 5 cycles, changement rapide d'onglets, fermeture, exceptions, annulation, échec worker, absence de catalogue, gros volumes.
- Repérer threads/processus/futures/QObjects/WebEngine/timers/signaux laissés vivants, collections globales, caches non bornés, objets Qt possédés par Python, références croisées, widgets invisibles, travail sur thread UI.
- Comparer à baseline du même SHA/environnement ou aux baselines archivées clairement identifiées ; ne jamais hausser les seuils pour faire PASS.

### D. Intégrité et fonctions métier
- Guide Ultime et Lanyel ; Quêtes ; Succès ; Bestiaire ; Craft ; Équipement ; Organizer ; Zaap ; Scan Monde ; macros/hotkeys/réseau : flux normaux et transversaux.
- Vérifier sources de vérité, identité des fiches, progressions, interconnexion Guide/Quêtes/Succès, navigation, persistance après relance et cohérence UI.
- Mutation partagée : `lock -> reload current -> mutate -> atomic write -> publish/invalidate -> unlock` ; race conditions, pertes de données, migrations et corruptions.
- Parcours Windows réels, launcher `DOFUS.bat`, résolution chemins, exceptions silencieuses, journalisation, Npcap/Win32/ctypes, comportements en environnement sans dépendance facultative.
- Relecture qualité : branches impossibles, logique dupliquée, noms trompeurs, files d'attente sans consommation, contournements temporaires restés permanents, tentatives automatiques risquées, test qui ne vérifie pas le comportement réel.

### E. Tests, sécurité et maintenabilité
- Recouper les contrats effectivement couverts, golden flows, erreurs et cas limites, tests qui valident seulement du texte/structure, mocks excessifs, tests supprimés avec vieux modules.
- Audit des dépendances (justification, compatibilité, maintenabilité), CI, hooks, scripts de déploiement, fichiers et logs générés, secrets, privilèges et surfaces d'entrées.
- Aucun affaiblissement des gates, skips, xfails, changement de budget, « silence on exception », suppression de test utile ou nouvelle architecture parallèle.

## 4. Exécution : revue globale, corrections par micro-lots

1. Inventaire de tous les modules + dépendances + usages + coûts + contrats ; aucune exclusion silencieuse.
2. Produire une **matrice de constats** vérifiable : `ID | domaine | chemin:ligne | symptôme | cause prouvée | preuve Graphify/source/runtime/test/Context7 | risque | action | priorité | validation`.
3. Classer `CRITICAL / HIGH / MEDIUM / LOW / NON-ACTIONABLE` ; distinguer **constat prouvé, hypothèse, fausse alerte et limite des outils**.
4. Présenter un plan de lots ordonné par impact, risque et dépendances, sans traiter les 10 000+ nœuds comme des bugs.
5. Corriger **un domaine / une responsabilité / quelques fichiers** par lot : cause racine, petit diff, tests ciblés, impact Graphify avant/après, mémoire/perf si concernés, contrôle de persistance/lifecycle, commit identifiable.
6. Après chaque lot : confirmer que les corrections précédentes tiennent, archiver les mesures et retirer toute régression introduite ; ouvrir un lot indépendant si l'élargissement devient nécessaire.
7. Certification cumulative finale sur **SHA exact**, Atlas Integrity FULL, Doctor pertinent, Public PR CI, AI Context, Graphify, Memory/Preload Benchmark, Phase Certification et DEEP Windows manuel lorsque requis.

## 5. Conditions de sortie / compte rendu

Livrables :
- inventaire **couvert vs non couvert** et justification des limites ;
- tableau complet des anomalies prouvées et faux positifs ;
- audit de chaque optimisation passée : **KEEP / IMPROVE / REVERT** avec preuves et mesures ;
- tableau **avant / après** RAM stable, pic process-tree, startup, preload froid/chaud, ouvertures, navigations, Home, CPU repos et 5 cycles ;
- Graphify avant / après : nœuds, relations, communautés, communautés fines, isolés, inferred edges, cycles, principaux hubs ;
- tests/CI/Doctor/Context7 exécutés et verdicts **PASS / FAIL / NOT RUN** par SHA ;
- PRs de correction rangées par domaine et déploiement sans perte de données ;
- rapport final : `CERTIFIED` uniquement si le workflow de certification complète a réellement passé sur le SHA exact et tous les bloqueurs de l'audit sont fermés.

**Interdictions :** nettoyage cosmétique massif ; suppression sur unique résultat AST ; optimisation qui déplace le coût vers le preload ; refonte totale sans preuve ; régression fonctionnelle justifiée par quelques Mo ; prétendre qu'un audit de toute la base a été effectué sans inventaire et preuves.
