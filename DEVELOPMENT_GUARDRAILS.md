# Dofus Atlas — Development Guardrails

Ce document est un **contrat de maintenance anti-régression**.

Il s'applique à toute modification du projet Dofus Atlas, qu'elle soit faite manuellement, par ChatGPT, Codex ou un autre agent de développement.

Le but n'est pas d'empêcher le projet d'évoluer. Le but est d'éviter qu'une amélioration locale casse silencieusement une règle globale, une donnée utilisateur, l'UI, le Guide Ultime ou le runtime Windows.

> **Règle principale : ne jamais remplacer une architecture existante ou une source de vérité sans avoir identifié ses consommateurs, ses données persistantes et ses tests.**

Le process permanent du projet privilégie les **micro-lots cohérents** : petit périmètre, une responsabilité principale, validation ciblée, diff relu, puis commit avant de passer au lot suivant.

---

## 1. Workflow permanent par micro-lot

### Avant de coder

Pour toute tâche non triviale :

1. Récupérer et vérifier le **HEAD réel** de la branche de travail.
2. Lire les fichiers actuels réellement concernés avant toute modification.
3. Rechercher leurs appels, imports et consommateurs, puis identifier la **source de vérité** actuelle.
4. Identifier les services canoniques existants à réutiliser avant d'en créer un nouveau.
5. Identifier les tests existants qui couvrent le comportement.
6. Vérifier si des données utilisateur persistantes ou un format disque sont concernés.
7. Définir le plus petit lot cohérent permettant d'avancer sans refactor parasite.

Pour un bug, identifier la cause racine avant de corriger le symptôme.

### Pendant le lot

- Garder un diff petit et lisible.
- Donner au lot une responsabilité principale.
- Ne pas lancer de refactor adjacent simplement parce qu'il serait « propre ».
- Ne pas dupliquer une source de vérité ou une logique métier existante.
- Réutiliser le service canonique quand il existe.
- Ne pas changer un format disque persistant sans migration ou compatibilité explicite.
- Préserver les données utilisateur et les contrats non concernés par la demande.

### Après le lot

1. Exécuter les tests ciblés adaptés au changement.
2. Relire le diff et retirer les modifications accidentelles ou hors scope.
3. Vérifier la compatibilité des données et de la persistence si elles sont concernées.
4. Documenter explicitement ce qui n'a pas pu être vérifié et la dette restante éventuelle.
5. Faire un commit clair et dédié.
6. Seulement ensuite commencer le lot suivant.

### Interdit

- Repartir de zéro alors qu'un système fonctionnel existe.
- Réintroduire un ancien système simplement parce qu'il est plus facile à appeler.
- Copier une logique déjà existante dans une deuxième implémentation parallèle.
- Modifier un format persistant sans migration ou compatibilité.
- Déclarer une fonctionnalité validée uniquement parce qu'un JSON se charge ou qu'un test superficiel passe.
- Mélanger une feature ciblée avec un grand nettoyage architectural non demandé.

---

## 2. Source de vérité du Guide Ultime

La source de vérité du Guide Ultime manuel est :

- `data/routes/guide_ultime_manual/manifest_v1.json`
- les chapitres canoniques référencés par ce manifeste.

Les anciens artifacts générés ne doivent jamais redevenir la source principale :

- `artifacts/guide_ultime_final.json`
- `artifacts/guide_ultime_gps_route.json`

Ils peuvent rester uniquement comme fallback de sécurité tant que le code de compatibilité existe.

### Règles obligatoires

- Le runtime, le Home et l'écran Guide Ultime doivent raconter la **même progression**.
- Le Home ne doit pas calculer sa progression principale depuis `guide_complet`.
- Le bouton `Continuer` doit revenir dans le Guide Ultime manuel, pas ouvrir une quête legacy au hasard.
- Les cartes manuelles doivent être identifiées par un identifiant stable dérivé de `manual_stage_id`.
- Un index numérique (`gps:12`, `page:gps:12`, position dans une liste) ne doit jamais être la nouvelle identité persistante d'une fiche manuelle.
- Toute migration d'une ancienne clé persistante doit être unidirectionnelle et préserver la progression existante.
- Une insertion ou un déplacement de fiche dans la route ne doit jamais déplacer une validation utilisateur sur une autre fiche.

