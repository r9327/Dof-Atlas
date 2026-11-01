# Organizer — Sélecteur radial de personnages (issue #320)

## Implémentation partielle
Le modèle pur `app/pages/organizer/radial_selection.py` et ses tests sont
développés. **Aucun menu n'est encore branché à l'application.** Cette PR reste
en Draft et ne doit pas être fusionnée comme fonctionnalité livrée.

## Comportement final demandé
- Une touche configurable **maintenue** affiche le camembert au curseur.
- Le mouvement sélectionne une part, le relâchement active la fenêtre visée.
- Relâchement au centre ou Escape : annulation, aucune activation.
- Slices dynamiques égales pour les seuls personnages **explicitement inclus
  dans Organizer**, présents, activés et identifiés; ni cases vides, ni auto-ajout
  de fenêtres seulement détectées; limite actuelle 8.
- Respecter l'ordre existant, utiliser les portraits/personnages et icônes de
  classe disponibles dans le dépôt avec fallback.
- Mettre à jour la liste en cas de fermeture/désactivation pendant le maintien.
- Conserver les raccourcis existants, le Stop d'urgence, la fenêtre favorite,
  le DPI multi-écrans et l'identité canonique des personnages.
- Aucun processus distinct, aucune duplication de `CharacterOrderService`.

## Intégration à développer avant Ready
1. Lire la carte Graphify correspondant au HEAD avant de toucher aux hooks/UI.
2. Prévoir une option explicite d'inclusion dans le camembert, distincte de
   la simple découverte automatique des sessions.
3. Brancher le cycle de vie du raccourci maintenu au runtime existant.
4. Construire le menu Qt avec composants/thème existants.
5. Tester hors écran, puis sur Windows réel avec #322 (RAD-005).
6. Compléter le contrat de livraison et certifier le SHA final.
