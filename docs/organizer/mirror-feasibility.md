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
