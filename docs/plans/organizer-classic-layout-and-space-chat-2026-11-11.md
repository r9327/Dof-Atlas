# Organizer — cahier des charges à valider (aucun développement dans cette PR)

État de référence : `main@4a540582d5f725575609665acbf1909c51454eb9` (11 novembre 2026). Références : [Organizer UI](../../app/pages/organizer/organizer_ui.py), [moteur clavier](../../app/macros/input_tools.py), [vitesses](../../app/core/settings.py), [Auto-groupe](../../app/macros/auto_group.py), [Zaap](../../app/macros/zaap.py), [tests des vitesses](../../tests/test_organizer_speed_presets.py). La PR #325 est fusionnée ; la recette Windows/Unity #322 reste ouverte.

> **Cadrage uniquement.** Aucun correctif de code, aucun refactor, aucun benchmark et aucun nouveau raccourci ne sont autorisés par ce document sans feu vert explicite. Conserver le moteur Macro/Miroir/Zaap et ses protections actuelles.

## A — Organisation approuvée à implémenter ultérieurement

1. **Contrôles — barre horizontale pleine largeur en tête** : Relancer scripts, Debug, Stop urgence rouge avec **badge du raccourci configuré à l'intérieur** du bouton. Garder son action et la suppression de raccourci ; n'inventer aucune touche par défaut.
2. **Module Macro — colonne gauche** : boutons Macro/Miroir avec raccourci de bascule Miroir intégré, état actif explicite ; **Activer/Arrêter Miroir demeure une action distincte** pour éviter un armement implicite ; Switch personnage, Switch déplacement, Switch clic, Switch clic ×2, leurs raccourcis existants, puis Vitesse Normal / Rapide / Instantané. Conserver le profil historique « Classique » non affiché pour compatibilité.
3. **Module Actions rapides — colonne droite** : Auto-groupe, Sélection perso (roue au maintien), ← Précédent et Suivant → avec raccourcis configurables existants, sur une même ligne. Aucune fonction en doublon.
4. **Zaap — barre compacte, tous les favoris directement visibles** : aucun bouton « +N », menu caché, pagination ni distinction entre « favoris » et « favoris visibles ». **Un favori enregistré = un raccourci visible et cliquable.** Le nombre maximum de favoris sélectionnables est déterminé par la place réellement disponible dans la barre, avec boutons suffisamment lisibles, sans étirement infini et sans empiéter sur la recherche. Si la limite est atteinte, empêcher proprement l'ajout d'un favori supplémentaire avec un message explicite ; l'utilisateur peut en retirer un pour le remplacer. Ne pas décider arbitrairement que 8 favoris tiennent sur une ligne : valider la capacité par largeur/DPI et choisir une limite simple qui garantit que tous les favoris tiennent visiblement. Préserver les favoris historiques déjà sauvegardés : ne pas les effacer ou en cacher silencieusement lors d'une éventuelle migration, proposer un traitement explicite si le nombre dépasse la nouvelle capacité. Conserver les callbacks d'ajout/retrait, recherche et lancement existants, sans second sender.
5. **Personnages** : rendu adaptatif de 2 à 8 emplacements, hauteur ajustable (1–4 = cases plus hautes ; 5–8 = cases compactes), sans huit cases vides permanentes. **L'utilisateur peut déplacer librement chaque personnage sur n'importe lequel des huit slots** par glisser-déposer, y compris vers un emplacement vide ; si un slot est masqué par le mode compact, rendre sa destination accessible pendant l'opération (révélation/extension temporaire). L'ordre choisi par l'utilisateur doit rester sauvegardé et cohérent après actualisation/redémarrage. Une permutation volontaire change la position : ne jamais verrouiller une case, conserver les identités des personnages, le favori, les raccourcis *attachés aux slots* et le runtime à jour. Aucun trou visuel inutile.
6. **Style** : disposition classique PC de la capture de référence, bleu nuit/vert et commandes compactes PySide6 ; ni icônes fantasy inventées ni « dashboard tablette ». Contrôler DPI 100/125/150/200 %, fenêtre réduite et navigation clavier.

