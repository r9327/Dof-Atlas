# PR #225 — UI Guide Succès / Lanyel : REPRODUCTION FIDÈLE DE LA MAQUETTE VALIDÉE

Date : 18 octobre 2026. Branche : `feature/guide-ui-compact-20261018`.
**ÉTAT : design verrouillé, NON implémenté. Ne pas fusionner sans comparaison visuelle avec la maquette validée.**

## DERNIÈRE VALIDATION UI — boutons Personnages et Sommaire DANS l'en-tête de la fiche (18/10, priorité maximale)

**Remplace toute consigne antérieure prescrivant une ligne séparée de boutons au-dessus de la fiche.** La ligne dédiée à `Mes personnages` et `Sommaire`, visuellement trop vide, est **SUPPRIMÉE**. Les deux boutons sont désormais positionnés **à droite DANS l'en-tête de la fiche active**, sur la même rangée que l'identifiant « FICHE N · CHAPITRE X » et le titre court de la fiche **à gauche**. Aucun nouveau bandeau ou titre annexe.

```text
┌────────────────────────────────────────────────────────────────┐
│ FICHE N · CHAPITRE X                    [👥] [Sommaire  ▾]     │
│ Titre court de la fiche                                        │
├────────────────────────────────────────────────────────────────┤
│ [x,y] · PNJ · combats cochables · actions de la fiche           │
│ ...                                                            │
│                      [Précédent] [Valider] [Suivant]            │
└────────────────────────────────────────────────────────────────┘
```

- Le bouton icône ouvre le menu **Mes personnages** ; le bouton **Sommaire** ouvre son panneau. Les deux restent compacts et indépendants, **fermés au chargement** ; l'ouverture se fait juste sous cette zone d'en-tête, sans masquer le titre ni chevaucher les actions.
- **Sommaire ne se referme jamais** à la sélection d'un chapitre/fiche, via Précédent/Suivant, Aller à la fiche ou Actuelle ; fermeture uniquement sur clic explicite sur Sommaire. La fiche sélectionnée reste la seule fiche montée.
- Les portraits de classes, les tooltips, la sélection multicomptes, la persistance et le retour **Actuelle** à la vraie étape métier demeurent **inchangés**.
- **Conserver strictement le style existant du Guide Lanyel** (couleurs, dimensions, marges, icônes, coins et typographie), sans barre d'outils flottante ou nouvelle section. Ajuster l'espacement de l'en-tête de fiche pour les petites largeurs et l'affichage Windows/HDPI, sans chevauchement.
- **Certification** : captures Doctor UI état fermé, Personnages ouvert, Sommaire ouvert, les deux ouverts, différents titres courts/longs, petites fenêtres (dont largeur min. prise en charge) ; interaction sans fermeture implicite du Sommaire, aucune régression de navigation.

## VERSION FINALE DE LA MAQUETTE — VALIDÉE AVEC L'UTILISATEUR LE 18/10/2026

Cette section synthétise les corrections successives et **prime sur toute maquette illustrative ou instruction antérieure contradictoire**. Elle décrit le comportement attendu, **pas un écran déjà implémenté**.

- **Identité** : titre principal EXACT du guide ouvert (ex. `Guide Succès`, `Dofus Sylvestre`), petit engrenage. Pas de `Guide optimisé`, ni de sous-titre `Progression générale du parcours`. Conserver le donut général, les trois barres `Route / Préparation / Succès`, leurs quantités réelles et leur emplacement.
- **Actions principales** : `Aller à la fiche`, juste à côté `Actuelle` (ou libellé complet `Retour à l'actuelle` selon la place validée), puis petite icône Overlay sans texte. `Actuelle` = **REVENIR À L'ÉTAPE ACTUELLE RÉELLE du guide**, établie par les objectifs/progressions, **jamais** le dernier numéro visité dans le Sommaire, jamais un numéro fixe comme `643`, jamais seulement la fiche ouverte au chargement. Voir contrat complet ci-dessous.
- **Préparation générale du guide** : bandeau de la capture fournie, sous-titre et déroulant. Vue `Préparation complète` avec filtres `Tout (résumé) / Métiers / Potions / Objets`. Des listes ultra-compactes, hauteur plafonnée et scroll. Chaque potion dans Potions, pierres d'âme seulement sous Objets. Chaque ligne montre un vrai besoin, une quantité et une **mini-coche ✓ Prêt en un clic**, avant le mini-chevron de détail ; la coche est une déclaration de couverture par participant, sans fausse preuve réseau, sans saisir un chiffre. Un clic sur le chevron déplie seulement le détail de CET article, par personnage. Catégorisation exacte et absence de doublons.
- **Multicomptes** : recalcul par personnage choisi et par objectif réellement restant, non par multiplication naïve des quantités ; stock déclaré/confirmé par personnage, distinction partageable/non partageable, confirmation `Prêt` conservée uniquement pour les participants/besoins couverts. Une sélection nouvelle ne devient pas automatiquement prête.
- **Navigation de la fiche** : commandes `Mes personnages` (bouton icône) et `Sommaire` intégrées **à droite dans l'en-tête de la fiche active**, en regard de son numéro/chapter et de son titre court à gauche ; **aucune ligne autonome au-dessus de la fiche**. Ni `Mon parcours`, ni `Fiche n / total` redondant. Les deux menus conservent tous leurs comportements.
- **Sommaire ouvert** : chapitre/fiches cliquables, **NE SE REFERME PAS au choix d'une fiche**, ni sur Précédent/Suivant ni sur `Actuelle`. Fermeture volontaire exclusivement au clic explicite du bouton/chevron Sommaire. La consultation libre d'une fiche ne change PAS ce qu'Atlas estime être l'étape actuelle.
- **Fiche dans le style Lanyel** : titre court et exact, mêmes coordonnées `[x,y]` et même style de lien (macro travel/zaap invisible sur la bonne sélection), actions courtes et réelles, combats `×N monstre` cochables, récoltes/drops/donjons/captures. **Survol de CHAQUE ligne** = nom de la/des quêtes liées, et **un seul petit accès à l'onglet Quêtes par quête ET par fiche**, sur la première ligne pertinente. Ne pas ajouter de panneau `Quêtes liées`, ni `Sources`, ni `Pourquoi cet ordre ?`.
- **`À prévoir` local JUSTE À TEMPS, pas bloc `À préparer`** : seul un rappel en une ligne au niveau de l'action critique si un objet indispensable manque effectivement à un personnage concerné et n'a pas été déclaré prêt ; pas de répétition globale, pas de fausse préparation des drops/récoltes déjà prévus sur la route.
- **Bas de fiche** : `Précédent / Valider / Suivant`. Progression réseau prioritaire et `Valider` manuel en secours uniquement, sans validation de quête/succès causée par la mini-coche d'objet.

