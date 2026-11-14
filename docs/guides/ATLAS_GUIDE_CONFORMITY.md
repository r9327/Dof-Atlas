# Atlas Guide Conformity — clean candidate

Status: prototype under development. No certification is claimed.
PR #363 branch: feat/atlas-guide-importer-pr337-20261102, rebuilt as a
single-parent clean commit on main@fa3ecd08b413824856febb918074a625f0387c78
(after #406 Organizer). It does not carry the old #337 commit history.
Its code and documentation diff was checked against the clean #363 candidate;
shared CI ownership rules from Organizer and Guides were reconciled.
PR #363 remains Draft. No real guide route is staged, activated, or certified.

## Scope

tools.atlas_guide_conformity compares an independently collected, authorized guide reference
with two successive Atlas representations. Offline, read-only and no Qt/runtime imports.
It reports missing and extra guides/steps/actions/fields, mismatched values or types,
order changes and duplicated stable IDs. Each discrepancy carries guide/step/action IDs,
field path, expected/actual values, source evidence reference and proposed correction.

The CLI writes before.json, after.json and before_after.json, with resolved, persistent
and introduced differences. A blocked comparison exits 1.

An exact JSON comparison is never gameplay or author-rights certification:
all reports explicitly contain certified=false.

## Data contract

Reference and Atlas snapshots contain a guides array. Stable identifiers are
guide_id, source_step_id and action_id. The reference also declares
reference_verified=true, rights_verified=true and complete=true. These flags
are input claims, NOT independent evidence; validate underlying permissions
and source parity separately. Evidence refs should identify source material
the user is authorized to consult. Do not publish protected source text in logs.

## Reproducible commands (full repository checkout)

    py -3.13 -m unittest tests.test_atlas_guide_conformity -v
    py -3.13 -m tools.atlas_guide_conformity --reference reference_authorized.json --before before_atlas.json --after after_atlas.json --output-dir artifacts/guide_conformity

## Evidence available and checks still mandatory

**Completed, synthetic-only evidence on previous exact HEAD
`400c80152917e31be5ee11e0146e1ea36183cf0f`:**

- Phase 0 stdlib Linux and Qt Windows: [run #43023319786](https://github.com/r9327/Dof-Atlas/actions/runs/43023319786), PASS.
- Doctor visual Windows campaign: [run #43023319897](https://github.com/r9327/Dof-Atlas/actions/runs/43023319897), PASS.
- Existing Graphify/Doctor bridge: [run #43023311623](https://github.com/r9327/Dof-Atlas/actions/runs/43023311623), PASS.
- Every subsequent source commit requires its own exact-SHA tests. A PASS
  on an earlier HEAD is **not** automatically a PASS on a later HEAD.

**Still NOT_CERTIFIED / NOT_RUN as applicable:**

- Rights-cleared real-source extraction, independent verification and complete
  95-guide inventory; no authorized real source has been processed.
- Protected publication/activation with complete install, rollback and
  integrity evidence, beyond synthetic staging.
- Full Windows/DOFUS Unity gameplay, real characters and performance/
  memory measurements; preservation of the two optimized guide routes.
- Independent manual comparison of the single future Cawotte pilot, and only
  then guide-by-guide certification. All GIMP criteria require honest evidence.

The library CLI and 95/7705 fixtures exercise the **tool contract** only.
The GitHub Delivery Guard remains blocking while GIMP criteria are PENDING.


## Création structurée et utilisation commune (PR #363)

**IMPORTANT — PHASE 0 : NE PAS EXÉCUTER LES COMMANDES CI-DESSOUS SUR DES
GUIDES RÉELS.** Elles décrivent la future interface de développement,
pas une autorisation d'extraire Cawotte ou les 95 guides. Avant la
qualification intégrale de tous les outils/classes UI, exécuter uniquement
les tests sur fixtures fictives. Le seul point d'entrée d'orchestration
contrôlé est `tools.atlas_guide_pipeline` et son CLI refuse toute
opération réelle en l'absence d'attestation de confiance.


La création hors ligne se fait avec `tools.atlas_guide_importer` :
une seule source JSON v1 autorisée, `guides` ordonnés, IDs stables
`guide_id` / `source_step_id` / `action_id`, `rights_verified`,
`reference_verified`, `complete`. **Les drapeaux déclarent un état,
ils ne constituent jamais une preuve indépendante de droits ou de fidélité.**

    py -3.13 -m tools.atlas_guide_importer --source authorized_export.json
    py -3.13 -m tools.atlas_guide_importer --source authorized_export.json --output artifacts/guide_preview/preview.json

Le mode complet exige exactement **95 guides et 7 705 étapes**.
`--partial` est disponible uniquement pour des lots explicitement incomplets,
sans possibilité de les qualifier de complets/certifiés. L'outil refuse
un fichier de sortie déjà présent, ne touche ni `data/` ni les sauvegardes,
n'installe aucune route et ne scrappe aucune source tierce.

L'adaptateur `guide_shared_route_contract.project_authorized_guide` forme
les cartes compatibles avec `SharedGuideManualCard` existant dans `main` :
IDs stables, positions au format `[x,y]` cliquables, objets/quantités,
PNJ/choix et combats structurés conservés. La **visualisation réellement
branchée à l'application et ses validations par personnage restent à faire**.

Commandes de test ciblé :

    py -3.13 -m unittest tests.test_atlas_guide_importer_preview tests.test_guide_shared_route_contract tests.test_atlas_guide_conformity -v

L'extracteur de source réelle autorisée, la publication live certifiée et
la recette Windows/DOFUS ne sont pas terminés. Les preuves Graphify et
CI citées plus haut portent uniquement sur la qualification synthétique ;
**tous les guides restent NOT_CERTIFIED**.

## Ordre obligatoire de livraison — zéro guide réel avant qualification

**Phase 0 (en cours) : architecture et outils uniquement.** À ce stade,
AUCUNE route réelle n'est extraite, prévisualisée, importée, publiée ni certifiée.
Les fixtures entièrement synthétiques sont permises pour les tests. La mise en
place de scripts capables de traiter les 95/7705 ne donne aucune permission
de les exécuter sur des guides réels maintenant.

Avant de toucher au premier vrai guide, certifier **chaque composant concerné** :
lecteur et cartes `SharedGuideManualView/Card` existants, en-tête commun,
navigation, couleurs et clics NPC/objets/positions, copie `/travel`,
préparation/combats, progression et validation par personnage, adaptateur,
outils de création/import, comparaison et certification, publi­eur atomique,
régression des deux grands guides, RAM/lazy loading et tests Windows/DOFUS.
Doctor et Graphify doivent fournir des preuves **au SHA exact** ; un
`NOT_RUN` ou une fonctionnalité uniquement documentée ne vaut pas `PASS`.
Tous les critères GIMP-001…016 concernés restent bloquants.

**Phase 1 : pilote UNIQUE, après qualification technique.** Choisir
`Dofus Cawotte` ; ne choisir `Dokoko` qu'en cas d'indisponibilité
de référence Cawotte (pas pour masquer une anomalie). Obtenir une référence
Ganymède **autorisée et indépendante de l'export Atlas**. Construire ce seul
guide de bout en bout, passer les outils de certification, puis réaliser
une **contre-comparaison manuelle indépendante** Atlas vs référence,
étape par étape et action par action : textes/ordre/positions/quantités/PNJ,
choix/dialogues, objets, prérequis, combats, liens, classes UI,
copie `/travel`, progression, persistance et validation sous Windows/DOFUS.

**Phase 2 : boucle de correction sans changer de guide.** Au moindre écart
ou contrôle non exécuté, bloquer et améliorer les outils/l'architecture ;
repasser **toute** la recette sur le même pilote. Le comparateur ne peut
ni se certifier lui-même ni remplacer l'observation humaine. Seules des
preuves indépendantes concordantes peuvent autoriser la certification
à 100 % de ce pilote ; aucun marqueur JSON auto-déclaré n'est suffisant.

**Phase 3 : extraction unitaire seulement.** Après pilote certifié,
extraire **un** nouveau guide, le rendre dans l'UI commune, comparer toute
son information à une référence indépendante, vérifier et certifier
ses classes UI et services utilisés, puis **seulement** commencer le
suivant. Aucun import en masse, aucune certification automatique des
autres 94 guides par simple extrapolation. Chaque dossier comporte
SHA du code, SHA des sources, rapports avant/après/delta, témoins
Doctor/Graphify/tests, recette réelle Windows/DOFUS, résultat final
par guide. Si une preuve manque : `NOT_CERTIFIED`.

Le protocole et les critères GIMP-016…018 sont conservés dans
l'issue #361 ; la recette Windows et le pilote sont détaillés
dans #362. Cette documentation ne constitue **aucune certification**.


## Un seul point de contrôle et verrou de séquence (GIMP-016…018)

Le point d'entrée de contrôle est `tools.atlas_guide_pipeline` :
ce module assemble le gate séquentiel, le prévisualisateur de création,
la comparaison indépendante avant/après et le stockage **non activé**
du candidat. Il **ne lit aucune route réelle au stade actuel**.

Commande de diagnostic **métadonnées seulement** (ne prépare jamais un guide) :

    py -3.13 -m tools.atlas_guide_pipeline --plan evidence_plan.json --head-sha <git-sha-40>

Le `plan` ne contient **que** des identifiants de guide et des reçus
de preuve, jamais le texte des quêtes. Sans vérificateur externe de
preuves fourni par un hôte de certification autorisé, la commande
échoue **systématiquement en BLOCKED**, même si le JSON indique PASS.
Aucun `--force`, `--trust`, `--apply` ou `--skip-checks` n'est disponible.
La fonction Python `stage_checked_candidate` n'est pas une commande
CLI : elle exige le vérificateur d'attestations indépendant et un
alignement des quatre représentations (source autorisée, référence
indépendante, Atlas avant et après), exactement **un** guide et zéro
écart après comparaison. Elle ne crée qu'un *candidat* immutable
sans activation de route ni modification de la progression.

`tools.atlas_guide_sequence_gate.assess_next` est le seul propriétaire
de la règle chronologique : Doctor/Graphify/tests/UI/Windows/perf et
outils d'abord ; **Cawotte seul** comme pilote (Dokoko uniquement si
l'indisponibilité de Cawotte est elle-même attestée) ; pour chaque guide
suivant, chaque preuve du précédent doit être **PASS et vérifiée
indépendamment** au SHA source+code exact, avec couverture positive
des étapes et actions et aucune anomalie bloquante ou non vérifiée.
Le verrou exige en plus `certification_status=CERTIFIED`, un reçu
`independent_final_certificate` vérifié par l'hôte de confiance et
l'égalité stricte `certified_steps == total_steps > 0` et
`certified_actions == total_actions > 0`. Une signature/attestation
indépendante absente interdit toute étape suivante.
Le retour `ELIGIBLE_FOR_INDEPENDENT_REVIEW` **n'est PAS un certificat**.
Une preuve manquante, un SHA périmé, une chaîne interrompue ou un
vérificateur indisponible retourne BLOCKED. Un guide ne peut être
certifié par le certificateur lui-même.

Commandes de tests uniquement sur **fixtures intégralement fictives** :

    py -3.13 -m unittest tests.test_atlas_guide_sequence_gate tests.test_atlas_guide_pipeline -v

Le `verifier` factice injecté dans les tests n'est pas un système
de confiance de production. Aucun export Ganymède réel, aucune fiche
Cawotte réelle, aucune donnée de guide réelle n'a été utilisée.
**Ne pas déclencher le pilote** tant que Graphify, Doctor,
l'architecture UI et les outils ne sont pas réellement qualifiés.
L'activation en production, la certification indépendante et la
vérification Windows/DOFUS restent des étapes futures obligatoires.

## Correctifs de sûreté du comparateur et du stockage candidat

Le comparateur n'ignore plus les `source_url` et champs métier/média
au niveau des actions, et vérifie désormais les champs racine du schéma,
les champs supplémentaires, ainsi que le **type** des identifiants.
Seul `evidence_ref` est exclu du rendu fonctionnel ; sa présence
dans la source n'établit pas à elle seule une vérification indépendante.

Le CLI de conformité exige un **dossier de rapports neuf**, hors des
répertoires de données et sauvegardes, sans lien symbolique. Il refuse
d'écraser un précédent `before.json`, `after.json` ou
`before_after.json`. Réexécuter un audit dans un **autre** dossier.

Le pipeline exige **deux attestations de source distinctes**,
`current.source_rights` et `current.independent_reference`,
sur les hachages réels des deux JSON et le SHA du code. Leur validité
doit être contrôlée par un hôte de confiance ; deux copies identiques
ne sont **pas** une preuve d'indépendance. Sans ce vérificateur,
le staging reste bloqué. Le callback fictif dans les tests ne
vaut jamais preuve réelle.

Le magasin de candidats est **hors runtime et jamais activant** :
chaque génération est créée via fichier temporaire synchronisé puis
renommage atomique, avec couverture `guide_count/step_count/action_count`
vérifiée et refus des liens symboliques pointant hors du stockage.
Le choix d'une génération utilise le contrôle compare-and-swap,
la reprise et le rollback de *candidats seulement*, jamais les
progressions de personnages.

Ces modifications sont du **code présent mais NON_VALIDÉ** tant que
l'exécution des tests sur un checkout du SHA courant n'est pas attestée.
Elles ne permettent en aucun cas de passer à la phase pilote.


### Conservation intégrale des données dans les cartes UI

Avant de stocker un candidat, le contrôleur vérifie également que
**chaque action source** figure **une seule fois et dans le même ordre**
dans les sections du lecteur commun, qu'aucune ligne rendue ne manque
et qu'aucun texte/titre/identifiant n'a été substitué. Il recoupe les
positions `[x,y]` copiables, le type et la catégorie d'action
(combats et avertissements inclus), les noms d'objets nécessaires
aux liens de copie, leurs quantités dans le panneau de préparation,
les prérequis, les noms/IDs de quêtes et les métadonnées source.

Une divergence de projection est bloquante même lorsque la comparaison
des JSON source/Atlas est verte : **deux exports identiques ne prouvent
pas que l'UI affiche fidèlement toutes leurs actions**. Les tests de
mutation correspondants utilisent exclusivement des objets imaginaires.
La certification finale des couleurs/clics effectifs attend toujours
la vérification réelle du lecteur sous Windows/DOFUS.


### Inventaire exhaustif et reconstruction canonique (durcissement Phase 0)

Le rapport `compare` comporte maintenant les compteurs
`reference_full_guides/steps/actions` et
`atlas_full_guides/steps/actions`, calculés **sur les deux documents
complets**, et pas seulement dans les guides communs. Deux exports
identiques contenant une route sans étapes, une étape sans actions ou
un type d'action inexploitable ne peuvent plus produire de PASS.
Un guide manquant reste bloquant, mais ses étapes/actions restent
comptabilisées dans l'inventaire source complet.

Les cartes candidates doivent être exactement identiques à une
**reprojection fraîche depuis les étapes source** via l'unique adaptateur
`project_authorized_guide`. Cela bloque les faux drapeaux de
certification/renderer, l'index de page altéré, l'en-tête substitué,
les étapes omises et les champs invisibles ajoutés hors du schéma.
Le guide conserve désormais ses métadonnées d'origine **une fois par
route**, pas une copie complète par fiche.

Ces protections sont testées avec des fixtures fictives. Une
coïncidence de données ne constitue toujours pas une preuve
d'authenticité de la source ou de validation UI réelle ; les
attestations indépendantes, Doctor/Graphify et Windows restent
obligatoires, et aucun guide réel n'est traité en phase 0.

## Phase 0 — contrôle supplémentaire des références (3 novembre 2026)

- Le gate de séquence refuse les versions de schéma booléennes, identifiants
  de guide non canoniques et un prédécesseur fictif sur le premier parcours.
- Le magasin hors runtime valide les références compare-and-swap et rollback
  **avant toute création/écriture de répertoire**, et refuse une sélection
  symbolique pendante au lieu de l'interpréter comme `NONE`.
- Des tests synthétiques négatifs ciblent chacun de ces scénarios. Leur présence
  dans le dépôt ne constitue **pas** une exécution : Doctor, Graphify exact-SHA,
  tests Python, Windows/DOFUS et bench restent `NOT_RUN` tant qu'un vrai
  checkout vérifié ne les a pas exécutés. Aucun guide réel n'est préparé.

### Sorties hors runtime et schémas déclarés

Le dry-run de création refuse maintenant les destinations de prévisualisation
par lien symbolique (fichier ou dossier parent), même lorsque le chemin lié
n'existe pas encore. Les chemins `data` et `saves` restent exclus, et
aucune donnée ne passe en production par ce CLI.

Dans le comparateur, une version de schéma explicitement déclarée doit être
l'entier `1` ; deux exports également falsifiés avec `true`, `null`,
`"1"` ou `2` ne peuvent obtenir `PARITY_CHECK_PASS`. Une référence
historique qui n'a pas ce champ conserve sa compatibilité, mais cette
comparaison ne confère ni autorisation ni certificat. Tests ajoutés et
exécution au SHA exact encore à prouver.

## Exactitude des identifiants dans le comparateur

Les identifiants de guide, étape et action doivent être comparés sans trim ou
normalisation silencieuse. Deux exports qui contiennent tous les deux un ID
avec espaces de début/fin sont `UNVERIFIABLE` et non `PARITY_CHECK_PASS`.
Ces vérifications protègent le comparateur hors runtime ; elles ne prouvent
pas la conformité du lecteur Qt ni une certification de guide.

Le schéma des IDs reste celui de l'adaptateur canonique : caractères ASCII
alphanumériques suivis de caractères alphanumériques, points, tirets ou
soulignés, longueur maximale 120. Les IDs comportant espaces internes,
segments de chemin, Unicode hors contrat, booléens ou entiers négatifs
sont `UNVERIFIABLE`, même s'ils sont identiques dans les deux exports.

## Correctifs du comparateur — inventaire et faux PASS (3 novembre 2026)

- Lorsqu'un guide ou une étape disparaît entièrement, les rapports listent
  aussi leurs étapes et actions enfants. Une clé de collection `guides`,
  `steps` ou `actions` entièrement absente déclenche cet inventaire détaillé
  des pertes ou ajouts, sans masquer les compteurs de chaque export.
- Les champs et valeurs identiques ne suffisent pas à rendre valide une source
  inexploitable. Le comparateur indépendant refuse les types d'action inconnus,
  les déplacements sans coordonnées valides, les titres vides, les ressources
  ou monstres sans nom/quantité positive et les combats sans monstres.
- Les listes optionnelles `items: []` et `monsters: []` sont acceptées pour
  les actions qui ne les exigent pas, conformément à l'adaptateur existant.
  Une liste requise vide reste bloquante.
- Tests adversariaux synthétiques ajoutés ; ils ne constituent pas encore une
  preuve d'exécution sur le SHA final. Doctor, Graphify, Windows/DOFUS et la
  certification des guides restent indépendants et `NOT_RUN`.

### Compatibilité des routes affichées — preuve synthétique

Le comparateur vérifie aussi l'ordre des rubriques partagées
(`now → opportunity → keep → boss → before_leave`), l'antériorité de la
préparation et les listes typées de quêtes/prérequis. Deux exports identiques
avec un rang de rubrique inversé, une rubrique inconnue ou des identifiants
de quête non entiers sont **bloqués** avant leur présentation comme parité.

Le contrôle Draft utilise les tests des modules Guide (stdlib, sans Qt)
uniquement lorsque leurs chemins changent ; une réussite certifie leur
exécution à un SHA donné, **pas** un guide réel ou la conformité Windows.

### Diagnostic complet sans copies géantes de collections (3 novembre 2026)

- Une clé entière `guides`, `steps` ou `actions` absente/ajoutée
  reçoit une preuve racine bornée `{collection, count, sha256}` au lieu
  de dupliquer une énorme liste source dans un seul `MISSING_FIELD`.
  Chaque guide, étape et action reste signalé individuellement, avec son
  identité, ses champs utiles, son emplacement et la preuve référencée ;
  l'empreinte permet de vérifier la collection complète sans l'afficher
  une deuxième fois. Il ne s'agit ni d'un raccourci de couverture ni
  d'une autorisation/certification.
- Les IDs invalides conservent la vraie valeur brute dans `actual` ;
  deux contenus différents partageant le même ID provoquent à la fois
  `DUPLICATE` et `AMBIGUOUS`. Des doublons strictement identiques
  restent `DUPLICATE` et sont bloquants.
- Ces cas sont couverts par des tests synthétiques. Aucune donnée de
  guide réel, progression, route ou lecteur Windows n'est modifiée.

### Empreintes réservées (séquence de certification)

Un SHA tout à zéro n'est jamais une preuve valide de commit, de guide
certifié ni d'artefact. Les vérifications refusent cette sentinelle même
si une fonction témoin renvoie un booléen positif. La sentinelle interne
`source_sha=00…00` reste autorisée **uniquement comme contexte de preuve
de Phase 0** et de preuve d'indisponibilité Cawotte, où il n'existe
volontairement aucun export de guide réel. Cela ne certifie rien par soi-même.

### Reconnaissance stricte des collections de parcours (3 novembre 2026)

- Seuls `guides` à la racine, `steps` sous un guide identifié et
  `actions` sous une étape identifiée déclenchent la comparaison
  par ID/ordre. Des champs `steps`/`actions`/`guides` contenus dans
  des métadonnées, captures ou actions restent des **champs génériques
  à préserver** et ne sont pas interprétés comme de nouveaux parcours.
- Si une vraie collection de parcours change de type (liste remplacée
  par un objet, texte, etc.), un `TYPE_MISMATCH` demeure bloquant et
  le comparateur énumère aussi les guides/étapes/actions identifiables
  du côté resté valide. Les pertes ne sont pas masquées par l'erreur de type.
- Tests de non-régression fictifs ajoutés. Le schéma du lecteur Qt et
  les sauvegardes existantes ne sont pas modifiés.

### Contrôle des fichiers JSON entrants (3 novembre 2026)

- Les CLI indépendantes de comparaison AVANT/APRÈS et de prévisualisation
  rejettent maintenant les clés JSON dupliquées à **tous les niveaux**
  (`object_pairs_hook`), ainsi que `NaN`, `Infinity` et `-Infinity`.
  Une paire de clés `actions` conflictuelles n'est plus écrasée
  silencieusement par le parseur Python.
- Un export ambigu est refusé **avant** la création du dossier de
  rapports ou du fichier de prévisualisation (code de sortie 2).
- La lecture des JSON par des API Python recevant déjà des dictionnaires
  impose toujours au producteur de valider l'authenticité/provenance ;
  ces contrôles CLI ne constituent pas une certification ni une extraction.

### Rapport AVANT/APRÈS : conservation de la multiplicité

Les anomalies sont maintenant rapprochées par identité **et occurrence**.
Deux validations indépendantes peuvent diagnostiquer le même champ
avec le même code `UNVERIFIABLE` (ex. coordonnées malformées et absence
de position de déplacement vérifiée). L'ancien dictionnaire de
rapprochement écrasait une des observations ; le rapport
`before_after.json` conserve toutes les anomalies résolues,
persistantes ou introduites. Les compteurs sont testés contre
`compare(...).issue_count` avant et après, sans prétendre certifier
un guide ou une source.

### Vérification supplémentaire des flottants JSON

Le parseur Python accepte par défaut aussi des nombres JSON comme `1e9999`,
qu'il transforme en `inf` (sans déclencher le contrôle `parse_constant`).
Les deux CLI vérifient donc également `math.isfinite` pour chaque flottant
avec `parse_float`. Ce débordement est bloqué au même stade que les clés
dupliquées et `NaN`, sans écrire de sortie. Les tests utilisent uniquement
des nombres et des parcours fictifs.

### Découverte des outils par Doctor / catalogue IA — Phase 0

Les cinq moteurs `tools.atlas_guide_*` exposent désormais des
`TOOL_SPEC` statiques, lisibles par `tools.tool_catalog` sans import ni
exécution des moteurs. Leur rôle, coût, modes, périmètre `encyclopedia_guide`
et tests recommandés sont déclarés à la même source que le code.

- **Point d'entrée préféré :** `tools.atlas_guide_pipeline` pour l'avis
  de séquence en lecture seule via sa CLI. La fonction Python
  `stage_checked_candidate` reste réservée à un hôte de certification
  équipé d'un vérificateur de preuves indépendant.
- **Utilitaires spécialisés :** aperçu source, comparateur AVANT/APRÈS,
  interverrouillage séquentiel et magasin de candidats. La
  qualification `repo_mutation_explicit` des composants comportant une
  fonction d'écriture empêche de les traiter comme de simples
  diagnostics automatiques, même si leur CLI usuelle est plus restreinte.
  Le gate séquentiel seul est `read_only`.
- Une régression automatisée vérifie la reconnaissance par le parseur
  réel du catalogue et l'existence des tests déclarés. **La présence
  dans le catalogue n'est pas une preuve que Doctor exécute
  automatiquement ces fonctions**, ni une autorisation de publication,
  ni une validation Qt/Windows/DOFUS. L'intégration structurelle au lecteur
  reste soumise au Graphify du SHA exact et au cycle Doctor complet.

### Sélection du catalogue vérifiée avec un dépôt miniature

Un second test utilise l'API réelle `catalog(root)` et `select_tools()`
sur un arbre temporaire limité aux cinq outils. Il vérifie que le
point d'entrée `atlas_guide_pipeline` est préférentiel, que le verrou de
séquence en lecture seule est éligible à la découverte et que les deux
API d'écriture (pipeline et magasin) ne deviennent pas
`automation_ready` du seul fait de leur déclaration.
Ce test n'autorise aucune action d'écriture et ne parcourt pas tout le
dépôt à chaque exécution ciblée.

### Protection des API Python contre les nombres non JSON

Les CLI contrôlent déjà le JSON entrant. Les interfaces **Python**
`prepare_preview`, `compare`, `stage_checked_candidate` et
`publish_candidate` peuvent aussi recevoir directement des dictionnaires
fournis par un appelant, sans passer par le parseur CLI. Leurs points
de sérialisation canonique interdisent désormais `NaN`, `+/-Infinity`
et les objets non sérialisables avec `allow_nan=False`. L'importeur,
le pipeline et le magasin remontent leur erreur métier explicite ;
le comparateur échoue sans produire de faux `PARITY_CHECK_PASS`.
Aucun candidat ni fichier de rapports n'est écrit si ces frontières
de sérialisation échouent. Quatre tests de régression purement fictifs
couvrent ces cas.

### Lecture sécurisée du magasin de candidats

L'écriture refusait déjà les valeurs JSON non finies. Le lecteur interne
`selected_candidate` et la vérification de génération/rollback contrôlent
désormais aussi les fichiers **déjà présents sur disque** : clés
dupliquées (y compris dans les objets imbriqués), `NaN`,
`Infinity`, `-Infinity` et débordement `1e9999`. Un pointeur
`selected.json` altéré est rejeté, même si ses champs obligatoires
restent cohérents ; de même une génération dont le SHA-256 a été
recalculé sur un JSON ambigu. Aucun contenu n'est promu, certifié
ou chargé dans le lecteur pour contourner ces vérifications.

### Écriture, rollback et reprise de staging (11 novembre 2026)

Le magasin `tools.atlas_guide_candidate_store` reste un **staging local non
activable**, distinct de l'installation d'Atlas et des sauvegardes. Sur
`publish_candidate()`, le remplacement atomique du pointeur `selected.json`
est inclus dans la transaction surveillée : même si le remplacement a
effectivement réussi puis qu'une erreur d'E/S remonte, le magasin rétablit
l'ancienne sélection. Après écriture, il relit le pointeur exact, puis vérifie
la génération SHA-256 choisie. Le rollback `rollback_candidate()` applique
désormais les mêmes contrôles après sélection de la génération restaurée.

Si l'intégrité du résultat ne peut être prouvée, la tentative **échoue
sans annoncer SUCCESS**. Une restauration du pointeur initial est effectuée,
puis elle-même contrôlée. Si le disque empêche aussi cette restauration,
l'erreur exige une **revue manuelle** : ne pas utiliser la sélection comme
preuve, ne pas réactiver un guide ni supprimer des fichiers de staging
à l'aveugle. Une génération immuable restée sur disque ne constitue
ni une installation ni un certificat.

Suite synthétique de référence :

    py -3.13 -m unittest tests.test_atlas_guide_candidate_store -v

Les tests simulent une corruption après sélection, un `os.replace` ayant
réussi avant de lever une exception, une reprise normale et un échec de
récupération nécessitant une revue manuelle. Ils ne valident ni un installateur
Windows réel, ni la provenance des guides, ni le jeu DOFUS/Unity. GIMP-004
et GIMP-011 restent **PENDING** jusqu'à ces preuves supplémentaires.

### AVANT/APRÈS : identité d'anomalie liée au motif (3 novembre 2026)

Deux diagnostics différents peuvent partager `issue_code` et `field_path` :
par exemple « coordonnées malformées » et « position requise absente ».
Le rapport rapproche désormais les anomalies en incluant leur
`expected` (motif indépendant de la valeur observée), en plus de
l'identité guide/étape/action et du champ. Corriger un seul des deux
motifs ne peut plus marquer le mauvais diagnostic comme persistant.
Une quantité fautive qui passe de 8 à 9 garde son statut **persistant** :
le référentiel attendu reste 10. Deux tests synthétiques vérifient ces
cas sans intégrer ni certifier de guide réel.

### Test de capacité fictif : inventaire entier 95 / 7 705

La suite stdlib couvre désormais la création d'un inventaire **entièrement
synthétique** de 95 parcours, 7 705 étapes et 7 705 actions, avec des
identifiants stables et une répartition 82/81 étapes. Le test confirme
l'ordre, les totaux, le dernier `manual_stage_id` et le statut
`PREVIEW_ONLY_NOT_CERTIFIED`. Un second test compare la totalité de la
référence fictive puis modifie uniquement la **dernière action du dernier
guide** pour vérifier la détection exacte et l'inventaire intégral.
Ce test prouve un comportement sur données fictives, pas l'extraction
ou l'exactitude des 95 guides réels ; ce n'est pas non plus un benchmark
Windows ou un certificat de RAM.

### Destination du staging : protection du code source

Une destination de candidat explicitement fournie ne doit pas pouvoir
se trouver par accident dans `app/`, `tools/`, `tests/`,
`docs/`, `.github/`, `local_dofus_data/` ou à la racine du
checkout. Le magasin refuse désormais **tout emplacement situé à
l'intérieur du dépôt**, sauf un sous-dossier explicitement choisi sous
`artifacts/`. Les emplacements externes restent soumis aux protections
existantes contre les segments `.git`/`data`/`saves`, les symlinks,
les dossiers appartenant à des tiers et les écritures concurrentes.
Ces chemins sont contrôlés **avant** toute création de dossier ; des
tests fictifs vérifient le refus des sources et l'acceptation statique
d'un chemin d'artefact sans l'ouvrir ni y écrire. L'activation réelle
reste interdite par Phase 0.

### Protection homogène des sorties hors runtime (3 novembre 2026)

Les trois outils hors runtime (importeur, comparateur, magasin de candidats)
refusent les chemins contenant un segment `..` **avant toute création** :
`Path.absolute()` ne supprime pas ces segments et un chemin
`artifacts/../app/` pouvait autrement être interprété comme autorisé.
Les fichiers et rapports sont refusés sous le code source du dépôt
(`app/`, `tools/`, `docs/`, etc.). À l'intérieur du checkout,
seul un **sous-dossier dédié** de `artifacts/` est autorisé ;
le dossier `artifacts/` directement ne devient jamais un magasin.
Les sorties explicites hors du dépôt restent autorisées sous réserve des
contrôles existants (dossiers sensibles, symlinks, existence et conflits).
Les tests de sécurité utilisent uniquement des parcours synthétiques et
ne prouvent pas une activation ni une certification Windows/DOFUS.

### Lot de cohérence des actions et d'attestations figées (3 novembre 2026)

Les cartes source interdisent désormais qu'une action `travel`, `talk`,
`combat` ou `item` soit cachée dans le panneau exclusivement destiné aux
préparatifs. Inversement, une action `prepare` ne peut quitter ce panneau.
L'adaptateur et le comparateur indépendant appliquent cette règle, et
refusent les noms de quête vides/non textuels et les prérequis qui ne sont
pas des objets structurés non vides. Les champs métiers inconnus de ces
objets sont conservés sans interprétation inventée.

`stage_checked_candidate` exige que l'identifiant du prochain guide
soit celui vérifié par le gate séquentiel, et fige les empreintes de la
source, de la référence indépendante et des exports Atlas AVANT/APRÈS.
Une mutation de ces documents par un hôte de vérification, ou durant la
préparation, bloque le stockage. Ces empreintes sont des protections
contre les mutations involontaires, **pas** des certificats de source.

Tests ciblés : uniquement fixtures fictives, jamais de guide réel.
Le contrôle Graphify exact-SHA, la boucle `doctor agent plan/check/validate`,
la recette UI/Windows/DOFUS et la certification de Phase restent à faire.

### Test de bout en bout : 95 transactions synthétiques isolées (3 novembre 2026)

Le test de `tests.test_atlas_guide_pipeline` exerce désormais une chaîne
**entièrement fictive** de 95 transactions unitaires, avec sélection CAS,
empreintes de génération distinctes, attestations simulées par une fonction
explicitement marquée `test-only`, ordre du pilote et chaînage des
prédécesseurs. Il injecte une action fausse au 48e passage, confirme le
refus et l'absence de création/remplacement de génération, puis valide le
passage après correction de la fixture. La 96e demande reste bloquée.
La sélection de candidats n'active jamais de route dans le runtime et
ne modifie pas de progression de personnage.

**À ne pas confondre avec une preuve de certification :** ces 95 parcours,
leurs attestations et leurs étapes sont fabriqués par le test. Aucun des
95 guides réels n'a été extrait, comparé, certifié ni publié. La Phase 0,
Doctor agent/Graphify exact-SHA, l'UI Qt et la recette Windows/DOFUS
restent des contrôles distincts obligatoires.

## Phase 0 — limites de lecture et redirections Windows

Les trois outils de préparation utilisent désormais des lectures **bornées avant
le décodage** : 64 Mio par export de l'importeur et par snapshot du comparateur,
128 Mio par génération candidate, 16 Kio par pointeur/marqueur de stockage.
Un document vide, surdimensionné, mal encodé ou profondément imbriqué est
refusé sans publication, sans certification implicite et sans modification des
sauvegardes. Ces limites s'appliquent à l'outillage hors runtime : elles ne
signifient pas qu'un guide installé peut consommer autant de RAM.

Les dossiers de sortie rejettent aussi les **jonctions Windows**, en plus des
liens symboliques et des chemins protégés ; le comparateur refuse `.cache`.
Les tests utilisent uniquement des routes fictives, injectent de très petites
limites pour tester les rejets sans allouer 128 Mio et simulent les jonctions
sous Linux. Ils doivent être exécutés au SHA exact avant de déclarer ce lot
PASS. Aucun guide Ganymède n'est autorisé, importé ou certifié par ce durcissement.

## GIMP-004 — préparation du paquet à témoin indépendant (Phase 0)

Une étape de plus sépare le candidat prévisualisé du déploiement :
`tools/atlas_guide_package_publisher.py` prépare **un seul** paquet JSON
authentifié à partir d'une génération CAS encore sélectionnée. L’hôte doit
fournir un reçu indépendant final, lié au guide, aux empreintes de la source
et du fichier, au HEAD Git exact et à la référence du certificat. Le
vérificateur est interrogé plusieurs fois et la sortie est relue par le
chargeur canonique ; la moindre révocation ou corruption refuse le paquet.

Aucun répertoire existant n'est réutilisé ; les pannes d'écriture et
les redirections Windows sont testées avec des fixtures fictives. Les
données réelles et la progression des personnages ne sont pas touchées.
**Statut GIMP-004 : PENDING pour la publication/installateur réel et la
recette Windows/DOFUS.** Un résultat `PACKAGE_PREPARED_NOT_INSTALLED`
reste `certified=false`, `runtime_activation=false`, et ne doit
jamais être présenté comme une certification du pilote Cawotte.
