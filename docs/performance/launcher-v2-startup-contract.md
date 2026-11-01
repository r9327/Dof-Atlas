# Atlas Launcher V2 — contrat de performance et livraison

État : spécification de travail, **pas une implémentation ni une certification**.

## Périmètre
Deux lots de développement séparables : (A) installation, mises à jour, launcher et continuité de fenêtre ; (B) démarrage de l'application, Home, preload et imports. Ne pas réécrire le moteur existant sans preuve. Conserver rollback, données utilisateur, propriétaire de domaine, tests et certification intelligente. Ne pas ajouter de mode hors ligne comme nouvelle fonctionnalité.

### A — Launcher professionnel
- Une seule fenêtre pendant vérification → téléchargement éventuel → installation → préparation → lancement. Ne fermer qu'après Home utilisable ; éviter un second splash/launcher visible.
- Logo, police Lexend si disponible, couleurs et composants cohérents avec le thème Unity Atlas ; repli sûr si police absente ; DPI 100/125/150 %.
- Dossier d'installation sélectionnable avant installation et modifiable proprement ; préserver données et état existants ; vérifier permissions et espace.
- Prérequis : inventorier ceux réellement requis par le packaging Windows, détecter leur présence et n'installer que ce qui manque. Ne pas installer arbitrairement Python/Qt si embarqués.
- Détecter une version identique sans réinstallation ni téléchargement. Manifeste versionné, SHA, cache validé persistant, invalidation sûre ; ne jamais omettre une vérification nécessaire à l'intégrité.
- Différentiel réel : fichiers inchangés réutilisés, pas de double extraction/copie/hash, téléchargement ciblé, vérification avant bascule atomique, parallélisme borné disque/réseau, rollback et récupération de corruption. Conserver les profils et la progression.
- Garder une UI minimaliste (logo, titre, barre de progression, état, réglage du dossier), sans menus superflus.

### B — Démarrage et preload
- Instrumenter horodatages : clic launcher, vérification, téléchargement, décompression, copie, validation, spawn process, imports Python/PySide6, création QApplication, Home visible, Home interactive, preload post-Home.
- Auditer imports coûteux, accès disque, JSON, images, création widgets, initialisations et doublons. Vérifier le mode de packaging Windows et le coût de l'antivirus avant de conclure.
- Initialiser seulement le chemin critique de Home ; Guides, Quêtes, Succès et autres modules lourds en lazy loading contrôlé. Préchargement adaptatif uniquement s'il ne dégrade ni Home interactive ni la RAM ; annulation et priorités.
- Pas de changement d'architecture non motivé ; corriger les causes vérifiées et préserver la navigation, les états et les données.

## Mesures et portes de validation
- Scénarios Windows réels : première installation, lancement sans changement, patch 1–3 fichiers, grosse mise à jour, reprise d'échec, corruption, migration du dossier, antivirus, DPI 100/125/150.
- Bench séparés : Home visible **et** Home utilisable ; temps par phase, octets téléchargés, octets copiés, nombre de fichiers hachés, CPU, I/O, RAM process-tree et RAM stabilisée après retour Home.
- Cibles initiales (à recalibrer sur machine de référence) : vérification locale <1 s ; lancement sans mise à jour 3–5 s ; Home <3 s après spawn ; patch léger <5 s hors réseau ; aucun octet inchangé téléchargé ; RAM Home <100 Mo, pic process-tree ≤250 Mo.
- Répétitions, médiane et dispersion ; comparer au baseline sur même machine et même cache. Détecter régression >5 % seulement si statistiquement significative, sans masquer les checks de sécurité.
- Tests unitaires ciblés + intégration launcher/install + build Windows complet exact SHA + Atlas Delivery Guard, Phase Certification, Public PR / Safe Validation, Certification Policy / Merge Gate. Audit de chaque commit puis audit global.
- Rapports reproductibles dans la PR avec mesures avant/après et logs anonymisés ; maintenir .ai/context_index.json et rapport HEAD si les règles du dépôt l'exigent.
- Aucun asset DOFUS extrait redistribué. Validation humaine Windows/launcher/image avant Release stable. Synchronisation DEV→APP uniquement après certification ; ne jamais fermer la PR APP permanente #4.