## B — Vitesses réelles définies dans le code (millisecondes)

| Paramètre `MacroTimings` | Normal | Rapide | Instantané |
|---|---:|---:|---:|
| `click_focus_settle_ms` | 8 | 6 | 4 |
| `travel_focus_settle_ms` | 12 | 10 | 6 |
| `activate_min_settle_ms` | 6 | 6 | 5 |
| `activate_retry_ms` | 12 | 10 | 8 |
| `activate_attempts` | 8 | 6 | 5 |
| `input_double_gap_ms` | 5 | 4 | 4 |
| `switch_background_pre_click_ms` | 18 | 14 | 10 |
| `switch_background_post_up_ms` | 5 | 3 | 2 |
| `auto_group_chat_open_ms` | 45 | 35 | 25 |
| `auto_group_key_step_ms` | 12 | 10 | 8 |
| `auto_group_paste_settle_ms` | 45 | 35 | 25 |
| `auto_group_invite_gap_ms` | 140 | 100 | 65 |
| `movement_key_hold_ms` | 18 | 17 | 16 |

D'autres paramètres restent identiques dans les trois modes, notamment `switch_click_down_ms=1`, `switch_client_settle_ms=0` et `switch_humanize_min_ms=4/max_ms=9`. Dans le moteur Switch clic, des planchers de fiabilité **35 ms de DOWN** et **50 ms de survol** restent en vigueur même en Instantané. Le mode « Classique » historique dispose de délais plus lents, conservés pour migration v1→v2. Ces valeurs représentent des **temporisations**, et non les performances p50/p95/p99 mesurées du jeu.

Les tests `test_organizer_speed_presets.py` injectent des appels simulés `send_chat_command` : ils montrent le passage des paramètres, **pas** la réception par DOFUS Unity.

## B2 — Règle cible des trois vitesses (décision utilisateur du 11 novembre 2026)

**Objectif prioritaire : les modes Normal / Rapide / Instantané pilotent les actions de switch et de clic, et non les scripts de chat.** La table B décrit **l'implémentation actuelle** ; ce paragraphe B2 est la **spécification future**, non développée.

| Action existante | Politique cible | Exigence |
|---|---|---|
| Switch personnage | Normal / Rapide / Instantané | Variation effective du changement de focus et de l'enchaînement des clients, sans perte de raccourci |
| Switch clic | Normal / Rapide / Instantané | Variation réelle de la réactivité/fan-out, maintien de la fiabilité de réception Unity |
| Switch clic ×2 | Normal / Rapide / Instantané | Différence perceptible sans clic manqué ou double émission non voulue |
| Switch déplacement | Normal / Rapide / Instantané | Adapter focus et maintien des touches, jamais de touche coincée après Stop |
| Miroir (clics, touches courtes, molette) | Normal / Rapide / Instantané | Réactivité de diffusion à 2/4/6/8 comptes et retour au favori, sans perdre d'événement |
| Précédent / Suivant | Réponse la plus rapide sûre, indépendante du choix si possible | Action immédiate au ressenti, sans retard artificiel ni faux succès |
| Sélection perso / camembert | Réponse immédiate, indépendante du sélecteur | Affichage au maintien et sélection fluides |
| Auto-groupe | **Cadence automatique fiable fixe** | Délais d'ouverture chat, collage, Enter et entre invitations adaptés à DOFUS, sans dépendance au mode |
| Zaap / Travel | **Cadence automatique fiable fixe** | Même règle que Auto-groupe, via le sender partagé, sans moteur doublonné |

### Contrat de comportement des trois modes