### Données métier à préserver sous forme structurée

Quand elles existent dans le guide, les informations suivantes ne doivent pas être réduites uniquement à une phrase UI :

- prérequis durs ;
- gates runtime ;
- niveau personnage attendu ;
- métiers requis et niveaux de métiers ;
- ressources à préparer ;
- ressources à conserver en banque ;
- pods / anticipation de longues collectes ;
- pierres de capture / préparation Ocre ;
- étapes avant de quitter une zone ;
- conditions classe / alignement / ordre ;
- donjons, monstres et succès liés ;
- quêtes prises, progressées et terminées ;
- destinations et positions vérifiées.

Le texte est une **vue de rendu**. Il ne doit pas devenir la seule représentation de la logique du guide.

---

## 3. Règles de données Dofus

Ne jamais inventer une information Dofus.

Pour les données actuelles ou sensibles aux mises à jour :

1. Dofus Pour Les Noobs en priorité pour les parcours de quête.
2. Données locales Dofus Atlas / QuestProvider pour les identifiants et données structurées.
3. Sources officielles Ankama si nécessaire pour confirmation.

### Coordonnées GPS

Une ancienne coordonnée ne doit jamais être considérée vraie simplement parce qu'elle existe déjà dans le dépôt.

Avant d'introduire ou corriger une coordonnée importante :

- vérifier sa provenance ;
- la recouper quand nécessaire ;
- ne pas propager une coordonnée historique non vérifiée dans plusieurs fichiers.

---

## 4. Progression utilisateur et persistence partagée

La progression Quêtes / Succès / Guides et toute mutation métier partagée sont des données utilisateur critiques.

### Contrat de mutation

Toute mutation partagée doit suivre le principe :

`lock -> reload current -> mutate -> atomic write -> publish/invalidate -> unlock`

Le `publish/invalidate` doit rendre le nouvel état visible aux autres consommateurs ou invalider leurs caches/snapshots avant qu'ils continuent à travailler sur une ancienne génération.

Deux widgets ou services possédant chacun un ancien snapshot complet ne doivent jamais pouvoir s'écraser mutuellement.

### Obligatoire

- Écriture atomique des JSON persistants.
- Relecture de l'état courant sous coordination avant une mutation partagée.
- Sauvegarde d'un JSON corrompu avant fallback quand la donnée est importante.
- Aucune corruption silencieuse transformée en « réglages par défaut » sans trace.
- Compatibilité ou migration explicite lors d'un changement de format.
- La validation d'une quête doit continuer à pouvoir synchroniser les succès et les guides concernés.
- Un service canonique de persistence doit être utilisé lorsqu'il existe, plutôt qu'un write direct concurrent depuis une vue.

### Interdit par défaut

- `self.progress` chargé une fois puis réécrit beaucoup plus tard sans relecture.
- Whole-file write à partir d'un snapshot ancien sans coordination.
- Plusieurs services indépendants qui pensent chacun être la source de vérité.
- Écriture directe d'un fichier métier sensible depuis l'UI lorsqu'un service canonique existe.

Une exception d'écriture directe depuis l'UI doit être rare, documentée et couverte par des tests adaptés.

---

## 5. UI globale — règles obligatoires

Dofus Atlas doit rester une seule application visuelle, pas une collection d'écrans indépendants.

La référence globale est :

- `app/ui/theme.py`
- `app/ui/components.py`
- les composants partagés déjà présents.

### Avant de créer un style local

Toujours vérifier si le besoin peut être exprimé via :

- un token de `PALETTE` / `THEME_TOKENS` ;
- un `objectName` couvert par le stylesheet global ;
- un composant partagé ;
- une variante d'un composant existant.

### Interdit par défaut

- Nouvelle palette parallèle pour un seul écran.
- Couleurs hexadécimales copiées dans plusieurs vues.
- Gros `setStyleSheet()` local reproduisant boutons, cartes, bordures ou textes déjà gérés globalement.
- Réimplémenter un bouton/card/panel juste pour changer deux propriétés visuelles.
- Ajouter des tailles fixes pour masquer un problème de layout.

Une exception locale est possible uniquement si le style représente une sémantique réellement spécifique et non réutilisable. Dans ce cas, utiliser autant que possible les tokens globaux.