### Contrat non négociable du bouton « Actuelle »

1. Distinguer deux états : **`viewed_stage_id`** = fiche que l'utilisateur regarde via sommaire/navigation, et **`actual_stage_id`** = étape courante de progression du guide selon la source métier. Ne jamais inférer l'étape actuelle depuis la vue (`view_index`), le dernier clic, un numéro codé en dur ou la première fiche visible à l'ouverture.
2. **Résolution en temps réel** : à chaque clic `Actuelle`, demander au moteur de guide, selon **le guide sélectionné et les personnages sélectionnés**, l'étape actionable réellement en cours, à partir des objectifs et validations réseau fiables, plus les validations manuelles de secours déjà persistées. Une étape visitée mais non validée reste à faire. Après validation de l'étape actuelle, `Actuelle` doit rejoindre la nouvelle étape du parcours. Préserver l'ID stable de fiche/stage plutôt qu'un numéro fragile.
3. **Plusieurs personnages avec progression différente** : chercher **la première étape encore nécessaire dans l'ordre prévu pour les participants sélectionnés** (ou utiliser l'arbitre métier existant qui construit leur parcours commun). Un participant plus avancé ne doit pas supprimer l'étape requise par un autre ; le résultat doit être déterministe et explicable en interne. Sélection/désélection d'un portrait puis `Actuelle` doit refléter immédiatement la nouvelle progression commune, sans changer automatiquement la fiche consultée avant que l'utilisateur clique.
4. **Incertitude / réseau déconnecté** : utiliser uniquement la dernière progression persistée **fiable et datée** et les validations manuelles explicites si disponibles ; si le moteur ne peut pas établir l'étape actuelle avec suffisamment de certitude, désactiver `Actuelle` / afficher un statut court non trompeur, **ne pas afficher une fausse étape 643 par défaut**. Si le guide est entièrement validé, revenir à l'état terminé / dernière fiche pertinente selon le contrat existant et le signaler sans inventer une étape non faite.
5. **Clic** : placer la vue sur `actual_stage_id` et scroller en haut de cette fiche, sans cocher de combat, valider d'objectif ou de quête, lancer de macro Travel/Zaap, modifier les sélections, refermer Sommaire/Préparation/Mes personnages ou altérer les stocks/états `Prêt`. Le bouton peut être désactivé lorsque la vue est déjà à l'étape actuelle, mais l'étape métier doit continuer à être tenue à jour.
6. **Tests Qt/réseau obligatoires** : depuis une étape actuelle 643, consulter 641 puis cliquer `Actuelle` → 643 ; valider 643 (réseau ou secours manuel) puis cliquer `Actuelle` → **étape suivante réellement nécessaire** ; deux participants divergents → première action nécessaire dans leur route commune ; retirer le participant en retard → étape recalculée ; changer de guide → référence isolée ; déconnexion/absence de preuve → pas de saut arbitraire ; Sommaire reste ouvert et aucune macro n'est lancée. Tester également navigation Précédent/Suivant et saisie Aller à la fiche : **consultation ≠ progression**.

**État des travaux : la PR #225 est une PR de spécification, pas une fonctionnalité certifiée. Conserver les captures Doctor UI sur le vrai Windows Qt comme critère de sortie.**


## CONSIGNE ABSOLUE — pas de liberté sur l'UI

L'interface doit **ressembler exactement à la dernière maquette validée avec l'utilisateur**, en conservant le style visuel déjà en place du guide Lanyel (couleurs, fonds, composants, typographie, espacements, cartes et contrôles). Les maquettes précédentes ne priment pas sur les dernières corrections. Cette PR NE DOIT PAS être interprétée comme « refaire un design inspiré de ». **C'est une reproduction 1:1 de la composition acceptée, à l'exception des suppressions explicites ci-dessous.**

Ne pas inventer :
- panneau dédié aux déplacements / Zaaps, boutons « Copier la commande », badges sur les coordonnées, statut macro permanent, légende supplémentaire de transport ;
- bloc « Quêtes liées à cette fiche », bloc local « À préparer », « Sources du guide », « Succès liés », « Pourquoi cet ordre ? », « Étapes précédentes », « À suivre » ou « Destination suivante » ;
- grosse liste de personnages, cartes individuelles de personnages ou tableau multicomptes toujours visible ;
- changement de structure par rapport à la capture validée du panneau **Préparation générale du guide** : conserver le bandeau, la carte et ses quatre filtres, mais **remplacer le gros bloc Pierres d'âme par une unique ligne compacte dans l'onglet Objets** ; ne pas substituer le menu « PRÉREQUIS » du catalogue.

Si un détail visuel n'est pas explicitement documenté ici, **préserver l'existant/maquette**, ne pas improviser ; confronter les captures Doctor UI à la composition validée avant de déclarer PASS.

## STRUCTURE VISUELLE EXACTE, DANS CET ORDRE

```text
┌─────────────────────────────────────────────────────────┐
│ Guide Succès / Dofus Sylvestre                    [⚙]   │
│                                                         │
│   (donut GLOBAL %)       Route       n / total           │
│                          ━━━━━━━━━━                     │
│                          Préparation n / total           │
│                          ━━━━━━━━━━                     │
│                          Succès      n / total           │
│                          ━━━━━━━━━━                     │
│                                                         │
│ [      Aller à la fiche      ] [Retour actuelle] [🗺]   │
├─────────────────────────────────────────────────────────┤
│ [ ▤ Préparation générale du guide              ▾ ]    │
│   (ouvert : Préparation complète + filtres, liste courte) │
│   (Objets uniquement : pierre d'âme en une ligne ▾)    │
├─────────────────────────────────────────────────────────┤
│ (les deux boutons sont à droite DANS l'en-tête fiche)  │
│       (Mes personnages : portraits si menu ouvert)       │
│       (Sommaire : demeure ouvert après choix d'une fiche)│
│ ┌─────────────────────────────────────────────────────┐ │
│ │ FICHE N · CHAPITRE X                               │ │
│ │ Titre court de la fiche                           │ │
│ │ [x,y] (clic identique ; trajet derrière)           │ │
│ │ Actions PNJ/combats/récoltes/drops...              │ │
│ │   [petit bouton Quêtes UNE fois par quête/fiche]   │ │
│ │   □ ×5 Nom exact du monstre                        │ │
│ │   Survol de ligne : nom de la quête                │ │
│ │                                                     │ │
│ │ [ Précédent ] [ Valider ] [ Suivant ]               │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

Le dessin ci-dessus décrit la HIÉRARCHIE des éléments, **pas un redesign graphique**. Le rendu visuel réel doit conserver les composants, mesures et apparences approuvés de la maquette de conversation et du Guide Lanyel.

### 1. En-tête fixe et compact — LE NOM DU GUIDE CHOISI
- Le **titre principal** est **le titre exact du guide ouvert depuis la liste/catalogue**, sans texte générique : si l'utilisateur ouvre `Dofus Sylvestre`, en-tête `Dofus Sylvestre` ; s'il ouvre `Guide Succès`, en-tête `Guide Succès` ; même règle pour Lanyel ou tout autre guide. Le libellé varie dynamiquement au changement de guide, sans refaire tout le panneau. Le titre est la référence du guide sur lequel l'utilisateur a cliqué au catalogue, pas un bouton inventé pour changer de guide.
- **SUPPRIMER totalement le sous-titre `Progression générale du parcours`** et le titre générique `Guide optimisé`.
- Petit engrenage paramètres à droite du titre réel ; en dessous, donut global à gauche et exactement trois barres à droite : `Route`, `Préparation`, `Succès`, avec compteurs RÉELS. Garder les dimensions/couleurs retenues.
- **Ligne des boutons** : `Aller à la fiche` (large), immédiatement à côté `Retour à l'actuelle` (bouton visible avec libellé et icône retour), puis petit bouton Overlay icon-only. Ce bouton revient instantanément à la fiche active courante, par opposition à la fiche parcourue via Sommaire, flèches ou accès direct. Ne pas modifier la sélection active ni les validations ; bouton désactivé ou neutre si déjà sur l'actuelle.
- **En-tête non repliable, ne disparaît pas au scroll**. Pas de quatrième barre. Progression Route = fiches réellement validées / total, jamais index de navigation ; ne pas coder en dur les comptes fictifs de la maquette.