## Ordre de travail
1. Capturer baseline et reproduire les lenteurs ; identifier causes racines.
2. Corriger le chemin critique et les doubles traitements mesurés, avec tests.
3. Unifier la fenêtre et l'UI sans régression du mécanisme de mise à jour.
4. Mesurer les gains, certifier SHA exact, puis organiser la validation Windows et la livraison APP.

**Ce document n'affirme aucun gain de performance ni correction livrée.**


## Contrat d'architecture et décisions obligatoires
- Cartographier le flux réel launcher → updater → installer → main → Home ; identifier les processus, fenêtres, chemins et responsables de chaque phase. Ne pas ajouter de processus ou de fenêtre sans justification mesurée.
- Séparer **vérification rapide** (version/manifestes signés ou authentifiés, état local) et **vérification d'intégrité approfondie** (après téléchargement, corruption suspectée, réparation ou changement de manifeste). Le cache ne doit jamais contourner la validation d'un contenu nouvellement installé.
- Définir le format et le versionnement du manifeste, les chemins canoniques, la stratégie de migration, la compatibilité anciens lanceurs/manifeste, et le comportement si manifeste absent, périmé ou malformé.
- Modèle d'installation explicite : staging sur le même volume lorsque nécessaire, écriture temporaire, fsync si pertinent, validation, commutation atomique si supportée, journal de transaction, nettoyage différé et rollback idempotent. Ne pas présumer qu'un remplacement de répertoire est atomique sur tous les chemins Windows.
- Définir la propriété et la durée de vie des fichiers : binaires immuables, cache, logs, données utilisateur, sauvegardes. Ne jamais effacer des données utilisateur lors d'un cleanup, rollback ou déplacement.
- Gérer antivirus/verrouillage de fichiers, permissions limitées, chemins Unicode/espaces/longs, disque plein, accès refusé, archive corrompue, réseau coupé, processus Atlas déjà lancé et interruption brutale. Prévoir messages d'erreur exploitables et reprise sûre.
- Prévoir le coût du protocole de distribution : une archive monolithique ne permet pas un vrai patch fichier par fichier. Vérifier les artefacts Release et adapter manifestes/packaging **avant** de promettre des téléchargements différentiels.
- Limiter l'usage CPU, I/O et parallélisme ; éviter que la vérification SHA ou la préparation des modules monopolise le disque. Pas de tâches de fond inutiles après Home.
- Définir un signal robuste de **Home utilisable** (événement applicatif explicite + boucle d'événements réactive) et un handoff launcher → app sans double fenêtre, sans fermeture prématurée, avec gestion de crash/timeout.
- Les prérequis Windows doivent être listés avec version, mode de détection, provenance, intégrité, privilèges et condition d'installation ; ne jamais installer silencieusement des composants non nécessaires.
- La sélection du dossier doit fonctionner en installation neuve et migration ; la migration doit préserver état, rollback et raccourcis, avec tests sur chemins non standards.
- Les couleurs/polices/logo du launcher doivent provenir d'un contrat de design partageable avec l'app ; tester rendu et repli sur machine Windows propre sans assets optionnels.

## Protocole de benchmark reproductible
- Documenter CPU, disque SSD/HDD, Windows, antivirus, mode d'alimentation, build Python/packaging, version Atlas, source réseau et état du cache ; comparer **même machine, mêmes conditions**.
- Distinguer cold/warm start, cache chaud/froid, première installation, patch minuscule, patch volumineux, aucune mise à jour, cache invalidé, démarrage avec et sans préchargement.
- Produire des traces monotoniques structurées par phase avec identifiant de session, SHA de build, durée, taille, compteurs I/O et mémoire ; aucun secret, chemin privé ou donnée personnelle dans les logs publiés.
- Décomposer le temps : latence distante, transfert, décompression, hash, copie, switch, démarrage process, imports, construction UI, premier paint, Home interactive. Donner p50/p95 et variabilité sur répétitions ; conserver raw results en artefact.
- Budgets par phase : fixer après baseline, puis suivre écarts absolus et relatifs. Une régression >5 % déclenche une enquête si signal robuste ; ne pas déclarer PASS sur bruit de mesure ou sans baseline comparable.
- Tester l'absence de re-download et de réinstallation **en comptant** les requêtes, octets réseau, fichiers écrits et hashes ; un simple message « déjà à jour » ne suffit pas.
- Ajouter un benchmark de charge du preload et de retour Home après navigation, avec surveillance du pic mémoire process-tree et stabilisation ; interdire le report caché d'un blocage de l'UI après premier paint.
- Séparer tests CI Linux rapides, tests Windows automatisables et validation humaine Windows propre ; aucune preuve CI non exécutée ne doit être présentée comme un PASS.

## Matrice d'acceptation et couverture
| Cas | Preuve minimale |
| --- | --- |
| Même version | 0 fichier d'application réinstallé, 0 octet d'artefact téléchargé, Home interactive mesurée |
| Patch 1–3 fichiers | Seuls contenus changés transférés et remplacés, intégrité et rollback testés |
| Mise à jour volumineuse | Installation sûre, progressions réelles et métriques par phase |
| Installation vierge | Dossier choisi, prérequis conditionnels, raccourcis et lancement fonctionnels |
| Coupure ou crash pendant installation | Ancienne version saine conservée ou restauration vérifiée |
| Corruption / cache obsolète | Invalidation ciblée, réparation, aucune donnée utilisateur perdue |
| Dossier déplacé | Paramètres, raccourcis, rollback et données préservés |
| Atlas déjà ouvert | Aucun écrasement de binaires actifs, comportement explicite |
| DPI et thème | Fenêtre unique, 100/125/150 %, police et palette cohérentes |
| Home / preload | Home réellement utilisable, pas de blocage, mémoire sous budget |
| Publication | SHA exact, tests requis, audit commit par commit, validation Windows humaine |

## Découpage des commits et critères de sortie
1. **Instrumentation seulement** : tests de mesure et baseline sans optimisation ; audit du commit.
2. **Différentiel et transactions** : changements limités à la distribution ; tests de reprise, cache et intégrité ; audit du commit.
3. **Launcher et installation** : fenêtre unique, design et emplacement ; tests Windows/DPI ; audit du commit.
4. **Startup et preload** : correction des goulots mesurés ; tests navigation, réactivité et RAM ; audit du commit.
5. **Certification** : comparaison avant/après par scénario, rapport de risques résiduels et audit transversal ; pas de fusion sans preuves.

Les travaux peuvent être scindés en PR dépendantes si le diff devient difficile à auditer, tout en conservant la traçabilité vers #285. **Definition of Done** : correctifs réels + preuves mesurées + tests + CI exacte + validation Windows ; le document seul ne satisfait pas le contrat.


## Optimisations transversales supplémentaires — temps réel double-clic → Home
- Mesurer **le temps bout-en-bout** du double-clic jusqu'à Home réellement utilisable, avec corrélation des traces entre launcher et processus Atlas. La somme des sous-étapes ne remplace pas la mesure utilisateur.
- Auditer les contrôles et initialisations en double entre launcher, updater et app : version, intégrité, configuration, images, index, ressources, dépendances et créations de processus. Supprimer seulement les doublons prouvés, sans retirer les vérifications nécessaires.
- Comparer le packaging Windows actuel et les alternatives pertinentes (one-file, one-folder ou équivalent) sur démarrage froid/chaud, extraction, occupation disque, antivirus, taille de distribution et coût des updates ; décider sur données, sans changement automatique de packaging.
- Cartographier chaque octet entre artefact GitHub et fichier final : téléchargement, staging, extraction, décompression, copie, hash, déplacement. Réduire les écritures et copies intermédiaires sans compromettre la transaction ni l'intégrité.
- Étudier un cache versionné pour index et données de démarrage : clé dépendant du schéma et des empreintes de sources, invalidation ciblée, migration, limite de taille, nettoyage sûr et test de corruption ; aucune sérialisation fragile d'objets Qt.
- Ajouter une séquence de plusieurs lancements consécutifs : installation neuve → premier démarrage → deuxième et troisième démarrages → patch léger → redémarrage → aucun changement. Mesurer cold/warm et cache valide/invalide.
- Vérifier le temps de création et de destruction des processus, les attentes bloquantes, les timers, les sous-processus zombies et le nombre de fenêtres visibles ; éviter une boucle de contrôle/polling qui ajoute une latence fixe.
- Prioriser le **gain net mesuré** : conserver les optimisations uniquement si elles améliorent le parcours global sans régression fonctionnelle, mémoire, intégrité ou sécurité.