### Layout

- Utiliser les layouts Qt et les `QSizePolicy`.
- Tester les tailles de fenêtre raisonnables.
- Éviter clipping, overlap et scroll horizontal involontaire.
- Le scroll doit appartenir au contenu qui déborde, pas à toute la page sans raison.
- Une modification du thème global doit pouvoir se propager sans réécrire chaque écran.

---

## 6. Architecture — sources de vérité et dépendances

Direction cible :

`core métier pur -> services -> UI`

Cette direction est un objectif simple de maintenance, pas une invitation à créer une architecture « enterprise » ou des abstractions sans consommateur réel.

### Identité personnage — règle absolue

L'identité métier canonique d'un personnage est une clé stable de la forme :

`character:<id>`

Ne jamais utiliser comme identité métier :

- l'ordre d'affichage ;
- un slot Organizer ;
- un PID de processus ;
- un pseudo ;
- une position ou un index dans une liste.

`CharacterOrderService` est la source canonique de **l'ordre logique uniquement**. Son ordre, ses labels d'affichage ou les 8 slots historiques de l'Organizer ne doivent jamais devenir l'identité d'une progression, d'une quête, d'un succès, d'un équipement, d'un état réseau ou d'une autre donnée personnage.

Changer l'ordre des personnages ne doit jamais déplacer une donnée métier d'un personnage vers un autre.

### Sources de vérité métier

Une donnée métier importante doit avoir une source ou un service canonique identifiable.

L'UI :

- consomme les services et sources canoniques ;
- ne recalcule pas dans une vue une règle métier déjà portée par un service ;
- ne maintient pas une source de vérité concurrente ;
- n'écrit pas directement un fichier métier sensible lorsqu'un service de persistence existe, sauf exception documentée.

Avant de créer un nouveau service, vérifier qu'un service existant ne porte pas déjà le même contrat.

### Direction des dépendances

- Le core métier doit rester aussi pur que raisonnablement possible.
- Pas de dépendance Qt dans le core métier sans raison technique réelle et documentable.
- Les détails UI, Windows ou persistence doivent rester aux frontières adaptées quand ils ne font pas partie du domaine.
- Le `core` ne doit pas dépendre d'une grosse couche UI uniquement pour lire un réglage ou un JSON.

### Pour tout nouveau code

- Pas de nouvel `import *`.
- Pas de nouveau hack `sys.path` pour rendre un import invalide artificiellement fonctionnel.
- Pas de nouvel effet de bord Windows/Qt à l'import d'un module de données.
- Préférer des imports explicites.
- Extraire un service quand plusieurs écrans partagent réellement une logique métier.
- Ne pas créer un deuxième service qui fait presque la même chose que le premier.
- Ne pas créer une interface ou une abstraction sans besoin concret juste pour « préparer le futur ».

### Legacy

Un fichier n'est jamais supprimé uniquement parce qu'il s'appelle `legacy`.

La migration legacy suit cet ordre :

1. identifier la responsabilité utile et les consommateurs réels ;
2. extraire le plus petit bloc testable lorsque cela réduit réellement la dette ;
3. migrer les consommateurs vers le contrat canonique ;
4. tester le comportement migré ;
5. supprimer l'ancien code seulement quand **zéro consommateur réel** est prouvé.

La preuve de zéro consommateur doit considérer les imports, appels, wiring runtime et tests/fixtures pertinents. Ne jamais supprimer un gros fichier legacy uniquement pour « nettoyer » si son contrat n'a pas été extrait.

### Monkey-patches

Tout nouveau monkey-patch est interdit par défaut.

S'il est exceptionnellement nécessaire, il doit avoir :

- une raison documentée ;
- des tests ciblés ;
- un propriétaire clairement identifiable dans le projet ;
- un plan ou une condition de suppression explicite.

Préférer toujours, lorsque c'est possible, placer le comportement directement dans la classe ou le service canonique réellement exécuté.

---

## 7. Runtime Windows / hooks / macros

Les hooks clavier/souris sont du code critique.

### Cycle de vie obligatoire

Un hook basé sur une boucle Win32 bloquante doit avoir un arrêt déterministe :

- conserver l'identifiant de thread natif ;
- envoyer un message de sortie (`WM_QUIT`) ;
- unhooker ;
- joindre le thread ;
- empêcher un nouveau `start()` si l'ancien thread est encore vivant.