### 2. Préparation générale du guide — COMPACTE, compatible avec une longue liste

**Dernière correction utilisateur : les pierres d'âme sont des OBJETS. Leur suivi n'est affiché QUE lorsque l'onglet `Objets` est sélectionné, jamais en section indépendante en bas de la préparation, jamais dans `Tout`, `Métiers` ou `Potions`. Cette règle prime la capture précédente montrant un gros encadré permanent Pierres d'âme.**

- Conserver le bandeau déroulant de la maquette fournie : icône clipboard/liste, `Préparation générale du guide`, sous-titre `Métiers, potions et objets · Parcours complet`, chevron. Fermé par défaut.
- Ouvert : titre `Préparation complète`, filtres horizontaux `Tout`, `Métiers`, `Potions`, `Objets`, puis **liste compacte** des exigences réelles du guide. Conserver les vrais noms/quantités et les états sans créer des tâches fictives. `Tout` montre les exigences générales/métiers/potions/objets ordinaires, **à l'exception de la ligne spécialisée `Pierres d'âme`**, visible uniquement en `Objets` conformément à la demande. Les objets ordinaires restent visibles dans `Tout`; ce n'est pas une règle d'exclusion globale des objets.
- **Une ressource = une ligne courte** (icône éventuelle minuscule ou pastille d'état, nom, quantité restante / totale, petit chevron optionnel), avec texte tronqué de manière accessible par survol. Pas de sous-titre explicatif sur chaque ressource, pas de grande carte pour chacune, pas d'une barre de progression par objet, pas d'une série de champs permanents qui étire la page.
- Dans le filtre **`Objets` UNIQUEMENT**, la rubrique des pierres apparaît dans la **même liste et au même format compact** que les autres objets : `Pierres d'âme — 50 / 150 · manque 100    ▾`. Aucun panneau dédié sous les filtres, aucune grande bannière `Pierres d'âme du guide` occupant plusieurs centaines de pixels.
- Le clic sur **cette ligne** peut déplier un **mini-détail inline** compact d'UNE à DEUX lignes maximum : `Possédées : [50]` (saisie non négative) et `Nécessaires : 150` (calcul automatique) ; état `Manque : 100`. Pas de texte de disclaimer long sous les champs, pas de barre de stock obligatoire. Au second clic, replier. Le stock demeure explicitement déclaré manuellement dans l'infobulle du libellé ou un texte court.
- Les pierres peuvent avoir plusieurs types/puissances : si le moteur prouve que des catégories différentes sont nécessaires, créer des **sous-lignes compactes différenciées** accessibles via l'expansion locale, avec leur besoin exact ; conserver agrégation cohérente, jamais additionner des catégories incompatibles au seul motif que ce sont des pierres.
- Si `Objets` contient beaucoup de ressources, la liste devient **scrollable avec une hauteur plafonnée dans le panneau**, des lignes de hauteur constante si possible, **virtualisation ou chargement incrémental**, aucun reflow coûteux ni dizaines de widgets hors-écran. Conserver les filtres en haut visibles, la navigation sommaire/fiche utilisable, les autres sections non décalées sur plusieurs écrans. Pas de chargement de tous les objets dans des widgets lourds en même temps.
- Toute la préparation est alimentée par les besoins réellement nécessaires, les possessions déclarées et la progression réseau/guide : déduplication, total restant, objets acquis sur le trajet exclus des achats à anticiper. L'exemple 50/150 est purement illustratif et ne doit pas être hardcodé. Ne pas déduire un stock depuis le réseau sans preuve.
- Attention à bien distinguer **le bloc global de préparation** (autorisé) et le bloc `À préparer` dans chaque **fiche** (interdit).

**Vue compacte, exemple (pas de données de jeu réelles) :**
```text
▤ Préparation générale du guide                        ▾
  Métiers, potions et objets · Parcours complet

  Préparation complète
  [Tout]  [Métiers]  [Potions]  [Objets]

  (Tout : obligations normales, pas de pierre d'âme)
  ● Alignement requis : Bonta
  ● Alchimiste niveau 40
  ● Potions de rappel ×12
  ● Ressource A ×8
  ...

  (Objets sélectionné : liste compacte, hauteur limitée)
  ● Ressource A                 3 / 8
  ● Ressource B                15 / 20
  ● Pierre d'âme          50 / 150 · manque 100  ▾
      Possédées [50] · Nécessaires 150 · Manque 100
  ● Ressource C                 0 / 12
  ...
```

**Certification UI/Qt :** screenshots sur `Tout`, `Objets` en état fermé/ouvert de la ligne Pierres, liste de 10/100/1 000 objets, scroll, hauteur du guide stable, absence de gros encart, troncature avec tooltip, pas de duplication en `Tout`, stockage/persistance après redémarrage, calcul `50/150 → 100`, 0 besoin, surplus, types/pouvoirs de pierre distincts et forte volumétrie sans RAM excessive.

### 2 bis. POTIONS ET OBJETS : liste ultra-compacte et quantités multicomptes CORRECTES

**Règle finale utilisateur (18/10) : les potions doivent être aussi compactes que les pierres d'âme, et les besoins changent quand on sélectionne plusieurs personnages.**

- **`Tout` = vue RÉSUMÉE** : une ligne par catégorie pertinente (métiers / potions / objets / conditions générales), avec le nombre d'éléments restant à préparer et éventuellement un statut global. Pas de centaines de lignes de potions/objets dupliquées dans Tout. Les détails des consommables sont uniquement dans leurs filtres respectifs : `Potions` pour les potions, `Objets` pour les autres ressources et les pierres d'âme. L'utilisateur peut ainsi voir le panorama puis ouvrir le bon filtre sans rallonger la page.
- **`Potions` : une potion = une seule ligne concise** : icône discrète, nom exact, résumé `possédées / nécessaires` ou `manque N`, petit chevron si un détail est utile. Aucun pavé descriptif, pas de gros formulaire permanent, **pas de barre de stock pour chaque potion**.
- Au clic sur une potion, ouvrir un **mini-détail local de 1–3 lignes max** : besoin par personnage participant, stock déclaré ou vérifié avec sa provenance, quantités encore nécessaires ; saisir ou corriger la possession via un contrôle minuscule, sans surcharger les autres lignes. Refermer au second clic, expansion d'un article ne déplie pas tous les autres. Dans une liste volumineuse, ne matérialiser le détail d'une ligne qu'à sa demande.
- **`Objets` : exactement le même composant réutilisable** pour ressources, consommables hors potions, clés et pierres d'âme ; aucune grande carte ni bloc spécial. Les pierres d'âme sont affichées uniquement dans `Objets`, les potions uniquement dans `Potions`. Les autres catégories restent propres et chaque item doit avoir un ID stable et une unité fiable ; les noms longs sont accessibles au survol.
- Les sélections du panneau **`Mes personnages` sont la source de vérité**. Recalcul IMMÉDIAT après sélection/désélection d'un portrait, après événement de progression du réseau, changement de guide ou actualisation des possessions. Une ligne n'affiche **que les besoins des participants sélectionnés**, hors ligne inclus si leur progression est connue ; si aucune sélection, afficher `Sélectionne un personnage` plutôt que des chiffres faux ou un total de tous les comptes par défaut.
- **Calcul par personnage AVANT agrégation, JAMAIS `besoin × nombre de portraits` aveuglément.** Exemple fictif : Pandawa a encore besoin de 4 potions de rappel et Huppermage de 2 ; sélection Panda seulement => 4, Hupper seulement => 2, les deux => **6 et non 8**. Une quête déjà finie, un Zaap accessible, une potion possédée, une capture déjà faite ou un donjon déjà validé peut supprimer une dépense propre à un personnage.
- **Distinction impérative `besoin total` vs `stock possédé` vs `manquant`.** Le total des besoins se somme par participant si l'objet est consommé individuellement ; un prérequis unique à l'équipe (ex. condition partagée réellement prouvée) ne se multiplie PAS. Les ressources transférables peuvent être suivies dans un stock partagé uniquement si ce caractère partagé a été confirmé ; une potion non transférable stockée sur Panda n'est pas automatiquement possédée sur Hupper. Calcul des manques par personne/stock éligible, puis somme des manques ; ne pas soustraire un stock partagé plusieurs fois.
- Par défaut la **ligne résumé regroupe le même objet identifié** plutôt que créer `Potion de rappel — Panda` et `Potion de rappel — Hupper` séparément ; le détail dépliable donne la ventilation pour chaque personnage. Les icônes des personnages du détail sont facultatives et petites, jamais un nouveau panneau de cartes.
- Filtres `Tout/Métiers/Potions/Objets` inchangés ; listes à **hauteur plafonnée**, scroll fluide, recherche facultative seulement si utile à la volumétrie, compteurs résumés `Potions · 6 lignes` et `Objets · 120 lignes` facultatifs. Garder le bandeau et la fiche accessibles même avec 100–1 000 lignes, préférer modèle Qt / delegate virtualisé à une création massive de QWidgets.
- Afficher `besoin inconnu` ou `stock non renseigné` lorsque c'est le cas, au lieu d'inventer 0, multiplier un chiffre incomplet ou afficher une fausse coche. Lors de la sauvegarde, stocker des besoins calculés uniquement comme cache recalculable et ne pas perdre les possessions déclarées, avec provenance, lors d'un changement de sélection.
- **Test majeur** : choisir Panda seul (4), Hupper seul (2), les deux (6), puis une quête déjà validée d'un seul personnage (moins pour lui uniquement). Changer la sélection plusieurs fois doit restaurer le même calcul ; combinaisons 0/1/2/5 personnages, offline, 100 objets, stock individuel/partagé, types différents de pierres et consommables ; aucun double compte.

**Nouvelle représentation compacte (chiffres illustratifs) :**
```text
▤ Préparation générale du guide                    ▾
   Préparation complète
   [Tout] [Métiers] [Potions] [Objets]

   Tout :
   ○ Alignement : Bonta (si pertinent)
   ○ Métiers : 2 exigences
   ○ Potions : 3 références — 6 à prévoir
   ○ Objets : 27 références — 42 à prévoir

   Potions :
   ○ Potion de rappel     0/6 · manque 6       ▾
       Panda : 4 restantes · Hupper : 2 restantes
   ○ Potion de cité       2/4 · manque 2       ▾

   Objets :
   ○ Pierre d'âme        50/150 · manque 100   ▾
       Stock déclaré : [50] · besoin calculé : 150
   ○ Ressource X         10/15 · manque 5      ▾
```

### 2 ter. Mini-coche « Prêt » par article + « À prévoir » contextuel dans les fiches

**Nouvelle règle (18/10) : quand le joueur possède déjà le nécessaire, une mini-coche à droite de chaque ligne Potion/Objet permet de marquer l'article `Prêt` d'UN clic, sans obligation de saisir son inventaire.** Ne pas créer une carte, un texte d'aide ou un formulaire supplémentaire.

#### Contrôle ultra-compact dans la préparation générale
- Chaque ligne détaillée sous `Potions` ou `Objets` affiche **[petite icône ✓ ou cercle] juste AVANT le mini-chevron de détail à droite** ; cible cliquable distincte du chevron, taille cohérente avec les autres boutons Atlas, infobulle `Marquer prêt`/`Annuler prêt`. Ex. `Potion de rappel    Besoin 6       [✓] [⌄]` ; `Pierre d'âme    Besoin 150      [✓] [⌄]`. Pas de long label « Valider », pas de grosse checkbox, pas de popup demandant un chiffre.
- Si l'utilisateur clique ✓, **il déclare simplement que les besoins de cet article sont couverts pour les personnages sélectionnés**. État `Prêt (déclaré)` visuellement lisible et réversible. Ne jamais assimiler cette confirmation à une preuve d'inventaire, à une quête accomplie ou à une validation réseau. **Ne pas afficher simultanément « Prêt » et un faux « Manque 6 » actif** : le calcul des quantités brutes reste disponible via le détail ; l'indicateur de manque est neutralisé dans le résumé tant que la confirmation reste valable.
- Confirmation mémorisée **par guide + item_id/type/puissance + ID des participants concernés et besoin à la confirmation**. Si Panda et Hupper sont sélectionnés, un clic peut marquer prêt pour ces deux personnes seulement ; l'ajout ultérieur d'Éca ne coche PAS automatiquement Éca. Si un besoin augmente ou devient inconnu pour une personne, sa confirmation doit être revue ; en cas de baisse inchangée des conditions, préserver l'état quand justifié. Un article paraît prêt pour une sélection **seulement si tous les participants ayant un besoin pour cet article sont couverts**. Cas 0 participant => pas de confirmation globale fictive.
- **Préférer une sémantique de couverture**, pas de stock numérique inventé : la coche est un raccourci de `j'ai prévu ce qu'il faut`. La saisie optionnelle du stock dans le mini-détail reste possible et exacte, avec provenance. Décocher restaure l'état réel des besoins et stocks saisis ; aucune perte de progression réseau.
- Les mêmes règles s'appliquent aux potions, pierres d'âme, clés, ressources et objets ordinaires **dans leur catégorie respective**, avec une mise à jour incrémentale rapide et persistance après fermeture/reprise d'Atlas.

#### « À prévoir » DANS les fiches : seulement au moment utile, pas de doublons
- **Conserver l'interdiction d'un gros bloc autonome `À préparer` dans chaque fiche**. En revanche, la nouvelle demande `À prévoir` signifie permettre un **court avertissement contextuel lié à l'ACTION** lorsque l'objet est indispensable à ce stade (ex. immédiatement avant l'entrée en donjon : `À prévoir : Clé du donjon ×1` ; avant un boss à capturer : `À prévoir : Pierre d'âme adaptée ×1` ; besoin d'une potion à ce trajet uniquement si réellement consommée).
- Le moteur #226 distingue `global_before_start`, `just_in_time`, `acquire_on_route` et `quest_drop` (ou équivalents). Un objectif/récolte planifié au fil du parcours **n'est pas une préparation à acheter en avance**. Avertissement contextuel **seulement s'il est nécessaire, non couvert et pas déjà prévu par l'optimiseur avant cette fiche** ; sinon ne rien rajouter.
- Montrer le rappel **sur la ligne concernée ou immédiatement avant l'action** (même apparence compacte des lignes Lanyel), PAS en carte/section séparée, PAS comme une recopie de la rubrique Potions/Objets, PAS de liste de toute la préparation. Si la préparation globale contient déjà l'article, la fiche ne doit pas le redemander systématiquement : afficher au maximum un état/rappel ponctuel lorsque le besoin risque de bloquer l'action et n'est pas marqué `Prêt`.
- La fiche lit **le même item_id, la même quantité et le même état par participant** que le panneau global ; clic ✓ dans le panneau global ou validation réelle observable rafraîchit les rappels de fiche. Attention : s'il y a plusieurs personnages, `Panda prêt / Hupper manque 1` n'est **pas** `tout prêt`. Le texte court du rappel montre la quantité encore requise pour les participants concernés, avec le détail sur survol ; ne pas inventer de possession réseau.
- Les **combats, drops de quête, PNJ et récoltes prévus par cette fiche** restent des **actions à faire**, jamais transformés en `À prévoir`. Ne pas réintroduire les sections `Quêtes liées`, `Sources`, `Succès liés` ni `Pourquoi cet ordre ?`.
- Pour les clics des lignes liées à des quêtes, conserver au survol les noms des quêtes et le petit bouton UNIQUE par quest_id et par fiche, inchangés.

**Tests de sortie complémentaires** : ✓ sur potion/objet sans saisie, annulation ✓, persistance redémarrage, ajout retrait participants, besoin qui augmente, 0 participant, stock numérique inconnu, quantités divergentes, aucune validation de quête causée par ✓ ; fiche donjon nécessitant une clé manquante, capture avec pierre manquante, objet préparé déjà déclaré prêt => pas de faux avertissement, drop acquis pendant la route => pas de liste « À prévoir », aucune section dédiée par fiche, 1 000 articles scrollables sans inflation de widgets.

### 3. Commandes Personnages / Sommaire — SANS `Mon parcours`
- **SUPPRIMER complètement le titre `Mon parcours` et son commentaire/sous-titre `Fiche N / total` placé dessous. Le numéro de fiche est déjà visible dans l'en-tête/contrôle de pagination de la fiche : ne jamais le dupliquer.
- Placer **dans l'en-tête de la fiche active, à droite**, le petit bouton icône `Personnages` puis le bouton `Sommaire` avec chevron ; aucun bandeau séparé ni nouvelle rangée réservée aux boutons. Garder le titre court et l'identifiant de fiche à gauche.
- Au clic Personnages, ouvrir l'ANCIEN MENU compact masqué par défaut, avec en-tête littéral **`Mes personnages`**, jamais `Personnages du guide`.
- Une ligne de petites **vraies images de classes** circulaires (36–42 px), anneau de progression et indication de sélection distincte ; pas de noms fixes ni de grosses cartes. Survol de chaque portrait => **vrai pseudo**, classe et % progression dans un tooltip près du curseur, sans sélection automatique. Cliquer portrait => inclure/exclure sa participation au guide et aux macros ; état persisté par ID stable et guide, y compris offline.
- **SUPPRIMER intégralement** le texte d'aide `Appuie sur un portrait pour inclure/exclure...` (ou tout équivalent), le panneau `Déclarer une progression antérieure`, ses champs `Chapitre fini avec` / `Guide fini avec`, et tout compteur manuel historique. **On exploite le réseau pour progression et validation automatiques** ; garder seulement le bouton `Valider` existant en secours manuel au cas où, sans falsifier les preuves réseau.
- **Sommaire** : bouton ouvre/ferme explicitement le panneau (par clic sur Sommaire/chevron), avec recherche, chapitres et fiches dépliables ; **un clic sur un chapitre ou une fiche NE LE FERME JAMAIS automatiquement**. Un clic fiche affiche la nouvelle fiche à droite/en dessous selon la mise en page existante et laisse le panneau visible. Fermeture uniquement par clic explicite sur Sommaire. Navigation manuelle via Précédent/Suivant, Aller à la fiche ou Retour à l'actuelle ne doit pas non plus fermer automatiquement le sommaire. La virtualisation garantit une seule fiche réelle montée à la fois.
- Première fiche = `Légende`, sans ajouter les sources en plein écran.

### 4. Corps de fiche — visuel Lanyel conservé
- UNE fiche visible, titre court fourni par #226, identité/pagination stable, coordonnées cliquables dans le texte **exactement comme avant** ; toutes les actions réellement nécessaires dans l'ordre de parcours : PNJ/dialogues, récoltes/drops, combats, donjons, captures, validations.
- Nom exact des monstres et quantités : ligne à cocher `×5 Tournesol sauvage` ; ne pas montrer `Faire les combats` sans cibles réelles. Les combats de quête sont cochables, y compris via intégration à l'onglet Quêtes ; gestion des preuves et validation manuelle conservées.
- Termes adaptés : `Récolter` pour les objets de métier, `Acheter` seulement si réellement achetable, `Obtenir`/`Récupérer` pour les drops et objets non échangeables. Les actions ne sont pas noyées dans de longs paragraphes.
- Les vrais liens/noms de quêtes **dans le contexte d'une action** restent cliquables avec infobulle du nom complet si nécessaire. **Ne jamais ajouter un bloc/liste `Quêtes liées`**.
- **Interdiction des sections suivantes dans la fiche** : `À préparer`, `Quêtes liées`, `Sources`, `Succès liés`, `Pourquoi cet ordre ?`, zone de contrôle Travel/Zaap ou boîte de confirmation de déplacement. L'ordre du guide doit faire le travail en amont. Garder les métadonnées et vérifications en arrière-plan.
- Boutons inférieurs UNIQUES : `Précédent`, `Valider`, `Suivant`, conserver comportement et position validés. La validation réseau fiable et le mode manuel doivent rester disponibles sans faux positifs.
- Conserver le style de la fiche Guide Lanyel existante : marges, polices, survols, contraste, alternances, cartes, tooltips, dimensions et règles de clic ; **pas d'écran réinventé**.

### 5. Clic sur [x,y] — AUTOMATIQUE, INVISIBLE VISUELLEMENT
- Le même texte `[x,y]`, les mêmes couleur, graisse, zone de clic et tooltip existants.
- Clic gauche = déclenche pour les seuls personnages participants et fenêtres Unity reconnues, le plan `/travel x,y` OU `/zaap zx,zy ; /travel x,y` choisi par le planificateur #226 et exécuté par Organizer #227.
- Ne PAS afficher `Zaap conseillé`, nouvelle carte trajet, bouton supplémentaire, icône nouvelle, chaîne de commande ni une notification de prévisualisation permanente.
- Identité de session vérifiée avant toute commande, arrêt d'urgence et refus sûr en absence de certitude ; les sources / règles de choix restent dans les données et diagnostics internes.

## Contrat graphique STRICT — vrais portraits, images et icônes des boutons

**Les boutons doivent avoir leurs vraies icônes, selon la maquette approuvée ; aucun bouton représenté par un caractère de remplacement, un carré, un emoji arbitraire, un glyphe police absent ou une image cassée.** Ne pas substituer une nouvelle charte graphique. Les boutons à texte conservent leur texte et leur style déjà validés. Les boutons icône-seule restent discrets et de mêmes dimensions que les contrôles voisins.

### Identités et portraits cliquables (obligatoire)
- L'ancien MENU DÉROULANT des personnages reste à sa place : petit bouton icône juste avant `Sommaire` sur la ligne compacte SANS titre `Mon parcours`. Il ouvre le **même panneau compact précédent**, fermé par défaut et repliable au clic ; ne pas utiliser un sélecteur de liste, un modal, des cartes par personnage ou des checkboxes à côté du pseudo.
- Chaque **portrait de classe est lui-même le bouton** (QToolButton/QWidget accessible et réellement cliquable), pas juste une image décorative. Clic gauche : inclure/exclure ce personnage du GUIDE courant. Sélection = appartenance aux quêtes/captures/déplacements du guide, **sans modifier sa progression**. À l'ouverture, recharger les choix persistés, même si Organizer a changé l'ordre des fenêtres.
- Pour les classes reconnues, image réelle issue de `data/images/classes/<class_key>.png` (ex. `pandawa.png`, `huppermage.png`, `ecaflip.png`, `enutrof.png`, `feca.png`, `forgelance.png` ; même principe pour les 19 fichiers). Réutiliser l'éventuel helper canonique `app/pages/organizer/common.py` pour résolution et variantes, mais **ne pas prendre la même icône pour tous les personnages**.
- Les images disponibles dans le dépôt sont **stockées via Git LFS** (un objet `*.png` de ~130 octets lu sans filtre est typiquement un pointeur LFS, pas une image). Le chargement, le packaging PyInstaller et les tests Windows doivent garantir les vrais octets d'image décodables ; ne pas considérer l'existence d'un fichier comme la preuve que QPixmap peut l'afficher. En cas d'image invalide, rapport Doctor UI FAIL avec classe/chemin, pas de validation de captures de « carrés » ou de lettres fictives.
- Diamètre visuel du portrait : environ **36 à 42 px**, avec une **fine couronne circulaire de progression** distincte du statut sélectionné. Images centrées, non déformées, fond identique aux contrôles précédents ; l'anneau ne doit pas cacher le portrait. Un **discret check/contour** matérialise la sélection, différence également perceptible sans couleur seule ; non-sélectionné atténué mais reconnaissable.
- Au survol du portrait : une infobulle compacte affichée près du pointeur avec le VRAI pseudo, classe, progression fiable, origine de preuve et état réseau/offline ; **pas de texte permanent sous les portraits**. Deux personnages de même classe conservent chacun leur bouton, leur pseudo et leur propre état.
- Ligne de portraits compacte, avec espacement homogène ; adaptation responsive quand >5 personnages : défilement horizontal du panneau si nécessaire, sans couper/cacher le dernier portrait ni agrandir la hauteur du guide. Aucune case numérotée. Permettre navigation clavier/focus et activation Enter/Space.
- Les personnages offline restent visibles et sélectionnables, mais ne sont jamais ciblés par une macro ; si aucun personnage sélectionné : aucune macro, jamais repli sur « tous les clients ».
- **Aucune saisie de progression antérieure** ni compteurs de chapitres/guides déjà finis. Le réseau est prioritaire pour la progression ; le seul secours manuel reste le bouton `Valider` de la fiche.

### Inventaire des contrôles et icônes à reproduire
| Emplacement | Visuel demandé | Interaction | Consignes graphiques |
| --- | --- | --- | --- |
| En-tête à droite | **Petit engrenage paramètres** | Ouvrir réglages | Même pictogramme et dimensions que la maquette ; utiliser icône valide, pas « ⚙ » en texte si fonte incertaine |
| Ligne navigation | Bouton **Aller à la fiche** + bouton **Retour à l'actuelle** juste à côté | Accès direct + retour à la fiche active après exploration | Garder la disposition compacte et l'icône de retour cohérente |
| À sa droite | **Bouton Overlay : icône carte uniquement** | Afficher/masquer l'overlay | Petit carré, pas de libellé ajouté, état actif/inactif |
| Préparation générale du guide | **Icône clipboard/liste + titre, sous-titre, chevron** | Filtres Tout/Métiers/Potions/Objets ; **Pierres uniquement dans Objets** sous forme de ligne compacte dépliable | Hauteurs limitées, scroll/virtualisation, pas de gros bloc pierre |
| Ligne avant fiche (sans titre) | **Icône personnages (groupe)**, icône seule | Afficher/masquer le menu **Mes personnages** | Juste avant Sommaire, même taille que bouton Overlay |
| Ligne avant fiche (sans titre) | **Icône sommaire/liste** + texte `Sommaire` + chevron | Ouvrir/fermer manuellement, **ne pas fermer sur sélection fiche** | Même ligne, pas de bouton de remplacement |
| Liste chapitres | Coche/cercle de progression + chevrons | Dérouler / aller à une fiche | Icônes discrètes et cohérentes avec les couleurs du thème |
| Fiche | Positions **[x,y] en gras** et apparence déjà existante | Clic unique macro auto Travel/Zaap selon #226/#227 | **AUCUNE** nouvelle icône, badge, image, marqueur Zaap ni bouton copier à côté |
| Fiche | **Cases de validation de combats** | Cocher ×N monstre précis | Vraies checkbox du style Lanyel ; pas de faux caractères □ / ■ |
| Navigation bas | `Précédent` flèche gauche, `Valider` état validé, `Suivant` flèche droite | Changer de fiche / validation | Garder les 3 boutons, ordre, proportions, labels, feedback existants |
| Overlay | Images/icônes **déjà fournies par Atlas** | Afficher les éléments existants | Aucune refonte des assets ou du placement en #225 |

- Utiliser les pictogrammes **cohérents avec les composants Qt/Atlas déjà en place**, icônes SVG/PNG réellement décodées ou icônes dessinées vectoriellement de façon fiable si l'équivalent Atlas existe déjà. Pas de dépendance à des caractères Unicode pour rendre un bouton fonctionnel, pas de « texte de secours » visible à la place d'images connues.
- Si une icône de la maquette est absente du dépôt, reprendre d'abord l'équivalent visuel dans les composants existants, documenter la provenance/licence d'un éventuel nouvel asset et faire valider son rendu ; **ne pas inventer un dessin ou remplacer par un emoji**. Garder le thème sombre/clair, survol, focus, état désactivé et écran HDPI cohérents.
- Bouton Retour à l'actuelle : icône et libellé, placé IMMÉDIATEMENT à côté de Aller à la fiche ; toute sélection Sommaire reste ouverte.
- Boutons icône-seule : `setAccessibleName`, vrai tooltip, état de bascule lisible ; éviter les signaux déclenchés au survol. Les zones cliquables restent suffisantes sans agrandir visuellement les icônes.

### Validation visuelle et packaging graphique
- Screenshots Doctor UI **avant/après** pour : (1) état initial menus fermés ; (2) Préparation générale du guide ouverte ; (3) personnes ouvertes, avec vrais portraits de 5 classes différentes ; (4) un portrait déselectionné et deux de même classe avec progression distincte ; (5) sommaire ouvert ; (6) fiche Lanyel et Succès ; (7) zoom/HDPI, écran minimal.
- Checks Qt d'existence d'image réelle : `QPixmap.isNull() == False`, taille lisible, décodage de tous les assets utilisés, absence de pointeur Git LFS dans la version Windows distribuée ; contrôles interactifs associés aux bonnes fonctions ; pas d'icône invisible ni de texte tronqué.
- Comparer **la forme, l'espacement, la position et le contenu** de chaque bouton et portrait à la maquette approuvée, pas simplement la présence d'un widget portant le bon objectName.
- Faire échouer la certification UI si des portraits/boutons sont des carrés ou du texte de remplacement, si le panneau Personnages a été changé en liste, ou si la sélection ne survit pas au redémarrage.

## Contrat de SURVOL et de navigation liée aux quêtes — obligatoire sur chaque ligne utile

**Règle de présentation : le texte de la fiche reste COURT. L'identité de la quête est portée par la ligne et apparaît au SURVOL, pas dans une section supplémentaire.**

### Personnages
- Le survol d'un petit portrait de classe dans le MENU DÉROULANT des personnages affiche **le vrai NOM/ PSEUDO du personnage** (élément obligatoire et vérifié), puis classe, progression pertinente, état de connexion et preuve réseau/manuelle/inconnue dans une **mini-infobulle au niveau de la souris**.
- Si plusieurs personnages ont la même classe ou la même icône, afficher leur nom propre et le bon taux ; aucun tooltip générique `Pandawa` au lieu du pseudo. Pas de pseudo écrit sous les icônes en permanence.
- Clic sur le portrait = inclure/exclure ce personnage du guide et des macros ; SURVOL = information seulement, pas de sélection, de macro ni de validation.

### Lignes de quête : infobulle sur la LIGNE ENTIÈRE
- Chaque ligne d'action ou d'objectif lié à une ou plusieurs quêtes doit afficher **au survol de sa zone utile** le(s) **nom(s) complet(s) et EXACT(s) des quêtes réellement associées à CETTE ligne**. Cela concerne, sans exception oubliée : PNJ/dialogues, déplacements avec objectifs de quête, combats (y compris les checkboxes `×N monstre`), collecte/récolte, drops, donjons, captures, validation/rendre quête.
- Prendre les **IDs des quêtes et des objectifs en données** ; résoudre leur vrai nom depuis le provider de quêtes. Ne pas déduire l'association en copiant toute la liste des quêtes d'une fiche sur toutes les lignes. **Pas de fausse association** : si aucun quest_id probant, pas de nom inventé ; si plusieurs quêtes, les lister une seule fois chacune, dans un ordre stable.
- L'infobulle est un petit commentaire contextuel **près du pointeur**, pas un encadré qui prend de la place dans la fiche. Format minimal : `Quête : <nom complet>` ou `Quêtes : <nom 1> ; <nom 2>`. Si pertinent et prouvé, ajouter l'objectif associé, sans longues phrases. Une étape de trajet non liée à une quête n'affiche pas arbitrairement une quête.
- Tooltip requis lorsque la souris se trouve SUR LE TEXTE mais également sur la zone cliquable associée et sur les cases de combats ; veiller au propagations Qt `QFrame`/`QLabel`/`QCheckBox`. Le survol ne doit ni recouvrir ni désactiver le clic sur `[x,y]`.
- Tooltip sur le petit bouton de navigation : **nom complet de la quête + `Ouvrir dans Quêtes`** ; le même objectif/quête doit être affiché pour la ligne et pour son bouton.

### Petit bouton « aller à la quête » SUR SA LIGNE — existant, à réparer/completer
- Le bouton est **déjà partiellement présent** dans `GuideUltimeManualCard._add_inline_quest_links` de `app/modules/encyclopedia/views/guide_ultime_manual_view.py` : `QToolButton` 24×24, icône Qt `SP_FileIcon`, objet `GuideManualQuestInlineButton`, tooltip du nom. Il est ajouté par `SharedGuideManualCard._add_line_section` dans `app/modules/encyclopedia/views/shared_manual_guide_view.py`. **RÉUTILISER CE CONTRÔLE** et le style validé plutôt que créer un gros bouton, une colonne dédiée ou une liste `Quêtes liées`.
- **Règle utilisateur définitive : UN SEUL petit bouton par quête et par fiche**, même si cette quête est associée à plusieurs lignes. Le mécanisme existant `_shown_quest_ids` est intentionnel et doit être **CONSERVÉ**. Le bouton apparaît sur la première ligne pertinente, jamais une deuxième fois pour le même `quest_id` dans cette fiche. Le compteur de déduplication est réinitialisé au changement de fiche ; la même quête peut avoir son unique bouton dans une autre fiche. L'absence de second bouton ne retire jamais les infobulles des lignes suivantes.
- Au clic, ouvrir **directement l'onglet Quêtes avec la bonne fiche quête, identifiée par quest_id**, pour le personnage sélectionné ; ne pas seulement afficher le titre, copier le nom, aller au sommaire ou rouvrir la fiche Guide. Réutiliser `questRequested = Signal(int, str, int)`, `SharedGuideManualView._open_quest_from_card` et `EncyclopediaPage.navigate_to_entity("quest", id, source="guide_gps", ...)` (à revalider au HEAD final), sans duplicer de système de navigation.
- Si une action sert **plusieurs** quêtes, le survol liste les vrais noms ; afficher au maximum **un bouton par `quest_id` sur toute la fiche** (chacune de ces quêtes peut posséder son accès unique sur la première ligne correspondante). Pas de lien arbitraire vers la mauvaise quête, pas de menu ni de répétition sur toutes les lignes.
- Si la ligne n'est liée à aucune quête vérifiée, **aucun faux bouton « aller à la quête »**. Les liens de progression du guide, et le bouton `Guide` unique déjà existant, doivent garder leur comportement.
- Cliquer la coordonnée `[x,y]` reste exclusivement le geste de déplacement (macro Organizer Travel ou Zaap+Travel suivant le plan) ; **cliquer le petit bouton de la ligne** est exclusivement le geste de navigation dans l'onglet Quêtes. Cliquer le checkbox combat coche l'objectif ; aucune de ces actions ne doit déclencher les autres par propagation accidentelle.

### Tests de survol et navigation à ajouter dans Doctor UI / Qt
1. Ouvrir Personnages : survol de chaque portrait => pseudo exact, classe exacte, progression individuelle ; classes identiques avec pseudos différents, offline, état inconnu. Fermer/rouvrir le menu et l'app => sélections sauvegardées.
2. Survol d'une ligne PNJ => nom quête exact ; survol combats/checkbox => nom complet de la quête + monstre/quantité ; survol récolte/drop/capture => bon quest_id ; ligne multi-quêtes => tous les noms ; ligne non liée => aucun faux nom.
3. Même quête sur **deux lignes successives** : le bouton n'apparaît qu'UNE fois sur la première ligne pertinente de cette fiche, mais **les DEUX lignes** affichent le bon nom de quête au survol ; les boutons des autres quêtes respectent la même règle de déduplication.
4. Clic bouton => onglet Quêtes, vraie quête ouverte sur le bon personnage, sans modifier l'état des fiches ; clic coordonnée => macro sans navigation Quêtes ; clic case combat => objectif uniquement ; survol => zéro déclenchement.
5. Captures Doctor UI réelles avec infobulles visibles près du curseur : **portrait**, **texte d'action**, **case combat**, **bouton quête**, et captures état sans survol pour prouver aucune pollution visuelle.
6. Le contrat doit être appliqué aux DEUX présentations Guide Succès / Lanyel depuis le rendu partagé et ne pas écraser les réparations de la PR #201.

## Scénarios supplémentaires de validation obligatoires
- Ouvrir Guide Succès, puis Dofus Sylvestre depuis le catalogue : le titre principal affiche EXACTEMENT le nouveau nom (pas `Guide optimisé`), aucun sous-titre de progression ; les barres sont conservées et liées au bon guide.
- Ouvrir Sommaire puis choisir Fiche 643 : le Sommaire reste ouvert. Choisir ensuite Fiche 641 et utiliser `Retour à l'actuelle` : retour à la vraie fiche active sans fermeture du Sommaire et sans validation parasite.
- En mode normal, les commandes icône Personnages et Sommaire sont présentes à droite mais SANS `Mon parcours` ni `Fiche 643/x` répété sous ce titre ; la pagination reste dans son emplacement existant.
- Menu Personnages ouvert : titre `Mes personnages`, vrais portraits avec pseudo au survol ; vérifier ABSENCE de message d'aide et de `Déclarer une progression antérieure`, pas de champs historique. Réseau prioritaire ; bouton Valider secours manuel conservé.

## Contrôle de fidélité obligatoire
1. Rendre une capture COMPLÈTE en **état par défaut** : en-tête fixe, préparation refermée, personnages refermés, sommaire refermé, une fiche seule. Comparer visuellement à la **dernière maquette approuvée dans le fil de discussion**, pas à un mockup plus ancien.
2. Rendre des captures distinctes **Préparation générale du guide ouverte**, **Personnages ouvert**, **Sommaire ouvert**, **Fiche Lanyel**, **Fiche Succès**, **état scrollé**. Comparer disposition, ordre, marges, largeurs, typographies, positions, boutons, couleurs, aucune zone superflue.
3. Tests d'absence explicite des sections interdites, tests screenshot Doctor Atlas produisant de VRAIS pixels lisibles (pas des carrés), détection des contrôles et de leurs chevauchements ; petit écran et minimum 900 px.
4. Tests Qt interaction : aucune macro déclenchée par hover, une seule macro par clic gauche, position identique, sélection de 0/1/5 participants, mêmes classes, offline/online, migration des IDs, progression réseau et secours manuel, persistance du stock 50/150 après redémarrage.
5. Tests de non-régression des progressions Quêtes/Succès, Guide Lanyel/Guide Succès, de l'intégration du rendu partagé #201 et de la libération Qt au retour Home. Rebaser après #201, puis validation Doctor/Graphify et CI au HEAD final.

**CRITÈRE DE SORTIE : si l'UI n'est pas reconnaissable comme la maquette validée, la PR est FAIL même si les tests unitaires passent.**