- **Normal** : vitesse de référence stable, utilisable sur toutes les actions interactives ci-dessus.
- **Rapide** : accélération **réellement mesurable** du temps total de switch/clic par rapport à Normal, pas uniquement 2–5 ms retranchées à un champ secondaire.
- **Instantané** : viser la latence minimale **effectivement réalisable** sur l'ensemble des clients. Objectif utilisateur : ne quasiment pas percevoir le défilement des fenêtres lors des changements de carte. **Ne pas déclarer cet objectif atteint si Windows oblige encore à activer les fenêtres une par une.**
- Les trois modes doivent agir sur le temps **commande physique → réaction visible du dernier client**, pas uniquement sur les valeurs de temporisation. Préserver Stop urgence, identité HWND/PID, garde de focus et événements DOWN/UP, y compris à 8 comptes.
- Les planchers actuels de clic (survol >=50 ms, maintien >=35 ms et double-clic >=60 ms dans certains chemins) expliquent pourquoi diminuer les seules valeurs du preset ne change pas beaucoup le ressenti. **Ne pas supprimer ces planchers sans preuve de réception Unity**, et ne pas afficher « instantané » comme une promesse de zéro délai.
- Le moteur actuel utilise `SetForegroundWindow` et des activations successives. **Aucune entrée Unity fiable en arrière-plan n'est établie** : étudier la faisabilité et mesurer, sans introduire injection de processus, réseau ou nouvelle méthode risquée/non prouvée.
- Les délais du chat Auto-groupe/Zaap/Travel sont aujourd'hui dérivés de `timings_for_speed` ; la règle cible demande de les dissocier et de réutiliser un seul profil de fiabilité commun. **Ne pas créer de second moteur, de quatrième vitesse ou de réglage UI supplémentaire.** Réparer d'abord la non-réception de `SPACE` constatée par l'utilisateur.

### Critères d'acceptation des vitesses (à prouver après autorisation de développer)

1. Vérifier, dans les vrais chemins de chaque action, que le profil choisi est chargé et appliqué à tous les consommateurs de switch/clic/Miroir ; conserver les anciennes préférences lors de la migration.
2. Comparer Normal, Rapide, Instantané sur **2 / 4 / 6 / 8** comptes, mêmes fenêtres, résolution, DPI et scénario ; enregistrer nombre d'actions tentées, reçues, perdues, doublonnées, interruptions, CPU/RAM, et **p50/p95/p99** avec effectifs. Mesurer aussi le temps « source → dernier client » et le nombre de changements de fenêtres réellement visibles.
3. Vérifier que Rapide est **significativement plus rapide en pratique** que Normal, et Instantané plus rapide que Rapide **si réalisable sans perte de fiabilité**. Sinon documenter précisément le goulot (focus Win32, injection SendInput, hover Unity, verrou, Qt) et l'absence d'écart utile ; ne pas masquer l'échec par une temporisation artificielle de Normal.
4. Confirmer que changer de mode **n'altère pas le rythme d'Auto-groupe/Zaap/Travel**, qu'ils marchent avec `SPACE` et que Stop/focus/clipboard restent sûrs. Ajouter un test de non-régression ciblé à cette séparation.
5. Les tests synthétiques sont insuffisants pour affirmer « invisible » ou « instantané » : la **réaction réelle de DOFUS Unity** doit être constatée sur Windows. Aucune performance ni fonctionnalité de cette section n'est déclarée livrée par la PR de cadrage.

## C — Diagnostic prioritaire : Auto-groupe et Zaap ne réagissent pas à la touche Espace

**Signalement utilisateur :** toutes les macros utilisant Espace (notamment Auto-groupe et Zaap) ne fonctionnent pas. **Non reproduit ici sur DOFUS réel** ; cause racine à établir, ne pas marquer « corrigé ».

**Code commun confirmé :** `AutoGroupMacro`, `ZaapMacro` et `TravelMacro` appellent `send_chat_command()` dans `app/macros/input_tools.py`, puis `replace_chat_text_with_clipboard()`, qui exécute :

