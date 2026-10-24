# [PLAN 07/07] Ganymède : parcours continus, intégration et activation contrôlée

> **DRAFT PLAN SEUL — aucune fonctionnalité implémentée. Ne jamais fusionner avant développement + CI finale.**

**Objectif :** Remplacer les itinéraires Atlas Dofus admissibles par les étapes continues Ganymède sans coexistence de deux routes, pertes de sauvegardes ou faux compléments automatiques.

**Révision auditée :** 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Pourquoi et état actuel
- [ ] Le catalogue Atlas contient 22 Dofus et 2 Alignements ; le manifeste contient 20 remplacements Dofus TRUSTED_SOURCE_STEPS activables seulement si le catalogue marque explicitement l'UI prête.
- [ ] Les entrées Ganymède du catalogue source sont metadata_only (95 références), aucune ne doit devenir jouable automatiquement.
- [ ] GuideProvider.select_verified_replacement_path impose un manifeste, un payload SHA-256, un ordre de pas signé, une preuve de complétude et un mode manuel sûr.
- [ ] Le lecteur ContinuousGuideRoutePanel existe déjà et diffère de SharedGuideManualView ; la sauvegarde multi-personnages est fournie par ContinuousGuideNavigation.

## Modifications exigées
- [ ] Cartographier et documenter les 20 remplacements Dofus par guide_id, source_guide_id, nombre de pas, champs requis, manifest, fingerprint et hash ; relever les Dofus sans correspondance et ne rien fabriquer pour Dofoozbz/Dokille.
- [ ] Préserver exactement l'ordre Ganymède des étapes ; désactiver l'ancienne route lorsque la nouvelle est sélectionnée, ne jamais afficher les deux parcours parallèlement.
- [ ] Adapter le lecteur continu aux composants et interactions Guides communs : fiche courante, consultation d'une autre fiche, Actuelle, Précédent/Suivant, Sommaire, Préparation, personnages, progression et boutons.
- [ ] Ne pas remplacer le Guide Succès optimisé par le parcours Ganymède brut : garder exclusivement les optimisations du Guide Succès dans son propre moteur ; Ganymède est source de parcours continus classiques.
- [ ] Préserver l'identité des étapes (source guide + rang) et le guide_id Atlas ; sauvegarde par character:<id>, validation manuelle et aucune complétion de quête/succès à partir de texte de source.
- [ ] Différencier une action candidate de source, une étape manuelle jouable et une action canonique réellement vérifiée ; aucune quantité, possession, déplacement ou objectif certifié inventé.
- [ ] Traiter les préparations Ganymède à partir des structures disponibles et des preuves de source, en indiquant clairement les inconnues ; garder le même cadre d'identité et de validation qu'en PR01/02/03.
- [ ] Tester planificateur de déplacements seulement avec projections vérifiées, sinon montrer la marche manuelle ; aucun /travel ou /zaap dangereux.
- [ ] Activer progressivement uniquement les guides complets dont les tests de parity source, manifeste, ordonnancement et UI sont verts ; modifier ganymede_manual_ui_ready guide par guide/groupe certifié.
- [ ] Pour Alignements Bonta/Brâkmar et les autres catégories : auditer les catégories et prérequis séparément, ne pas activer tant que la couverture et le rendu ne sont pas prouvés ; le catalogue les affiche selon leur statut réel.
- [ ] Préserver progression historique sous les anciens guides sans migration mensongère ; distinguer marques manuelles de nouvelles étapes, anciennes validations et quêtes réellement terminées.
- [ ] Prévoir rollback au guide ancien en cas de manifeste invalide sans effacer les nouvelles ou anciennes sauvegardes ; vérifier remplacement en EXE et données de distribution.
- [ ] Assurer lisibilité du texte, labels PNJ/monstre/donjon, positions, combats et durées sans importer du texte source incomplet ou de la prose non autorisée ; contrôle des 95 métadonnées séparé du statut jouable.
- [ ] Ne pas charger les 7705 étapes possibles au démarrage ; ne charger que le guide sélectionné et garder CPU/RAM dans les budgets existants.

## Connexions et surfaces concernées
- [ ] guide_ganymede_cutover.py ; guide_provider.py ; manual_route_guides_view.py ; guides_view.py ; guide_continuous_route_panel.py ; guide_continuous_navigation.py ; guide_continuous_preparation.py ; guide_library_sources.py.
- [ ] data/encyclopedia/guides/catalog.json ; replacement_drafts/cutovers/cutover_manifest.json et guide payloads, snapshots et source crosswalks ; états de progression et export runtime Windows.

## Critères d'acceptation
- [ ] Sur un guide certifié : nombre exact de pas et ordre source, aucune étape manquante, une seule route visible, navigation rapide et fiche actuelle cohérente après relancement.
- [ ] Sur un guide non certifié : aucun bouton jouable trompeur, retour de repli et ancienne progression intacte.
- [ ] Deux personnages valident des pas différents sans corruption ni auto-complétion de quêtes ; Ganymède source ne se confond pas avec Guide Succès Opti.
- [ ] Tests ganymede_* ciblés (manifest/fingerprint/actions/parity/prepa), guide_continuous_navigation, guide_continuous_route_panel, Doctor UI Windows, performance et packaging ; preuve par guide/groupe avant activation.
- [ ] La PR entière est considérée finie uniquement après identification claire des guides activés et de ceux restant bloqués ; ne jamais proclamer 95/95 jouables par le simple index.

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
