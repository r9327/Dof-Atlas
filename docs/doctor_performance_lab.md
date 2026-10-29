# Atlas Doctor — Performance Lab approfondi

## Un seul pilote, aucune duplication de certification

**Entrée publique unique : `python -m tools.atlas_doctor perf`.**

Le mode standard conserve le benchmark Doctor existant. Le mode `--deep`
confie à Doctor la campagne exhaustive des guides ; il **ne relance pas**
simultanément le benchmark standard et **ne remplace pas** les certifications
Phase 8 RAM et Preload, qui restent les références de budget et comparabilité.

Le moteur `tools/benchmark_atlas_exhaustive.py` est un module interne
uniquement piloté par `tools.atlas_doctor_lib.exhaustive_performance`.
Il réutilise les échantillonneurs RAM/process-tree et les fonctions de
navigation Qt du benchmark Phase 8 : pas de deuxième implémentation de
collecte RSS, de réveil des preloads ou de lancement Qt.

## Commandes Doctor

```powershell
python -m tools.atlas_doctor perf
python -m tools.atlas_doctor perf --files-only
python -m tools.atlas_doctor perf --deep --cycles 2 --checkpoints 3
python -m tools.atlas_doctor perf --deep --cycles 5 --checkpoints 3 --diagnose-slow-ms 750
python -m tools.atlas_doctor perf --deep --cycles 2 --diagnose-guide guide_complet
python -m tools.atlas_doctor perf --deep --cycles 2 --profile-startup --diagnose-guide dofus_sylvestre
python -m tools.atlas_doctor perf --deep --cycles 2 --profile-startup --profile-imports
```

Le CI lance exactement `doctor perf --deep` dans un job séparé et ciblé
quand les fichiers du laboratoire changent, ou manuellement. L'exhaustif
ne devient jamais une nouvelle FULL automatique à chaque petite PR.

## Preuves générées sous artifacts/atlas_exhaustive/

- `guides.json` : mesures par guide, ouverture Home, P95/P99 de la boucle
  événementielle Qt, temps méthodes inclusif/exclusif, CPU/processus, RAM,
  I/O logiques, piles d'appels durant les blocages et checkpoints de parcours.
- `guides.csv` : synthèse triable.
- `guides.html` : rapport de lecture, sans ressources externes.
- `guides.doctor.json` : **verdict de Doctor**, vérification SHA exact,
  couverture du manifeste, statut et raisons de blocage.

Les 95 références de catalogue Ganymède sont distinguées des guides Atlas
réellement exécutables. Aucune référence non jouable n'est présentée comme
un parcours certifié. Un parcours échoué ou incomplet vaut `BLOCKED`.

L'option `--profile-startup` capture le CPU du premier chargement Qt, du preload et du catalogue ; elle **n'inclut pas les imports Python antérieurs à l'entrée du moteur** et ne doit pas servir de référence de temps non instrumenté.

L'option `--profile-imports` active le profilage CPython `-X importtime` dès l'entrée de l'interpréteur ; elle conserve `guides.imports.txt` et le TOP des imports dans le verdict Doctor. Ces durées sont instrumentées et non comparables aux temps standards.

Les mesures `cProfile`/`tracemalloc` sont volontairement plus intrusives ;
Doctor les déclenche sur les guides lents, en passage ultérieur, et leur
durée est **exclue des percentiles normaux**.

## Outils open source additionnels

- `py-spy` : profiler Python externe, option `--py-spy` via Doctor
  (installation séparée). Trace Speedscope, charge additionnelle à déclarer.
- `VizTracer` : trace Python/changement de threads pour reproduction ciblée,
  étude d'intégration optionnelle ; pas installé dans le runtime Atlas.
- `Scalene` 2.x : analyse CPU et allocations Python y compris sur Windows,
  option à étudier, ne pas imposer à toutes les PR.
- `Windows Performance Recorder/Analyzer` : traces Windows ETW natives,
  indispensable pour diagnostiquer les blocages GPU/Win32 et le vrai EXE.
- `Memray` : Linux/macOS seulement, ne doit pas être imposé sur Windows.

Aucun de ces outils optionnels n'est nécessaire à la certification actuelle.
Ne pas ajouter de dépendances d'instrumentation à l'application distribuée.

## Limites et suite nécessaire

La boucle Qt mesurée dans GitHub Actions tourne **offscreen**, et n'est pas
un indicateur FPS d'un bureau Windows. `tracemalloc` ne mesure pas les
allocations natives Qt, et les stacks échantillonnées suggèrent une cause
sans constituer une preuve de causalité. Les profils doivent être comparés
sur un même matériel, après plusieurs répétitions.

