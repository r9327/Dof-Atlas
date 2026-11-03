# Atlas Guide Conformity — clean candidate

Status: prototype under development. No certification is claimed.
Clean branch: feat/atlas-guide-importer-clean-20261102, created at main@060803282269098dfc6919e6e85f24309d2c485f.
No commit, file, module or runtime code from abandoned PR #337 was imported.
The original PR #363 has not yet been moved to this branch.

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

## Remaining mandatory checks (not done)

- Build an authorized real-source extractor for all 95 guides and every step.
- Validate independence and completeness of each source, then per-guide compliance.
- Add one secure transactional publisher with crash recovery, no bypass.
- Attach only to already-existing main UI services without copying PR #337.
- Run Doctor/Graphify at exact SHA before any structural or destructive changes.
- Run repository tests, Qt/Windows/DOFUS manual verification, benchmarks and CI.
- Complete GIMP-001 through GIMP-011 and exact-SHA delivery evidence.

Current proof: GitHub clean branch creation and ancestry review only.
Local Doctor, Graphify and automated tests remain NOT_RUN in this session.


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
    py -3.13 -m tools.atlas_guide_importer --source authorized_export.json --output preview.json

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

L'extracteur de source externe, le publieur protégé/transactionnel,
la preuve Graphify exact-SHA et la recette Windows/DOFUS ne sont pas livrés :
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