Tester au minimum :

`start -> stop -> start`

### Runtime

- Un warning facultatif ne doit pas rendre tout le runtime « en erreur ».
- L'état affiché doit correspondre à l'état réellement actif.
- Les callbacks de statut ne doivent pas être des no-op silencieux.
- Une erreur de macro doit rester diagnostiquable dans les logs.

### Capture réseau privilégiée

- L'interface principale, QtWebEngine, les hooks et les services de progression ne doivent pas être élevés uniquement pour capturer le réseau.
- Seul un helper minimal de capture passive peut demander l'UAC.
- Le helper élevé ne doit ni charger l'UI, ni muter la progression, ni écrire des données persistantes.
- Son IPC local doit être authentifié, borné, validé et ne jamais utiliser de désérialisation exécutable.
- Le helper doit être arrêté déterministement avec l'application et ne doit pas rester orphelin.
- La calibration et le runtime doivent partager le même helper par lancement afin d'éviter plusieurs demandes UAC.

---

## 8. Threads et préchargement

Tout worker démarré par l'application doit avoir un état terminal garanti.

### Obligatoire

- `try/except/finally` au niveau du worker quand nécessaire.
- Un résultat final ou un signal d'erreur doit toujours atteindre le consommateur.
- Pas de boucle d'attente infinie uniquement parce qu'une queue est vide.
- Les erreurs doivent être loggées ou remontées, pas avalées silencieusement.
- Le thread UI Qt ne doit pas effectuer du travail lourd évitable.

---

## 9. JSON / cache / SQLite

### JSON

Pour les données persistantes utilisateur :

- écriture atomique ;
- corruption sauvegardée ;
- schéma/version quand le format est amené à évoluer.

### Cache

Un cache reconstructible ne doit pas utiliser une désérialisation exécutable.

**Ne pas réintroduire `pickle` pour les caches chargés automatiquement.**

Préférer JSON, JSON compressé ou un autre format non exécutable.

### SQLite

Pour une base utilisée en runtime :

- `foreign_keys = ON` si approprié ;
- WAL quand plusieurs accès sont possibles ;
- `busy_timeout` raisonnable ;
- transactions cohérentes ;
- migrations explicites avant les changements de schéma.

### Backup SQLite

Si une DB fonctionne en WAL, ne pas faire un simple `copy2()` du fichier principal pendant que la connexion est active.

Utiliser `sqlite3.Connection.backup()` ou une stratégie de checkpoint sûre.

---

## 10. Launcher / installation

Le lancement normal de Dofus Atlas doit être reproductible et autant que possible offline.

### Interdit

- `pip install` à chaque lancement normal.
- Mise à jour automatique de pip au démarrage.
- Télécharger puis exécuter un installateur sans vérification d'intégrité.

### Séparation attendue

- **Launcher normal** : vérifie l'environnement et lance l'application.
- **Bootstrap/réparation** : installe uniquement si nécessaire.

Les versions de dépendances critiques doivent être pinées pour éviter qu'un lancement futur installe une combinaison différente sans changement de code.

---

## 11. Git et fichiers générés

Ne pas versionner les déchets runtime.

Par défaut, exclure :

- logs runtime ;
- caches ;
- `__pycache__` / `.pyc` ;
- backups locaux ;
- fichiers temporaires ;
- artifacts générés non destinés à devenir une source de vérité.

Ne pas modifier ou supprimer une règle LFS sans vérifier pourquoi elle existe.

Ne jamais faire de `git reset --hard` vers une autre référence ou de suppression massive sur une branche partagée sans comprendre l'impact.

---

## 12. Tests minimum par type de changement

Les tests ciblés adaptés au micro-lot sont obligatoires dès qu'un comportement exécutable est modifié. Un lot purement documentaire n'invente pas un résultat de test : il utilise le statut `NOT RUN` lorsqu'aucune exécution n'est pertinente.

### Progression / persistence

Tester :

- lecture ;
- écriture ;
- deux instances concurrentes ;
- corruption ;
- migration éventuelle ;
- rechargement après écriture.

### Guide Ultime

Tester :

