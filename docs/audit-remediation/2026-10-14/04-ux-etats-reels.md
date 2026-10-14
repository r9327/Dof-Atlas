# [PLAN 04] UX honnête Bestiaire, Équipement et Craft (AT-007/022/023/027)

> PLAN PRÉPARATOIRE — aucun correctif applicatif implémenté ici. PR DRAFT à compléter en code et tests ciblés avant revue/fusion.

Audit source : PR #160, SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`. Branche de base : `main` ; éviter de mélanger les modifications de PR #159 et #138.

## Objectif
Supprimer les parcours silencieusement vides ou annonçant une réussite fictive.

## Dépendances et ordre
Indépendant ; ne pas confondre état Bestiaire explicite et livraison complète d’un Bestiaire.

## Constat et preuves détaillées
### AT-007 — Les quatre entrées Bestiaire ouvrent des onglets vides
- Priorité / état : P1 / CONFIRMÉ / main.
- Localisation : main.py:965 menu Bestiaire; app/modules/encyclopedia/constants.py:6 onglets Bestiaire; app/modules/encyclopedia/views/encyclopedia_page.py:245 création des slots; app/modules/encyclopedia/views/encyclopedia_page.py:265 ensure_tab_loaded; app/modules/encyclopedia/views/encyclopedia_page.py:451 on_search_changed.
- Cause : DONJONS, MONSTRES, ARCHIMONSTRES et AVIS DE RECHERCHE sont proposés par la navigation, mais aucun constructeur de vue ne remplace leurs EncyclopediaLazySlot. La recherche commune reste visible sans consumer pour ces widgets.
- Preuve audit : ui-probe.json : pour chacun, QWidget sans layout ni enfants ; capture bestiary-empty.png inspectée. Catalogue vide injecté pour isoler le shell ; le code de chargement ne contient aucune branche Bestiaire, quel que soit le contenu du catalogue.
- Correction du registre : Correction immédiate minimale : état «module en préparation» explicite, recherche désactivée, retour/navigation cohérents. La construction d’un vrai Bestiaire constitue ensuite un lot fonctionnel distinct fondé sur les données existantes, pas une fusion opportuniste de widgets.

### AT-022 — L’ouverture du navigateur annonce un succès en cas d’échec
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/pages/equipment_page.py:91 EquipmentPage.open_huzounet.
- Cause : La valeur booléenne de QDesktopServices.openUrl est ignorée ; le message «Huzounet ouvert» est toujours affiché.
- Preuve audit : reproductions.json/external_browser_failure : openUrl retourne False, statut de succès malgré tout. Le navigateur réel n’a pas été lancé dans cette probe.
- Correction du registre : Distinguer le retour vrai/faux et afficher une erreur actionable ; conserver Huzounet externe et la page légère volontaire.

### AT-023 — Craft peut être déclaré prêt avec un catalogue absent
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/craft_preload.py:37 build_compact_craft_preload; app/pages/craft_page.py:590 CraftPage.hydrate_runtime; main.py:2192 collect_preload_result.
- Cause : Le preload absent renvoie items=[], _prepared=true, _lazy_items=true, _skipped_reason et errors=[]. hydrate_runtime accepte la liste vide et annonce «Craft prêt». Le shell traite errors, mais pas _skipped_reason. L’absence de données n’est donc pas un état terminal explicite.
- Preuve audit : pr159-worker-data-probes.json : catalogue absent et aucune erreur ; conditions hydrate_runtime/collect_preload_result relues. Le cas d’un catalogue présent mais volontairement sans sélection doit rester READY.
- Correction du registre : Séparer résultat prêt et indisponible à la frontière existante ; propager le motif absent/vide en UI, avec retry après restauration. Ne pas déclencher un gros import SQLite sur le thread Qt pour cacher l’absence.

### AT-027 — Les suppressions de sélection Craft sont étiquetées seulement x
- Priorité / état : P3 / CONFIRMÉ / main.
- Localisation : app/pages/craft_page.py:919 CraftPage.refresh_selection.
- Cause : Le bouton AtlasButton("x") n’ajoute ni tooltip ni accessibleName qui explique quelle ligne sera supprimée. Le nom de l’objet apparaît dans la ligne, mais le contrôle lui-même reste ambigu au lecteur d’écran.
- Preuve audit : Composition du widget relue : la quantité a un tooltip, le bouton delete n’en a pas et ne définit pas de libellé accessible spécifique.
- Correction du registre : Tooltip «Retirer <nom> de la sélection» et accessibleName équivalent ; conserver le bouton compact et le comportement actuel.

## Implémentation attendue
1. Bestiaire : chaque entrée Donjons, Monstres, Archimonstres, Avis de recherche affiche une indisponibilité explicite tant qu’aucune vue métier n’est chargée.
2. Empêcher recherche/spinner non opérationnels ; préserver Home et le shell Encyclopédie lazy.
3. Équipement : propager false/échec QDesktopServices.openUrl au lieu de signaler systématiquement un succès.
4. Craft : déclarer READY uniquement après présence/validation du catalogue ; proposer retry/diagnostic sinon.
5. Remplacer les boutons x de suppression Craft par libellé accessible/tooltip avec navigation clavier.

## Validations ciblées
- [ ] scénario Qt quatre entrées Bestiaire, retour Home
- [ ] test QDesktopServices.openUrl false
- [ ] Craft dataset absent/corrompu puis retry
- [ ] test focus/tooltip du bouton supprimer

## Critères de sortie
- [ ] Aucun onglet vide présenté comme fonctionnalité prête.
- [ ] Échec ouverture navigateur visible et gérable.
- [ ] Craft ne passe plus READY sans dataset utilisable.
- [ ] Contrats lazy/Qt et retour Home non régressés.

## Garde-fous communs
- Conserver toutes les fonctionnalités, les sources JSON et le comportement lazy sauf correction justifiée.
- Vérifier HEAD réel, git status et diff avant de coder. Aucun refactor de masse fondé sur le seul degré Graphify.
- Faire tests ciblés pendant le développement ; FULL uniquement à la certification si la policy l'exige.
- Recouper les observations avec les preuves de PR #160 ; distinguer CONFIRMÉ, PROBABLE, NON CONFIRMÉ.
- Mettre à jour AI Context avec son générateur après code, puis preuve exacte-SHA.
- Pas de merge automatique de cette PR préparatoire.

Sources : [rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) ; [registre anomalies](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