Pour enquêter sur le **démarrage > 1 min** vécu par l'utilisateur, ajouter
une campagne Windows desktop sur EXE/launcher : mise à jour, cache,
première image et première navigation réellement utilisable. Cette preuve
reste distincte de la mesure Qt offscreen.

Le lab reste volontairement un **outil de diagnostic**, pas un mécanisme
qui modifie les budgets existants ou déclare artificiellement les lenteurs
acceptables. Toute optimisation doit être associée au commit avant/après,
aux traces, et à une vérification de non-régression.

## Suite complète automatisée (volontaire, pas de nouvelle FULL)

Le workflow `.github/workflows/atlas-doctor-complete-benchmark.yml` orchestre **une seule fois**
les moteurs existants et leurs propres preuves, sans recréer de second benchmark :

- Doctor `perf --app` : 20 entrées × 10 cycles, preload Quêtes/Encyclopédie/Craft,
  CPU/RSS/process-tree/latences Qt, retour Home et 60 secondes de repos mesuré.
- Doctor `perf --app --one-core` : scénario séparé avec affinité CPU Windows
  **appliquée puis vérifiée**, 3 cycles et 60 secondes de repos. **Ce n'est
  pas un vrai ordinateur bas de gamme** et ne limite ni RAM ni disque.
- Doctor `perf --app --parallel-instances 8 --cycles 1` : huit
  **processus Atlas distincts** lancés en parallèle, profils APPDATA et TEMP
  isolés, préchargements et 20 routes contrôlés pour chaque processus.
  Preuves et logs par PID ; échec bloquant si un seul processus ou parcours
  manque. **Ce ne sont pas huit comptes DOFUS.**
- Doctor `perf --deep` : chaque guide Atlas exécutable, 2 passages, gardien
  de couverture du manifeste et attribution des coûts. Les sources Ganymède
  non exécutables restent distinctes.
- Phase 8 mémoire et préchargement : workflows canoniques réutilisés,
  budgets RAM historiques inchangés, comparaison cold/warm.
- Tests de contrats métiers internes représentatifs : navigation détaillée,
  identité, progression, succès, équipement, Craft, cartes, launcher,
  rollback et preload. Ils ne remplacent pas un essai humain de l'EXE.

La suite produit `artifacts/doctor_complete/suite.json` avec le SHA exact et
un état par étape. Une étape `skipped`, `cancelled` ou `failure` est
**bloquante** ; aucune réussite de navigation ne remplace une réussite de
preload ou de budget mémoire. La suite complète est opt-in et n'allonge pas
les certifications des PR ordinaires. Les campagnes de banc peuvent être
lancées sur la PR de développement, puis sur `main` via workflow_dispatch.

Limites bloquantes pour une vraie certification exhaustive de release :
8 clients **DOFUS** simultanés (distincts de huit personnages Atlas),
matériel faible réel, FPS Windows/DPI/GPU, véritable EXE/launcher et scénario
d'installation/MAJ/rollback réseau bout en bout. GitHub Hosted Windows en
Qt `offscreen` ne peut pas attester ces essais. Ils restent **NOT RUN**
dans le rapport, et nécessitent une station de test Windows graphique avec
un opérateur et des données de validation isolées. Les 5 placeholders du
menu ne deviennent pas des fonctionnalités certifiées.

## Doctor — cerveau central et attribution en pourcentage

La commande canonique `python -m tools.atlas_doctor evidence-hub --sha <SHA> --jobs-json artifacts/doctor_complete/jobs.json --source app_navigation=artifacts/quick_app/report.json`
réconcilie des preuves indépendantes de Doctor, UI, Graphify, CI, Memory,
Preload et Distribution **uniquement sur le même SHA complet**. Doctor ne
refait pas ces benchmarks. Chaque spécialiste conserve son rapport d'origine.

La campagne complète GitHub orchestre, en mode explicite et **sans publier** :
- 20 écrans Atlas × 10 cycles, préchargements Quêtes/Encyclopédie/Craft et RAM
  après retour Home, plus 60 s d'observation au repos ;
- 8 processus Atlas distincts avec stores temporaires isolés et affinité CPU
  à un cœur dans un autre scénario ; 26 guides × 2 passages ;
- les cinq scénarios Doctor UI réels (Qt offscreen, images capturées,
  contrôles de géométrie, interaction et exceptions) ;
- le **vrai paquet Windows candidat** : compilation AtlasApp.exe, launcher,
  installateur et installation automatique sur le runner, démarrage du binaire
  gelé, prérequis, données Craft, quêtes, guides/succès et SHA-256 de chaque
  fichier dans le ZIP et manifeste ;
- les contrats de mise à jour et de rollback, les tests métiers, la carte
  Graphify complète et la recherche AST de doublons du code par Doctor.

