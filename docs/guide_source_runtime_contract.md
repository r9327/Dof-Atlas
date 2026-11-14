# Imported Guide runtime contract — PR #363 / Phase 0

Status: **architecture and synthetic proof only**. No source guide is
automatically installed, registered or certified. This document defines the
runtime boundary for the eventual one-by-one certified import.

## Ownership and memory

- `tools.atlas_guide_pipeline` stages source documents **outside** the app.
  A candidate is SHA-pinned, read-only, `NOT_CERTIFIED`, and non-active.
  The staging pipeline cannot write into user Guide progress.
- `app/modules/encyclopedia/services/guide_shared_route_contract.py`
  projects one authored source guide into canonical card sections, preserving
  source action/step IDs. No runtime app module imports a `tools` module.
- `ImportedSourceManualRuntimeService` consumes **one explicitly supplied**
  already-projected route without opening the V5 generated artifacts or
  `guide_ultime_manual` manifest. It copies that one route into its own
  memory; **do not construct this service for all 95 guides at startup**.
- `ManualRouteGuidesView` accepts an optional map of explicitly supplied
  source services and a trusted per-route approval callback. The default map
  is empty, and without a callback, construction or selection fails closed.
  Existing `guide_complet` and `dofus_sylvestre` routing is unchanged.
- `SharedGuideManualView` remains the only renderer. It uses the same
  preparation, copy/travel, NPC, combat and navigation components as the two
  optimized guides; no second reader is allowed.

## Source progress and validation

- One Guide identity: `source_guide:<guide_id>`.
- One stable stage identity: `source:<guide_id>:<source_step_id>`.
- One character identity: `character:<id_dofus>`.
- `GuideProgressService` alone owns atomic persistence and multi-character
  compare-and-swap. The source service **never** writes under
  `guide_ultime_v5` or `catalog_manual:dofus_sylvestre`.
- A quest mentioned by an authored step is **not** sufficient automatic proof
  that the step is finished. Source automatic completion is disabled until
  guide-specific, independently verified evidence becomes available.
- A step with `hard_runtime_gates` is blocked unless its **own guide-specific
  evaluator** explicitly approves it for that particular character.
  A missing, failing or unqualified evaluator is not success.
- Both the manual progress setter and the shared multi-character validation
  button recheck runtime authorization on each write. Revocation must not
  leave a stale clickable page able to mutate progress.
- Locked progress navigation, preparation status and other manual states
  remain scoped to the source Guide's own progress identity.

## Exact trust boundary

The authorizer is injected by **trusted application composition**, not by a
candidate's `certified` field, a source JSON file, an exported URL or the
end-user Guide catalogue. Its future implementation must verify independent
certificate evidence against the exact packaged route bytes and block
withdrawn/invalid attestations.

A callback returning `True` in synthetic tests is **test scaffolding**, not
a production certificate. Until the verification/publishing owner exists,
do not wire `imported_source_services` into the production `EncyclopediaPage`
composition and do not expose unverified source routes on the Home catalogue.

Opening an authorized route by ID is implemented. **Home listing of certified
source entries, section ordering (Dofus, Alignment, Islands, Dimensions,
Events) and the public certificate loader are NOT implemented.** Do not mark
that scope complete based on synthetic navigation tests.

## Repeatable evidence

Targeted, source-only tests (Python 3.13):

```powershell
py -3.13 -m unittest -v tests.test_guide_imported_manual_runtime_service
py -3.13 -m unittest -v tests.test_guide_imported_manual_runtime_ui.ImportedSourceRouterQtTests
py -3.13 -m unittest -v tests.test_guide_manual_selected_validation.ImportedSourceSharedManualUiTests
```

The first suite belongs to the lightweight Scoped PR Feedback owner. Both
Qt suites run on Windows in the reused focused Doctor UI proof. Run
`tools.atlas_doctor agent plan/check/validate` on changed paths, consult
Graphify for the **exact final HEAD**, and carry out the complete
Phase Certification/Windows/DOFUS evidence only when the architecture and the
first pilot Guide are ready. Neither a successful stdlib suite nor an offscreen
Qt proof is final Guide certification.

