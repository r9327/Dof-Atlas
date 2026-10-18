# PR UI — Guides Succès / Lanyel : affichage verrouillé et multicomptes compact

Date : 18 octobre 2026. Base : main au démarrage, SHA 6a52522d1bd7e501a5c3b4d6d58253bfec755fdc.
Statut : cahier des charges initial, **pas une implémentation validée**. Ne pas merger avant implémentation et tests.

## Frontière claire avec la PR #201
La PR #201 corrige les régressions de rendu et de données. Cette PR porte les **nouveaux choix d'interface**. Rebaser après l'intégration de #201 ; ne pas annuler ses corrections et ne pas modifier les identifiants de progression persistants. Éviter une refonte parallèle de `shared_manual_guide_view.py` tant que #201 est ouverte.

## Interface commune verrouillée
- Même présentation compacte pour Guide Succès et Guide Lanyel ; en-tête `Guide optimisé` toujours visible, non replié avec le défilement ; roue progression globale + barres Route (fiches réellement validées), Préparation et Succès ; engrenage.
- Rangée de navigation `Aller à la fiche`, puis petit bouton Overlay uniquement en icône.
- `Préparation générale du guide` : **ancien menu déroulant conservé**, masqué par défaut, regroupement par métiers/potions/objets/captures sur le guide ENTIER, globalement dédupliqué. Suivi des pierres : `J'en ai 50 / besoin 150 / manque 100`, saisie non négative persistante et compte précis par type / puissance / personnage.
- `Mon parcours` : `Fiche N / total`, sommaire repliable, navigation directe, recherche chapitres/fiches, une seule fiche lourde matérialisée à la fois, légende initiale ; `Précédent / Valider / Suivant` ; index stable `manual:chapter:stage`.
- Sur la fiche : titre, coordonnées cliquables strictement IDENTIQUES à l'existant ; lignes d'actions PNJ/combats avec vrais monstres et quantités, drops de quêtes, captures, donjons, validations. On n'affiche **ni** la section `Quêtes liées à cette fiche`, **ni** de bloc local `À préparer`/pré-requis (le parcours suit l'ordre calculé), **ni** la section `Sources`/liens externes, **ni** de panneau spécial déplacement. Les sources demeurent dans les données internes pour traçabilité et audits. Les dépendances bloquantes restent contrôlées par le moteur et ne doivent jamais entraîner une action impossible.
- Rien d'inutile : pas de colonne `Étapes précédentes`, `À suivre`, `Destination suivante`, pas de doublons PNJ/combats, pas de validations intempestives.

## Personnages (Organizer)
- Petit bouton Personnages près de Sommaire ; **ancien déroulant compact**, masqué par défaut, avec **une rangée de petites vraies icônes de classe** existantes (pas de grosse liste de cases).
- Anneau circulaire = progression, état inconnu distinct de 0 %, infobulle survol : nom du personnage, classe, avancement fiable, réseau / manuel / inconnu. Un clic sur le portrait sélectionne/désélectionne ce personnage comme participant au guide. Icônes cohérentes lors d'une reconnexion ou permutation de slots. Ne jamais confondre classe commune et identité individuelle.
- La sélection des participants est conservée par identifiant stable, par guide, y compris hors ligne. Les nombres `ont déjà terminé le chapitre` et `ont déjà terminé le guide` peuvent être déclarés, mais doivent être distingués des validations individuelles constatées ; jamais transformer un compteur en preuve réseau.
- Progression guidée par personnage + contrôles réseau déjà en place ; ne pas certifier une action automatique sans événement probant. Réactualiser seulement les indicateurs concernés.

## Clic sur les coordonnées — AUCUN ajout visuel
- Le clic existant sur `[x,y]` déclenche via Organizer une macro planifiée : `/travel x,y`, ou si l'optimiseur a décidé qu'un Zaap est utile et accessible, `/zaap zx,zy ; /travel x,y`.
- Le même visuel pour tous les cas ; **aucun encadré, icône Zaap, mention Zaap, bouton copier ou menu déroulant de trajet supplémentaire sur la fiche**. Le clic cible uniquement les personnages sélectionnés, actuellement identifiés et avec fenêtres Unity valides.
- Retour non bloquant en cas d'indisponibilité ; garder le clic droit / secours copier si nécessaire sans altérer le clic principal. UI ne décide jamais seule des zaaps.

## Tests de sortie
- Captures Doctor UI raster réellement lisibles, vérification visuelle boutons, infobulles, scroll, overlay, sommaire, fiche Lanyel et Succès ; aucune preuve carrée/placeholder acceptée.
- Personnages de classes identiques, 0/5 sélectionnés, reconnexion, permutation slots, un personnage hors ligne, deux quêtes communes.
- `50/150` => manque `100`, valeurs invalides, recharge application, quantité par type ; précédent/suivant/retour Home sans fuite Qt, une seule fiche active.
- Absence formelle de trois sections interdites et invariance du rendu des coordonnées.
- Checks CI ciblés, Doctor/Graphify/UI au HEAD exact puis certification avant fusion.
