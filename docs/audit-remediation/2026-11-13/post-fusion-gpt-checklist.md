# DOFUS ATLAS — reprise après fusions (lot GPT du 13/11/2026)

**Source et périmètre** : [contrat #430](https://github.com/r9327/Dof-Atlas/issues/430) ; `main@76c0008bdfcbb8dca3315121496e5e52388e0b9f` au cadrage ; uniquement les 19 PR fusionnées/fermées du 6 au 13 novembre 2026.

**PR concernées** : #285, #292, #293, #325, #358, #371, #392, #394, #397, #398, #406, #407, #413, #415, #416, #420, #425, #426, #429. Aucune PR encore ouverte n'est auditéе ni terminée dans ce lot. Aucun travail sur l'UI globale/Guides/Opti V3 en cours ne doit être dupliqué.

## Règles de travail

- **DRAFT tant que le lot est en développement** ; CI ciblées locales/Doctor à chaque correction, *une* Phase Certification finale au SHA stabilisé et après revue des commits. Pas de fusion automatique.
- Première étape : vérifier l'état *actuel* sur main, les consommateurs et tests des éléments en cause, les statuts des exigences, puis l'impact des fusions ultérieures. Les cases DONE dans une PR sont des déclarations d'inventaire, pas une recette native.
- **Ne jamais corriger un écart supposé** : repro documentée, cause identifiée, test qui échoue avant et passe après, modification minimale. Préserver les services canoniques (hooks, Sender, MacroLock, Atlas Doctor, stockage) et les données utilisateur.
- Toute modification structurelle exige les vérifications et Graphify exact-SHA prévues par AGENTS.md ; toute modification non triviale suit le parcours Doctor `plan → check → validate`.
- Les tests Windows Qt synthétiques ne prouvent pas la réception des entrées dans le jeu DOFUS Unity.
- Les fichiers et états produits par l'application et les captures/logs sensibles ne sont pas commités ; uniquement des preuves expurgées et autorisées.

## Travail GPT — checklist de lots

### GQA-001 — Réconcilier les fusions [docs]
- [ ] Reconstruire un tableau pour chaque PR : contrat, statut historique, code actuel sur main, correctif postérieur éventuel, tests au SHA concerné.
- [ ] Requalifier individuellement les **29 PENDING + 2 DEFERRED historiques de #325** après les fusions #398, #406, #416, #425 et #429. Ne pas transformer PENDING en bug certain.
- [ ] Distinguer `CONFIRMÉ / PARTIEL / NON FAIT / NON VÉRIFIABLE` et `P0/P1/P2` avec preuve et lien.
- [ ] Retirer de la liste active ce que les PR fusionnées plus tard ont réellement corrigé.

### GQA-002 — Organizer, callbacks, sûreté [code et tests ciblés]
- [ ] Examiner `app/macros/mirror_input.py`, `app/macros/zaap.py`, `app/macros/auto_group.py`, `app/macros/input_tools.py`, `app/core/macro_lock.py`, `app/pages/organizer/organizer_ui.py`, ainsi que leurs consommateurs et tests actuels.
- [ ] Vérifier par instrumentation/test les conditions d'activation explicite du Miroir, Stop/Relancer, focus inconnu, DOWN/UP, absence de double émission, ordre du roster, identité du maître, persistance et prévention de doubles callbacks.
- [ ] Vérifier les signaux des boutons Macro/Miroir, Précédent/Suivant, raccourcis, Zaap, auto-groupe, vitesses et camembert ; **ne pas prétendre que le jeu a reçu un événement**.
- [ ] N'ajouter une correction et ses tests que pour une anomalie reproductible. Préserver l'interface approuvée de #429 et éviter toute nouvelle palette/thème local.

### GQA-003 — Craft et bundle [code et tests ciblés]
- [ ] Inspecter `app/pages/craft_page.py`, `app/craft_preload.py`, `local_dofus_data/` et tests existants.
- [ ] Confirmer le clic unique sur un métier, la priorité des vrais guides et le fallback honnête en leur absence ; vérifier le chemin `data/raw/json/gamosaurus/metiers_leveling.json` ignoré par Git.
- [ ] Contrôler les chemins et la présence des icônes en archive publiée (LFS), la recherche normalisée, l'ordre d'ajout, le scroll, Échap et la classification des armes.
- [ ] Corriger uniquement un bug vérifié ; n'inventer ni guides Gamosaurus ni quantité/XP ni source éditoriale. Les sources manquantes restent signalées explicitement.

### GQA-004 — Launcher V2 [code et tests ciblés]
- [ ] Revoir `app/distribution/install.py`, `launcher.py`, `health.py`, `archive_parts.py` et les contrats existants.
- [ ] Vérifier no-op (aucune installation sans changement), delta réseau, vérification SHA, rollback atomique, crash et mutex, progression et Home réellement interactive dans les limites des tests disponibles.
- [ ] Constater la limitation connue de `_copy_unchanged_verified` : sur volume sans clone CoW, le fichier inchangé est recopié dans le nouveau slot. Mesurer avant une proposition d'optimisation ; ne jamais substituer un hardlink mutable dangereux.
- [ ] N'altérer le moteur que si bug confirmé et test de régression disponible.

### GQA-005 — Doctor, CI, dépendances [code et tests ciblés]
- [ ] Vérifier l'intégration effective des correctifs #392, #394, #397, #413 et #426 sur le code actuel et les propriétaires de tests.
- [ ] Vérifier les pinning et exécutions des changements d'actions #292/#293/#371/#426, sans modifier ou relancer des workflows non concernés.
- [ ] Contrôler les décisions d'outillage #358 : sélection opt-in, absent=NOT_RUN, versions/provenance et exécution prouvée ; éviter les installations de 34 outils non nécessaires.
- [ ] Pour chaque CI revendiquée, vérifier le **SHA exact**, la conclusion, le workflow et la pertinence des tests ; aucune assimilation à un PASS DOFUS réel.

### GQA-006 — Preuves et retours [docs]
- [ ] Tenir une matrice `fonction → fichier → test → SHA → résultat → preuve → limites → propriétaire`.
- [ ] Consigner les retours de l'utilisateur : scénario, version, nombre de comptes, résultat OK/KO, symptômes, logs/screens expurgés.
- [ ] Rattacher chaque défaut confirmé à un correctif minimal et à un test ciblé ; si impossible de reproduire, marquer `NON VÉRIFIABLE`, jamais `FAIT`.

### GQA-007 — Sortie du lot [docs]
- [ ] Revue de chaque commit dans l'ordre et audit final du diff, des régressions, du respect du périmètre et du code actuel.
- [ ] Tests ciblés Doctor/Qt/CI pertinents, preuves du HEAD courant ; aucune preuve historique appliquée à un SHA différent.
- [ ] Phase Certification finale uniquement lorsque tout le code du lot est terminé, puis verdict `REVIEW OK / IMPROVEMENTS ADVISED / CHANGES REQUIRED`.

## Tests que l'utilisateur fera **plus tard** sur son PC (hors attestation automatique GPT)

La validation humaine est volontairement **NOT_RUN** tant que l'utilisateur n'a pas transmis un résultat. Ne pas refaire une liste de faux PASS et ne pas lui demander de tout tester d'un seul coup.

1. **DOFUS réel 2 puis 4/8 comptes** : activation Miroir uniquement sur commande, clic/double-clic/molette/clavier, perte de focus, Stop → Relancer, roue, Précédent/Suivant, maître après réorganisation et redémarrage.
2. **Zaap et Auto-groupe** : touche Espace ouvre le chat, texte envoyé et action reçue réellement.
3. **Trois vitesses** : comparer l'effet effectivement perçu, sans présumer Instantané imperceptible.
4. **Organizer visuel** : 8 slots, étoile décorative du premier, boutons/raccourcis/padding, ratio Personnages/Zaap, fond et débordements à taille normale. Comparaison de PNG exacts à viewport/DPI égal, cf. #424.
5. **Launcher installé** : zéro changement, mise à jour de quelques fichiers, interruption/rollback, Home réellement utilisable, cf. #287.
6. **Craft installé** : popup métier récolte/fabrication, images, armes, recherche, ajout/scroll/Échap, fallback sans guide éditorial, cf. #421.

**Format de retour suffisant** : `module | action | attendu | observé | nombre de comptes | Atlas SHA/version | capture/log si disponible`. GPT confirme la cause dans le code avant toute correction.

## État au premier commit

- Contrat et matrice de travail rédigés, **aucun correctif de code poussé**.
- **Aucun nouveau test exécuté**, aucune capture nouvellement générée, pas de certification Windows/Unity ou Phase revendiquée pour ce lot.
- Les rapports des PR fusionnées ne sont que des pistes initiales : la requalification de leur état sur main reste le prochain travail.