## Pilot and scaling gates

1. Finish trusted certificate loader and Home catalogue mapping, with no
   global startup hydration.
2. Validate the source reader with one **fictional** projected route, including
   team validation/undo, prerequisites, and disabled authorization.
3. Only when the entire toolchain is ready, take one small real pilot guide
   (Cawotte or Dokoko), compare authored actions and displayed Guide against
   the source line-by-line, and refine the independent certificate until it
   verifies the actual in-app content at 100%.
4. Import each remaining authorized route **one by one**. No next guide until
   extraction, projection, display and per-guide certification are all 100%.
5. Preserve the two optimized existing routes and the Phase 8 RAM requirements;
   measure RAM only after the Guide is functionally complete.

## P0 GIMP-019 — coordinate copy versus opt-in Zaap

The shared Guide row has two independent actions. Clicking the bold `[x,y]`
always copies `/travel x,y` to the clipboard, whether or not Organizer's
travel callback is configured. It must never dispatch the character macro.

A compact cached local Zaap pictogram sits beside the displayed coordinate.
Only that icon tries an optimized route. On click, the shared UI asks the
trusted current Guide service for an optional
`plan_verified_zaap_travel((x, y), selected_character_keys)`. The result
must be the existing `GuideTravelPlan` with `ZAAP_THEN_TRAVEL`, an exact
matching destination, and exactly the connected selected characters. The
existing two-command Travel macro callback is invoked **only** when those
conditions hold. Missing route evidence, unavailable planner, unconnected
participants, a non-Zaap/direct plan or mismatched destination always
copies the classical `/travel x,y` instead; no fictitious Zaap is chosen.

The plan provider is an **optional, explicitly trusted composition input**:
this PR has not established any live verified Zaap/character-position
registry for imported guides. Do not treat the Qt icon or a synthetic test
callback as proof that an optimized route can be used in production.
Route planning is on-demand at click time and is never run while rendering
the Guide. The original optimized guides retain their shared renderer.

Focused contract tests:
`tests.test_guide_manual_selected_validation.ImportedSourceSharedManualUiTests`
(clipboard-only classic click, independent icon/fallback, verified synthetic
`GuideTravelPlan`, no planning during render). Run with Doctor
`agent plan/check/validate` and include Windows/DOFUS interaction proof
before marking GIMP-019 PASS. Status until then: **PENDING / NOT_RUN**.

## Shared UI / Dev UI styling and bounded reader lifetime

The developer UI gallery in PR #365 (`app/pages/dev_ui_page.py`,
`app/ui/ui_registry.py`) is the **visual reference** for Guide controls:
Unity tokens, typography, icons, button states, badges, breadcrumbs,
scrolling, panels, spacing and hover/focus behavior. PR #363 must keep
using `SharedGuideManualView`, `AtlasButton` and the existing global Qt
stylesheet; no Guide-specific parallel palette or second style system. The
styling rollout remains owned by #365, which is not yet merged; this
architecture change intentionally does not cherry-pick its QSS or widgets.

A source Guide reader is now cached only while that source route is active.
Selecting another source, an existing optimized/legacy route, going Home,
or losing authorization releases the previous source reader from the Qt stack
with deferred deletion. Reopening reconstructs the same **shared renderer**
from the explicitly injected service and independently checked authorization.
The optimized Guide Ultime/Sylvestre readers are not evicted. This bounds
retained *Qt reader* instances, not the caller-provided source services: the
composition owner must still avoid constructing 95 source services at startup.
No guide is certified or activated by this lifecycle optimization.

## Factories de services vérifiées à la demande (Phase 0)