```text
press_key("SPACE") ; attendre 25/35/45 ms ; CTRL+A ; DEL ;
CTRL+V ; attendre 25/35/45 ms ; ENTER [ENTER supplémentaire pour Zaap/Travel]
```

**Hypothèses par priorité :**
- **P0 / ouverture non confirmée** : le sender n'attend aucun signal fiable confirmant que le chat Unity a obtenu le focus avant d'envoyer CTRL+A/DEL ; le mode Instantané ne laisse que 25 ms.
- **P0 / durée d'appui** : `press_key("SPACE")` est appelée avec `hold_ms=0` ; le DOWN/UP est immédiat. Vérifier dans le jeu si le raccourci ouvre vraiment le chat et distinguer émission Win32 de réception Unity. Ne pas imposer arbitrairement de nouveaux délais au moteur entier.
- **P0 / raccourci clavier du jeu** : `SPACE` est codé en dur ; vérifier la correspondance avec l'attribution réelle de la commande « activer le chat » sur chaque compte DOFUS. Éviter de supposer que toutes les configurations sont identiques.
- **P1 / autres arrêts en amont** : l'expéditeur annule en cas de presse-papiers non texte/non restaurable, Stop, focus volé, HWND non vérifié ou échec SendInput. Capturer la première étape qui échoue à partir des logs existants.
- **P1 / résultats trompeurs** : `send_chat_command` renvoie succès une fois les événements envoyés ; aucune garantie de chat ouvert, commande acceptée ou effet en jeu.

**Méthode de diagnostic sans refonte ni nouvel outil :**
1. Répéter un appui manuel sur Espace avec une fenêtre DOFUS au premier plan ; noter si le curseur du chat s'active, puis si `/invite` et `/zaap` tapés **manuellement** marchent.
2. Comparer les **trois vitesses actuelles** sur **1, 2, 4, 6, 8** comptes pour diagnostiquer l'existant ; à terme, confirmer que le **profil de chat fiable est indépendant des trois modes**. Contrôler l'état du chat, l'identité de la fenêtre, l'ordre, le Stop et la source étoilée.
3. Avec Doctor et `session_runtime.log` existants, consigner : début macro, focus final, émission SPACE DOWN/UP (ou refus), ouverture chat constatée, CTRL+V, ENTER, restauration clipboard, nombre réel de clients réussis.
4. Ajouter ultérieurement uniquement les tests qui reproduisent la panne constatée, notamment chat non prêt, mapping alternatif, focus modifié, clipboard propriétaire, échec partiel et zéro frappe dans une fenêtre étrangère.
5. **Critère de sortie futur :** sur Windows réel + DOFUS, Auto-groupe et Zaap s'exécutent avec un profil de chat fiable commun, **quelle que soit la vitesse des switches choisie** ; aucun double envoi, aucune action après Stop, aucun vol de focus. Conserver mesure physique et limites.

## D — Défauts fonctionnels connus / limites de preuve

- **Confirmé dans le code :** Espace est imposé et l'ouverture du chat n'est pas attestée avant la suite du clavier.
- **Confirmé dans le code :** les trois vitesses ajustent actuellement aussi Auto-groupe/Zaap ; **c'est contraire à la politique cible** (chat à vitesse automatique fiable, switches/clics pilotés par les trois modes). Les temps physiques et la prise en compte Unity ne sont pas certifiés.
- **Confirmé dans le code :** Miroir exige une activation explicite ; la diffusion clavier/souris sans focus n'est pas prouvée. Les planchers 35/50 ms empêchent la latence théorique nulle.
- **Constat utilisateur non reproduit ici :** Auto-groupe et Zaap ne fonctionnent pas.
- **Recette restante :** #321 / #322 : Windows/DOFUS réel, 1/2/4/6/8 comptes, p50/p95/p99, Stop, chemin clavier, sélection roue, Miroir, focus et clipboard ; ne pas confondre tests simulés et jeu.

