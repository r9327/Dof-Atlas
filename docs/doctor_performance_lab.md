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