- identité stable d'une fiche ;
- migration des anciennes clés ;
- Home et écran Guide sur la même progression ;
- insertion/reorder sans déplacer les validations ;
- choix d'Ordre ;
- conditions classe/alignement si touchées ;
- source `manifest_v1.json` active.

### UI

Quand l'environnement le permet :

- construction offscreen ;
- écran affecté ;
- navigation ;
- resize ;
- interactions principales ;
- absence de régression sur l'écran voisin.

### Runtime Windows

Tester autant que possible :

- démarrage ;
- arrêt ;
- redémarrage ;
- absence de thread dupliqué ;
- état badge/status cohérent.

### Base de données

Tester :

- migration depuis ancien schéma si concerné ;
- transaction ;
- intégrité ;
- backup si modifié ;
- concurrence/timeout si concerné.

---

## 13. Tests / CI — politique de statut

Deux niveaux de validation restent souhaités quand l'infrastructure est disponible :

1. CI globale de l'application pour les changements généraux.
2. CI spécialisée Guide Ultime pour ses données, services, vues et audits spécifiques.

Pendant les micro-lots, les **tests ciblés sont la validation obligatoire** du comportement touché. La full suite est exécutée lorsque l'infrastructure et les runners nécessaires sont disponibles.

Ne jamais réduire le scope de la CI globale pour accélérer une modification locale sans comprendre ce qui ne sera plus couvert. Un changement de persistence, runtime, launcher, DB ou core ne doit pas dépendre uniquement de la CI spécialisée Guide Ultime.

### Statuts à employer

- `PASS` : test ou validation réellement exécuté et réussi.
- `FAIL` : test ou validation réellement exécuté et échoué.
- `NOT RUN` : test ou validation non exécuté.
- `BLOCKED` : exécution empêchée par une contrainte d'environnement ou d'infrastructure identifiée.

**Ne jamais appeler `FAIL` un test qui n'a pas été exécuté.**

Une baseline rouge préexistante ne bloque pas automatiquement un micro-lot si :

- les validations ciblées du changement sont exécutées ;
- l'absence de nouvelle régression liée au changement est établie ;
- les échecs préexistants restent clairement identifiés comme baseline/dette connue et ne sont pas présentés comme de nouveaux résultats.

L'indisponibilité de runners ne justifie pas de modifier la CI globale dans un lot sans rapport.

---

## 14. FEATURE CHECK — checklist réutilisable

Avant de considérer un micro-lot prêt à être commité :

- [ ] HEAD réel vérifié.
- [ ] Fichiers actuels et consommateurs pertinents inspectés.
- [ ] Source de vérité identifiée.
- [ ] Service canonique existant réutilisé, ou absence justifiée.
- [ ] Aucune identité personnage basée sur ordre / slot / PID / pseudo / position de liste.
- [ ] Aucun write métier direct inutile depuis l'UI.
- [ ] Aucun monkey-patch ajouté, ou exception complètement documentée.
- [ ] Aucun format persistant modifié sans migration/compatibilité explicite.
- [ ] Tests ciblés exécutés, ou statut `NOT RUN` / `BLOCKED` explicitement indiqué.
- [ ] Compatibilité données/persistence vérifiée si concernée.
- [ ] Diff relu et sans refactor parasite.
- [ ] Dette ou limitation éventuelle documentée.
- [ ] Aucun code/workflow temporaire oublié.
- [ ] Commit clair et dédié.

Les garde-fous spécialisés des sections précédentes restent applicables en plus de cette checklist courte.

---

## 15. Ordre de priorité quand plusieurs problèmes existent

Toujours privilégier :

1. perte/corruption de données utilisateur ;
2. incohérence de source de vérité ;
3. bug runtime / thread / hook ;
4. migration et persistence ;
5. fiabilité DB / cache / launcher ;
6. tests et CI ;
7. architecture et découplage ;
8. homogénéisation UI ;
9. nettoyage cosmétique.

Ne pas faire une grosse refonte visuelle ou un nettoyage de code pendant qu'un problème de progression ou de persistence connu reste dangereux.

---

## 16. Definition of Done commune

Une feature ou un refactor n'est terminé que si :