## F — Audit de fiabilité et critères anti-régression (ajout du 11/11, cadrage seulement)

Relecture croisée avec `app/pages/organizer/organizer_ui.py`, `character_sessions.py`, `organizer_drag_drop.py`, `organizer_hotkeys.py`, `app/storage.py`, `app/input/hotkeys.py`, `app/macros/input_tools.py`, `app/macros/mirror_input.py` et le contrat historique #321. **Ce sont des exigences de fiabilisation à vérifier / implémenter uniquement après autorisation de développer ; pas des défaillances toutes reproduites ni des travaux déjà livrés.**

### F1 — Priorité P0 : fonctionnement et sécurité

1. **Raccourcis concurrents et propagation des clics sur les badges.** Conserver les priorités actuellement implémentées (Stop urgence prioritaire, Miroir/roue/slot/switch sans déclenchement double, mode Miroir armé = navigation Précédent/Suivant désactivée). L'affichage du raccourci *dans* le bouton doit permettre sa reconfiguration/suppression **sans déclencher l'action sous-jacente**. Sur Miroir, distinguer sans ambiguïté **sélectionner le mode** (clic « Miroir ») et **armer/désarmer** la diffusion (bouton dédié / raccourci associé) ; ne jamais armer automatiquement à l'ouverture, au changement de mode ou après Stop. Les éventuels conflits avec la touche Espace utilisée pour le chat et les touches de déplacement doivent être testés.
2. **Miroir et macro occupée : action non consommée silencieusement.** Réutiliser le verrou et le hook existants ; contrôler le cas `MIRR-007` déjà suivi dans #321. Quand un geste arrive pendant une macro, ne pas consommer le geste physique du maître puis prétendre qu'il a été diffusé. Choisir un repli non destructif ou une file strictement bornée et périssable *si nécessaire et prouvée*, jamais de replay périmé après Stop/changement de personnages. Ne pas créer un second orchestrateur.
3. **Stop urgence et nettoyage après erreur.** Tester Stop au milieu d'un DOWN/UP souris ou clavier, pendant un double-clic, entre deux clients, pendant l'envoi `SPACE`/presse-papiers, pendant un changement de mode/roster, et après échec `SendInput`. Aucun événement synthétique restant maintenu, aucune entrée dans une application étrangère, aucune nouvelle activation ni retour forcé au favori après Stop/perte de focus. Nettoyage et état UI cohérents ; ne pas marquer « réussite » sur un simple ACK Win32.
4. **Diagnostic Espace reproductible avant correction.** Séparer les causes possibles : `SPACE` non émis (Win32/hook), émis mais ignoré par Unity, chat non prêt, raccourci de jeu différent, fenêtre non active, presse-papiers refusé, macro stoppée. Capturer **la première étape défaillante**, conserver le sender commun, et vérifier qu'une correction sur Auto-groupe fonctionne aussi sur Zaap et Travel. Pas de durée d'appui ou d'attente arbitraire inventée sans test.
5. **Vitesses : différenciation effective sans fragiliser le jeu.** Conserver Normal/Rapide/Instantané pour Switch personnage, Switch clic/x2, Switch déplacement et Miroir ; Précédent/Suivant et camembert à réponse rapide ; chat Auto-groupe/Zaap/Travel avec cadence propre commune et sûre. Mesurer la latence de bout en bout **pour chaque fonction** et les planchers existants, vérifier le mode chargé après sauvegarde/redémarrage/reload, le changement de mode pendant worker actif et la compatibilité des profils historiques. Ne pas accélérer Normal artificiellement pour produire un écart. Comparer 2/4/6/8 et signaler clairement si « changements quasi invisibles » est incompatible avec les activations Windows successives.

### F2 — Priorité P1 : interface durable, données et navigation

