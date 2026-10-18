# PR #225 — UI Guide Succès / Lanyel : REPRODUCTION FIDÈLE DE LA MAQUETTE VALIDÉE

Date : 18 octobre 2026. Branche : `feature/guide-ui-compact-20261018`.
**ÉTAT : design verrouillé, NON implémenté. Ne pas fusionner sans comparaison visuelle avec la maquette validée.**

## CONSIGNE ABSOLUE — pas de liberté sur l'UI

L'interface doit **ressembler exactement à la dernière maquette validée avec l'utilisateur**, en conservant le style visuel déjà en place du guide Lanyel (couleurs, fonds, composants, typographie, espacements, cartes et contrôles). Les maquettes précédentes ne priment pas sur les dernières corrections. Cette PR NE DOIT PAS être interprétée comme « refaire un design inspiré de ». **C'est une reproduction 1:1 de la composition acceptée, à l'exception des suppressions explicites ci-dessous.**

Ne pas inventer :
- panneau dédié aux déplacements / Zaaps, boutons « Copier la commande », badges sur les coordonnées, statut macro permanent, légende supplémentaire de transport ;
- bloc « Quêtes liées à cette fiche », bloc local « À préparer », « Sources du guide », « Succès liés », « Pourquoi cet ordre ? », « Étapes précédentes », « À suivre » ou « Destination suivante » ;
- grosse liste de personnages, cartes individuelles de personnages ou tableau multicomptes toujours visible ;
- variantes visuelles du menu de préparation générale, nouveaux onglets ou présentation en pleine page.

Si un détail visuel n'est pas explicitement documenté ici, **préserver l'existant/maquette**, ne pas improviser ; confronter les captures Doctor UI à la composition validée avant de déclarer PASS.

## STRUCTURE VISUELLE EXACTE, DANS CET ORDRE

```text
┌────────────────────────────────────────────────────────┐
│ Guide optimisé                                   [⚙]  │
│ Progression générale du parcours                        │
│                                                        │
│   (donut GLOBAL %)       Route         640 / total       │
│                          ━━━━━━━━━━━                   │
│                          Préparation   n / total         │
│                          ━━━━━━━━━━━                   │
│                          Succès        n / total         │
│                          ━━━━━━━━━━━                   │
│                                                        │
│ [             Aller à la fiche              ] [🗺]     │
├────────────────────────────────────────────────────────┤
│ [ Préparation générale du guide                 ▾ ]     │
│     dépliable UNIQUEMENT sur action utilisateur          │
├────────────────────────────────────────────────────────┤
│ Mon parcours                         [👥] [Sommaire ▾] │
│ Fiche N / total                                        │
│                                                        │
│   (si 👥 ouvert : PETITS portraits ronds SUR UNE LIGNE) │
│   (si Sommaire ouvert : chapitres/fiches recherchables)  │
│                                                        │
│ ┌────────────────────────────────────────────────────┐ │
│ │ FICHE N · CHAPITRE X                              │ │
│ │ Titre court, naturel, déjà calculé par Guide Tools  │ │
│ │ [x,y]  ← exactement comme les coordonnées actuelles│ │
│ │                                                    │ │
│ │ Actions utiles à faire dans l'ordre du parcours    │ │
│ │ Parler au PNJ [x,y]                                │ │
│ │ Faire les combats                                  │ │
│ │   □ ×5 Nom exact du monstre                        │ │
│ │   □ ×3 Autre monstre                               │ │
│ │ Drops / captures / donjon / validation UNIQUEMENT   │ │
│ │ s'ils font partie de la fiche actuelle             │ │
│ │                                                    │ │
│ │ [ Précédent ] [ Valider ] [ Suivant ]              │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

Le dessin ci-dessus décrit la HIÉRARCHIE des éléments, **pas un redesign graphique**. Le rendu visuel réel doit conserver les composants, mesures et apparences approuvés de la maquette de conversation et du Guide Lanyel.

### 1. En-tête fixe et compact
- Texte affiché littéralement : `Guide optimisé`, sous-titre `Progression générale du parcours` ; petit engrenage à droite.
- En dessous : donut circulaire global **à gauche** ; exactement 3 barres horizontales fines **à droite**, libellées `Route`, `Préparation`, `Succès` avec compteurs réels.
- En dessous : bouton principal `Aller à la fiche` **large** ; juste à droite, petit bouton **icône Overlay uniquement**, infobulle `Afficher/Masquer l'overlay`, indicateur d'état discret.
- **En-tête non repliable, ne disparaît pas au scroll**, ne duplique pas sa navigation. Pas de quatrième barre.
- Progression Route = nombre de fiches réellement validées / total des fiches réelles, pas index courant ; toutes les quantités viennent du service runtime, aucun exemple fictif de `1600` codé en dur.

