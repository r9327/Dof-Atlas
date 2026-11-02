# Doctor — diagnostics OSS opt-in

L'étude des 29 projets (+ 5 annexes) reste dans
[le plan GitHub OSS](roadmap/GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md).
**Présence ≠ compatibilité ≠ exécution ≠ certification.**

## État réel

- **Outils Atlas existants** : Doctor, Graphify, le registre dérivé
  `tools.tool_catalog`, les tests Qt natifs, le moteur de benchmark
  et les contrôles JSON gardent leurs propriétaires et leurs gates.
  Le routeur lit les outils `automation_ready` du catalogue canonique
  pour *recommander*, sans jamais les invoquer à leur place.
- **Ruff (ATOSS-20)** : seul outil tiers exécuté dans ce premier lot,
  **à la demande uniquement**, sur au plus 16 fichiers Python explicites.
  Le lancement utilise le Python actif, sans install automatique,
  sans exécution d'un chemin PATH, sans cache, sans correctif et avec timeout.
  Les règles sont isolées de la configuration locale. La version observée
  est une simple *déclaration*, pas une qualification Windows/3.13.
- **pytest-qt, Hypothesis, pywinauto, ast-grep, Semgrep, zizmor, Gitleaks,
  OSV, ImageHash, RapidFuzz, msgspec, orjson, ijson et autres candidats**
  : non automatiquement exécutés ni embarqués. Ils doivent avoir une
  preuve de version/licence, tests ciblés et intégration chez leur owner.
- **py-spy** : le chemin existant Doctor Perf Lab demeure propriétaire ;
  aucun deuxième profiler ou collecteur parallèle.
- **QtAwesome et PyQtDarkTheme** : rejetés comme remplacements du thème
  Unity. Les SDK MCP sont à évaluer côté Holding, pas dans l'EXE Atlas.


## Sélection contextuelle : même Doctor, pas un second orchestrateur

Doctor choisit les **capacités utiles** en fonction des fichiers explicites :

| Périmètre | Propriétaire existant prioritaire | Spécialiste OSS |
|---|---|---|
| Python | Agent check, tests ciblés | Ruff installé (opt-in), ast-grep/Semgrep en évaluation |
| Workflows GitHub Actions | Doctor CI, Delivery Guard | **zizmor** hors ligne (opt-in), Gitleaks en évaluation |
| Guide / progression | Certification Guide + tests de parcours | Hypothesis / RapidFuzz en évaluation |
| Qt / Unity | Scénarios Qt existants | pytest-qt, ImageHash / fontTools à qualifier |
| JSON / Quêtes | Index JSON / benchmark canonique | msgspec vs orjson vs ijson : comparer avant choix |
| RAM / freeze | Doctor Perf Lab / benchmark Phase 8 | py-spy et psutil propriétaires existants ; pas de profiler double |
| Launcher | Tests Windows du launcher | pywinauto, zstandard en qualification ciblée |
| Dépendances | Verrouillage et contrôles CI | OSV ou pip-audit (pas les deux par défaut) |

L'algorithme utilise \`ai_context.classify_path\` et **la même étude
ATOSS-01..29**, sans nouvelle base d'inventaire. Il retourne
\`intelligent_selection\` : \`scopes\`, \`recommended\`,
\`reason_scopes\`, \`native_routes\` et \`omitted_count\`. Les outils
non sélectionnés ne s'exécutent pas. Les outils rejetés (#28/#29),
hébergés dans Holding (#26/#27) ou doublonnant un moteur existant
restent exclus des nouveaux exécuteurs.

Avec \`--run\` ou \`agent check --run-oss\`, Doctor lance au plus
**deux diagnostics explicitement autorisés** selon le scope : Ruff
pour les fichiers Python, zizmor pour les YAML GitHub Actions.
Pour zizmor, \`--offline --no-config --no-progress --no-exit-codes
--format=json\` empêche toute collecte GitHub en ligne et interdit le
chargement des configurations locales. L'environnement du processus
ne transmet ni tokens ni proxy. Les résultats sont des **compteurs**
(\`CLEAN\`, \`FINDINGS\`, \`NOT_AVAILABLE\`, \`ERROR\`, \`TIMEOUT\`), sans
contenu sensible. Aucune installation ni correction n'est réalisée.
Un fichier donné explicitement doit exister et être situé sous un
périmètre autorisé ; max. 16 fichiers, timeout total 1..60 secondes.

Le rapport \`execution_results\` sépare les diagnostics réellement
lancés. \`execution_count\` compte uniquement les réponses valides
CLEAN/FINDINGS, jamais une détection de paquet ; une absence ou un
timeout d'un spécialiste fait ressortir un code de sortie non nul
sur la commande \`doctor oss\`. Pour \`agent check\`, les résultats
restent **consultatifs** et n'écrasent jamais les tests, les erreurs,
les preuves de certification ou le verdict Doctor.

Les 29 projets ne sont **pas** tous installés ni adaptés par ce lot.
Les candidats de niveau P0/P1 restent soumis à la qualification de
version/licence, aux tests Windows, aux benchmarks de parité et au
rattachement à leur propriétaire réel avant toute activation.

## Commandes

Plan consultatif sans processus tiers :

```powershell
py -3.13 -m tools.atlas_doctor oss tools/tool_catalog.py --json
```

Exécution opt-in si le paquet Ruff est *déjà* installé :

```powershell
py -3.13 -m tools.atlas_doctor oss tools/tool_catalog.py --run --json
```

L'agent Doctor peut également déclencher ce diagnostic **pendant son
`check`**, mais seulement avec un opt-in explicite :

```powershell
py -3.13 -m tools.atlas_doctor agent check tools/tool_catalog.py --run-tests --run-oss --json
```

Le résultat figure sous `oss_advisory` ; il ne change jamais le
`status`, `exit_code` ou la décision de certification Doctor.
Un agent bloqué ne lance pas Ruff, et un outil absent n'est jamais installé.

Le rapport expose aussi `native_catalog`, calculé **uniquement par
`tools.tool_catalog`** : nombre d'outils internes inventoriés,
`automation_ready`, outils à revoir, mutateurs non gardés et échantillon
de chemins. Il s'agit d'un audit de câblage **statique**,
`execution_witnesses: 0` tant qu'aucun test n'a été exécuté.

Le rapport retourne aussi `open_source_inventory` : les 29 entrées `ATOSS-XX`
lues directement depuis l'étude canonique, sans table de correspondance
à maintenir séparément. Chaque entrée distingue `NOT_VERIFIED`,
`EXISTING_OWNER_NOT_RETESTED`, `DOCTOR_OPT_IN_ONLY` ou `REJECTED`.
`execution_witnesses: 0` signifie qu'aucune exécution des 29 candidats
n'est certifiée par ce simple inventaire. Les données observées lors de
`--run` sont fournies séparément dans `execution`.

Pour un fichier de workflow, Doctor recommande les outils canoniques
de CI, sans lancer de scanner tiers non approuvé.

Les résultats `CLEAN`, `FINDINGS`, `NOT_AVAILABLE`, `TIMEOUT` ou
`ERROR` ne sont **jamais** assimilés à `PASS` de Doctor, à une
certification Windows ni à un benchmark.

L'intégration du reste des candidats appartient à l'[issue #313](https://github.com/r9327/Dof-Atlas/issues/313)
et à des PR ciblées dans les propriétaires existants. Le développement
de nouveaux runners tiers doit comparer risque, coût, faux positifs et
effet sur la RAM, sans modifier le runtime de base.