6. **Favoris Zaap : tous visibles ou non enregistrés comme nouveaux favoris.** L'ancienne limite de rendu à 8 ne justifie pas 8 favoris dans une barre trop courte. **Aucun favori caché derrière « +N » : tous les favoris sélectionnés sont affichés directement.** Déterminer une limite pratique selon la largeur disponible, la longueur des libellés et le DPI ; conserver une présentation compacte et alignée. Quand tous les emplacements visibles sont pris, refuser clairement un nouvel ajout ou demander d'en retirer un, sans masquer ni écraser un favori. Ne pas supprimer silencieusement les données historiques existantes : traiter explicitement les profils ayant plus de favoris que la capacité décidée. Tester recherche, ajout/retrait, lancement direct, redimensionnement et absence de troncation. Réutiliser `launch_zaap` et le sender existants.
7. **Réorganisation libre des personnages entre tous les slots (obligatoire).** Le moteur garde **8 slots internes** ; le glisser-déposer doit permettre **n'importe quelle permutation choisie par l'utilisateur**, ou le déplacement vers un slot vide, **sans figer l'ordre et sans le réinitialiser automatiquement**. Le code existant `move_session_to_slot()` permute deux cases occupées ou déplace vers une case vide ; `export_client_index()` appelle déjà `save_session_order()`. **Préserver ce fonctionnement**, y compris le glissement en direct et l'export final, plutôt que prétendre que les slots deviennent immuables. Conserver les raccourcis associés à la *position du slot* (ils ciblent le nouvel occupant après une permutation volontaire), l'identité attachée au personnage et le favori. Lorsque des slots sont masqués pour gagner de la place, prévoir un moyen simple de révéler/déposer vers **n'importe quel slot 1 à 8**, sans perdre la destination. Couvrir 0/1/2/4/6/8 détectés, cases vides intercalées, ordre personnalisé, reconnexion, actualisation, sauvegarde, redémarrage, clic sur Précédent/Suivant et raccourcis après permutation.
8. **État de connexion, désactivation et retours utilisateur.** Les boutons Macro/Miroir, Stop, vitesse, Précédent/Suivant, sélection perso, Auto-groupe et Zaap doivent refléter l'état réel du runtime : arrêté, actif, Miroir armé, macro occupée, cible absente ou erreur. Désactiver seulement ce qui doit l'être, éviter boutons « actifs » quand le runtime a refusé, et conserver les messages d'échec ou de réussite partielle. Tester rechargement, fermeture et navigation entre modules pendant capture de raccourci ou macro active.
9. **UI Qt accessible et sans coupure.** Même hauteur de contrôles entre modules, présence des raccourcis complets en tooltip, accessibilité des sous-boutons, ordre Tab, focus clavier visible, touches Espace/Entrée dans l'interface sans lancer une commande non voulue, taille du widget à DPI 100/125/150/200 %, largeur minimale, défilement raisonnable, fermeture des sous-menus Zaap, scroll sur écran réduit. Ne pas reproduire les dimensions fixes actuelles qui laissent des cartes immenses et de l'espace inutilisé ; conserver les composants et tokens Unity partagés de #365.

### F3 — Critères de sortie et anti-doublons