### 2. Préparation générale du guide — ANCIEN MENU DÉROULANT
- Immédiatement sous l'en-tête ; bande `Préparation générale du guide`, chevron ouvrir/fermer, fermé par défaut.
- **Reprendre l'ancien déroulant validé**, pas réinventer des onglets, cartes ou sections permanentes.
- Agréger pour TOUT le guide les ressources, achats, récoltes, potions, métiers, accès donjon et pierres d'âme ; dédoublonner et décompter ce qui est réellement requis selon le parcours, sans listes de préparation redondantes sur les fiches.
- À l'intérieur du déroulant, petite ligne/contrôle de stock : `Pierres d'âme — J'en ai 50 / Besoin 150 / Manque 100`. Saisie non négative, persistée entre redémarrages, avec suivi réel des puissances/types/nécessité par personnage et du besoin restant. Présentation aussi compacte que les autres lignes.
- Si un objet est acquis naturellement au cours du guide, ne pas le compter à acheter d'avance ; les prérequis internes demeurent contrôlés par le moteur.

### 3. Mon parcours — seulement la navigation demandée
- Titre `Mon parcours`, sous-titre `Fiche N / total`. À droite sur la MÊME ligne de commandes : un **petit bouton Personnages avec icône** puis `Sommaire` avec chevron. Aucun grand panneau permanent.
- **Bouton 👥** : ouvre/ferme l'ANCIEN MENU déroulant compact **juste sous cette ligne**, masqué par défaut. Ne pas remplacer par un menu de cases textuelles.
- Dans ce déroulant : sur une seule ligne quand possible, les **vraies images de classes** (déjà fournies par Atlas, pas des lettres fictives) dans de petits disques, cerclées par un anneau fin de progression ; pas de noms affichés en permanence.
- **Survol** d'un portrait : tooltip près de la souris avec pseudo réel, classe, pourcentage du chapitre/fiche pertinent et source de preuve (réseau/manual/inconnu). Pour deux personnages de la même classe, portraits indépendants (identité de personnage stable).
- **Clic** sur le portrait : sélectionne/désélectionne sa participation au guide. Retour graphique discret (coché/sélectionné), **sans remplacer l'anneau de progression** ni valider une quête. Personnages hors ligne toujours visibles/choisissables, mais aucune commande ne leur est envoyée.
- Sélection sauvegardée par identifiant de personnage stable et par guide, pas par indice de slot, PID, HWND ou nom approximatif.
- Déclarations `Guide déjà terminé avec X personnages` et `Chapitre déjà terminé avec X personnages` : accessibles de façon **secondaire/repliée** à l'intérieur du même menu, jamais nouveaux gros blocs ; si IDs connus, possibilité d'identifier exactement qui a fait quoi ; sinon compteur explicitement `déclaré`, sans preuve automatique ni fausse attribution.
- **Sommaire** : menu indépendant, fermé par défaut, recherche fiche/chapitre, chapitres dépliables, libellés et compteurs, clic pour rejoindre une fiche ; **une seule fiche coûteuse montée à la fois**, virtualisation/lazy rendering.
- Première fiche = `Légende` déjà convenue, pas une nouvelle page de sources ou explications permanentes.

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

## Contrôle de fidélité obligatoire
1. Rendre une capture COMPLÈTE en **état par défaut** : en-tête fixe, préparation refermée, personnages refermés, sommaire refermé, une fiche seule. Comparer visuellement à la **dernière maquette approuvée dans le fil de discussion**, pas à un mockup plus ancien.
2. Rendre des captures distinctes **Préparation ouverte**, **Personnages ouvert**, **Sommaire ouvert**, **Fiche Lanyel**, **Fiche Succès**, **état scrollé**. Comparer disposition, ordre, marges, largeurs, typographies, positions, boutons, couleurs, aucune zone superflue.
3. Tests d'absence explicite des sections interdites, tests screenshot Doctor Atlas produisant de VRAIS pixels lisibles (pas des carrés), détection des contrôles et de leurs chevauchements ; petit écran et minimum 900 px.
4. Tests Qt interaction : aucune macro déclenchée par hover, une seule macro par clic gauche, position identique, sélection de 0/1/5 participants, mêmes classes, offline/online, migration des IDs, compteurs déclarés vs vérifiés, persistance du stock 50/150 après redémarrage.
5. Tests de non-régression des progressions Quêtes/Succès, Guide Lanyel/Guide Succès, de l'intégration du rendu partagé #201 et de la libération Qt au retour Home. Rebaser après #201, puis validation Doctor/Graphify et CI au HEAD final.

**CRITÈRE DE SORTIE : si l'UI n'est pas reconnaissable comme la maquette validée, la PR est FAIL même si les tests unitaires passent.**
