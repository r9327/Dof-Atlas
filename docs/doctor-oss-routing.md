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