10. **Tests ciblés avec vrais propriétaires des suites.** Mettre à jour les assertions de layout qui supposent **exactement huit lignes visibles** et que la vitesse est dans Actions rapides ; conserver leurs autres invariants. Cas à ajouter seulement lorsque les modifications correspondantes existent : raccourci intégré qui ne déclenche pas l'action, vitesses réellement séparées du sender chat, Zaap sans favoris cachés (limite d'ajout alignée sur la capacité d'affichage), permutations libres entre huit slots (raccourcis par position), Stop et perte de focus. Exécuter les tests exact-SHA et la CI propriétaire Windows synthetic ; la réception DOFUS Unity réelle et les p50/p95/p99 visuels restent distincts et non présumés.
11. **Coordonner #321/#322/#365, sans recréer les protections.** #321 contient déjà les exigences MIRR-007 (worker occupé), MIRR-008/009/010 (focus, Stop, diagnostic), MIRR-015 (conflits), MIRR-017 (ancienne politique de vitesse) ; la nouvelle politique de #416 **remplace uniquement la cible fonctionnelle de vitesse Zaap/Auto-groupe/Travel**, pas les exigences de fiabilité de #321. Lors du développement, annoter cette évolution dans le contrat propriétaire pour ne pas laisser deux exigences contradictoires. #365 reste propriétaire du style et des composants globaux ; #416 ne doit pas dupliquer le moteur #325.
12. **Définition de « fonctionnel ».** Une PR n'est prête à fusionner que si les actions visibles sont réellement câblées et ont les mêmes effets qu'avant, si les tests automatiques ciblés passent au HEAD courant, si les limites de Windows/DOFUS sont notées sans les maquiller, et si la recette utilisateur Windows/Unity #418/#322 est traitée ou explicitement bloquante. Ne jamais transformer une simple émission `SendInput` en garantie de réception en jeu.

### Verdict de cadrage

- **Ce qui est connu dans le code :** le widget affiche actuellement jusqu'à huit favoris, mais la capacité d'affichage compact n'est pas justifiée ; **la nouvelle cible est d'afficher directement tous les favoris acceptés, sans menu caché**, avec une limite d'ajout adaptée à la place disponible. Huit positions backend restent **réorganisables par glisser-déposer**, raccourcis attachés aux index des slots, widgets Qt avec dimensions fixes, fonction chat `SPACE` sans vérification d'ouverture, modes vitesse affectant actuellement aussi les pauses de chat.
- **Ce qui est déjà protégé / à préserver :** priorité Stop, exclusions partielles de raccourcis, vérifications focus/HWND, clavier DOWN/UP, cleanup et anti-replay ; ne pas déclarer ces protections absentes à partir du seul cahier des charges.
- **Ce qui reste à prouver :** panne Espace exacte, fiabilité du Miroir saturé sur jeu réel, objectif quasi invisible d'Instantané, différences de vitesse perceptibles, validation 2/4/6/8, captures et temps de réaction Unity.
- **Règle de périmètre :** aucun développement demandé dans la PR #416 à ce stade ; cette section est un audit documentaire / une liste de tests et non une livraison.

## E — Lots futurs uniquement après autorisation de développer

1. **LOT P0 :** diagnostic exact-SHA de la chaîne Espace→chat, reproduction et test de non-régression, puis correctif minimal à la cause prouvée ; conserver ensuite le rythme de chat commun indépendant des trois vitesses.
2. **LOT VITESSES :** mesurer les vraies latences de switch, clic, clic ×2, déplacement et Miroir, identifier leurs seuils/planchers et rendre les trois modes perceptiblement différents sans contourner les protections ; intégrer les scénarios réels 2/4/6/8 et les cas sans gain possible.
3. **LOT UI :** réorganisation pure `organizer_ui.py` sans déplacer les connexions de signaux métiers ; tests de structure/focus/DPI.
4. **LOT ZAAP :** favoris tous visibles directement dans le module, maximum déterminé par la place réelle, refus clair d'ajout au-delà de la capacité ; pas de « +N » ni favoris masqués, pas de second sender, perte de raccourcis ou suppression de données historiques.
5. **LOT SLOTS :** adaptation visuelle 2→8 avec **ordre librement modifiable par drag/drop vers n'importe quel slot**, destinations masquées accessibles, raccourcis par position et ordre sauvegardé ; tests synthétiques et captures.
6. **LOT CERTIF :** Doctor ciblé, CI propriétaire, revue exacte du diff puis validation réelle Windows/DOFUS ; benchmarks seulement si nécessaires à la fiabilité.

**Statut actuel : PROPOSITION UNIQUEMENT — 0 développement / 0 test de réception Unity.**