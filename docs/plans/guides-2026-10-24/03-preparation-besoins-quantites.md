# [PLAN 03/07] Guides : Préparation, besoins réels et bouton Prêt

**STATUT : BROUILLON DE CADRAGE — aucune implémentation. NE PAS FUSIONNER CE COMMIT SEUL.**

Objectif : Exposer intégralement les préparatifs du guide, garantir les quantités et enregistrer Prêt indépendamment par personnage.

Base analysée : 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Diagnostic et causes
- [ ] La préparation actuelle retourne vide sans personnage sélectionné et le filtre Tout présente uniquement trois compteurs.
- [ ] Les besoins proviennent de a_preparer, profession_gates ou d'une regex limitée sur les textes, avec risque d'omission.
- [ ] La déduplication par carte et les pierres d'âme cachées du résumé peuvent sous-estimer les besoins.

## À réaliser intégralement
- [ ] Afficher sans sélection la préparation globale consultable sans prétendre connaître l'inventaire ou autoriser un état Prêt anonyme.
- [ ] Le filtre Tout doit présenter listes détaillées et sous-sections Métier / Potion / Objet / spécial, pas seulement des comptes.
- [ ] Lire l'intégralité des structures de préparation présentes dans les cartes/chapitres/manuels sans modifier le texte affiché des étapes.
- [ ] Différencier prérequis, objets à conserver, consommables, métiers, potions, pierres d'âme, clefs, besoins particuliers et actions à faire sur place.
- [ ] Identifier les ressources par ID lorsque disponible, sinon nom normalisé sûr ; distinguer répétition d'affichage vs consommations cumulées.
- [ ] Calculer les quantités réelles par personnage et à l'échelle du parcours restant ; ne pas multiplier des ressources réutilisables.
- [ ] Définir les états aucun besoin / aucune donnée fiable / aucun participant, éviter l'illusion d'une préparation à 100 % sans preuve.
- [ ] Bouton Prêt réellement opérationnel pour les participants concernés ; non mélange entre prêt pour tous et pour certains ; décochage et persistance après relancement.
- [ ] Synchroniser barre Préparation, filtres et agrégats à chaque modification de personnage ou de fiche ; limiter I/O et RAM, pas d'instanciation Qt de centaines de cartes.
- [ ] Ne pas inférer possession d'un item sur la seule base d'actions candidates Ganymède ou d'une source non vérifiée.

## Connexions et fichiers à protéger
- [ ] shared_manual_guide_view.py ; guide_ultime_manual_runtime_service.py et core ; guide_catalog_manual_runtime_service.py ; GuideProgressService.
- [ ] Sources Guide Succès, Sylvestre et préparations candidates Ganymède, filtres Qt et badges/progressions.

## Critères de réception et tests ciblés
- [ ] Affichage complet sans personnage ; cas 1/2/6 personnages à avancements différents ; quantités et pierres d'âme réellement exposées.
- [ ] Prêt individuel, collectif, annulation, retour sur filtre Tout, rechargement, version EXE ; pas de faux doublons ni données masquées.
- [ ] Tests ciblés des vrais besoins, lanyel_shared_manual_ui, guide_ultime_manual_ui_navigation, doctor_ui_qt, RAM et chronométrage ciblés.

## Compléments explicites — contenu et ergonomie
- [ ] Le bloc `À préparer` visible dans une fiche reste minimaliste et ne doit pas être dupliqué avec la Préparation générale ; pas de blocs redondants « sources », « succès liés » ou prérequis répétés dans cette PR.
- [ ] Préserver les **couleurs et distinctions par type** d'objet, potion, métier et ressource sans transformer un simple texte d'action en exigence d'inventaire.
- [ ] Le filtre `Tout` doit afficher **les pierres d'âme et leurs quantités** (aujourd'hui exclues des résumés), y compris après changements de participants.
- [ ] Assurer des infobulles/étiquettes de besoin compréhensibles, une vérification de l'item ID et un cumul de quantités explicable lorsqu'un objet est nécessaire à plusieurs fiches.
- [ ] La commande `Prêt` valide les objets pour **les personnages sélectionnés concernés uniquement**, sans marquer une fiche, une quête ou un succès terminé ; persistance distincte des données de progression Route.

