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
- **Ruff (ATOSS-20)** : diagnostic Python sélectionné sur périmètre, exécuté si présent lors des checks autorisés,
  **automatiquement pendant `agent check --run-tests` si installé**, ou par
  `doctor oss --run` explicite, sur au plus 16 fichiers Python explicites.
  Le lancement utilise le Python actif, sans install automatique,
  sans exécution d'un chemin PATH, sans cache, sans correctif et avec timeout.
  Le drapeau Python `-P` empêche de charger un faux module depuis le dépôt,
  sans désactiver les installations `pip --user` proposées par
  `tools/setup_doctor_oss.ps1` ; la découverte et le diagnostic Ruff
  utilisent donc le même environnement Python utilisateur.
  Les règles sont isolées de la configuration locale. La version observée
  est une simple *déclaration*, pas une qualification Windows/3.13.
- **pytest-qt, Hypothesis, pywinauto, ast-grep, Semgrep, Gitleaks,
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

L'algorithme utilise `ai_context.classify_path` et **la même étude
ATOSS-01..29**, sans nouvelle base d'inventaire. Il retourne
`intelligent_selection` : `scopes`, `recommended`,
`reason_scopes`, `native_routes` et `omitted_count`. Les outils
non sélectionnés ne s'exécutent pas. Les outils rejetés (#28/#29),
hébergés dans Holding (#26/#27) ou doublonnant un moteur existant
restent exclus des nouveaux exécuteurs.

Avec `--run` ou `agent check --run-oss`, Doctor lance au plus
**deux diagnostics explicitement autorisés** selon le scope : Ruff
pour les fichiers Python, zizmor pour les YAML GitHub Actions.
Pour zizmor, `--offline --no-config --no-progress --no-exit-codes
--format=json` empêche toute collecte GitHub en ligne et interdit le
chargement des configurations locales. Le scanner et sa vérification
`--version` utilisent un chemin exécutable absolu résolu et régulier ;
la détection seule sur PATH ne permet pas de lancer un nom nu depuis
le répertoire du dépôt (notamment sous Windows). Un binaire trouvé
**dans le dépôt analysé** est également refusé, et Windows n'accepte
que l'exécutable `.exe` (pas de script `.cmd`). L'environnement du processus
ne transmet ni tokens ni proxy. Les résultats sont des **compteurs**
(`CLEAN`, `FINDINGS`, `NOT_AVAILABLE`, `ERROR`, `TIMEOUT`), sans
contenu sensible. Aucune installation ni correction n'est réalisée.
Un fichier donné explicitement doit exister et être situé sous un
périmètre autorisé ; max. 16 fichiers, timeout total 1..60 secondes.

Le rapport `execution_results` sépare les diagnostics réellement
lancés. `execution_count` compte uniquement les réponses valides
CLEAN/FINDINGS, jamais une détection de paquet ; une absence ou un
timeout d'un spécialiste fait ressortir un code de sortie non nul
sur la commande `doctor oss`. Pour `agent check`, les résultats
restent **consultatifs** et n'écrasent jamais les tests, les erreurs,
les preuves de certification ou le verdict Doctor.

Les 29 projets et les cinq outils complémentaires ne sont **pas** tous installés ni adaptés par ce lot.
Les candidats de niveau P0/P1 restent soumis à la qualification de
version/licence, aux tests Windows, aux benchmarks de parité et au
rattachement à leur propriétaire réel avant toute activation.


## Utilisation obligatoire avant chaque développement Atlas

La méthode canonique est **Doctor plan → développement → Doctor check →
Doctor validate → audit de chaque commit → CI adaptée → certification**.

Pour un travail Python ou GitHub Actions, **`agent check --run-tests`**
déclenche désormais automatiquement les scanners externes déjà approuvés
et disponibles, en complément des tests ciblés canoniques :

```powershell
py -3.13 -m tools.atlas_doctor agent plan tools/atlas_doctor.py --json
# faire la modification prévue
py -3.13 -m tools.atlas_doctor agent check tools/atlas_doctor.py --run-tests --json
py -3.13 -m tools.atlas_doctor agent validate tools/atlas_doctor.py --json
```

Ce choix automatique utilise uniquement les **fichiers explicites et
existants** du périmètre : Ruff pour les fichiers `.py`, zizmor (offline)
pour les workflows `.yml/.yaml` sous `.github/workflows/`. Pas de scan
global de fichiers, de téléchargement de dépendances, de mutation, ni de
raccourci de CI. La sélection est bornée à 16 fichiers et le budget
externe automatique à 20 secondes maximum.

Les cas exclus (documentation, assets, fichiers supprimés, chemins non sûrs)
sont comptés comme ignorés ; un périmètre plus large que 16 fichiers est
marqué **incomplet** et exige une vérification complémentaire. Un outil absent
reste `NOT_AVAILABLE`. Ce constat ne transforme jamais un résultat
de test ou de certification en PASS et ne supprime aucune exigence Doctor.

`--run-oss` conserve le lancement explicite sans tests, et `--no-oss`
permet de désactiver les outils tiers sans désactiver les tests Doctor.
Pour lancer un audit des 18 capacités natives, utiliser séparément
`doctor capabilities --run-tests` lorsque le scope le justifie.

La matrice de recommandation utilise la liste **29 ATOSS + 5 AT-SUP** du
document d'origine. Aucun outil "évalué" ne devient "exécutable" par sa
simple présence dans cette matrice ; les intégrations de données/Qt/Windows
sont encore suivies par #313, et la recette réelle Windows des deux scanners
par #343.

## Branches de développement désormais reliées (PR #358)

Le plan Doctor choisit parmi les candidats pertinents issus de l'étude
canonique 29+5 et fournit `oss_local_preflight` : disponibilité déclarée
en métadonnées Python ou présence d'un exécutable sur PATH, jamais
preuve d'exécution, de licence, de compatibilité ou d'installation réussie.
Les candidats non pertinents ne sont pas sondés. Les projets Holding,
QtAwesome et PyQtDarkTheme ne sont pas exécutés dans Atlas.

Les modifications de `oss_router.py` et `oss_intelligence.py` sont
reliées aux tests Doctor spécialisés par `tools.ai_context`, dans le
runner unittest existant. L'ajout d'Hypothesis est optionnel : quand
installé, ses propriétés de sécurité sur les chemins des scanners sont
sélectionnées ; sinon elles ne comptent pas comme exécutées.

L'owner JSON existant peut effectuer des essais ciblés :

```powershell
py -3.13 -m tools.atlas_json_benchmark --compare-parsers
py -3.13 -m tools.atlas_json_benchmark --compare-streaming
py -3.13 -m tools.atlas_json_benchmark --compare-compression
py -3.13 -m tools.atlas_json_benchmark --compare-process
```

Les trois commandes nécessitent les données locales Quêtes ; elles
n'installent rien. `orjson`, `msgspec`, `ijson` et `zstandard` sont importés
**uniquement pendant le test demandé**, jamais au démarrage d'Atlas.
La parité des valeurs/IDs ou la restitution strictement octet par octet
des données compressées est vérifiée. La troisième compare le ratio et
les temps zlib/zstandard, sans modifier les formats du Launcher, du pack
de release ni les installations existantes. Ces micro-comparaisons ne
prouvent pas la RAM process-tree ni l'intérêt d'une migration runtime.

`--compare-process` lance explicitement trois processus Python indépendants
(stdlib, orjson, msgspec, si installés) sur les mêmes octets : SHA-256
canonique à types conservés, premier décodage, médiane des décodages suivants,
RSS du processus avant/après (via psutil quand disponible), temps total
avec imports/démarrage et limite de 45 secondes **par moteur**. Un module
absent, un résultat modifié ou un RSS indisponible donne `REVIEW`, jamais
une adoption automatique. Les mesures RSS sont des **instantanés du
processus**, pas des pics de l'arbre des processus. Le premier décodage
n'atteste ni cache disque froid ni démarrage Qt/Atlas : ces preuves doivent
venir du benchmark Windows canonique.
L'essai `msgspec` utilise précisément `msgspec.json.decode`, et non
une API `loads` inexistante. Les comparaisons retournent **0** seulement
si tous les résultats demandés sont conformes, **1** si une dépendance est
indisponible ou si le résultat est à examiner, et **2** sur parité rompue
ou erreur d'exécution, tout en conservant le rapport JSON pour diagnostic.

**État de développement :** brancher une recommandation ou observer un
paquet disponible ne valide pas OSR-002..010. Les intégrations propres
au Launcher, à Organizer, aux Guides et à Holding doivent encore avoir
leurs vrais témoins sur leurs branches propriétaires ; conserver la PR
Draft jusqu'à la fin du code, puis audit et certification sur le HEAD final.

## Essai ImageHash sur assets choisis

Pour des icônes ou illustrations du même périmètre (jamais un scan
automatique de tout le bundle Unity), Doctor expose un essai de doublons
**visuels potentiels** :

```powershell
py -3.13 -m tools.atlas_doctor oss data/images/items/exemple1.png data/images/items/exemple2.png --asset-trial --json
```

Remplacer les deux chemins par des assets **réellement présents**. Le mode
`--asset-trial` valide explicitement les chemins, refuse les symlinks et
les entrées non-image, limite les images à 2 millions de pixels et 2 Mio
par fichier, puis importe Pillow/ImageHash uniquement à la demande.
Il compare les empreintes perceptuelles sous un seuil Hamming de 6,
revérifie les SHA256 des sources avant/après, et ne publie ni pixels ni
suppression. Les différences de charte, variantes Unity/DPI et vrais
consommateurs de chaque image doivent rester examinés séparément.
Un outil absent donne `NOT_AVAILABLE`, un scan impossible `ERROR`,
et aucun de ces états n'autorise une suppression ou un PASS CI.
Le mode `--asset-trial` ne se combine pas avec `--run` ou `--verify-live` ;
aucun asset n'est analysé par ce spécialiste automatiquement lors
d'un simple `agent check`.

## Essai fontTools pour les polices Unity

Pour une police TTF/OTF locale précise, le propriétaire Assets peut interroger
`fontTools` sans modifier la police ou le pack Unity :

```powershell
py -3.13 -m tools.atlas_doctor oss app/assets/themes/dofus_unity/ma_police.ttf --font-trial --json
```

Remplacer le chemin par une police **réellement présente**. Le mode
`--font-trial` lit seulement les TTF/OTF explicitement sélectionnés,
au maximum 16 fichiers de 2 Mio chacun. Il vérifie les SHA256 avant/après,
lit les noms de famille/style et la **présence** d'une mention de licence
sans en déduire des droits de redistribution. Le chargement Qt, le rendu DPI,
l'intégration aux consommateurs et la provenance des assets restent à vérifier
séparément. Sans `fontTools`, le rapport indique `NOT_AVAILABLE`; si une
police est illisible, `ERROR`. Aucun fichier n'est transformé.
`--font-trial`, `--asset-trial`, `--verify-live` et `--run` sont des
modes exclusifs ; les deux essais Assets sont toujours manuels.

## Commandes

Plan consultatif sans processus tiers :

```powershell
py -3.13 -m tools.atlas_doctor oss tools/tool_catalog.py --json
```

Exécution opt-in si le paquet Ruff est *déjà* installé :

```powershell
py -3.13 -m tools.atlas_doctor oss tools/tool_catalog.py --run --json
```

Pendant `agent check --run-tests`, Doctor active automatiquement les
diagnostics approuvés et déjà disponibles. `--run-oss` reste un opt-in
explicite pour un check sans exécution des tests :

```powershell
py -3.13 -m tools.atlas_doctor agent check tools/tool_catalog.py --run-tests --json
# Sans tests, forcer uniquement le diagnostic tiers déjà approuvé :
py -3.13 -m tools.atlas_doctor agent check tools/tool_catalog.py --run-oss --json
```

Le résultat figure sous `oss_advisory` ; il ne change jamais le
`status`, `exit_code` ou la décision de certification Doctor.
Un agent bloqué ne lance pas Ruff, et un outil absent n'est jamais installé.

Le rapport expose aussi `native_catalog`, calculé **uniquement par
`tools.tool_catalog`** : nombre d'outils internes inventoriés,
`automation_ready`, outils à revoir, mutateurs non gardés et échantillon
de chemins. Il s'agit d'un audit de câblage **statique**,
`execution_witnesses: 0` tant qu'aucun test n'a été exécuté.

Le rapport retourne aussi `open_source_inventory` : les 29 entrées `ATOSS-XX` et les 5 `AT-SUP-XX`
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


## Preuve réelle avant certification (Ruff + zizmor)

La Phase Certification valide les **contrats** à l'aide de tests Python
simulés. Elle ne prouve pas que les deux exécutables tiers sont présents
sur le PC de l'utilisateur. Depuis la racine du dépôt, sous Windows :

```powershell
py -3.13 -X utf8 -m tools.atlas_doctor oss tools/atlas_doctor_lib/oss_router.py .github/workflows/phase-certification.yml --verify-live --timeout-seconds 45 --json
```

Cette commande ne télécharge et n'installe **rien**. Elle exige Ruff
installé dans le Python actif et zizmor accessible via PATH ou le dossier
`Scripts` du Python user-site Windows ; un outil
manquant reste `REVIEW` avec un code retour non nul. Elle exécute les
deux diagnostics en lecture seule, constate leurs réponses JSON, interroge
leur version réelle **aux versions verrouillées dans
`tools.doctor_oss_wheels.PINS`** et compare les empreintes SHA-256 des
fichiers analysés avant/après. Une version absente ou différente donne
`REVIEW`, même si les deux scanners ont répondu correctement. `LIVE_PASS`
signifie seulement que les deux outils aux versions choisies ont fonctionné
pour ces fichiers sur **cette machine**, sans modifier ces fichiers. `windows_13_qualified` ne devient vrai que sur
Windows et Python 3.13 avec ce constat.

Cette qualification ne certifie pas l'absence de modifications d'autres
fichiers, ni l'absence de trafic réseau mesuré par capture, ni la licence,
ni l'exactitude de toutes les règles, ni la Phase Certification, ni le
fonctionnement des 29 + 5 candidats. zizmor garde son mode `--offline`
et aucun jeton GitHub n'est transmis à son processus.

Les rapports ordinaires `doctor oss --run` et `agent check --run-tests`
exposent désormais `execution_summary` (`expected_tools`,
`confirmed_executions`, `gaps`). La valeur `COMPLETE` n'est attribuée
que lorsque chaque outil sélectionné a retourné un JSON valide.
`ADVISORY_ONLY` reste le statut global, sans remplacer les preuves Doctor.

**Sans exécution native sur le PC de l'utilisateur, l'issue #346 reste ouverte.**
Une éventuelle qualification Windows GitHub prouverait ce runner et non
la machine personnelle. Ne pas relancer de CI pour masquer cette lacune.


## Installation reproductible (uniquement outils de développeur Windows)

`tools/setup_doctor_oss.ps1` est le point d'entrée Windows pour qualifier
les deux **seuls** adaptateurs tiers approuvés dans Doctor. Par défaut, il
**ne fait aucune installation** : il exécute la qualification réelle.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/setup_doctor_oss.ps1
# Uniquement si Ruff ou zizmor manque, installation volontaire des deux wheels:
powershell -NoProfile -ExecutionPolicy Bypass -File tools/setup_doctor_oss.ps1 -Install
```

Le mode `-Install` exige **Windows x64 et Python 3.13 64 bits** et
utilise `tools.doctor_oss_wheels`. Il télécharge explicitement les deux
wheels officiels `ruff==0.17.3` et `zizmor==1.30.1` depuis PyPI, consulte
le document JSON versionné de **PyPI** pour chaque *nom de fichier exact*,
compare le SHA-256 des bytes téléchargés, puis fait revérifier ces SHA par
`pip --isolated --require-hashes --no-index --no-deps` sur les fichiers
locaux vérifiés. Un digest absent, une redirection de métadonnées, une
architecture non conforme, une version imprévue ou une divergence bloque
l'installation. Aucun SHA-256 non vérifié n'est conservé comme une constante.

L'installation n'est **jamais** automatique pendant Doctor `plan/check` ;
elle ne modifie pas le runtime Atlas, mais peut mettre à jour les deux
packages du user-site Python du développeur. Les sources, wheels et fichiers
temporaires sont supprimés après l'opération. L'installation pip n'est pas
transactionnelle et ne garantit pas le rollback d'un environnement utilisateur
en cas de panne partielle : préférer un environnement de développement isolé.
Après installation, Doctor cherche également `zizmor.exe` dans les
`Scripts` du user-site Windows.

La comparaison des hashes vérifie le téléchargement contre les métadonnées
PyPI récupérées en HTTPS au moment de la commande, **pas** la licence, la
chaîne de provenance complète, les dépendances de l'outil, ni le comportement
réel de ce binaire sur la machine. Ces preuves restent distinctes de
`LIVE_PASS`, qui nécessite d'exécuter réellement les deux scanners.

Les versions ci-dessus sont les versions de qualification choisies pour ce
lot ; les mises à jour restent des décisions explicites, avec vérification
compatibilité/licence/CPython et tests. Installation réseau par pip uniquement
si l'opérateur choisit le switch `-Install` ; aucun installation silencieuse
lors de `agent plan/check/validate`.

Le contrat **réellement consommable par les agents IA** est
`ai_tool_workflow` dans le JSON renvoyé par chaque commande
`tools.atlas_doctor agent plan/check/validate` : étapes avant/après code,
propriétaires natifs recommandés, outils tiers attendus, exécutés ou absents,
couverture incomplète et interdiction de se déclarer certifié par sélection.
Cette description ne remplace jamais le statut Doctor, les tests spécialisés
ou la Phase Certification au SHA exact. Lire `AI_ENTRYPOINT.md` et
`tools/skills/dofus-atlas-tools/SKILL.md` pour l'utilisation obligatoire.

Les candidats optionnels/rejetés de l'inventaire 29+5 ne sont pas installés
par ce script. Les travaux de qualification restent #313 ; la preuve
de fonctionnement sur le PC personnel doit toujours être attestée dans #346.