Le `doctor_evidence.json` contient l'inventaire de couverture des outils :
`PASS / FAIL / STALE / UNVERIFIED / NOT_RUN`. Un job absent, sauté ou échoué
ne peut pas devenir PASS. Les anomalies de versions, la provenance, les
suspects de travail répété et les sources d'origine sont conservés dans
`audit.html` et `suite.json`. Doctor `audit` et `report` joignent le
dernier dossier de preuves **seulement si le SHA correspond** ; sinon ils
signalent une preuve périmée ou absente.

**Comprendre les pourcentages :**

- Temps : durée chronométrée d'un constructeur, du preload, de l'ouverture
  de chaque écran et du retour Home divisée par la durée totale de la sonde.
  La partie non instrumentée est publiée, jamais masquée.
- CPU : différence de temps CPU du **processus Atlas** dans les mêmes phases,
  divisée par le temps CPU de ce processus durant la sonde. Les workers enfants
  ne sont pas attribuables de cette manière ; la proportion n'est pas un
  `% d'un cœur` ni une mesure de CPU physique par fonctionnalité.
- CI : pour chaque job GitHub, secondes réelles par étape divisées par la
  somme des étapes mesurées de **ce même job**. Les étapes de jobs parallèles
  ne sont pas additionnées. Utile pour distinguer dépendances, préparation
  des données, compilation, installation, tests et vérifications.
- RAM : le pic total du process-tree et sa phase, les snapshots Home,
  les deltas et les allocations Python ciblées sont affichés, **mais aucun
  faux pourcentage RAM par module** n'est calculé : les objets Qt, pages
  partagées, workers enfants et libérations rendent ces pics non additifs.
- « Doublons » : les coûts d'ouverture répétés à chaud signalent un
  **suspect**, pas une preuve de double exécution du code. Seules les
  conclusions de l'analyse AST Doctor/Graphify et des profils de fonctions
  ciblés peuvent étayer une suppression de source.

**Limites sans preuve automatique :** vrais huit clients DOFUS (distincts de
huit instances Atlas), rendu GPU/FPS sur poste Windows interactif, machine
bas de gamme physique, téléchargement et rollback d'une release publique
avec réseau réel, chaque modification métier de chaque panneau, placeholders
non développés. Ces éléments restent explicitement **NOT RUN**. Aucune
certification finale ne doit être accordée sur le seul fait qu'un bouton ou
une page s'ouvre.


## Rapport d'optimisation Doctor — issu des mesures du benchmark

Le workflow Doctor complet produit maintenant deux preuves supplémentaires,
**\`optimization.json\`** (machine) et **\`optimization.md\`**
(rapport lisible), dans les artefacts du **même SHA**. Elles réutilisent les
mesures déjà collectées, sans nouveau parcours Qt, ni deuxième benchmark.

Commande canonique, après le benchmark :

\`\`\`powershell
python -m tools.atlas_doctor optimization-report --sha <SHA-COMPLET> --app-report artifacts/quick_app/report.json --hub-report artifacts/doctor_complete/doctor_evidence.json --ci-costs artifacts/doctor_complete/ci_step_costs.json
\`\`\`

Pour comparer un candidat avec un rapport antérieur, ajouter
\`--baseline artifacts/baselines/atlas_before.json\`. Si le scénario,
le nombre de cycles, les options CPU/repos ou les routes ne correspondent
pas, Doctor refuse la comparaison. Même sur des scénarios compatibles,
le pourcentage de variation reste **directionnel** : il faut répéter
sur un matériel et un jeu de données comparables avant de promettre un
gain mesuré.

La table de recommandations P0/P1/P2 fournit les temps et pourcentages
mesurés, pics RSS et phase responsable, suspects de chargements répétés,
absence éventuelle de données de fonctions CPU et trous de couverture
UI/installation/mise à jour. Le profil détaillé des fonctions Python
n'apparaît que si un résultat Doctor \`--deep --profile-startup\` du
même commit est explicitement fourni avec \`--guides\`.

**Aucun faux pourcentage RAM par module** : Qt, workers et caches partagés
rendent les mesures RSS non additives. Doctor conserve une valeur
\`null\` plutôt que d'inventer une répartition. Un delta mémoire positif
au retour Home n'est pas une preuve de fuite et un coût répétitif n'est
pas une preuve de fonction dupliquée. Les actions internes de chaque
module, les FPS desktop réels et la mise à jour publique sur réseau réel
restent explicitement \`NOT_RUN\` jusqu'à vérification dédiée.

Ce rapport sert à prioriser des optimisations à partir de faits, il ne
modifie pas les seuils Phase 8 ni les verdicts Doctor/Graphify/CI.