L'installateur futur peut fournir explicitement à `EncyclopediaPage`
`imported_source_factories={source_guide_id: factory}`. Chaque fabrique
est une fonction sans argument qui retourne un `ImportedSourceManualRuntimeService`
avec exactement le même identifiant canonique. Aucun parcours n'est créé
pendant l'affichage de l'accueil. Lorsqu'un guide est sélectionné, sa fabrique
est appelée uniquement pour lui, puis le contrôle indépendant
`imported_source_authorizer` doit rendre littéralement `True` avant
l'ouverture. Un refus, une exception ou une identité erronée échoue fermé,
sans repli sur une autre route. L'Encyclopédie refuse un registre de
fabriques sans authorizer dès sa construction ; les identifiants et types
sont contrôlés lorsque le routeur Guides est créé, avant toute fabrique.

Le service construit à la demande est libéré avec son unique lecteur Qt lors
d'un retour à l'accueil, changement de guide ou retrait d'autorisation.
Les services explicitement injectés restent la propriété de l'appelant.
Attention : une closure de fabrique qui capture toutes les routes réelles
annulerait ce gain mémoire ; le futur fournisseur doit lui-même conserver un
index de métadonnées léger sans précharger les données des 95 guides.

Ce mécanisme n'effectue aucune découverte des dossiers locaux, ne certifie
aucun contenu et n'active aucun guide Ganymède réel. La preuve actuelle
porte uniquement sur des fixtures fictives ; l'autorisation indépendante
et la recette native Windows/DOFUS restent obligatoires.

## Paquet installé attesté — frontière de confiance (Phase 0)

`app/modules/encyclopedia/services/guide_trusted_source_package.py`
fournit une passerelle **optionnelle**, sans Qt et sans import du dossier
`tools/`, entre un répertoire de guides packagés par un éditeur de confiance
et les factories explicites introduites ci-dessus. Ce n'est **pas** un
certificateur : aucune instance n'est automatiquement branchée dans `main.py`
ni créée par les données utilisateur. Le registre contient uniquement les
métadonnées indépendantes `GuidePackageEntry(guide_id, filename, sha256,
source_sha256, head_sha, certificate_ref)`. Aucun guide n'est lu pendant
l'ouverture d'Atlas.

À la sélection explicite, le chargeur vérifie le fichier JSON avec une limite
de 16 Mio, refuse les chemins de traversée, liens symboliques et jonctions
Windows, exige l'empreinte SHA-256 **exacte des octets installés**, refuse
les clés JSON dupliquées et NaN/Infinity, contrôle l'identité canonique et
impose `source_compliance=NOT_CERTIFIED` dans le contenu. Une **preuve externe**
est impérative via
`witness(guide_id, file_sha256, source_sha256, build_head_sha,
certificate_ref) is True`.
Cette fonction doit appartenir à la composition de confiance, reconnaître
les justificatifs indépendants de droits/provenance, la source exacte et les
preuves complètes (Windows/DOFUS) avant d'accepter une certification réelle.
Ni le JSON ni son SHA seul ne peuvent fabriquer cette preuve.

Le composition owner peut ensuite transmettre
`imported_source_factories=package.factories(quest_progress,
achievement_progress, guide_progress)` et
`imported_source_authorizer=package.authorize` à `EncyclopediaPage`.
Le callback d'autorisation vérifie le contenu mémorisé contre l'instantané
approuvé et reconsulte l'attestation indépendante à chaque écriture, pour
refuser une révocation ou une modification de route entre deux clics.
Les fixtures de tests utilisant un témoin booléen ne constituent PAS une
vraie certification et ne doivent pas être copiées dans la composition
production. Le registre de certificats, la signature, la livraison réelle,
le catalogue public et la qualification de Cawotte restent **PENDING**.

Régression ciblée : `tests.test_guide_trusted_source_package` (faux exports
uniquement), plus le test Qt sur la révocation de l'attestation dans
`tests.test_guide_imported_manual_runtime_ui`. Ces suites sont ajoutées
au workflow Phase 0 Windows avec rapport exact-SHA ; une PR non fusionnée
ne constitue pas une preuve d'exécution.

### Conservation fidèle des actions à l'ouverture

