# Organizer — Miroir expérimental, issue #321

**État : interface, clics, clavier court et molette séquentiels intégrés, NON certifiés.**
Compatibilité Windows/Dofus réelle NOT_RUN (issue #322).

## Interface
- Dans la carte Macro : sélecteur compact Macro | Miroir sur le titre.
- Macro est le mode par défaut ; Miroir désactive et grise les quatre macros classiques.
- Action rapide : Auto-groupe, Sélection personnage puis Vitesse de script.
- Troisième carte Contrôles : Relancer scripts et Debug côte à côte ;
  Stop urgence en dessous sur toute la largeur.
- Même ligne de trois cartes, aucun panneau Miroir supplémentaire.

## Source et destinataires automatiques
- Filtre de processus Organizer/Miroir : `UnityWndClass` seule ne suffit pas.
  L'exécutable doit être identifié par un chemin Windows absolu `Dofus.exe`.
  La détection automatique d'Organizer et chaque destination Miroir refusent
  les processus inconnus. Les autres noms nécessitent un test Windows réel.
- Source : exclusivement le favori explicitement étoilé dans Organizer,
  réellement détecté et au premier plan ; jamais le premier slot par défaut.
- Cibles : toutes les autres fenêtres Unity connues d'Organizer, maximum
  huit fenêtres. Sans favori explicite, aucun clic n'est intercepté.
- Le moteur existant SwitchClickMacro recopie SEQUENTIELLEMENT les clics
  physiques sur le favori, y compris la source dont le hook consomme le clic
  original, une fois par fenêtre ; mêmes SendInput, MacroLock, arrêt d'urgence,
  conversion des coordonnées et vérification des fenêtres.
  Pas de second moteur d'injection, pas de PostMessage non attesté.
- Le hook ignore les clics synthétiques. Il ne doit jamais intercepter les
  clics sur d'autres applications ou d'autres fenêtres du jeu.
- Un changement d'étoile favorite rafraîchit l'index et le runtime.
- Le mode est mémorisé dans le profil sous __organizer_macro_mode.
  Les raccourcis classiques sont désactivés à la source dans le registre,
  les préférences restent intactes et Stop urgence reste actif.

## Manques et preuves obligatoires
- Gestion pure du cycle clavier : `MirrorHeldKeys`, `mirror_key_transition` et
  `mirror_release_all_keys` couvrent les répétitions et relâchements orphelins
  dans des tests dédiés ; ce **planificateur de maintien n'est pas branché**.
- Les touches courtes et la molette sont raccordées au hook/sender séquentiel.
  Les touches maintenues de façon continue et les mouvements/glisser-déposer
  restent non supportés : le repli séquentiel change de focus et ne peut garantir
  les mêmes séquences DOWN/MOVE/UP à tous les clients.
- PostMessage ciblé en arrière-plan et compatibilité réelle avec Unity
  NON PROUVÉS ; pas de diffusion simultanée annoncée.
- Scénarios 1/2/4/6/8 fenêtres en jeu et mesures p50/p95/p99 : NOT_RUN (#322).
- Exigences MIRR-001/002/003/004/005 et certification indépendante non
  closes : PR Draft. Ne pas fusionner avant implémentation et preuves finales.


## Raccordement incrémental des entrées discrètes (PR #325)

- Le hook clavier existant route les **touches brèves sans modificateur**
  seulement si le favori DOFUS Unity est au premier plan. Il exclut les
  raccourcis système (Ctrl/Alt/Win/Shift), le Stop urgence, les répétitions
  et les événements synthétiques. Une touche physique interceptée est
  rejouée comme un appui + relâchement, jamais comme une touche maintenue.
- Le hook souris existant route les crans de molette verticaux et horizontaux,
  avec signe et position relative du curseur. L'envoi utilise SendInput,
  pas PostMessage ni un deuxième injecteur.
- Le moteur MirrorInputMacro utilise le verrou de macro, le favori exact,
  la liste figée des clients DOFUS, la validation avant chaque activation,
  l'arrêt d'urgence, la libération des touches dans finally et le retour
  au favori après une diffusion. Les clics gardent le moteur existant.
- **Toujours non supportés :** touches maintenues répliquées comme un maintien
  continu, raccourcis combinés, glisser-déposer, mouvements de souris en
  continu, diffusion réellement simultanée/en arrière-plan. Le mode
  séquentiel avec changements de focus ne peut garantir ces comportements.
- **Statut de validation** : tests de simulation ajoutés et tests clavier/molette
  restaurés après audit ; aucune exécution Python/Windows certifiée au HEAD final.
  Recette Windows / DOFUS Unity #322 : NOT_RUN. Les p50/p95/p99 des étapes de diffusion
  sont journalisés, pas des mesures de rendu Unity.

- La télémétrie `delivery_step_ms` mesure chaque étape d'envoi (incluant
  les durées d'appui et positionnements), et non le temps brut de `SendInput`
  ni la latence de rendu Unity. Le statut distingue une diffusion complète
  d'une diffusion interrompue.

## Correctifs de fiabilité ajoutés le 03/11/2026 — non certifiés

- Auto-groupe : recontrôle de la fenêtre avant chaque invitation, élimination
  des destinataires en double, retour au favori sous `finally` sauf Stop
  d'urgence ou focus volé, reporting complet / partiel / interrompu.
- Switch personnage : ne pas publier un succès d'activation tant que le
  HWND cible n'est pas effectivement au premier plan, ni après Stop.
- Switch déplacement : distinguer les cibles traitées des cibles ignorées,
  sans assimiler une commande `SendInput` au comportement visible du jeu.
- Switch clic et Miroir : vérifier le focus juste avant chaque injection ;
  cesser immédiatement la diffusion si le focus a changé et ne pas
  reprendre le focus de l'utilisateur au cours d'un abandon.
- En cas de **refus de démarrage** du Switch clic classique, ne pas
  consommer l'événement physique original. Ce correctif ne résout PAS le
  cas distinct d'un geste bloqué alors qu'une macro est déjà active.
- Les résultats Miroir `terminé / partiel / interrompu` correspondent à
  l'émission des entrées, jamais à la confirmation que Unity les a traitées.
- Des tests simulés couvrent plusieurs scénarios 2/4/6/8 et les échecs
  de focus / arrêt / gestes partiels. Ils restent **non exécutés** tant
  qu'aucun checkout Python complet n'a permis Doctor et le runner ciblé.

### Transfert de code depuis la PR #365 : fichiers déplacés, essais manquants

Les 25 critères Organizer/Macro/Zaap et les cinq améliorations transversales
sont dans le contrat #321 et la PR #325. Les modifications du Switch clic
physique classique (DOWN/UP natif sur le favori, réémission uniquement sur les
autres fenêtres), les hooks de relâchement, les contrôles de molette et les
tests ont été regroupés dans la branche #325. Le diff de #365 contient
désormais **seulement six fichiers UI globale**.

La séparation des sources est réalisée ; **elle n'est pas une certification**.
Les correctifs du clic natif et de l'architecture des hooks doivent encore
passer Graphify au SHA exact, Doctor/tests ciblés, audit d'intégration et
recette réelle Windows/DOFUS Unity.

Le critère utilisateur est un **ressenti proche entre 2 et 8 comptes**,
à établir par comparaison sur le même PC et les mêmes gestes, avec
pertes/doublons, p50/p95/p99 de bout en bout, temps de retour au maître,
CPU/RAM et résultats visibles Unity. Le moteur séquentiel ne peut
garantir une latence strictement identique pour 2 et 8 clients.

## Continuation P0 du 03/11/2026 — latence et focus

- `MirrorInputMacro` compare l'ordre et l'identité des HWND à partir de
  l'inventaire mémoire à chaque client (coût linéaire, pas de nouvelle API).
  Avant la **première émission**, toutes les cibles sont authentifiées par
  Windows comme DOFUS Unity, puis chaque destinataire est revérifié juste
  avant l'entrée. Un changement de favori, d'ordre ou de liste interrompt
  la diffusion.
- Les vérifications natives de processus passent théoriquement d'un coût
  quadratique à un coût linéaire : au plus `2N+1` vérifications pour un
  cycle clavier complet sur N fenêtres, sous le chemin nominal testé par
  mocks. Aucun gain réel en millisecondes n'est annoncé sans bench Windows.
- Le Miroir ne restaure ni focus ni curseur après activation refusée,
  exception Win32 ou vol de focus après repositionnement de la souris.
  Le dernier client n'ajoute plus de délai de changement de fenêtre inutile.
- `SwitchClickMacro` traite également l'exception d'activation sans
  restaurer le focus ou repositionner le curseur chez l'utilisateur.
- Un premier correctif **isolé** de la PR #365 est porté dans
  `app/windows/clicks.py` : si un temps de survol est demandé, il
  intervient après le déplacement effectif du pointeur (et avant DOWN).
  Deux tests mock du délai et de l'arrêt sont ajoutés à
  `tests/test_organizer_sendinput.py`.
- Tests de non-régression ajoutés sur la diffusion clavier 2/4/6/8,
  l'ordre du roster, les cibles étrangères, l'échec d'activation, la
  perte de focus avant molette et les exceptions Win32.

**Limites non levées :** les hooks et le clic physique sont regroupés
dans #325 et retirés du diff de #365, mais leur comportement combiné reste
non testé sous Windows. Graphify exact-SHA, Doctor/tests Python, rendu
DOFUS réel et ressenti 2 à 8 : **NOT_RUN**.

## Instrumentation focus et recettes multi-comptes (03/11/2026)

- Les journaux Miroir distinguent les durées `focus_activation_ms`
  (demande d'activation d'une fenêtre) de `delivery_step_ms` (envoi
  de l'événement sur la cible) et `worker_total_ms` (durée du worker).
- Les percentiles p50/p95/p99 sont issus d'échantillons réels de
  `perf_counter` pendant la session, mais **n'attestent ni du rendu du
  jeu ni du délai complet de l'événement physique capturé par le hook**.
- Tests simulés 2/4/6/8 fenêtres : le Miroir vérifie un roster figé,
  authentifie les processus au départ et avant chaque destinataire ;
  le compteur de contrôles natifs du chemin nominal clavier est borné
  à `2N+1` pour N clients, plutôt que répété à chaque tour.
- Une exception Win32 d'activation, un focus volé ou un refus du dernier
  envoi ne doit pas afficher de faux succès ni réactiver la mauvaise
  fenêtre. La molette ne se diffuse plus si le focus a été perdu après
  déplacement du pointeur.

**Preuves manquantes** : tests Python réellement exécutés, benchmark CPU/RAM
et p50/p95/p99 sous Windows sur la même machine avec 2/4/6/8 comptes,
réactions observées dans Unity, validation d'intégration des
hooks transférés, Graphify exact-SHA, audit final et certification.

## Favori placé hors du premier slot (03/11/2026)

- La capture clavier/molette ordonne maintenant les destinataires à partir
  du personnage **étoilé**, quelle que soit sa position dans Organizer ;
  les autres suivent leur ordre relatif d'origine.
- La vérification rapide du roster compare cet ordre normalisé avec les
  slots réels sans scanner tous les processus Windows à chaque destinataire.
  Les validations natives des processus et du focus avant chaque envoi
  restent inchangées.
- Tests simulés 2/4/6/8 fenêtres : favori situé en dernier slot, pas de
  doublon, ordre des émissions et rejet des changements de composition
  de l'équipe. **Aucun test Windows/Unity réel n'a été exécuté.**

## Fiabilité ciblée des entrées, nouvelle série de commits — 03/11/2026

- Le hook souris donne priorité au couple physique déjà **consommé**
  DOWN/UP, avant tout callback de relâchement du clic natif : impossible
  de transmettre à Unity un UP d'une paire dont le DOWN a été avalé.
  Un UP synthétique ne décharge jamais cette paire physique.
- `send_client_click` vérifie toujours la fenêtre au premier plan
  pendant l'attente de survol Unity, avant DOWN et avant le second
  DOWN d'un double-clic. Un vol de focus ou un Stop annule l'envoi,
  avec libération de l'entrée déjà tenue dans le `finally` canonique.
- Les callbacks Miroir clavier/molette consultent désormais uniquement
  la fenêtre connue et authentifiée au premier plan si une macro est
  déjà occupée. Les entrées reçues hors du personnage favori avant
  démarrage sont rejetées avant le scan des processus Windows.
  Les clics provenant d'applications étrangères suivent le même chemin
  rapide et ne déclenchent aucun scan du roster complet.
- Le diagnostic des événements physiques **effectivement bloqués**
  signale un DOWN avec un warning borné (0,4 s). Les nombreux MOVE ne
  peuvent plus masquer ces warnings. Ce warning est la preuve d'une
  entrée non diffusée, **pas** une solution à la saturation.
- Un clic natif déjà transmis à un unique personnage contourne
  désormais totalement la création d'un worker Switch clic et le
  blocage temporaire de la souris ; aucune injection ni modification
  du curseur n'est nécessaire.
- En cas d'échec d'activation de tous les clients, le Switch clic
  n'impose plus de retour au favori : aucune cible activée ne justifie
  de reprendre le focus utilisateur.
- Tests mock ajoutés : ordre et appariement du DOWN/UP, arrêt et perte
  de focus pendant survol/double-clic, entrées étrangères sous
  2/4/6/8 comptes, clic natif unique, saturation signalée et absence
  de restauration du focus sans cible.

**Reste P0 — non résolu :** un clic reçu pendant un worker Miroir actif
peut encore être bloqué globalement avant d'atteindre le gestionnaire.
Ne pas annoncer zéro perte, diffusion immédiate, ni une file de replay
testée. L'éventuelle file bornée de gestes, avec contrôle du destinataire,
expiration, dédoublonnage et annulation au Stop, exige une analyse
Graphify exacte et des tests Windows/Unity avant changement de structure.

**Preuves :** commits GitHub et code relu, mais Doctor
`agent plan/check/validate`, Graphify, tests Python et essais sur PC
DOFUS 2/4/6/8 **NOT_RUN** faute de checkout complet. PR Draft.


## Correction des faux événements synthétiques et des releases — 03/11/2026

**Constat code** : le hook souris traitait aussi les événements physiques
survenant durant une temporisation résiduelle après `SyntheticInputGuard`
comme s'ils étaient synthétiques. Un clic ou cran de molette très rapide,
effectué une fois le worker terminé, pouvait donc ne pas être diffusé.
Windows fournit dans `MSLLHOOKSTRUCT.flags` l'indicateur documenté
`LLMHF_INJECTED` et Atlas marque ses propres `SendInput` dans
`dwExtraInfo` (`ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO`).

**Nouveau comportement ciblé** :
- Un `DOWN` ou cran de molette réellement **physique** reçu après la fin
  du blocage de souris peut atteindre le callback même si une ancienne
  fenêtre temporelle de garde synthétique est encore active.
- Les événements réellement injectés, identifiés par le flag Windows
  ou le marqueur Atlas, sont toujours exclus de la duplication.
- `InputState.is_mouse_blocked()` demeure prioritaire pendant un worker
  actif. **Les gestes physiques sous ce blocage peuvent encore être perdus** :
  ce correctif ne revendique ni replay sous saturation, ni file d'attente.
- Le moteur ne génère plus de `UP` souris ou clavier isolé après un
  `DOWN` refusé par Windows. Si un bouton synthétique déjà pressé
  n'a pas pu être relâché, une seconde tentative a lieu ; l'échec de
  cette tentative est enregistré explicitement.
- Échec de diffusion clavier/molette ou vol de focus pendant le survol :
  aucun retour forcé au favori, ni repositionnement du curseur sans
  fenêtre cible validée. Les replays natifs annulés émettent une cause
  bornée (`expired`, `emergency_stop`, `worker_busy`,
  `drag_or_moved`, `focus_changed`, `source_untrusted`,
  `mode_changed`, `dispatch_refused`).

**Scénarios mock ajoutés** : second clic physique dans la fenêtre
résiduelle synthétique, clic réellement injecté avec flag/marqueur,
blocage réel actif, refus de DOWN ou UP (premier/second clic),
relâchement clavier même sous Stop, source native et glisser-déposer,
annulation de replay et diagnostic, vol de focus pendant le survol.

**Validation Windows/Unity non exécutée** : ces tests sont ajoutés au
dépôt mais n'ont pas été exécutés ici. Aucun résultat de performance
CPU/RAM, p50/p95/p99 ou succès d'interaction Unity n'est attesté.
Rester Draft. La file bornée éventuelle des gestes durant un worker
reste une décision structurelle bloquée jusqu'à Graphify exact-SHA et
Doctor agent plan/check/validate.


## P0 — Geste reçu pendant une diffusion active (03/11/2026)

**Constat vérifié dans le code, pas encore reproduit sur DOFUS Unity** :
`MouseHook._mouse_proc` bloque les événements physiques tant que
`InputState.is_mouse_blocked()` est vrai. Ce blocage évite un clic dans
une mauvaise fenêtre pendant les `SetForegroundWindow`/SendInput
séquentiels, mais **peut perdre un geste du joueur**. Une file de
relecture différée n'est pas actuellement sûre sans qualification des
cibles, expiration et preuve que l'action a encore un sens.

**Correctifs ciblés effectués dans l'architecture existante :**

- Si un `DOWN` physique est bloqué pendant la diffusion, son `UP`
  associé reste bloqué même lorsque le worker termine entre les deux.
  Ce principe couvre boutons gauche, droit, milieu et X, y compris
  l'arrêt d'urgence qui vide le blocage. Les `UP` injectés ne peuvent
  pas libérer un `DOWN` physique réservé.
- Deux `DOWN` reçus avant le `UP` attendu (même bouton ou boutons
  différents) annulent le replay natif devenu ambigu. Les pressions
  source restent physiques ; **aucun geste ambigu n'est recopié**.
- Le mapping des paires `DOWN/UP` est statique : le hook ne recrée
  pas de dictionnaire par événement `WM_MOUSEMOVE`, important lorsque
  la souris se déplace pendant une diffusion à plusieurs clients.
- À l'arrêt du hook Windows, les paires physiques réservées restent
  protégées jusqu'à la désinstallation effective du hook ; elles ne sont
  nettoyées qu'après. Le premier avertissement du prochain démarrage
  n'est pas supprimé par un ancien délai de throttling.
- Le hook compte **tous** les `DOWN` et crans de molette physiquement
  bloqués, y compris ceux qui n'ont pas produit d'avertissement à cause
  du seuil de 400 ms. Un relevé cumulatif apparaît dans les logs à
  fréquence bornée, puis une dernière fois à l'arrêt du hook. Les
  mouvements de souris et relâchements ne sont pas faussement comptés
  comme de nouveaux clics. Aucune coordonnée n'entre dans cette
  télémétrie.
- Tests mock : appuis superposés, `UP` après disparition du blocage,
  `UP` synthétique, Stop urgence et comptage des rafales 2/4/6/8.
  **Tests rédigés mais NON EXÉCUTÉS ici.**

**P0 restant à développer/qualifier** — restitution d'un clic sous
saturation sans le déclencher trop tard, sur la mauvaise fenêtre ou
deux fois. Avant de modifier la structure du dispatcher/hook ou
d'introduire une file, le contrat `GRAPHIFY.md` impose la carte
Graphify **au SHA exact**, l'analyse des consommateurs, un plan Doctor
puis les tests ciblés. La carte n'était pas disponible dans cette
session GitHub et le checkout local du dépôt n'était pas accessible :
**pas de file de replay risquée introduite**.

**Recette requise :** Windows/DOFUS Unity 2/4/6/8, rafales et holds,
Stop au milieu, déplacement du focus vers une application tierce,
compter actions visibles, clics/roulettes bloqués, doublons, p50/p95/p99
du geste complet, CPU/RAM et usage du favori. **Aucun PASS revendiqué**.


## P0 — Relâchement natif et application tierce, 04/11/2026

Deux anomalies ciblées ont été corrigées **sans créer de file ni modifier
l'architecture des hooks** :

- Si l'utilisateur a pressé un bouton physiquement **avant** le lancement
  du worker, puis le relâche pendant le blocage du Miroir, cet UP sans
  DOWN consommé est désormais transmis. Le hook continue à bloquer tout
  UP dont il a réellement intercepté le DOWN, y compris après un Stop.
  Boutons couverts : gauche, droit, milieu et X.
- Pendant l'intervalle entre la prise de `MacroLock` et l'activation du
  blocage souris, un raccourci Switch actif n'absorbe plus un clic destiné
  à une autre application. La fenêtre au premier plan, sa position sous
  le pointeur et son identité DOFUS sont vérifiées avant interception.
  **Limite :** si `InputState.is_mouse_blocked()` est déjà actif, le
  filtrage global précède toujours le callback runtime ; le problème
  de saturation MIRR-007 n'est pas résolu par ce garde supplémentaire.

Les tests de non-régression comprennent les quatre types de boutons,
les UP associés à des DOWN consommés, la molette et les clics en
application étrangère. Le comportement réel Win32/Unity reste NOT_RUN.

La prochaine étape structurelle de MIRR-007 requiert toujours Graphify
sur le SHA exact, Doctor puis tests et recette Windows 2/4/6/8 pour
garantir l'absence de clics différés dangereux ou doublonnés.


## Reprise P0 du 04/11/2026 — sécurité dans les fenêtres de transition

- **UP natif antérieur à un worker :** un bouton pressé avant le démarrage
  du Miroir peut être relâché pendant un blocage sans laisser le bouton
  coincé. Seuls les UP d'un DOWN réellement intercepté par le hook sont
  avalés ; les événements marqués injectés conservent leur exclusion.
- **Fenêtre entre verrou et blocage :** quand `MacroLock` est déjà pris,
  mais qu'`InputState` ne bloque pas encore, le Switch ne consomme un
  clic qu'après contrôle du HWND actif, de la fenêtre sous le pointeur
  et de l'identité DOFUS Unity. Les clics sur les autres applications
  restent natifs.
- **Rafales instrumentées :** un test de non-régression emprunte le vrai
  chemin `MouseHook._mouse_proc` avec 2/4/6/8 DOWN/UP et crans de
  molette, puis simule un Stop et un clic neuf. Les compteurs de gestes
  bloqués doivent correspondre aux événements physiques observés.
- **Statut réel :** tous ces tests sont écrits, mais non exécutés sur
  un runner Windows avec DOFUS. Ils ne prouvent pas une interaction
  Unity réussie ni un débit de 8 personnages.

### Décision de sécurité : aucune file active sans graphe certifié

La carte Graphify du SHA exact de #325 n'est pas accessible dans cette
session GitHub. Le workflow `Graphify Code Map` n'est pas déclenché par
les simples pushes sur la PR : `workflow_dispatch` et
`workflow_call` uniquement. Faute d'artefact ou de checkout local,
le contrat `GRAPHIFY.md` interdit une refonte structurelle.

Une file future doit impérativement : conserver le couple DOWN/UP ;
limiter et horodater chaque geste ; vérifier favori, identité du
processus, HWND sous le curseur, génération de roster et focus avant
l'injection ; être annulée au Stop ou au changement de mode ; ne
jamais rejouer un geste périmé ou déjà envoyé ; utiliser le worker
canonique sans deuxième moteur ; journaliser acceptés/expirés/refusés
et couvrir des séquences adversariales sur 2/4/6/8 comptes.
**MIRR-007 demeure PENDING.** Le moteur séquentiel qui active les
autres fenêtres peut déplacer le focus au milieu d'un geste humain :
rejouer ce geste plus tard sans contexte fiable serait plus dangereux
que le supprimer. La faisabilité doit être établie sur Windows/Unity.


## P0 — Résilience des diagnostics et arrêt du hook (04/11/2026)

Deux protections locales sont maintenant en place, sans modification
structurelle du dispatcher et sans file de replay supplémentaire :

- **Arrêt Windows incomplet** : `stop_message_hook` peut revenir alors
  que le thread de hook est encore vivant (la fonction conserve alors
  `_thread`). Dans ce cas, les relâchements physiques réservés ne
  sont plus vidés avant que le thread ne se termine : le `finally`
  de `_run_hook` réalise le nettoyage final. Un warning signale
  l'état encore actif.
- **Diagnostic défaillant** : une exception dans
  `_log_blocked_event` ne fait plus sortir le chemin
  `InputState.is_mouse_blocked` en laissant passer un DOWN vers une
  autre fenêtre. La paire `DOWN/UP` reste protégée et l'exception est
  journalisée, sans remettre en cause l'ordre des contrôles.
- Des tests mocks couvrent un arrêt de hook qui dépasse son délai et
  une exception de journalisation sous blocage.

Le problème fonctionnel plus large **MIRR-007** reste ouvert : les
nouveaux clics physiques bloqués durant la diffusion ne sont pas
automatiquement redistribués. Ni la télémétrie ni ces protections
locales ne constituent une solution complète. Carte Graphify exacte,
Doctor, exécution des tests Python et recette Windows/Unity restent
**NOT_RUN**. Aucun verdict de certification n'est implicite.


## Lot P0 du 04/11/2026 — arrêt, sélection et refus d'envoi

Le lot de 14 commits suivant `11ec726` améliore les chemins existants
sans changer les hooks ni introduire de nouveau moteur :

- **Stop urgence Switch clic** : la sortie du worker ne restaure
  plus le favori ni le curseur après l'ordre d'arrêt, même si
  un premier personnage avait déjà été activé.
- **Miroir molette** : pas de retour du curseur après Stop, refus
  `SendInput`, perte de focus ou modification des slots Organizer.
  L'échec de lecture de `GetCursorPos` génère un état incomplet
  explicite plutôt qu'un retour silencieux.
- **Clic Miroir** : un `SendInput` refusé interrompt la diffusion
  sans envoyer les mêmes gestes aux destinataires suivants.
  L'application ne prétend ni succès ni restauration du favori.
- **Liste de personnages figée** : le clic Miroir compare à nouveau
  le favori, le mode et l'ordre des HWND avant chaque destinataire
  et après son activation. Une sélection modifiée interrompt le
  worker au lieu de cibler les anciennes fenêtres.
- **Clavier Miroir** : si Windows refuse le premier `KEYUP`
  synthétique, une seule tentative de secours est autorisée.
  Si elle échoue encore, l'exécution est déclarée incomplète.

Les tests simulés couvrent les interruptions, l'échec d'envoi dès
le premier destinataire ou après livraison partielle, les modes
`Macro`/`Miroir`, les changements de favori ou de liste en cours
d'activation, ainsi que les favoris en dernier slot à **2/4/6/8**
comptes. Ces tests sont **ajoutés mais non exécutés** sur un runner.

**Limites P0** : la perte des gestes reçus pendant un
`InputState.is_mouse_blocked()` actif n'est **pas résolue** par ce
lot. MIRR-007 reste ouvert ; l'introduction d'une file de gestes
différés est une modification structurelle qui exige une carte
Graphify au SHA exact, Doctor et une recette Windows/Unity.
Les temps de réponse, l'absence de doublons en jeu et la mémoire
sur 8 comptes ne sont pas mesurés ni certifiés ici.

## Lot ciblé P0 du 04/11/2026 — vérification de focus et refus tardifs (non certifié)

À partir de la base `434691f76ad7729c822a914eda740e6a8454c8ea`, une série de **10 commits ciblés** (source et tests) renforce les chemins déjà présents sans nouveau backend, thread, queue ou remplacement des hooks Win32 :

- **Changement de personnage / retour au favori :** indices invalides refusés avant de lancer un worker ; retour favori confirmé par le premier plan réel et Stop vérifié avant de mettre à jour le client actif.
- **Miroir clavier / molette :** un HWND devenu étranger ou des coordonnées cible indisponibles annulent la livraison et interdisent le retour tardif du curseur ou du favori après échec.
- **Miroir clic :** une cible invalide, un échec d'activation ou un point non disponible interrompent immédiatement le fan-out capturé au lieu de sauter silencieusement un compte. Le comportement classique Switch clic reste distinct.
- **Auto-groupe et /zaap :** après un refus du chat, revérification du focus avant toute invitation ou commande suivante. En cas de focus volé, interrompre et ne pas restaurer automatiquement le favori.
- **Tests de non-régression ajoutés :** cas invalides, focus confirmé / volé, Stop, refus tardifs clavier/molette/clic, première livraison partielle, focus perdu après refus du chat et fan-out 2/4/6/8 existant. **Tests écrits, non exécutés sur cette reprise.**

### Portée et limites

Les modifications de ce lot ne résolvent **pas** `MIRR-007` : pendant un blocage physique global, le hook peut encore consommer un nouveau DOWN sans le diffuser. La stratégie de conservation/rejeu borné (TTL, génération de roster, Stop, ordre DOWN/UP) est une évolution structurelle conditionnée à une carte Graphify au **SHA exact** et au plan Doctor. Pas d'ajout d'une file risquée pour simuler la correction.

**Validation de ce lot : NOT_RUN** pour Python/unittest et Qt, Doctor `agent plan/check/validate`, Graphify exact SHA, `git diff --check` local, essais DOFUS Unity réels et mesures CPU/RAM/p50/p95/p99 de 2 à 8 comptes. La lecture du diff GitHub n'est pas une exécution de test. Garder la PR Draft, le Delivery Guard bloquant et les exigences de #321/#322 ouvertes ; aucun Ready, PASS ou fusion tant que les preuves ne sont pas établies.

## Lot ciblé du 04/11/2026 — fiabilité macros et Zaap (non certifié)

Correctifs locaux conservant le même moteur de macros et le mode séquentiel :

- **Stop pendant une commande chat** : `send_chat_command` vérifie l'arrêt d'urgence immédiatement avant chaque validation ENTER, y compris après une copie réussie et avant le second ENTER du Zaap. Aucun ENTER supplémentaire ne doit partir quand Stop est déjà observé.
- **Presse-papiers indisponible** : l'échec de l'import pywin32 ou des dix tentatives d'ouverture/remplacement du presse-papiers annule la macro par erreur explicite au lieu de coller un ancien contenu utilisateur. La restauration du presse-papiers sur réussite conserve le contrat existant ; les formats non texte et échecs de restauration demeurent une limitation à qualifier.
- **Roster Organizer** : les handles de fenêtre absents, non finis ou malformés sont écartés sans faire échouer le reste du fan-out Auto-groupe ou le classement des clients. Les HWND Dofus restent vérifiés par les chemins Win32 existants.
- **Sélection Zaap** : fermeture du popup avant le callback de mise à jour ou d'activation DOFUS, y compris en cas de destination invalide. Aucun panneau flottant ne devrait persister au-dessus du jeu pendant une activation.
- Tests ajoutés pour les courses de Stop autour des ENTER, le refus du presse-papiers, les HWND invalides, et la fermeture Zaap avant lancement.

**Statut de preuve :** correctifs enregistrés dans #325 et tests écrits ; exécution des tests Python, Doctor `agent plan/check/validate`, Graphify exact-SHA et essais Windows/Unity 2/4/6/8 : **NOT_RUN** depuis ce contexte sans checkout local. MIRR-007 (perte des gestes physiques pendant un worker occupé), MIRR-002 et MIRR-005 restent ouverts. La PR reste Draft ; ni validation réelle, ni latence identique 2→8, ni certification n'est revendiquée.

## Durcissement ciblé des macros historiques — 04/11/2026 (non certifié)

Les commandes multi-fenêtres **Auto-groupe**, **Direction** et **/zaap**
ne se contentent plus de vérifier `UnityWndClass` : elles utilisent le
validateur DOFUS existant (`is_dofus_unity_process`) avant toute émission.
Le contrôle est répété immédiatement avant la frappe ou la commande chat,
y compris après une activation de fenêtre. Un HWND dont le processus a
changé interrompt le parcours ; le favori n'est pas réactivé aveuglément.
La validation reste **fail-closed**, sans nouveau moteur, hook ou file de
rejeu, et sans modification des données persistantes.

`tests/test_organizer_macro_reliability.py` adapte ses mocks de processus
et ajoute sept scénarios ciblés (usurpation après activation, client
remplacé en cours de diffusion, Stop avant tout accès Win32 et Stop
entre contrôle d'identité et restauration du favori).
Le Stop /zaap ne provoque plus de requête d'identité de processus tardive ;
Auto-groupe et /zaap reconsultent Stop juste avant le retour au favori.
Les simulations existantes 2/4/6/8
restent dans leur ordre canonique.

**Preuves manquantes :** ces tests sont écrits mais **NOT_RUN**, faute de
checkout complet Python/Windows dans cette passe. Atlas Doctor
`agent plan/check/validate`, Graphify au SHA exact, `git diff --check`,
tests PySide6, recette DOFUS Unity, p50/p95/p99, CPU et RAM ne sont pas
déclarés PASS. Le travail de MIRR-007 (gestes absorbés quand le worker est
occupé) reste ouvert ; pas de replay différé sans carte Graphify ni
preuve Windows. Conserver la PR Draft et ne pas fusionner.

## Lot P0 du 04/11/2026 — vérifications après activation et nettoyage du Miroir

- Le Miroir **clavier et molette** revalide le mode, le favori, l'ordre des
  fenêtres et l'identité du processus DOFUS **après** chaque activation native,
  juste avant l'injection. Un changement pendant `activate_window` annule
  la diffusion avec statut incomplet ; aucun appel `key_down` ou envoi de
  molette ne doit suivre cette invalidation.
- Pour la molette, un second contrôle du Stop, des sessions et de l'identité
  du processus est effectué **après** `set_cursor_pos` et le contrôle du
  premier plan, pour empêcher une émission tardive si le mouvement du
  curseur a permis une réaffectation de fenêtre ou un arrêt.
- Le blocage physique de souris reste actif durant la restitution du
  curseur **et** du favori, comme dans Switch clic. Une clause `finally`
  imbriquée débloque la souris même si une vérification de restitution
  lève une exception. Le code n'introduit ni hook, ni sender, ni queue.
- Tests ajoutés : changements de roster/processus durant l'activation,
  Stop/roster/processus invalidé pendant le déplacement molette,
  ordre blocage → restauration → déblocage, déblocage sur erreur de
  vérification. La borne de contrôles natifs clavier en 2/4/6/8 passe
  de `2N+1` à `3N+1` (vérification de sécurité additionnelle) :
  aucun gain ou maintien de latence n'est revendiqué sans benchmark.

**Validation : NOT_RUN.** Aucun checkout Windows Python/PySide6 ni Doctor
`agent plan/check/validate`, aucune carte Graphify exact-SHA, ni mesure
CPU/RAM/p50/p95/p99 ni recette DOFUS Unity. Ces tests sont écrits et
versionnés, pas certifiés. **MIRR-007 reste PENDING** : le blocage global
peut toujours absorber les gestes physiques reçus pendant un worker.
Conserver la PR en Draft et éviter tout replay structurel sans Graphify.

## Lot fiabilité ciblée du 04/11/2026 — fenêtres et erreurs de clipboard

- Miroir clavier et molette : le contrôle de la fenêtre au premier plan
  intervient **après** les probes d'identité/roster et immédiatement avant
  l'émission. Le Stop est revérifié avant chaque envoi. Les tests simulent
  un vol de focus pendant le dernier contrôle du processus et vérifient
  que ni touche ni molette n'est injectée dans une autre application.
- Switch clic Miroir : après calcul de la position, nouveau contrôle du
  roster, de l'identité du processus et du Stop avant le sender canonique.
  Tests sur favori changé, HWND recyclé et arrêt durant le calcul du point.
- Switch Déplacement, Auto-groupe et /zaap : ordre des probes d'identité et
  focus corrigé (focus vérifié en dernier), Stop consulté juste avant frappe
  ou commande. Après un échec d'envoi chat, refaire le contrôle de focus en
  dernier : aucune tentative suivante si un probe Win32 a changé le premier
  plan. Mocks ajoutés sur ces cas.
- **Erreur de fond identifiée dans le presse-papiers** : un `return` dans
  le `finally` de `clipboard_text` absorbait les exceptions sorties du
  corps du contexte (par exemple un refus `SendInput`). Remplacement par
  un marqueur de restauration et une sortie normale de boucle ; l'erreur
  originelle remonte désormais, même si la restauration du presse-papiers
  échoue. Tests sur échec d'envoi et de restauration.

**Portée :** gardes ciblées dans les moteurs existants, aucun changement de
format de profil, aucun moteur d'injection secondaire et aucune file de replay.
L'utilisation du clipboard reste limitée à la restauration du texte ; les
formats non texte/multiformats ne sont pas entièrement restaurés et doivent
être qualifiés avant certification.

**Preuves :** lecture des sources, tests ajoutés mais **NOT_RUN** : accès
GitHub seulement, pas de checkout local permettant `atlas_doctor agent
plan/check/validate`, ni `git diff --check`, ni tests Python/Qt, ni carte
Graphify exacte, ni bench CPU/RAM/p50/p95/p99 ni recette Windows DOFUS
2/4/6/8. **MIRR-007** (gestes capturés durant un worker) demeure PENDING.
PR Draft, non certifiée ; ne pas exécuter FULL/Phase Certification ni fusionner.

## Lot P0 du 04/11/2026 — protection du presse-papiers et séquences chat

- La préparation de `clipboard_text` refuse désormais les contenus dont
  le module ne peut pas conserver les données : presse-papiers non texte,
  image et formats enrichis (CF_HTML, format d'application, etc.). Seuls les
  formats texte Win32 usuels CF_TEXT, CF_OEMTEXT, CF_UNICODETEXT, CF_LOCALE
  sont autorisés à passer dans le moteur texte actuel ; les données non
  restaurables restent intactes. Le presse-papiers **vide** reste utilisable.
- Avant de restaurer l'ancien texte, le numéro de séquence Win32 est comparé
  à celui pris sous le verrou de préparation. Si l'utilisateur copie un
  nouveau contenu pendant la macro, la copie récente est conservée, sans
  restauration tardive. Le garde reste conservateur si Windows ne fournit
  pas un numéro de séquence exploitable (0).
- `send_chat_command` ne touche plus au presse-papiers si le Stop était déjà
  demandé avant sa préparation. Les vérifications précédentes de Stop entre
  les étapes de collage et avant Entrée demeurent.
- Auto-groupe et /zaap passent au sender canonique un prédicat d'annulation
  combinant Stop et perte du premier plan. Il est évalué entre les étapes de
  la commande : un basculement de fenêtre en plein collage empêche les
  actions clavier suivantes, sans créer un autre sender ni nouveaux threads.
- Nouveaux tests isolés sur image/texte riche/vide, formats Win32 texte,
  changement externe du clipboard, propagation des erreurs sur Stop et
  refus SendInput, verrou de lecture de séquence, restauration séquentielle
  simulée pour 2/4/6/8 et interruption de chat après vol de focus.

**Portée/risque :** correctifs ciblés sur les trois moteurs existants et
leurs tests, sans migration de profil ni modification des hooks natifs.
Ce garde de presse-papiers volontairement strict peut refuser une commande
si un format riche est copié ; effacer/copier du texte simple est alors
nécessaire. Il ne constitue pas une restauration multi-format complète.

**Validation : NOT_RUN** dans cette session GitHub-only : Doctor plan/check,
Graphify exact SHA, tests Python/PySide6, benchmarks de latence/CPU/RAM,
recette DOFUS Unity et `git diff --check`. Les scénarios sont **ajoutés**,
mais aucun PASS ne doit être revendiqué. Le blocage de MIRR-007 (gestes
physiques avalés pendant le worker) demeure à résoudre sur carte Graphify
exact-SHA, puis à vérifier sur Windows réel. **PR Draft, CHANGES REQUIRED**.

## Audit complémentaire 04/11/2026 — restauration en cas de refus Win32

- Une erreur `SetClipboardText` après `EmptyClipboard` déclenche une
  restauration immédiate du texte utilisateur préalablement capturé, sous
  le même verrou. Si cette restauration échoue, la préparation échoue
  définitivement : ne pas relire le presse-papiers vidé comme une nouvelle
  source de vérité et ne pas annoncer une commande envoyée.
- La distinction entre formats explicitement interdits et exception
  technique Win32 évite de réinterpréter un défaut d'écriture en presse-
  papiers riche. Les tests simulent le premier échec, une réparation
  réussie suivie d'une reprise, et la réparation définitivement refusée.
- Les tests ajoutés et les gardes de focus intra-commande sont purement
  localisés dans `input_tools`, `auto_group`, `zaap` et leurs suites.

### MIRR-007 — plan de reprise structurelle (non implémenté)

La suppression des pertes de clics **pendant un worker occupé** n'est pas
résolue par les gardes ci-dessus. Avant de modifier le hook global :

1. Construire la carte Graphify sur le **HEAD exact** ; faire `Doctor agent
   plan --structural` pour `mouse_hooks`, `input_state`,
   `runtime_state`, `switch_click`, `mirror_input` et les tests.
2. Comparer la stratégie de repli non destructif et une file bornée
   périssable. Une file éventuelle doit conserver les couples DOWN/UP
   physiques, ordre, coordonnées/ratio et distinction source native déjà
   livrée vs source consommée ; ne jamais inventer un second sender.
3. Définir une limite stricte de taille/ancienneté et une invalidation
   atomique sur Stop, bascule Macro/Miroir, favori, roster, HWND/processus ;
   bannir toute réinjection tardive dans une autre application ou fenêtre.
4. Tests déterministes : saturation et doubles clics, wheel, 2/4/6/8,
   Stop pendant une pression, HWND recyclés, changement de focus, file
   pleine, expiration, ordonnance et non-réentrance. Compléter par la
   recette réelle DOFUS Unity et les métriques CPU/RAM/p50/p95/p99.

**Statut:** ce document est une feuille de reprise, pas une preuve Graphify
ni un certificat. Tous les tests de cette session restent **NOT_RUN**
(plateforme GitHub seulement). **MIRR-007 reste PENDING.** Ne pas fusionner.

## Lot 04/11/2026 — annulation immédiate si presse-papiers modifié pendant le chat

### Constat et correction

Avant ce lot, `clipboard_text` sauvegardait la révision native Windows
pour **éviter d'écraser une nouvelle copie pendant la restauration**, mais
`send_chat_command` ne la recontrôlait pas avant les étapes de saisie.
Un Ctrl+C utilisateur pouvait donc remplacer la commande temporaire avant
Ctrl+V ; le chat risquait alors de coller puis envoyer un autre texte.

Le contexte existant `clipboard_text` expose désormais la révision dont
il est propriétaire à `send_chat_command`. L'annulation combine le Stop
fourni par le consommateur (qui inclut le focus dans Auto-groupe et /zaap)
et un contrôle de révision Win32 à chaque frontière clavier cancellable,
après collage et avant chaque Entrée. Si la révision a changé ou sa lecture
échoue, le sender retourne `False` sans soumettre un texte devenu inconnu.
La restauration continue de respecter une nouvelle copie utilisateur :
elle ne remet pas l'ancien contenu lorsque la révision diffère.

La valeur renvoyée par pywin32 est un `int` Win32 **signé** : les révisions
négatives ne sont pas des erreurs ; seul zéro représente un suivi absent.
Quand le numéro n'est pas disponible, le sender ne colle ni ne soumet
la commande. Les contextes simulés non Windows gardent la logique Stop.

### Régressions ajoutées / ajustées

- Copie pendant la préparation (après Espace, avant Ctrl+A) : aucune frappe
  destructive supplémentaire ni commande soumise.
- Copie entre collage et Entrée : pas de soumission du contenu étranger.
- Copie après le premier Entrée Zaap : pas de deuxième soumission.
- Révision indisponible, lecture impossible et valeur signée négative.
- Mocks existants munis d'une révision stable ; correction du scénario
  Stop sur double Entrée et des contrôles de verrou / d'indentation.

**Validation : tests ajoutés, mais NOT_RUN.** Aucun checkout exécutable sur
l'hôte de cette session (DNS GitHub inaccessible), aucune exécution Doctor,
Graphify exact-SHA, tests PySide6, mesures CPU/RAM/p50/p95/p99 ou
recette DOFUS Unity 2/4/6/8. Ne pas affirmer une exécution PASS.
**MIRR-007 reste PENDING** ; le correctif de chat ne traite pas les gestes
physiques perdus sous worker occupé. PR toujours Draft / non certifiée.

## Maxi-lot 04/11/2026 — garde Miroir en cours d'envoi et focus de fin

### Corrections implémentées

- Le Switch clic Miroir passe au sender natif existant un prédicat
  d'annulation tenant compte du Stop **et** du roster courant (mode Miroir,
  favori et ordre des destinataires), y compris durant le survol Unity,
  entre les clics d'un double-clic et pendant les délais. Le contrôle reste
  **en mémoire**, sans nouveau probe natif sur chaque tranche de 10 ms,
  pour éviter une surcharge accrue avec 8 personnages. Si la liste change,
  les destinataires restants ne reçoivent aucune nouvelle action.
- Le refus du sender distingue maintenant Stop, roster modifié, focus perdu
  et refus d'injection ; il ne présente pas une annulation de roster comme
  un refus Win32 SendInput. Le sender historique et les macros classiques
  restent réutilisés, sans API de dispatch supplémentaire.
- Le Miroir clic, clavier et molette vérifie que l'ancien destinataire
  activé est **encore au premier plan** à la fin de la diffusion, avant
  de reprendre le curseur ou le favori. Une application nouvellement
  sélectionnée conserve le focus, même si les émissions étaient complètes.
- Le Miroir molette et le Switch clic refont aussi ce contrôle **après**
  avoir remis le curseur à sa position initiale : une activation survenue
  durant le déplacement du pointeur ne déclenche pas un retour forcé
  au favori. Un échec du contrôle natif de focus ou de restauration du
  curseur laisse les protections se nettoyer sans nouvel envoi.

### Tests et preuve manquante

- Simulations ciblées de roster/favori/mode/Stop changé pendant le survol
  du clic sur **2/4/6/8 clients**, sans destinataires supplémentaires.
- Simulations clavier, molette et clic de changement vers une autre
  application **après** les émissions finales sur 2/4/6/8 clients ; aucun
  retour au favori ni curseur déplacé si le focus appartient à l'utilisateur.
- Scénarios de vol de focus et d'erreur native **pendant** le retour du
  curseur ; les blocs souris doivent toujours être relâchés. Les mocks
  de focus des parcours précédemment complets ont été adaptés aux nouveaux
  contrôles finaux. Le cas de roster inversé sur deux clients, sans réel
  changement du parcours favori-first, est remplacé par un HWND réellement
  périmé afin de ne pas inventer une régression.

**Portée** : modifications localisées dans `app/macros/switch_click.py`,
`app/macros/mirror_input.py` et `tests/test_organizer_mirror_ui.py`,
sans format persistant, nouvelle dépendance, hook ou système de file.

**NOT_RUN** : Atlas Doctor `agent plan/check/validate`, Graphify SHA
exact, `git diff --check`, tests Python/PySide6, métriques et recette
DOFUS Unity Windows 2/4/6/8 indisponibles sur l'hôte GitHub-only.
L'analyse statique du code et des tests n'est pas une exécution PASS.
La finalisation du comportement global dépend toujours de **MIRR-007** :
les gestes physiques arrivant pendant un worker occupé peuvent encore
être consommés sans diffusion. Aucune nouvelle politique de replay ou
modification structurelle de hook sans Graphify exact-SHA + Doctor.
**PR Draft, certification manquante, verdict provisoire CHANGES REQUIRED.**

### Complément P0 — favori/roster invalidés durant la restitution du clic

En plus du contrôle de focus, le nettoyage du Switch clic Miroir
revalide maintenant explicitement la sélection Organizer (mode, favori,
roster) **après la dernière émission**, avant de replacer le curseur, et
**une seconde fois avant de réactiver le favori**. Une sélection modifiée
par l'utilisateur ou un rafraîchissement de l'Organizer ne peut donc plus
provoquer de restauration sur un favori différent de celui du geste initial.
La vérification utilise seulement les données de sessions déjà chargées,
sans scan de tous les processus Windows. Une lecture du roster devenue
impossible est traitée comme un refus de restauration, tout en libérant
normalement le blocage de souris.

Tests supplémentaires sur **2/4/6/8 clients** : changement du roster par
HWND remplacé, modification du favori ou bascule du mode immédiatement
après le dernier envoi ; modification du favori pendant le retour du curseur.
Les actions déjà émises ne sont pas inventées comme « non envoyées » :
le statut de diffusion peut rester complet même lorsque la restitution
du focus est volontairement abandonnée.

**État de preuve :** audit statique uniquement, tests écrits mais NOT_RUN,
Doctor / Graphify exact-SHA / Windows DOFUS non exécutés. MIRR-007 (gestes
avalés sous charge) demeure ouvert : cette mesure n'implémente ni file de
replay ni repli non destructif. PR Draft, non certifiée.

## Lot 04/11 — restitution des macros classiques après changement de focus/favori

**Cible :** correction minimale dans les moteurs déjà canoniques
`auto_group.py`, `zaap.py`, `direction.py`, sans mutation des hooks,
modification des paramètres de vitesse, changement de profil ni backend
supplémentaire.

- Auto-groupe : après une invitation (succès, refus ou exception), avant
  la restitution de la fenêtre favorite, Atlas recontrôle le premier plan
  du lanceur et le favori sélectionné en début de macro. Une nouvelle
  fenêtre ou un favori changé dans Organizer ne sera pas réactivé.
- Zaap : même vérification sur la dernière fenêtre effectivement activée
  pour le chat ; une diffusion séquentielle 2/4/6/8 ne ramène pas DOFUS
  devant l'application que l'utilisateur a sélectionnée après la dernière
  commande. La sélection du favori est capturée avant diffusion.
- Direction : même protection après la dernière touche virtuelle sur le
  dernier client réellement activé ; ne restaure pas un favori nouveau.
- Les erreurs de lecture de premier plan sont **fail-safe** : abandon de
  la restitution, sans provoquer un retour au favori non vérifié.
- La télémétrie distingue désormais **l'émission** de la **restitution** :
  le drapeau `restore_skipped` empêche le retour au favori sans marquer
  à tort `interrompu` une commande déjà envoyée à tous les clients. Une
  perte de focus détectée durant la saisie ou un Stop conserve l'état
  `interrompu` selon le comportement préexistant.

**Tests écrits :** Auto-groupe, Zaap et Direction sur 2, 4, 6 et 8 clients
avec changement de focus juste après le dernier geste, changement de favori
pendant le travail et lectures de premier plan rejetées. Les assertions
sur le nombre réel de commandes émises et les états complets restent
séparées des assertions `restore_preferred_client.assert_not_called()`.
Les tests historiques de diffusion complète/échec/Stop restent en place ;
le parcours Direction 2/4/6/8 a été ajusté pour la lecture Win32 finale.

**Validation actuelle : NOT_RUN.** Sans checkout local exécutable, Doctor
`agent plan/check/validate`, Graphify exact-SHA, exécution Python/PySide6,
`git diff --check`, recette DOFUS Windows et mesures CPU/RAM/p50/p95/p99
ne peuvent pas être déclarés PASS. Les seuls contrôles possibles via ce
connecteur sont la revue des patches et du code retourné par GitHub.

**MIRR-007 reste PENDING.** La gestion des gestes physiques arrivant pendant
un worker occupé reste un blocage P0 exigeant un graphe exact-SHA et le
plan Doctor `--structural` avant tout changement de hook ; ni replay
périssable ni politique non destructive ne sont revendiqués ici. PR Draft,
non certifiée et non fusionnée.

## Lot 04/11 — sûreté SendInput souris, pointeur et données numériques

- Un `UP` refusé interrompt immédiatement le double-clic, avant le second
  `DOWN` ; le `finally` tente un unique relâchement de secours.
- `SetCursorPos` refusé, `GetCursorPos` illisible ou position effectivement
  différente de la cible (notamment `ClipCursor`) empêchent toute injection.
  La vérification ajoute une lecture Win32 par déplacement, sans polling.
- Les valeurs NaN/inf, le HWND non fini et les temporisations invalides
  ne font plus planter le worker ni cliquer avec des données incertaines.
- Tests ajoutés : boutons gauche/droit, release échoué, écran secondaire à
  coordonnées négatives, curseur contraint, panne native, valeurs invalides.

**Preuves :** correctifs + tests GitHub, audit statique uniquement. Tests
Python/Windows DOFUS Unity, Atlas Doctor, Graphify exact-SHA, p50/p95/p99
et CPU/RAM **NOT_RUN**. **MIRR-007 PENDING** (gestes sous worker occupé).
PR Draft, non certifiée et non fusionnée.

## P0 04/11 — vérification du clipboard avant écriture et comptage post-UP

- Une séquence presse-papiers Windows absente (0), non entière ou
  illisible est maintenant un **refus précoce**, sous `OpenClipboard`
  et **avant** `EmptyClipboard`. Aucun collage ni saisie ne démarre dans
  cet état. Une valeur négative signée reste valide côté pywin32.
- Si la séquence devient illisible juste **après** l'écriture temporaire,
  l'ancien texte (ou l'état vide) est réparé **sous le même verrou**, puis
  la commande est refusée. Un échec de réparation n'est pas suivi d'un
  nouveau cycle destructif ; une exception diagnostique est conservée.
- Tests ciblés ajoutés/ajustés : absence du compteur, exceptions natives,
  séquences concurrentes, réparation texte/clipboard vide et erreur de
  réparation, avec absence de touche synthétique lors du refus.
- Un clic souris dont le dernier `UP` est confirmé reste marqué livré
  quand un Stop ou un échec de temporisation survient pendant le délai
  optionnel post-UP. Stop pendant l'appui déclenche toujours un relâchement
  de secours ; Stop entre deux clics supprime le deuxième DOWN.
- Tests gauche/droit, simple/double, Stop pendant l'appui, pendant le
  double-gap et après UP ; vérification du nombre réel de DOWN/UP.

**Validation technique toujours NOT_RUN** : aucun checkout exécutable pour
Doctor `agent plan/check/validate`, tests Python/PySide6, Graphify au SHA
exact, mesures CPU/RAM/p50/p95/p99 et recette DOFUS Unity Windows 2/4/6/8.
Tests présents ne signifie pas PASS. **MIRR-007 PENDING** : gestes physiques
sous worker occupé, modification structurelle à réserver à Graphify exact-SHA
et Doctor `--structural`. PR Draft, non certifiée, ne pas fusionner.

## Lot 04/11 — protection du focus Win32 et Stop du worker

Le propriétaire existant `app/windows/focus.py` a été renforcé **sans
refonte ni nouvel appel réseau**. La sélection du favori et les workers
Macro/Miroir gardent leurs APIs et timers actuels.

- **Stop précoce** : aucune vérification ou manipulation native de fenêtre
  quand le Stop est déjà demandé. Même une cible déjà au premier plan ne
  doit pas renvoyer un faux succès après l'arrêt.
- **Focus déjà actif** : à la fin du délai Unity, le premier plan est
  recontrôlé ; un autre programme sélectionné pendant la pause annule
  l'activation plutôt que de faire croire au caller qu'elle réussit.
- **Activation native** : gardes Stop après l'attachement des threads
  (qui sont détachés par le `finally`), après `SetWindowPos`, juste avant
  `SetForegroundWindow`, avant le repli temporaire `HWND_TOPMOST`, et
  avant de retourner un succès. La règle s'applique aux 2-8 comptes.
- **Valeurs corrompues** : `NaN`, `inf` et `None` dans les timings
  d'activation retournent un refus diagnostiqué, sans faire planter un
  worker. Le nombre de tentatives est borné à **8**, valeur maximale des
  profils rapides/normaux vérifiés dans `app/core/settings.py`, pour éviter
  des boucles massives sur un profil mal formé.

**12 tests unitaires ciblés ajoutés** dans
`tests/test_organizer_focus_preflight.py` : Stop initial, focus volé
pendant settle, Stop tardif, timings invalides, énorme nombre de tentatives,
libération des threads, omission des fallbacks topmost, et chemin court
sur 2/4/6/8 fenêtres déjà actives. **Tests écrits, pas exécutés** : aucune
preuve Windows/DOFUS ni mesure de latence réelle n'est disponible ici.

**Évidence toujours manquante :** Doctor `agent plan/check/validate`,
Graphify exact SHA, `git diff --check` local, PySide6/Windows réel,
recette 2/4/6/8, mesures CPU/RAM/p50/p95/p99 et CI finale. Ces scénarios
ne valent ni `VALIDATED` ni `CERTIFIED`.

**MIRR-007 reste un P0 ouvert** : le hook souris peut encore consommer
un geste physique quand le worker est déjà occupé. L'architecture des
hooks ne peut pas être modifiée sans Graphify au SHA exact et route
Doctor `--structural`. Cette PR reste Draft, non fusionnable.

## Lot 04/11 — retrait TOPMOST garanti et bornes anti-blocage

**Portée :** garde localisé des moteurs `app/windows/focus.py` et
`app/windows/clicks.py` ; nouveaux tests unitaires de focus et de clics.
Pas de refonte du hook souris, de changement de profil ni de dépendance.

- Le dernier recours `HWND_TOPMOST` utilise un `try/finally` pour
  **toujours tenter** `HWND_NOTOPMOST`, y compris quand l'API initiale
  lève une exception. Si le retrait échoue une fois, une seule nouvelle
  tentative est autorisée avant de renoncer à l'activation. Un double
  échec est signalé explicitement comme une fenêtre potentiellement
  coincée au premier plan ; il est impossible de garantir le retrait
  si Windows refuse réellement les deux appels.
- Stop vérifié après le retrait TOPMOST, après `SetForegroundWindow`,
  après `ShowWindow` et `BringWindowToTop` : le worker ne lance pas
  les manipulations suivantes quand l'arrêt vient d'être demandé.
  Les `AttachThreadInput` sont toujours détachés par le `finally` existant.
- Les profils actuellement livrés configurent des délais d'activation
  de 12–24 ms et de retry de 12–18 ms. Une temporisation de focus
  **supérieure à 1 000 ms** est refusée, plutôt que de bloquer des workers
  pendant plusieurs secondes ou minutes sur 8 comptes.
- Le clic synthétique refuse maintenant une somme de temporisations
  (`pre + post + click_count * down + double_gap`) supérieure à
  **1 000 ms**, avant de modifier le curseur ou d'armer le garde souris.
  Les timings légitimes et le chemin de double-clic existant restent
  inchangés.

**Tests ajoutés/ajustés :** injection Win32 simulée des refus TOPMOST,
NOTOPMOST (simple/double), Stop pendant BringWindowToTop, Stop entre
SetForegroundWindow et SetFocus, annulation après ShowWindow ; budgets
extrêmes et budget normal des clics. Aucun de ces tests n'a été exécuté
sur Python/Windows/DOFUS dans cette session.

**NOT_RUN** : Atlas Doctor `agent plan/check/validate`, Graphify
exact-SHA, tests Python/PySide6, `git diff --check`, vraies sessions
Windows 2/4/6/8 et mesures RAM/CPU/p50/p95/p99. Le P0 **MIRR-007**
(gestes physiques perdus pendant worker occupé) demeure non résolu et
ne doit pas être traité par une refonte structurelle des hooks sans
Graphify+Doctor au SHA exact. PR Draft ; pas de fusion ni certification.

## Lot 04/11 — surcharge numérique dans les callbacks et identités Organizer

Cette reprise corrige des conversions numériques ponctuelles exposées
à des données de profil, d'identité ou de raccourci malformées, **sans
modifier la politique des hooks** ni ajouter de mécanisme de replay.

- `app/core/runtime_state.py` : un `client_index` ou un `click_count`
  égal à `inf`/`NaN` ne peut plus lever `OverflowError` hors de la
  gestion de repli prévue. Les raccourcis de personnage invalides sont
  refusés ; le compteur de clics malformé conserve son repli historique
  sur un clic, sans geste supplémentaire.
- `app/windows/unity_windows.py` : un HWND infini dans le roster
  Organizer est ignoré lors du hit-test, et une fenêtre Unity authentique
  parmi les autres clients reste sélectionnable.
- `app/core/settings.py` : `int_value` applique aussi son défaut en
  cas d'`OverflowError`, au lieu de faire planter le chargement des
  profils.
- `app/pages/organizer/character_sessions.py` : les IDs de personnage
  ressemblant à des chiffres Unicode mais impossibles à convertir ne
  bloquent plus le chargement des identités réseau vérifiées. Même garde
  sur les PID et HWND des sessions et du favori.

**Tests ajoutés :** `tests/test_organizer_numeric_hook_guards.py`
(5 scénarios) et `tests/test_organizer_identity_overflow.py`
(4 scénarios), avec cas d'identités réseau malformées, hit-tests
physiques, hotkeys, favorite et PID invalide. Tests présents au HEAD,
**non exécutés** faute de checkout complet avec dépendances.

**Blocage non levé : MIRR-007**. Le hook souris consomme toujours les
nouveaux `DOWN` physiques sous `is_mouse_blocked()` avant le callback
Miroir. Rejouer ces gestes en différé sans identité/cible et timing
fiables n'est pas autorisé ; aucune file n'a été ajoutée sans Graphify
exact-SHA et Doctor `--structural`.

**NOT_RUN :** Doctor `agent plan/check/validate`, Graphify exact-SHA,
Python/PySide6, Windows réel, mesures CPU/RAM et latence 2/4/6/8, et
certification CI. Verdict : **CHANGES REQUIRED**, Draft, non fusionnée.

## Lot ciblé 04/11 — authentification du changement de personnage (PR #325)

- `SwitchCharacterMacro.activate_by_index` refuse désormais une fenêtre Unity
  étrangère même si son HWND correspond à un ancien slot Organizer : contrôle
  de l'exécutable DOFUS avant toute activation et nouveau contrôle après
  `activate_window`, avant publication de `active_client_handle`.
- `restore_preferred_client` applique le même contrôle avant la restitution
  au favori et juste avant de mettre à jour le handle actif. Cette correction
  réutilise l'authentification canonique `is_dofus_unity_process` de
  `app/macros/mirror_plan.py`, sans moteur supplémentaire.
- Quatre tests mock explicitent les refus d'un processus Unity étranger
  et d'un HWND réaffecté en cours d'activation ; les tests existants de
  raccourcis, de focus et de Stop sont adaptés au nouveau garde.
- **État : code et tests ajoutés, non exécutés.** L'agent n'a pas de
  checkout du dépôt et PySide6/Windows ne sont pas disponibles dans son
  environnement. Atlas Doctor, Graphify exact-SHA, suite Python, mesures
  de latence et recette DOFUS Unity restent NOT_RUN. La PR reste Draft.
- **P0 MIRR-007 inchangé :** gestes physiques perdus pendant un worker
  occupé. Ne pas modifier structurellement le hook sans Graphify exact-SHA,
  préflight Doctor `--structural` et scénarios Windows correspondants.

## Maxi-lot 04/11 — identité Win32 et cohérence des personnages (PR #325)

**Périmètre : durcissement local, pas de refactor du hook partagé.**

- `SwitchCharacterMacro` ne choisit plus de source, favori ou destinataire
  appartenant à un autre processus Unity ; la validation de l'exécutable
  DOFUS est appliquée aux chemins de secours et au roster, pas seulement
  à l'activation directe.
- Un raccourci mis en file ne peut plus activer un ancien HWND si le slot a
  été réaffecté ; le slot est revérifié avant l'activation et avant de publier
  `active_client_handle`. Les autres changements de slots restent permis.
- Le retour au favori ne publie pas un ancien favori si l'utilisateur en a
  choisi un autre pendant `activate_window`. Le deuxième contrôle d'identité
  est conservé **après** activation, pas exécuté deux fois avant.
- `AtlasSettings.client_by_handle` saute les HWND corrompus (NaN, inf,
  booléens, valeurs fractionnaires, chaînes non convertibles, dépassements)
  sans masquer les autres clients valides du profil.
- `SwitchClickMacro` vérifie aussi en mode classique le propriétaire DOFUS
  de chaque fenêtre avant l'activation et à nouveau juste avant
  `send_client_click`, après calcul des coordonnées : les contrôles de
  non-régression Miroir restent appliqués.
- `is_dofus_unity_process` refuse les HWND hors plage native 64 bits
  et les PID qui ne sont pas de vrais entiers DWORD positifs, avant tout
  accès au chemin exécutable.
- Les simulations ajoutées couvrent notamment 2/4/6/8 personnages lors
  du réaffectation d'un slot, un autre Unity au premier plan, un favori
  modifié pendant l'activation, un HWND repris par une autre application,
  et les identifiants/valeurs malformés.

**Évidence disponible :** modifications et tests versionnés sur la branche
de PR, relecture statique de ce lot ; les cas ne sont **pas** des PASS
d'exécution. **NOT_RUN :** Doctor `agent plan/check/validate`, Graphify
exact-SHA, tests Python/PySide6, `git diff --check` local, CI finale,
benchmarks et tests Windows/DOFUS Unity 1/2/4/6/8. Une campagne réelle
reste indispensable pour mesurer entrée→rendu, erreurs et p50/p95/p99.

**Bloquants conservés :** MIRR-007 (perte de geste physique quand le
worker est déjà occupé), MIRR-002 (arrière-plan Unity non attesté),
conflit éventuel avec `main` et recette #322. Le hook souris partagé
ne doit pas être refactoré sans Graphify du SHA exact et plan Doctor
`--structural`. **CHANGES REQUIRED**, PR Draft.

## Maxi-lot suivant 04/11 — aucun geste consommé sur roster périmé

- Le snapshot Miroir clavier/molette conserve **exactement** la sélection
  enregistrée : 2 à 8 HWND entiers uniques et natifs, avec favori inclus.
  Aucune fenêtre invalide, hors ligne ou Unity étrangère n'est écartée
  silencieusement pour continuer avec moins de destinataires.
- Le clic Miroir utilise le même refus anticipé : si un personnage
  enregistré n'est plus authentifié, le clic physique **reste natif**.
  Cela évite la consommation sans diffusion qui survient quand le worker
  découvre ensuite que le roster attendu ne correspond pas au réel.
- Une mise à jour de `AtlasSettings` pendant les probes Win32 empêche
  la capture et le clic de déclencher un worker sur un ancien snapshot.
  La comparaison d'identité de l'objet settings ne remplace pas la
  revérification du worker ; elle ferme la fenêtre avant consommation.
- En mode classique, `ordered_clients_from_source(source_hwnd)`
  refuse un HWND source positif explicitement fourni mais détaché du
  roster, au lieu de substituer silencieusement le favori.
  L'appel sans source explicite (`0`) conserve le comportement historique.
- Les entrées clavier rejetées par la whitelist et les callbacks
  souris/molette malformés ne déclenchent pas de scans de processus.
  Le contrôle souris vérifie des coordonnées Win32 signées ; la
  validation des touches interdit les touches système et modificateurs.
- Régressions ajoutées : roster tronqué, doublon/fraction/HWND hors
  plage, conservation du geste natif, favori en dernier slot,
  changement de settings pendant le probe, raccourci vers source
  inconnue, et comportement nominal 2/4/6/8 clients.

**Audit statique uniquement :** code, tests et commits versionnés, mais
**NOT_RUN** pour Doctor/Graphify exact-SHA, tests Python/PySide6,
Win32/Unity, benchmarks et p50/p95/p99. Aucune affirmation de PASS
ou de geste garanti en conditions réelles.

**MIRR-007 reste ouvert :** les DOWN physiques pendant un worker
avec le blocage global souris actif peuvent encore être interceptés.
Ne pas refactorer `app/input/mouse_hooks.py` sans graphe Graphify
du SHA exact et préflight Doctor structurel. La PR reste Draft.

## Lot fonctionnel 04/11 — vitesses Classique / Normal / Rapide / Instantané

- Le contrat ATMC-002/MIRR-017 utilise les presets réels du runtime, pas un simple changement de libellé. L'ancien **Normal** devient **Classique** (délais inchangés) et l'ancien **Rapide** devient **Normal** (délais inchangés). Les nouveaux **Rapide** et **Instantané** réduisent des attentes identifiées dans le moteur partagé ; des minima de maintien/survol restent appliqués par le sender.
- Le schéma de vitesse v2 est exporté avec `client_index.json` et `.ini`; les profils v1 non migrés sont lus sans accélération silencieuse. Dès que l'utilisateur choisit un mode, le profil et le marqueur de schéma sont sauvegardés ensemble.
- Les quatre boutons sont dans la carte Actions rapides, utilisent la classe `segmentedButton`/`segmentedButtonActive` commune, et déclenchent un rechargement du runtime.
- Les tests couvrent la migration, la persistance, l'ordre des délais, les modes et la compatibilité de chargement. **NOT_RUN** : tests PySide6/Windows, Doctor, Graphify, mesures CPU/RAM et ressenti réel DOFUS. En particulier, Rapide et Instantané ne sont PAS certifiés fiables sur 2/4/6/8 comptes. La PR reste Draft.

## Lot fonctionnel 04/11 — Miroir clavier sans blocage souris

- Le Miroir clavier (2/4/6/8 comptes) n'acquiert plus `InputState.begin_mouse_block` : aucune émission de souris ni déplacement du curseur n'y avait lieu. Les clics physiques doivent rester natifs, sans second worker.
- Le clic physique du favori pendant `Miroir clavier` n'est plus consommé par le callback occupé ; la diffusion clavier conserve ses vérifications de focus et Stop.
- Le Miroir molette authentifie tout son roster avant de bloquer la souris ; son blocage reste actif pendant l'activation, le déplacement du curseur, SendInput et la restitution.
- Tests 2/4/6/8 + roster invalide + callback occupé, et attentes historiques du blocage clavier corrigées sans supprimer de tests.
- Non certifié : tests Windows/PySide6 et Doctor/Graphify NOT_RUN dans cette session. **MIRR-007 reste partiellement ouvert pour le Miroir clic/molette et SwitchClick ; le hook partagé n'a pas été modifié.** PR Draft.

## Complément du lot fonctionnel — préflight molette et paires physiques

- Tant que `Miroir molette` n'a pas acquis le blocage natif (phase de validation des sessions), les clics physiques traversent le hook comme dans `Miroir clavier`. Dès que le pointeur doit être déplacé, les clics restent bloqués jusqu'à la restitution, afin d'éviter de cliquer une autre fenêtre pendant SendInput.
- Tests d'intégration simulée Win32 sur les paires DOWN/UP physiques en Miroir clavier avec 2/4/6/8 comptes, tests de bascule preflight→delivery pour la molette et adaptation de l'ancienne assertion de blocage clavier.
- Ne constitue pas une résolution complète de MIRR-007 : les clics pendant la diffusion des clics ou des molettes sont toujours bloqués. **NOT_RUN** pour Doctor, PySide6, Graphify et recette DOFUS Unity ; PR Draft.

## Fast-path natif du callback pendant Miroir clavier/molette (04/11)

Le callback souris laisse désormais immédiatement passer les clics physiques si un worker clavier est occupé ou si le worker molette n'a pas encore acquis son blocage protecteur. Ce chemin ne parcourt plus le roster ni n'interroge Win32 pour 2 à 8 comptes sur ces clics : il réduit la durée du callback low-level et évite de traiter comme un clic Miroir une action qui ne doit pas l'être. Le clic pendant le déplacement du curseur par la molette reste protégé. Tests ciblés 2/4/6/8 ajoutés ; exécution Python/Windows et Doctor non réalisée. MIRR-007 global reste ouvert, PR Draft.

## Maxi-lot fonctionnel 04/11 — Switch clic sans blocage avant la diffusion

**Cause racine :** `SwitchClickMacro.run_async` réservait le blocage souris depuis le callback Win32, avant que le worker n'examine la source, la composition 2/4/6/8 et les conditions d'arrêt. Une attente ou un refus de démarrage prolongeait ainsi inutilement la consommation de clics natifs.

**Nouveau contrat :** le callback capture et lance uniquement le worker. Le worker lit la position originale, valide source/favori/roster et ne prend le blocage qu'après ce preflight, juste avant la phase d'activation et de déplacement du pointeur. Une source manquante, un roster incomplet, une demande Stop, une seule fenêtre source déjà servie n'acquièrent aucun blocage. Les cas où le worker déplace réellement le pointeur conservent le blocage jusqu'après restitution du curseur/favori. La durée réelle du blocage est maintenant journalisée en millisecondes (`blocage_souris_ms`), sans attribuer cette mesure à un rendu Unity.

**Scénarios ajoutés :** 2/4/6/8 personnages, callback avec worker en attente, prévalidation sans blocage, protection lors de chaque émission, roster incomplet, Stop avant diffusion, refus de spawn et exception du runner. Tests écrits, **NOT_RUN** sur Python/Windows/DOFUS dans cette session. **MIRR-007 non clos** : les clics physiques pendant une diffusion où le curseur est activement déplacé restent bloqués par le hook partagé ; pas de replay ou refonte structurelle sans Doctor + Graphify exact-SHA. PR Draft.

### Contrat physique complété : paire native DOWN/UP et worker différé

Des tests d'intégration simulée du vrai callback `MouseHook._mouse_proc` vérifient qu'un DOWN du favori est consommé une fois, que son UP reste réservé même avant l'acquisition du blocage physique par le worker, et que la diffusion suivante émet un clic par session pour 2, 4, 6 et 8 clients. En cas de roster rejeté avant envoi, le UP reste consommé (pas de libération orpheline) sans vol de focus ni blocage physique permanent. Tests écrits mais **non exécutés** sur Windows/PySide6 ; résultat réel DOFUS à mesurer. MIRR-007 reste ouvert pour les clics reçus pendant la phase de diffusion active.

### Pas de clic perdu dans l'intervalle d'attente du worker (Macro et Miroir)

Le callback souris avait un second point de consommation : quand `MacroLock` était déjà occupé par `Miroir` ou `Switch clique`, il avalait un nouveau clic même si le worker était encore en prévalidation **sans avoir acquis le blocage souris**. Les deux chemins (Macro classique et Miroir) laissent désormais passer l'événement physique sans appel Win32 supplémentaire pendant cet intervalle. Dès que le worker prend réellement le contrôle du pointeur, les protections existantes restent en vigueur. Tests 2/4/6/8 comptes et transition entre les deux phases ajoutés. MIRR-007 reste ouvert pendant la diffusion réelle, pas pendant le préflight. Tests et Doctor/Graphify/Windows réels NOT_RUN.

## Maxi-lot fonctionnel — camembert Organizer complet (04/11)

Le camembert dispose désormais d'un interrupteur **Sélection personnage** réellement persistant (un clic sur la tuile, distinct du badge de capture de raccourci). La désactivation arrête le poll Qt et ferme immédiatement le popup, sans redémarrage des macros. Un raccourci configuré pendant OFF reste enregistré mais inactif ; à la réactivation il retrouve ses participants et sa touche. Les anciens profils restent ON par défaut pour conserver leur comportement.

**Roue :** couleurs `UNITY_PALETTE` et portraits déjà configurés ; logo local DOFUS ATLAS rendu au centre avec suppression légère du fond sombre, mis en cache après le premier affichage. Pointer volontairement vers le centre puis relâcher le raccourci ramène **la fenêtre Atlas existante** au premier plan (HWND sentinel `0`), sans instance supplémentaire. Relâchement sans déplacement ou Escape : annulation ; sélection d'un secteur : fonctionnement initial inchangé. Reconfigurer une touche encore maintenue requiert un relâchement avant ouverture.

**Sessions :** les fenêtres nouvellement détectées par la surveillance Organizer sont automatiquement proposées dans la roue si la fonctionnalité est activée. Retirer manuellement un personnage crée une exclusion enregistrée ; le scan suivant ne l'ajoute pas de force. Cliquer à nouveau retire l'exclusion. L'ID `character:<id>` garde la sélection entre redémarrages du jeu ; une identité non vérifiée n'est suivie que pour le processus courant (PID). Aucun watcher, réseau ou second roster introduit.

**Sécurité :** les HWND/PID invalides, float/NaN/inf/bool, doublons et index non entiers sont refusés dans la sélection. 2/4/6/8 secteurs et l'ordre Organizer conservés. Nouveaux tests Qt offscreen et purs : centre, annulation, rebind, cache logo, activation Atlas, toggle ON/OFF, sync/optout, profil absent et identité vérifiée. **Exécution Python/PySide6/Doctor/Graphify/Windows : NOT_RUN.** PR Draft, pas de fusion.

## Conflits de raccourcis résolus : roue > slot, Stop toujours prioritaire

Un même raccourci peut désormais être attribué à **Sélection personnage** et à un slot. Quand la roue est activée, la construction canonique du registre supprime seulement l'action de changement direct du slot qui utilise la même combinaison, évitant deux activations. Quand elle est désactivée, le slot récupère sa touche après un rechargement ciblé. Le toggle ne relance le registre que lorsqu'il existe un partage réel. L'interface précise la priorité. Stop urgence, Switch clic, personnage suivant et déplacements restent exclusifs (et un ancien profil ayant partagé Stop/roue ne peut jamais ouvrir la roue).

La touche de roue n'est pas dupliquée par le Miroir clavier : interception explicite dans le callback, avec analyse de combinaison mise en cache sur 32 entrées ; la roue ne s'ouvre pas si l'utilisateur ajoute un modificateur système non configuré (ALT/CTRL/SHIFT/WIN). Tests ciblés sur les deux ordres de capture, 2/4/6/8 sessions, toggle ON/OFF, profils runtime, Stop, modificateurs et clavier Miroir. **NOT_RUN** : Python/PySide6, Doctor, Graphify exact-SHA et Windows/DOFUS. Pas de certification.

## Lot fonctionnel Auto-groupe : invitations prévalidées et état réel (04/11)

- Prépare et déduplique les destinataires avant de changer le focus : exclut le lanceur, les noms vides et les doublons. 1 compte seul ou Stop déjà demandé → aucune activation de fenêtre ni saisie chat.
- Envoie séquentiellement aux destinataires dans l'ordre Organizer conservé ; l'attente configurable entre invitations est maintenue mais **pas après la dernière**, pour éviter le retard inutile avant le retour au favori.
- Le résultat booléen du lancement traverse maintenant `AutoGroupMacro` → `AtlasRuntime` → `AtlasWindow` → `Organizer`. L'UI distingue worker accepté, lancement refusé et ancien callback sans réponse, sans prétendre que les invitations ont été réellement reçues.
- Une exception du callback de lancement est journalisée et signalée sans remonter dans l'événement Qt. Les logs détaillent les exclusions de destinataires sans nouveaux scans ni threads.
- Tests écrits : 2/4/6/8 comptes et doublons, absence de dernier délai, chat partiellement refusé, Stop précoce, 1 compte, statuts Organizer True/False/None, exception UI, refus du runtime. **NOT_RUN** (Python/PySide6/Doctor/Graphify/Windows). Macros Zaap et Direction existantes déjà dotées de garde focus/restauration en finally, laissées inchangées. PR Draft, MIRR-007 ouvert.

## Lot Zaap — fermeture immédiate + lancement réellement confirmé

Le panneau Zaap fermait déjà son sous-menu avant le rappel runtime (preuve dans `tests/test_organizer_zaap_popup.py`). Le résultat du lancement est maintenant transmis `ZaapMacro.run_async` → `AtlasRuntime.launch_zaap` → `AtlasWindow.launch_zaap` → `ZaapWidget.launch_zaap` : **accepté / refusé / non confirmé**. Il n'annonce plus « lancé » lorsque la macro est occupée, que le callback manque, qu'il lève une erreur, ou qu'un ancien adaptateur ne confirme rien. Les coordonnées invalides ferment aussi le sous-menu sans envoyer de commande, comme avant. Tests Qt offscreen nouveaux : cinq états de lancement, exception callback, absence de runtime, compatibilité callback sans argument et statut confirmé; test de validation du parseur et refus du verrou.

Les envois réels restent séquentiels et soumis aux protections de focus/Stop. La réception effective de la commande par Unity n'est **jamais** déduite du retour de `run_async`. Vérifications locales Doctor et tests Windows **NOT_RUN**.

### Compteurs visibles en fin de macro Auto-groupe / Zaap (04/11)

Le worker émet un statut final dans l'interface (pas seulement un log) : `termine`, `partiel`, `interrompu` ou `ignore` avec le nombre de **commandes effectivement transmises** au moteur SendInput sur le nombre prévu. Les statuts d'absence de fenêtre, de commande invalide, de Stop initial ou d'activation impossible sont explicites. La mention « réception DOFUS non vérifiée » reste systématique : ni un test mock ni SendInput ne prouvent que le jeu a effectivement pris en compte l'invitation ou le zaap.

Tests ciblés rédigés pour Auto-groupe/Zaap en 2, 4, 6 et 8 comptes, succès et échecs partiels, aucune cible, stop précoce et absence de vol de focus pour un seul compte. **Exécution NOT_RUN** ; livrable non certifié.

### Arrêt de l'application entre le clic et le runtime (Auto-groupe et Zaap)

Le chemin UI `AtlasWindow` vérifie `quit_requested` et `_background_services_stopped` **avant et après** le rechargement des sessions. Si la fermeture de l'application commence pendant celui-ci, le lancement Auto-groupe/Zaap retourne `False` et ne crée ni worker ni runtime. Tests ciblés sur les deux états de shutdown et sur le retour vrai/faux du runtime. Le Stop urgence actif continue de contrôler les travailleurs déjà lancés via `MacroLock.should_stop`. Tests non exécutés, PR Draft.


## Suite fiabilité Organizer/Macro/Miroir — 04/11/2026 (PR #325)

**Objectif :** ne jamais envoyer une action reçue pour une génération Organizer
vers des fenêtres rechargées, même si les mêmes HWND restent visibles.

- MirrorInputMacro garde le profil exact entre capture clavier/molette,
  acceptation du worker et premier contrôle du worker. Les callbacks
  natifs abandonnent le geste sans consommation si le profil change pendant
  les vérifications Win32, y compris après calcul des ratios de molette.
- SwitchClickMacro reçoit le profil capturé du Miroir ou du clic physique
  natif classique. Le DOWN/UP qui n'a pas été avalé reste transmis au jeu ;
  une duplication devient un refus explicite si le profil change pendant
  le contrôle du processus avant émission.
- Direction, Auto-groupe et Zaap transportent la génération d'acceptation
  jusqu'au worker. Un worker différé ne peut pas reprendre une action
  précédente sur un nouveau profil.
- SwitchCharacterMacro refuse les index/handles altérés et protège
  Personnage suivant, le roster, la découverte du personnage actif et
  le retour au favori contre les rechargements pendant les sondes Win32.
  Les sources HWND fractionnaires/booléennes/non finies ne sont plus
  converties en une autre fenêtre ; seule une source 0 implicite déclenche
  la recherche historique du personnage actif.
- Auto-groupe n'arrondit plus les HWND des invitations : un destinataire
  nommé ne peut être supprimé simplement parce que 101.9 avait été
  interprété comme le HWND 101 du lanceur. Les anciennes chaînes
  numériques entières restent reconnues.
- Zaap : fermeture du sous-menu avant le rappel runtime déjà conservée.
  Les callbacks Qt d'affichage planifiés **avant** la sélection ne peuvent
  plus le rouvrir après clic. Une nouvelle recherche ou interaction explicite
  réautorise le menu.
- Instrumentation Miroir : dispatch_to_worker_ms mesure le délai entre
  acceptation et démarrage du worker ; dispatch_to_last_emit_ms finit à la
  **dernière émission SendInput réussie** ou vaut NOT_MEASURED s'il n'y en
  a aucune. Ce n'est ni la latence du hook initial ni celle du rendu Unity ;
  aucune équivalence mesurée 2→8 comptes n'est revendiquée.
- Tests mock et Qt offscreen **ajoutés/actualisés**, en ciblant les rechargements
  identiques, les courses Win32, le Stop, les sources corrompues et les
  scénarios 2/4/6/8 ; attentes historiques activate_next mises en
  cohérence avec expected_profile.

**Preuves :** commits présents sur la branche, mais tests Python/PySide6,
Doctor, Graphify exact-SHA, campagnes Windows/DOFUS Unity, mesures p50/p95/p99
et CPU/RAM **NOT_RUN** dans cette session. Aucun critère manuel n'est validé
par des mocks. Le P0 **MIRR-007** (clics consommés lors du blocage physique du
Miroir molette / Switch clic) **n'est pas résolu** : le changement structurel
du hook partagé attend Graphify au HEAD exact et une recette réelle. PR Draft,
ne pas fusionner ; conflit de fusion GitHub avec main à traiter avant revue.

## 05/11/2026 — dispatch raccourcis et Switch clic figés à leur génération

- Le callback des raccourcis **slot**, **personnage suivant** et **déplacement**
  utilise désormais un seul instantané de profil Organizer. Il propage
  l'identité du profil jusqu'au point d'acceptation de la macro ; si une
  mise à jour survient pendant la lecture du HWND, du bouton de commande
  ou le passage au worker, la commande périmée est refusée.
- Le **Switch clic classique** garde la même génération entre l'action du
  registre, le hit-test souris, les vérifications du focus et le démarrage
  d'un worker ; un changement de profil préserve le DOWN physique plutôt
  que de le transformer en ancien double-clic.
- Un clic arrivé pendant la bascule **Macro/Miroir** ne peut plus démarrer
  la diffusion Miroir si le mode actif est redevenu Macro. Pour les gestes
  clavier/molette reçus sous occupation Miroir, un rechargement du profil
  pendant le contrôle natif d'un secondaire conserve l'entrée physique
  au lieu de l'avaler sur la base d'un ancien roster.
- Les activations différées de personnage figent maintenant le **slot, HWND
  et libellé** : modifier en place un objet de session dans le roster ne
  peut plus altérer la cible d'un worker déjà accepté.
- Nouveaux scénarios de non-régression **simulés** pour 2, 4, 6 et 8
  comptes : mutations de session, remplacement pendant raccourci, capture
  et contrôles natifs, bascule du mode et démarrage différé.

**Preuves et limites :** code et tests présents sur la branche, aucun test
Python/PySide6 réellement exécuté ici, ni Doctor agent plan/check/validate,
ni Graphify exact-SHA, ni essai Windows/Unity. Le P0 **MIRR-007** reste
ouvert : ces refus explicites de gestes périmés ne corrigent pas la perte
de gestes pendant un blocage souris actif. Ne pas déclarer zéro perte ni
équivalence des latences 2 à 8 comptes. Maintenir la PR en Draft, résoudre
les conflits GitHub avec main avant toute certification et fusion.

## 05/11/2026 — sécurité des raccourcis et arrêt du runtime (PR #325)

- La sélection directe d'un personnage transmet désormais son identifiant de
  slot jusqu'au `should_stop` de l'activation Win32. Une réaffectation du
  même profil pendant les tentatives de focus annule la commande, même si
  l'objet de paramètres n'a pas été remplacé.
- Le retour au favori fige le HWND choisi : un enregistrement de session
  modifié en cours d'activation ne peut plus devenir le nouveau HWND publié.
  L'entrée canonique rejette aussi les HWND absents, non entiers, booléens ou
  hors plage avant les contrôles Windows, avec la même sélection normale.
- Le bouton **Personnage suivant** n'initialise plus le runtime si la
  fermeture est engagée, y compris lorsque l'état d'arrêt change pendant
  l'acquisition du runtime.
- Le chemin **Switch Déplacement refusé** n'envoie plus quatre KEYUP
  synthétiques dans une application étrangère alors qu'aucun KEYDOWN n'a
  été émis par cette action. Les relâchements explicites du **Stop urgence**
  et le `finally` de chaque appui autorisé restent inchangés.
- Scénarios Python de régression **rédigés** pour 2/4/6/8 comptes :
  mutations slot/HWND pendant l'activation, favori réaffecté, source hors
  DOFUS, profil remplacé au milieu des sondes Win32 et absence de
  rechargement du runtime pendant sa fermeture.

**Classification du lot : MEDIUM** (contrôles Win32/focus et chemin de
libération clavier). La revue statique au SHA du lot n'est pas une preuve
d'exécution des tests. `Doctor agent plan/check/validate`, tests
Python/PySide6, Graphify exact-SHA et recette Windows/DOFUS : **NOT_RUN**
dans cette session. Les tests de simulation rédigés ne sont pas PASS.

**Ouverts :** MIRR-007 (gestes physiques avalés sous blocage souris),
validation réelle du ressenti 2/4/6/8, contrôles Doctor/Graphify, conflit
GitHub avec `main`, et certification indépendante. Ne pas marquer les
exigences #321 terminées ni transformer la PR Draft en Ready avant preuves.

## 05/11/2026 — sélection et admission Miroir (reprise PR #325)

- Le statut de **Miroir clavier/molette** distingue désormais une émission
  complète (N/N appels synthétiques) d'un **profil ou roster modifié après
  le dernier envoi**. Ce statut n'est jamais une preuve de rendu Unity.
- Le worker refusé **pendant l'admission** ne fait plus consommer le geste
  physique si Organizer a changé de génération avant le retour au hook.
  L'entrée clavier/molette vérifie aussi le favori, le mode, l'ordre des
  HWND et les limites entières 64 bits dans la mémoire du profil, **sans
  ajouter de sondes Win32 aux hooks**.
- Les cibles **Personnage suivant**, la liste ordonnée des fenêtres et
  la détection du personnage actif refusent une mutation d'un objet de
  session **pendant** les sondes de processus. L'identité vérifiée d'un
  HWND ne peut plus autoriser par alias un nouvel HWND flottant/booléen
  ni une réaffectation d'un client déjà inspecté.
- Matrice de tests déterministes **rédigés** pour 2/4/6/8 comptes :
  modification du dernier geste clavier/molette, rechargement pendant
  `_spawn_macro`, HWND altéré dans le roster, fenêtre source/slot réaffecté,
  comparaison favorite-first nominale, et handles entiers hors plage.

**Risque du lot : MEDIUM (entrées natives et contrôle de source).**
Aucun test Python/PySide6, Doctor agent, Graphify exact-SHA, benchmark ni
essai Windows/Unity **exécuté** dans cette session GitHub.
Les 2/4/6/8 sont des *configurations de tests écrits*, pas des PASS.
Le P0 **MIRR-007** demeure ouvert : aucun Graphify Code Map artifact
du HEAD exact n'a été retrouvé, le hook partagé n'a donc pas été refactoré
sans preuve d'impact. Les conflits avec `main`, l'audit PR complet et la
certification indépendante restent à résoudre avant fusion.

## Reprise de fiabilité du 05/11/2026 — génération du favori et du mode

Cette reprise part de la PR #325 au SHA `6f66a67bf6a45e511c77dd02662e16238fd3ced0`.
Les corrections **non structurelles** restent confinées aux workers Organizer,
sans modifier les hooks globaux, leur source de vérité ni le sender canonique.

- **Auto-groupe, /zaap et Direction :** chaque travailleur conserve le profil
  d'origine et la paire `(primary_handle, macro_mode)` au dispatch. Il annule
  avant les sondes natives si cette paire a changé pendant l'admission ;
  il revérifie ensuite pendant les recherches source/roster, chaque activation
  et chaque frontière d'envoi, y compris les callbacks de chat annulables.
  Une nouvelle sélection de favori ou une bascule Macro/Miroir ne doit pas
  poursuivre silencieusement une diffusion multi-fenêtres.
- **Restitution :** les trois workers refont la vérification de génération
  immédiatement avant de restaurer le favori. Un changement pendant une
  sonde native de nettoyage ne permet plus une restauration obsolète.
- **Changement de personnage :** le hotkey direct lie le slot/HWND et la
  génération favori/mode ; sa restauration préférée protège la sélection et
  le mode pendant et après `activate_window` et le contrôle natif final.
  L'action **Personnage suivant** vérifie également cette génération
  pendant son scan de 2 à 8 clients et la résolution du client actif.
- **Simulation ajoutée :** `tests/test_organizer_favorite_inflight.py`
  contient 26 méthodes de régression sur **2/4/6/8 comptes** : changements
  en place pendant admission, lookup source/roster, focus, chat, dernière
  émission et nettoyage. Elles conservent la distinction entre commandes
  acceptées, interruptions et réception non prouvée côté Unity.
- **CI ownership :** le nouveau test possède une entrée explicite dans
  `ORGANIZER_TEST_PATHS` et une assertion dédiée dans le test du
  routage par domaine. La classification des chemins inconnus reste
  bloquante ; aucun wildcard n'a été ajouté.

**Preuves / limites :** revue statique des sources et des commits de cette
reprise ; Python/PySide6 et Doctor agent plan/check/validate **NOT_RUN**
(absence de checkout exécutable dans la session GitHub), Graphify exact-SHA
**NOT_AVAILABLE**, campagne Windows/DOFUS 2/4/6/8, p50/p95/p99,
CPU/RAM et certification **NOT_RUN**. Le P0 **MIRR-007** reste ouvert :
les clics physiques reçus pendant un véritable blocage du pointeur
ne sont pas rejoués. Une file bornée ou un refactor du hook partagé
demandent Graphify sur le SHA exact, Doctor structurel, essais ciblés
et recette Windows avant de prétendre à la non-perte. Garder #325 en
**Draft / CHANGES REQUIRED**, sans fusion.


## Suite ciblée du 05/11/2026 — nettoyage sûr, admission et Stop

Base : `abf6a786eb36fe47e13e5e7b401a8f9042598942`.
HEAD de code : `c345089ac8511b1ec1c23201d2009590bb1aabba`
(**9 commits**), PR #325 en **Draft**. Périmètre non structurel :
Auto-groupe, Direction, /zaap, Switch clic, Miroir clavier/molette et tests.

- **Restitution non intrusive :** le Miroir vérifie une seconde fois
  favori/mode/roster/Stop après sa sonde native finale ; Auto-groupe,
  Direction et /zaap revérifient leurs identités HWND juste avant le
  retour au favori. Le Switch clic refuse de repositionner le pointeur
  si Stop arrive lors du contrôle de focus en fin de diffusion.
- **État exact :** les trois macros ne déclarent plus une émission complète
  comme `termine` lorsqu'un favori change pendant la dernière commande.
  Elles refusent aussi de déclarer leur lancement accepté si le profil,
  le mode ou Stop change pendant `_spawn_macro`.
- **Miroir :** une touche/molette native n'est pas avalée lors d'un Stop
  pendant l'admission. Le worker annule avant les sondes Win32 et avant
  l'acquisition du blocage souris si Stop est actif ; il interrompt la
  prévalidation des autres clients dès qu'un Stop arrive dans une sonde
  de processus, sans émission résiduelle programmée.
- **Tests ajoutés (mais non exécutés) :** scénarios déterministes
  2/4/6/8 dans `tests/test_organizer_mirror_ui.py` et
  `tests/test_organizer_macro_reliability.py` : mutations au nettoyage,
  changement de favori après la dernière émission, admission concurrente,
  Stop pendant admission/préflight/focus. Le comparatif GitHub constate
  exactement 9 commits de code, 7 fichiers modifiés, aucun changement de
  hook global ou de sender canonique.

**Preuve disponible :** revue statique des chemins et tests (noms uniques,
pas de marqueurs de conflit ni d'espaces finaux), comparatif exact des
commits GitHub. **Non exécuté :** tests Python/PySide6, Doctor
`agent plan/check/validate`, Graphify exact-SHA, Windows/DOFUS,
p50/p95/p99, CPU/RAM, Phase Certification et audit global de la PR
historique. L'environnement présent ne permet pas un checkout Windows
exécutable. Les contrôles sont des protections de logique, pas une preuve
d'acceptation des événements par Unity. **MIRR-002, MIRR-005, MIRR-007
et recette #322 restent bloquants** ; ne pas annoncer READY / CERTIFIED
ni fusionner.

## 05/11/2026 — admission physique du Miroir et contrat Stop (PR #325)

Les corrections de cette reprise privilégient une **acceptation stricte du
geste physique avant toute injection**, sans changer le hook natif partagé :

- **Clic Miroir** : validation bornée des ratios et des pixels client
  avant consommation du DOWN ; le roster favori-first est figé avant les
  premières sondes Win32 et revérifié après celles-ci et pendant le worker.
  Un changement de mode, favori ou HWND n'autorise jamais une nouvelle
  diffusion au titre de l'ancien clic.
- **Clavier/molette** : même gel des 2–8 HWND avant les sondes de processus,
  annulation si les destinataires changent en place, liste illisible,
  profil remplacé ou focus source perdu avant le worker.
- **Worker occupé** : pour clavier, molette et clic, le signalement d'un
  geste non diffusé revérifie Stop, l'état du worker et les valeurs
  d'Organizer. Les événements physiques ne sont pas consommés au titre
  d'une session déjà terminée ou réaffectée.
- **Sémantique de Stop** : `MacroLock.request_stop` garde `stop_event`
  positionné jusqu'à un futur `try_begin`. Cela **n'interdit pas** un
  nouveau geste après libération du verrou : les vérifications de Stop
  à l'entrée du hook concernent seulement un **worker encore actif**.
  Les workers conservent leurs propres vérifications après admission,
  après `try_begin`, avant chaque envoi, et en nettoyage.
- **Mesures** : la durée `blocage_souris_ms` instrumente le bail physique
  pendant la diffusion molette, indépendamment de la latence des appels
  SendInput et **sans prétendre mesurer le rendu Unity**.
- **Régressions rédigées** : cas de curseur corrompu, snapshots modifiés
  pendant les premières sondes, Stop actif/terminé, favori en premier ou
  dernier slot, état muté durant le signalement occupé, et reprise après
  Stop pour 2/4/6/8 comptes.

**Validation : NON CERTIFIÉ.** Modifications et tests sauvegardés dans la
PR ; aucun test Python/PySide6 ou Doctor agent exécuté par l'environnement
GitHub de cette reprise. Aucun Graphify exact-SHA, aucune recette Windows
DOFUS/Unity, mesure CPU/RAM ou preuve p50/p95/p99 native. Une expérience
de rendu réel et des règles d'utilisation applicables restent à évaluer.

**MIRR-007 PENDING** : les DOWN physiques interceptés **pendant le blocage
global du pointeur** peuvent toujours être perdus. Ce lot protège surtout
l'admission et l'invalidation des gestes ; il ne crée **aucune file de
replay** et ne refactore **aucun hook global**. Faire Graphify exact-SHA,
Doctor structurel et la recette Windows 2/4/6/8 avant toute politique de
diffusion différée. Garder la PR **Draft / CHANGES REQUIRED**.

## Lot P0 du 05/11/2026 — intégrité des XBUTTON et mesures clic Miroir

- Le hook Win32 différencie `XBUTTON1` et `XBUTTON2` via le HIWORD de `MSLLHOOKSTRUCT.mouseData` lors de l'appariement d'un DOWN physique consommé avec son UP. Deux boutons latéraux pressés pendant un blocage ne doivent plus s'annuler mutuellement ; le Stop ou un UP synthétique n'efface pas la paire restante.
- Le chemin chaud `WM_MOUSEMOVE` évite d'interpréter le HIWORD des boutons X à chaque déplacement. Aucune nouvelle requête Win32 ni file de replay sur le thread hook.
- Les clics Miroir utilisent le moteur `SwitchClickMacro` existant et publient désormais aussi `dispatch_to_worker_ms` et `dispatch_to_last_emit_ms` lorsque la séquence a réellement émis un clic. `NOT_MEASURED` est affiché si aucun clic n'a été émis. Ce temps commence à l'admission `run_async` (après les contrôles de hook), **pas** au premier signal matériel : ni délai physique complet, ni rendu Unity attesté.
- Tests mock nouveaux/ciblés pour X1/X2, Stop, UP synthétiques, rafales de MOVE, propagation du timestamp, et cas de rejet sans émission, y compris 2/4/6/8 profils.
- **Preuves manquantes :** la suite Python ciblée et la recette Windows/Unity restent à lancer/confronter au SHA courant. Doctor on-demand est `FULL_REQUIRED` sur ce large diff et n'a pas dispatché les tests (cela n'est PAS un PASS). Les gestes perdus quand le blocage est actif restent **MIRR-007 PENDING** ; le support ciblé sans focus reste MIRR-002 PENDING ; MIRR-005/ATQA-002 restent NOT_RUN sous #322.


## Lot P0 — génération des baux souris et sélection radiale stricte (05/11/2026)

- `InputState.begin_mouse_block/end_mouse_block/clear_mouse_block` conservent
  les signatures existantes mais lient désormais chaque réservation à la
  génération en cours **et au thread acquéreur**. Stop invalide la génération
  précédente : la sortie tardive de Miroir, Switch clic ou d'un ancien worker
  ne peut plus retirer le blocage d'un nouveau worker. Pas de file ou
  d'injection parallèle ajoutée.
- Pendant qu'un worker Miroir est occupé **sans bail de pointeur**, les touches
  et molettes d'une fenêtre secondaire déjà inscrite passent directement en
  entrée native. Les contrôles de processus Win32 coûteux ne sont plus
  exécutés sur ce chemin de callback. Le chemin avec bail de pointeur conserve
  son contrôle d'identité et son refus des gestes non synchronisés.
- `radial_selection` refuse les alias d'identifiants HWND/PID (booléens,
  fractions, notations scientifiques, dépassements, chiffres non ASCII)
  pendant la construction du roster, la sélection et la confirmation sur
  relâchement. Les anciens entiers et nombres décimaux ASCII restent valides.
- **Validation partielle exacte source** : tests Python isolés du bail souris
  (`tests/test_organizer_pointer_lease_epoch.py`) : 5/5 réussis sous Python
  3.13 sur copies dont les SHA Git blob correspondent à la PR. Vérifications
  pures `radial_selection` pour 2/4/6/8 clients et cas HWND/PID corrompus
  réussies sur une copie de SHA Git blob exact. **Pas** une validation du
  runtime Windows, du hook Win32 ni de la suite PySide6 complète.
- **Limite de MIRR-007** : les clics physiques pendant une diffusion déjà
  propriétaire du pointeur peuvent encore être consommés. Ne pas annoncer
  résolution complète, replay garanti, compatibilité Unity sans focus ou
  performances identiques 2→8 sans recette Windows.


## Lot P0 — exclusivité des générations Macro et routage CI explicite (05/11/2026)

Point de départ : `8eb44acef96e6fe1483f89b79245334c66eb27e2`.
PR #325 conservée en **Draft** pendant le développement.

- **Cause racine :** le contrôle du verrou `MacroLock` par le seul label
  `Miroir` ne suffisait pas à distinguer un ancien thread d'une nouvelle
  exécution de même nom après Stop/restart. Les `try_begin` restaient exclusifs,
  mais une fin retardée ou une annulation de démarrage pouvait relâcher un bail
  réutilisé ou remettre à zéro la protection synthétique d'un autre worker.
- **Correction :** `try_begin_generation` réserve le bail et retourne son
  numéro **atomiquement**. `_spawn_macro` lie chaque worker à cette génération
  avant `target()`; un runner périmé ne démarre pas et sa fin ne libère plus
  un bail plus récent. `MacroLock.should_stop()/wait()` restent en arrêt
  même si un nouveau runner efface le signal Stop partagé. Le contrat
  `try_begin(label) -> bool` est conservé pour les consommateurs existants.
  Le même contrôle empêche la fin d'un vieux runner de réinitialiser le
  `SyntheticInputGuard` du nouveau.
- **Tests :** `test_organizer_macro_generation.py` contient les cas de
  démarrage différé, relâchement/Stop d'une génération précédente, reset
  synthétique, délai et contestation simultanée du même nom pour **2/4/6/8**
  comptes. `test_runtime_lazy_macros.py` vérifie le numéro du bail libéré
  lors d'un échec de création/démarrage du thread.
- **Routage CI intelligent :** 15 fichiers de tests Organizer P0 explicitement
  revus ainsi que `test_managed_hooks_lazy.py` bénéficient désormais de
  leurs vrais domaines de certification ; `app/windows/focus.py`,
  `app/windows/unity_windows.py` et `app/storage.py` gardent leurs
  dépendances inter-domaines réelles. Aucun wildcard permettant à un nouveau
  backend d'injection de se déclarer Organizer n'a été ajouté. Les tests de
  routage continuent à déclarer les chemins non revus **BLOCKED**.
- **Preuves ciblées :** contrôle Git blob SHA et exécution isolée de
  `MacroLock` sous Python 3.13, **6/6 tests PASS**, dont 5 tours de
  concurrence pour 2, 4, 6 et 8 threads. Les tests Python/PySide6 de
  `AtlasRuntime`, le hook Win32 réel, le rendu Unity et les performances
  p50/p95/p99 **ne sont pas certifiés**. Graphify exact `b54444f6`
  a produit `PASS` structurel, mais son workflow a échoué en étape
  fraîcheur à cause de nouveaux commits ; ce résultat n'est PAS celui
  du HEAD final.

**Limite technique :** le P0 **MIRR-007** reste PENDING pour les clics natifs
produits lorsque le worker détient réellement le pointeur. Ne pas rejouer
ces clics à l'aveugle vers un HWND potentiellement différent : les tests
Windows/DOFUS Unity et une politique d'émission fiable sont indispensables.
Ne pas changer la PR en Ready ni déclencher Phase Certification globale.


## Lot P0 — courses de génération en entrée physique et Stop urgent (06/11/2026)

Base : `cfe29e614076490d0414882603693b9a3e242329`.
Les changements ci-dessous sont **locaux** au chemin Miroir/Stop et
maintiennent le comportement non destructif lorsqu'un événement peut
encore être transmis nativement sans toucher au pointeur. La PR reste
Draft et MIRR-007 n'est **pas** considéré comme résolu.

- `c6bb7667`, `cf695ecf` : lors d'un événement physique alors que le
  worker est occupé, comparer **label + génération réelle du bail Macro**
  au début, après les sondes Win32 et après le signalement d'un geste
  non diffusé. Si un ancien worker finit et qu'un autre commence sous
  le même nom pendant ces opérations, ne pas avaler le DOWN/clic,
  la touche ou le cran de molette au titre du nouvel occupant.
- `e8e74820` : `MacroLock.wait` vérifie son Stop / token de génération
  par tranches d'au plus 25 ms pour ne pas manquer indéfiniment l'annulation
  si un redémarrage efface le même `threading.Event`. C'est la limite
  des **tranches de sommeil**, pas une latence p99 mesurée sous Windows.
- `a9dd4ddb` : `MacroLock.request_stop` revalide le signal Stop
  sous le verrou d'admission, en plus du premier signal immédiat ; ce
  dernier ne peut plus être effacé silencieusement par un `try_begin`
  concurrent avant la fin du Stop.
- `f0674640` : les clics et les molettes perdus pendant un blocage
  disposent de deux horloges de logs limitées séparément (400 ms),
  avec leurs compteurs cumulés, pour qu'une rafale de molette ne masque
  pas l'avertissement du clic perdu. Aucun événement n'est rejoué,
  ni reclassé comme transmis.

**Tests rédigés :** scénarios 2/4/6/8 pour changement de génération
pendant les sondes natives, pendant la publication du statut, attente
périmée et relance, entrelacement précis de Stop et d'un nouveau
`try_begin_generation`, et limitation de fréquence indépendante des
deux types d'entrées. Ces tests n'ont **pas** été exécutés sur Windows,
PySide6 ni DOFUS Unity dans cet environnement.

**Risques à certifier :** le hook physique continue à bloquer un
DOWN quand un worker détient effectivement le pointeur ; MIRR-007
nécessite une politique de conservation/repli reproductible sur Windows.
Le support Unity sans focus (MIRR-002) et les mesures 2/4/6/8 (MIRR-005)
restent sans preuve réelle. Pas de READY, de Phase Certification ni de
fusion sur ce lot.


## Lot complémentaire P0 — souris native rapide et propriétaire atomique (06/11/2026)

Base `334a14783b24fdc034377c42d50888f2f97f8be8`.
Graphify exact de cette base = PASS avec 18 426 nœuds.
Graphify exact de `b79c6e2d` = PASS avec 18 428 nœuds.
Ces rapports orientent l'impact structurel des consommateurs du
`MacroLock`, de `AtlasRuntime` et du hook souris.

- **Hot path natif :** `MouseHook._mouse_proc` évite de décoder
  `MSLLHOOKSTRUCT` lors d'un simple `WM_MOUSEMOVE` non bloqué. Le mouvement
  est transmis par `CallNextHookEx`. Le cas pointeur bloqué conserve le
  décodage des drapeaux d'injection, le refus du mouvement physique et
  la transmission des mouvements synthétiques. Un test de 50 × 2/4/6/8
  mouvements et un test de mouvement pendant blocage sont rédigés.
- **Propriétaire cohérent :** `MacroLock.snapshot_active()` retourne sous
  le même verrou l'étiquette et la génération du worker actif.
  Les trois entrées Miroir comparent ensuite le bail exact avant toute
  suppression d'un événement physique, après les sondes et après les
  callbacks de journalisation. Les entrées clavier/molette prennent ce
  snapshot **avant** `GetForegroundWindow`, qui peut lui-même céder
  l'exécution à un Stop/redémarrage. Tests dédiés au snapshot,
  au remplacement en préflight et aux changements lors du focus
  pour 2/4/6/8 comptes.
- **Aucun changement du moteur d'envoi :** pas de nouveau `PostMessage`,
  pas de nouvelle file de replay, pas d'injection, pas de chemin secondaire
  contournant les contrôles natifs.

**Validation** : les tests ci-dessus ont été rédigés mais **pas** exécutés
sur Windows/Unity/PySide6 dans cette session. Le graphe couvre les
dépendances statiques, pas le rendu du jeu. MIRR-007 demeure PENDING
pour les clics supplémentaires reçus pendant un blocage réellement
actif du pointeur. Bench 2/4/6/8, p50/p95/p99, comportement souris
sur Windows et certification restent NOT_RUN.


## Lot P0 — nettoyage atomique et préflight natif sûr (06/11/2026)

Base exacte : `da757f64cbd70aac400b83220839e91f7c335767`.

- **Course de Stop/reprise :** `MacroLock.end(..., on_owner_end=...)`
  exécute la remise à zéro du `SyntheticInputGuard` uniquement sous le
  verrou du propriétaire courant, puis libère le bail. Un nouveau Miroir ne
  peut plus démarrer entre la validation de génération et l'ancien reset.
  Un échec de nettoyage reste journalisé sans bloquer les futurs démarrages.
- **Souris :** pour `WM_MOUSEMOVE` pendant un bail de pointeur, le hook
  ne décode plus coordonnées, statut de clic ou diagnostics inutiles ;
  il vérifie uniquement la provenance injectée avant de bloquer un MOVE
  physique. Les déplacements synthétiques continuent à passer.
- **Préflight Miroir :** les fiches client sans `handle` sont refusées sans
  exception pendant les contrôles des clics/touches/molette, y compris si
  une session est remplacée en cours d'identification. Un profil Organizer
  temporairement détaché conserve l'entrée native, sans lancement d'un worker.
- **Tests ajoutés :** contention nettoyage/réadmission 2/4/6/8,
  panne `SyntheticInputGuard.reset`, 2/4/6/8 profils incomplets,
  burst MOVE bloqué vs injection Atlas, paramètres de session absents.
  Ces tests sont versionnés, **pas un PASS Windows/Unity**.
- **Reste bloquant :** `MIRR-007` pour les véritables clics physiques
  absorbés lorsqu'un worker tient déjà le pointeur ; `MIRR-002` (ciblage
  Unity sans focus) et recette DOFUS 2/4/6/8 / p50/p95/p99 restent
  `PENDING/NOT_RUN`. Ne pas ajouter de replay non certifié.

## 06/11/2026 — reprise des tests réels et refus de focus à la dernière seconde

La dépendance Ubuntu `libEGL.so.1` de PySide6 a été corrigée dans la PR
d'outillage **#392**, fusionnée dans `main` (merge
`6754747f8b9ff54c7b34972118219316d77cb1d5`). Cette correction
ne modifie pas les critères de certification de la PR #325.

