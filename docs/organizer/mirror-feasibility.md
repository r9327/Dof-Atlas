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
- Scénarios 1/2/4/8 fenêtres en jeu et mesures p50/p95/p99 : NOT_RUN (#322).
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
  Recette Windows / DOFUS Unity #322 : NOT_RUN. Les p50/p95/p99 de SendInput
  par geste sont journalisés, pas des mesures de rendu Unity.

- La télémétrie `delivery_step_ms` mesure chaque étape d'envoi (incluant
  les durées d'appui et positionnements), et non le temps brut de `SendInput`
  ni la latence de rendu Unity. Le statut distingue une diffusion complète
  d'une diffusion interrompue.