Le chargeur reconstruit aussi chaque fiche via
`project_authorized_guide` à partir des étapes originales embarquées,
puis exige une égalité de tous les champs du JSON projeté. Un dossier
authentifié avec une fiche modifiée (texte, ordre, sections, prérequis,
actions ou coordonnées cachées) est refusé, même si l'attestation
synthétique accepte son empreinte. Cette comparaison structurelle ne
remplace pas la vérification humaine indépendante contre Ganymède.

## Empreintes de source, HEAD exact et remplacement de fichier

L'entrée externe `GuidePackageEntry` porte obligatoirement deux autres
empreintes : `source_sha256` (export autorisé) et `head_sha` (code exact
ayant fait l'objet des preuves). L'application fournit séparément le
`build_head_sha` issu de ses métadonnées de livraison **de confiance** :
une différence bloque la construction du chargeur, avant la lecture du guide.
Le témoin indépendant reçoit le quintuplet
`(guide_id, file_sha256, source_sha256, build_head_sha, certificate_ref)`.
La source, le code et le paquet doivent tous être vérifiés par l'autorité
externe ; un SHA-256 en lui-même ne prouve aucune autorisation.

Le lecteur réévalue désormais l'empreinte des octets installés à chaque
autorisation. Un fichier modifié ou remplacé après son ouverture bloque
également l'écriture de progression, sans relancer la route ou importer
un autre guide. Cette lecture bornée peut avoir un coût I/O et doit être
mesurée sur une vraie installation avant certification. La fonction témoin
de tests est synthétique : son retour `True` ne certifie jamais la source.

### Révocation pendant la construction du lecteur

Un contrôle d'autorisation peut réussir avant de créer une vue Qt puis être
révoqué avant l'affichage effectif. Le routeur recontrôle donc **le service
associé à la vue réellement créée** et détruit uniquement ce lecteur si le
second contrôle refuse. Un guide source différent, déjà actif et autorisé,
reste affiché ; aucun lecteur refusé ne persiste en cache. Si une factory
échoue, elle est appelée une seule fois par tentative de sélection : on
ne relit pas le même paquet en échec pendant le traitement de l'erreur.
Des tests Qt fictifs couvrent les trois scénarios.

### Retrait irréversible des services créés à la demande

Lorsque le routeur libère une instance de service issue d'une factory,
il la marque `retired` et coupe définitivement son callback
d'autorisation. Même si un composant Qt détient temporairement une
ancienne référence avant `deleteLater()`, les clics tardifs ne peuvent
plus enregistrer d'étape. La même instance ne peut pas être réautorisée :
la factory de confiance doit créer un **nouveau service** lors d'une
réouverture. Les services injectés explicitement par l'appelant conservent
leur propre cycle de vie et ne sont pas retirés par cette règle.

### Correction du workflow Phase 0 au SHA exact

Les journaux de la CI du commit `7fdfc04` ont révélé deux défauts
de **montage des tests**, pas de preuve que les données réelles sont
validées :

- Linux : le test pure Python était lancé par
  `-m unittest tests.test_guide_trusted_source_package`, ce qui importe
  `tests/__init__.py` et donc PySide6, volontairement absent du job
  stdlib. La fixture est maintenant autonome et lancée via
  `unittest discover -s tests -p 'test_guide_trusted_source_package.py'`.
- Windows : trois tests du cycle de vie des routes source appelaient
  `show_home()`, qui déclenchait aussi le chargement réel du catalogue
  Quest (fichier `quest_categories.json` absent sur le runner).
  Ces tests conservent la transition Home et la libération réelle des
  lecteurs ; ils isolent uniquement `refresh_home()` via un mock dont
  l'appel est vérifié. Ils ne prétendent pas tester le catalogue Quest.

Les tests de la véritable intégration des données, du rendu Windows et
du jeu DOFUS restent des preuves distinctes et bloquantes.

### Injection des évaluateurs propres à chaque guide

Le paquet de confiance accepte maintenant une table explicite
`gate_evaluators={guide_id: callback}` dans `factories(...)`.
Elle est fournie **par la composition de confiance**, jamais par l'export
JSON, et chaque ID doit appartenir au registre de guides attestés.
Une valeur non callable ou un guide étranger est rejeté avant toute
lecture. Les callbacks reçoivent `(character_key, canonical_card_copy)`
et ne peuvent satisfaire un prérequis qu'en renvoyant exactement
`True`. Sans évaluateur qualifié, tout `hard_runtime_gates` reste
bloquant, y compris après ouverture du guide. L'autorisation
indépendante est reconsultée au moment de l'écriture et peut encore
révoquer une progression dont les prérequis seraient satisfaits.

Ce raccordement **ne fournit pas** un évaluateur métier Ganymède
certifié et n'active aucun guide. Les politiques de prérequis spécifiques,
leurs sources de vérité, et leur recette Windows/DOFUS restent à
implémenter et qualifier guide par guide. Des fixtures fictives
vérifient le raccordement et l'isolation par personnage.

### Zaap — raccordement du service importé sans trajet inventé

`GuideTrustedSourcePackage.factories(..., zaap_planners={guide_id: planner})`
accepte désormais uniquement un callback qualifié provenant de la
composition de confiance, pas du contenu source. Le service importé expose
`plan_verified_zaap_travel(destination, participant_keys)`, appelé **au clic
sur l'icône Zaap** par le lecteur partagé. Il demande le plan au fournisseur
et revérifie l'attestation indépendante avant et après l'appel. Absence,
exception, révocation ou fermeture du guide : retour `None` et repli
existant sur la copie de `/travel`. Le lecteur partagé garde l'autorité
de vérifier `GuideTravelPlan`, la destination, le mode Zaap et l'équipe
connectée avant toute commande.

La fabrique ne constitue **pas** la base de Zaaps vérifiés ; aucun trajet
réel n'est inscrit, ni aucune macro déclenchée sans click explicite.
Le fournisseur réel et la recette Windows/DOFUS de GIMP-019 demeurent
PENDING. Les tests ne fournissent que des routes fictives.

## Préparation transactionnelle d’un paquet par guide (GIMP-004, Phase 0)

Le module `tools.atlas_guide_package_publisher.prepare_attested_guide_package`
est une API **réservée à l’hôte de confiance**, sans commande CLI et sans
intégration automatique dans l’application. Il exige une sélection CAS
`expected_selected` encore valide, **un seul guide complet**, une identité
`source_guide:<id>` explicite et le témoin de certificat final indépendant
`witness(guide_id, file_sha256, source_sha256, build_head_sha, certificate_ref)
is True`. Le témoin est reconsulté avant et après la préparation.

Le fichier JSON est borné à 16 Mio et recontrôlé avec
`GuideTrustedSourcePackage`, qui reconstruit les fiches depuis les actions
sources originales : une modification de rendu ne peut pas être masquée par
l'empreinte seule. La sortie est **un nouveau répertoire dédié uniquement**,
avec création exclusive, publication du fichier via remplacement atomique,
relecture et suppression sur échec contrôlé. La sortie ne peut écraser ni
un paquet préexistant, ni le magasin des candidats, ni les sources Git, ni
les sauvegardes. Le code rejette les chemins redirigés ou les jonctions.

Le retour `PACKAGE_PREPARED_NOT_INSTALLED` conserve expressément
`certified=false` et `runtime_activation=false` : **aucun guide n'est
installé ou enregistré dans le catalogue**. Un vrai propriétaire de
publication devra fournir la racine de confiance indépendante, les reçus
révocables, les métadonnées de version du build et la procédure Windows
avec rollback avant toute mise en service. Les tests utilisent un témoin
synthétique explicitement fictif et ne certifient aucune source Ganymède.

Régressions ciblées : `tests/test_atlas_guide_package_publisher.py`,
`tests/test_atlas_guide_candidate_store.py` et
`tests/test_guide_trusted_source_package.py`. Le workflow Guides Phase 0
collecte les tests `test_atlas_guide_*.py` sur Linux au SHA exact ; la
qualification Windows/DOFUS réelle reste `NOT_RUN`.