**Preuve ciblée exacte** : Doctor-lot
[run #42194327949](https://github.com/r9327/Dof-Atlas/actions/runs/42194327949),
candidat `007bff1f15ff22d5d6e6d9dd1dcaf4ae4331d093`, base
`e373c393eb2ac9e3ed419e7ea3e93ad7127cb91b` :
**382 tests exécutés, 382 PASS, 0 échec**, fraîcheur exacte du HEAD
confirmée. Les tests concernés sont
`tests.test_organizer_macro_reliability` et
`tests.test_organizer_mirror_ui` ; ce run ne couvre pas l'ensemble de
l'application et n'est **pas** une Phase Certification.

Correctifs confirmés dans le développement :
- `SwitchClickMacro` refuse toute restauration de focus après un Stop
  concurrent et journalise le HWND dont l'activation vient d'être annulée
  pour changement du roster, avant tout `SendInput`.
- `DirectionMacro` fige les HWND configurés **avant** la sonde Win32 du
  client source ; la modification d'une session entre la capture et
  l'envoi annule le geste au lieu de taper sur un autre personnage.
- `AtlasRuntime._mirror_gesture_targets` interrompt immédiatement une
  inspection native quand favori, profil, sessions ou Stop deviennent
  incompatibles. Le worker molette/clavier refuse un profil sans
  temporisations valides avant de manipuler une fenêtre.
- Les fixtures de tests distinguent les profils complets, le pointeur
  occupé, la véritable interruption Stop et les gestes déjà envoyés.
  Les compteurs et libellés n'assimilent plus un envoi interrompu par
  changement de favori à un parcours achevé.

**Bloquants conservés** : `MIRR-007` — nouveaux clics physiques
absorbés pendant la réservation effective du pointeur (pas de replay
garanti) ; `MIRR-002` — entrée Unity hors focus non démontrée ;
`MIRR-005`/`ATQA-002` — recette réelle Windows/DOFUS 1/2/4/6/8
et p50/p95/p99 d'actions non mesurés. Ces trois points restent
`PENDING/NOT_RUN` ; conserver la PR **Draft** et ne pas fusionner.

## 06/11/2026 — interruption du fan-out à la première nouvelle entrée physique

**Problème MIRR-007 :** une nouvelle pression/coche de molette pendant
`InputState.is_mouse_blocked()` était absorbée pendant toute la diffusion.
Ce nouveau lot ne tente **aucun replay** sur une cible ou un focus devenu
indéterminé : la première entrée interceptée reste non diffusée.

**Mitigation P0 effective dans le code :**
- `InputState` mémorise un signal `mouse_block_interrupted` uniquement
  pendant le bail courant ; un Stop révoque l'ancien epoch. Les leases
  imbriqués ne réinitialisent pas le signal d'une collision déjà détectée.
- `MouseHook` avertit le worker après un DOWN ou cran de molette physique
  absorbé. La paire DOWN/UP est conservée même si le worker quitte
  immédiatement le verrou. MOVE physique et événements injectés ne
  provoquent pas de fausse interruption. Le signalement en échec reste
  **fail-closed**.
- Les workers de clic et de molette détectent cette interruption **avant
  l'activation, avant SendInput et entre deux destinataires**. Ils
  arrêtent les émissions suivantes, libèrent leur bail et ne restaurent
  ni curseur ni favori sur une décision périmée.
- Le suivi du `DOWN` natif a été séparé des `DOWN` absorbés : un
  `UP` isolé ou d'un autre bouton ne peut plus déclencher une lecture
  de relâchement qui ferait démarrer la macro classique.
- Les compteurs de fenêtres restent exacts et le statut mentionne
  explicitement **« geste physique non rejoué »**.

**Tests simulés** : 2/4/6/8 personnages, collision au premier clic/molette,
Stop/reprise avec epoch différent, paire native/unmatched/synthetic,
contre-exemple de signalement qui lève une exception. La
[PR d'outillage #394](https://github.com/r9327/Dof-Atlas/pull/394)
est **fusionnée** (`2dfe7c5778d28dc9fe69a1a056d44278f98032f3`).
Au SHA de code `be306409e2c4fcd00b68394da0cba8df752944a5`, le
[Doctor-lot #42201197808](https://github.com/r9327/Dof-Atlas/actions/runs/42201197808)
confirme **477 tests Python exécutés, 477 PASS, 0 échec**, statut
`READY`, aucune source non couverte, `global_full_required=true`,
`phase_certified=false` et contrôle de fraîcheur exact-SHA réussi.
Il s'agit d'un **PASS ciblé**, pas de la certification globale.

**Ne pas certifier MIRR-007 comme résolu.** Les pressions arrivant pendant
le verrou restent absorbées, même si le worker s'arrête plus tôt.
Réception Unity hors focus (MIRR-002), mesures p50/p95/p99 et essais
réels Windows 1/2/4/6/8 (MIRR-005/ATQA-002) restent `PENDING/NOT_RUN`.
Ne pas rendre la PR non-Draft.


## 06/11/2026 — interruption des pauses Miroir après collision physique (P0, non certifié)

- `MacroLock.wait(duration_ms, interrupted=...)` accepte un prédicat optionnel
  et continue de recontrôler Stop, le bail générationnel et l'interruption
  externe par tranches d'attente d'au plus 25 ms. Les appels existants sans
  prédicat conservent le même contrat.
- Pendant un blocage réel du pointeur, les pauses entre destinataires du
  **Miroir clic/molette** passent `mouse_block_interrupted` comme prédicat :
  la première pression ou molette absorbée annule le fan-out sans attendre
  toute la pause réglée. Les pauses clavier et les macros classiques sont
  inchangées ; pas de deuxième moteur, ni de replay différé.
- Tests de logique `MacroLock` et tests simulés de diffusion clic/molette
  à **2/4/6/8 comptes** ajoutés ; ces tests ne démontrent aucune latence
  Windows ni réception Unity.
- Limite conservée **MIRR-007 PENDING** : la première entrée physique sous
  bail reste absorbée pour éviter un clic dans la mauvaise fenêtre. Le
  prédicat limite l'attente **nominale** avant vérification, mais ne garantit
  aucun p99 de bout en bout, et ne remplace pas la recette réelle #322.

## 06/11/2026 — collision atomique à la libération et pertes par diffusion (P0)

- `InputState.end_mouse_block` photographie sous **le même verrou** l'interruption physique survenue avant la libération du pointeur. Le résultat est propre au thread détenteur, invalide après Stop/epoch ancien et réinitialisé au début d'un nouveau bail ; l'ancien retour numérique de `end_mouse_block` reste compatible.
- `SwitchClickMacro` et `MirrorInputMacro` consultent ce résultat après la fin du bail. Une nouvelle pression arrivée entre leur dernière sonde et le déverrouillage ne peut plus être annoncée comme une diffusion sans collision.
- `InputState` compte les gestures physiques signalés **par bail** (`last_release_blocked_count()`), indépendamment des warnings globaux plafonnés à 400 ms. Les workers publient après déverrouillage `Miroir clic/molette collisions_physiques=N cibles=M`. Le rapport local regroupe les compteurs pour la taille d'équipe exacte et exclut les ratios p95 de séances contenant des pertes, sans masquer les mesures brutes.
- Tests de modèle : collision à la frontière de fermeture, 2/4/6/8 comptes, compteurs par action, Stop/reprise, epoch obsolète, thread étranger, baux imbriqués, séparation des rosters et données perdues malgré un p95 court.
- **Limite MIRR-007 PENDING** : aucun replay de la première pression physique absorbée pendant le bail ; pas de nouveau backend ni de promesse de fidélité Unity sans focus. Les essais réels Windows/DOFUS, coût CPU/RAM, état visuel et p50/p95/p99 de réaction restent **NOT_RUN** tant que la recette #322 n'a pas été attestée sur le SHA exact.