- [ ] le comportement demandé est implémenté ;
- [ ] la source de vérité concernée est identifiée ;
- [ ] aucune nouvelle duplication métier n'a été introduite ;
- [ ] les tests ciblés nécessaires sont ajoutés/actualisés et leur statut réel est reporté ;
- [ ] aucune régression connue liée au changement ne reste non traitée ;
- [ ] la persistence et les données existantes restent compatibles, ou une migration explicite existe ;
- [ ] l'identité `character:<id>` est préservée si des données personnage sont concernées ;
- [ ] aucun code temporaire ou workflow temporaire n'est oublié ;
- [ ] le diff final est relu ;
- [ ] le commit est propre et dédié ;
- [ ] toute dette restante est explicitement documentée.

Un code qui compile, un JSON valide, une route qui s'affiche ou un test isolé qui passe ne suffisent pas à eux seuls à satisfaire cette Definition of Done.

---

## 17. Fichiers à lire en priorité selon la zone

### Guide Ultime

- `data/routes/guide_ultime_manual/manifest_v1.json`
- `app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py`
- `app/modules/encyclopedia/services/guide_ultime_runtime_service.py`
- `app/modules/encyclopedia/views/guide_ultime_manual_view.py`
- `app/pages/home_page.py`

### Progression

- `app/modules/encyclopedia/services/quest_progress_service.py`
- `app/modules/encyclopedia/services/achievement_progress_repository.py`
- `app/modules/encyclopedia/services/serialized_achievement_progress_service.py`
- `app/modules/encyclopedia/services/guide_progress_service.py`
- `app/core/json_store.py`

### Personnages

- `app/services/character_order_service.py`
- les services qui portent les clés stables `character:<id>` pour le domaine concerné.

### UI

- `app/ui/theme.py`
- `app/ui/components.py`
- l'écran concerné et les écrans analogues.

### Runtime

- `app/core/runtime_state.py`
- `app/input/hotkeys.py`
- `app/input/mouse_hooks.py`
- `app/input/managed_hooks.py`

### Données locales

- `local_dofus_data/data_store.py`
- `app/cartography/world_db.py`

### Démarrage

- `Dofus_Atlas.bat`
- `bootstrap_dofus_atlas.ps1`
- `requirements-pyside.txt`

---

## 18. Dette connue — baseline mise en pause

Cette section est un **snapshot de dette préexistante connu à la fin du grand ménage**. Elle sert à ne pas confondre cette dette avec une nouvelle régression.

Ce n'est **pas** le résultat d'une nouvelle exécution de tests de ce document. Une entrée historique marquée rouge ne doit pas être présentée comme un `FAIL` courant si elle n'a pas été réexécutée.

Baseline connue mise en pause :

- 56 `FAIL/ERROR` préexistants dans la dernière baseline concernée ;
- crash Windows préexistant sur le test d'image ;
- audit Guide Ultime prerequisite order rouge ;
- audit Guide Ultime final success coverage rouge ;
- monkey-patches encore présents ;
- `app/modules/encyclopedia/views/guides_view_legacy.py` encore actif ;
- legacy Succès encore partiellement actif via le moteur de progression historique.

### Politique sur cette dette

- Ne pas la corriger opportunistement dans un lot sans rapport.
- Ne pas la compter comme nouvelle régression sans preuve qu'un changement récent l'a modifiée ou aggravée.
- Lorsqu'un lot touche directement une de ces zones, établir une validation ciblée et comparer au comportement de référence disponible.
- Lorsqu'une dette est réellement supprimée, mettre à jour cette section dans le même changement afin qu'elle ne devienne pas une fausse baseline éternelle.

---

## 19. Simplicité de l'architecture

Ces garde-fous doivent rester applicables au quotidien.

Ne pas introduire uniquement pour respecter ce document :

- un nouveau framework interne ;
- une multiplication d'interfaces abstraites ;
- des couches « enterprise » sans besoin concret ;
- de nouveaux dossiers sans responsabilité réelle ;
- une règle qui oblige à du boilerplate sans protéger un contrat du projet.

La bonne solution reste la plus petite solution cohérente qui respecte les sources de vérité, l'identité stable, la persistence et les consommateurs existants.

---

Ce fichier doit évoluer avec l'architecture. Lorsqu'une ancienne règle n'est plus pertinente, la modifier dans le même changement qui remplace proprement le système concerné. Ne jamais laisser le code et le contrat de maintenance raconter deux architectures différentes.