## Modèle de besoins et matrice d'acceptation (préparation)

**Sources exactes inspectées :** `SharedGuideManualView._requirements_from_card` privilégie les objets `a_preparer`, puis seulement en absence de ceux-ci parcourt `manual_sections_for_card(...).prepare` via regex « quantité x texte » ; `profession_gates` est traité séparément. La présence d'un objet structuré peut donc masquer des besoins additionnels uniquement textuels. Ce point nécessite un contrat de fusion dédupliqué, **pas** un remplacement aveugle de l'une des deux sources.

**Modèle de données à spécifier lors de l'implémentation :** identité d'item si disponible, libellé, type, quantité par occurrence, unité/persistance (consommable vs réutilisable), source (chapitre/fiche/ligne), validité du rapprochement, participants associés, état `Prêt` pour chacun ; état `inconnu` conservé si la source ne permet pas de calculer la quantité. Ne pas déduire une ressource par simple présence dans `manual_resource_names`.

**Matrice concrète :**
- [ ] B1 : aucun personnage => lire tous les besoins exploitables, bouton Prêt personnel absent/désactivé, pas de `0/0 = 100 %`.
- [ ] B2 : besoin identique dans 3 lignes : une mention redondante + 2 consommations distinctes => compter les 2 consommations, sans les confondre avec le doublon.
- [ ] B3 : pierres d'âme, clés de donjon, potion, objet, métier et prérequis dur => visible avec type/couleur, y compris filtre Tout.
- [ ] B4 : fiches franchies puis retour arrière => la liste générale ne mélange pas « besoin de toute la route » et « reste à préparer » ; la portée est expliquée.
- [ ] B5 : A prêt, B non prêt => progression commune non complète ; permutation/déconnexion/restart ne change aucune marque d'un autre personnage.
- [ ] B6 : informations Ganymède non certifiées => texte de source lisible avec « quantité non vérifiée » sans impact sur les totaux numériques certifiés.
- [ ] B7 : changement de filtre et panneau refermé/ouvert => liste, état des boutons et pourcentages cohérents sans reconstruire tout le Guide en Qt.

**Recevabilité ciblée :** `test_guide_action_preparation_contract.py`, `test_guide_prerequisite_lookup.py`, `test_guide_continuous_preparation.py`, `test_guide_progress_persistence.py`, `test_doctor_ui_qt.py` ; s'assurer de couvrir les vrais contenus du manuel et pas uniquement des fixtures synthétiques.

## Processus de livraison
- [ ] Cette PR est ouverte en brouillon pour CADRAGE : ce commit ne contient aucun correctif applicatif et ne doit pas être fusionné seul.
- [ ] Développer les PR dans l'ordre des dépendances, UNE SEULE à la fois. Avant chaque lot, repartir de main actualisé, vérifier HEAD et git status, ne pas intégrer la branche accidentelle non validée.
- [ ] Pas de FULL ni de certification répétée pendant les commits : seules les vérifications rapides et ciblées nécessaires au développement sont autorisées.
- [ ] Quand le lot entier fonctionne, passer Ready for review et déclencher la certification adaptative finale une seule fois, sur le SHA exact du candidat. Doctor ciblé, sécurité, Windows et mesures RAM selon l'impact.
- [ ] Un échec impose correction, nouvelles vérifications ciblées et certification finale actualisée ; ne jamais déclarer PASS une preuve ancienne ou non exécutée.
- [ ] Conserver les sauvegardes, les identités vérifiées, les interfaces Quêtes/Succès, le chargement paresseux et les données des étapes. Ne pas élargir le périmètre sans nécessité documentée.
- [ ] Certifier sur un vrai client Windows tout ce qui nécessite Npcap/Unity ou une capture UI réelle ; en absence de preuve, afficher BLOQUÉ plutôt qu'inventer un succès.
