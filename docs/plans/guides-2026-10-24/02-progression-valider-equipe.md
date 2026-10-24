# [PLAN 02/07] Guides : Valider et progression multi-personnages

**STATUT : BROUILLON DE CADRAGE — aucune implémentation. NE PAS FUSIONNER CE COMMIT SEUL.**

Objectif : Rendre Valider et la progression réellement corrects par personne et par équipe, sans perdre d'historique.

Base analysée : 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Diagnostic et causes
- [ ] Le bouton actuel appelle set_page_checked sur self.character_key tandis que l'en-tête suit une sélection de plusieurs personnages.
- [ ] Le progrès de groupe prend le minimum des nombres terminés, pas l'intersection effective des fiches communes.
- [ ] GuideProgressService possède déjà une API de validation multi-personnages atomique, utilisée par le navigateur Ganymède.

## À réaliser intégralement
- [ ] Unifier la politique du clic Valider : destinataires = identités vérifiées explicitement sélectionnées ; état sans sélection clair et non ambigu.
- [ ] Recalculer chaque validation (état/activé/désactivé) lorsque sélection, personnage global, progression réseau ou fiche changent ; ne pas conserver de widget périmé.
- [ ] Différencier fiche affichée, fiche actuelle de l'équipe, état manuel et état auto ; navigation historique et Actuelle ne valident jamais par inadvertance.
- [ ] Définir et implémenter le progrès commun comme intersection des fiches réellement complétées, sans confondre avec minimum de comptage ; portraits individuels exacts.
- [ ] Conserver les pourcentages Route / Préparation / Succès et cercle cohérents, montrer données manquantes distinctes de 0 %, tester révisions externes.
- [ ] Validation multi identités atomique au SHA/état de fichier récent ; jamais toucher une personne non sélectionnée, non connue ou à clé de progression non canonique.
- [ ] Décoche possible pour le manuel seulement ; respect des blocs d'ordres/alignement et des validations automatiques sur preuves de quête/succès.
- [ ] Conserver la migration paresseuse des anciennes clés de fiche GPS vers identifiants stables ; vérifier idempotence, sauvegarde avant migration, rollback et anciennes sauvegardes.
- [ ] Persistance après fermeture/réouverture, changement de guide, refresh externe et lancement Windows ; aucune confusion des ID Guide Succès, Sylvestre et Ganymède.
- [ ] Corriger/étendre les tests Qt réels de clic sur Valider, remplacement de widget, écriture disque, actualisation barres et absence d'attribution au mauvais personnage.

## Connexions et fichiers à protéger
- [ ] SharedGuideManualView/Card ; GuideUltimeManualView/Card ; GuideUltimeGenerated/ManualRuntimeService ; GuideProgressService ; GuideParticipantService ; ContinuousGuideNavigation.
- [ ] Quêtes/Succès réseau, caches, mises à jour externes, migration ancienne page:gps et stockage guide_progress.

## Critères de réception et tests ciblés
- [ ] A et B ont cinq fiches différentes : progression commune ne doit PAS afficher faussement 5 fiches communes.
- [ ] Valider pour A, puis A+B, puis annuler pour B ; C hors sélection inchangé, auto-validé non supprimé ; cohérent après restart.
- [ ] Tests guide_progress_persistence, guide_ultime_manual_ui_navigation, doctor_ui_qt, progress_concurrent_instances, character_identity_guardrails.
- [ ] Doctor vrai clic et persistance, aucun faux PASS avec faux service set_page_checked sans sauvegarde.

## Compléments explicites — invariants fonctionnels
- [ ] Clic sur Valider / annulation : comportement déterministe pour les mélanges de fiches déjà validées, automatiques, non validées et fiches bloquées parmi plusieurs personnages. Ne jamais utiliser un seul booléen d'équipe pour écraser les résultats individuels.
- [ ] Vérifier les transitions de personnage **sans rechargement du Guide** : portrait coché/décoché, personnage courant global modifié, onglet quitté puis réouvert, identité devenue hors ligne, évènement réseau concurrent. État du bouton et textes doivent suivre les bons destinataires.
- [ ] État Route à 100 % : `Actuelle` et bouton Valider doivent afficher le bon statut de fin, sans renvoyer arbitrairement à la dernière fiche comme si elle était encore à faire.
- [ ] Le résultat de `route_sheet_progress`, les caches manuels et les mises à jour Quêtes/Succès doivent rester cohérents après les migrations paresseuses de clés ; aucun write-on-read inattendu ne doit perdre une modification récente.
- [ ] Tester annulation manuelle après auto-validation et rechargement : la preuve de quête/succès est toujours autoritaire ; seule la marque manuelle associée peut être modifiée.

## Contrat exact des états de progression (préparation)

**Sources et divergences :** `SharedGuideManualView._progress_participant_keys` se rabat actuellement sur `self.character_key` si la sélection est vide ; `GuideParticipantService.selected_keys` vérifie seulement le format canonique, pas l'appartenance au registre courant. `SharedGuideManualView._actual_index_for_participants` prend le plus petit premier index incomplet. `GuideUltimeGeneratedService.first_incomplete_index` renvoie le **dernier index même si tout est terminé** ; à distinguer explicitement du statut `ALL_COMPLETE` que gère `ContinuousGuideNavigation`.

**Table de vérité obligatoire à figer avant codage :**
- [ ] P1 : sélection vide / identité globale existante => aucune validation implicite, statut « sélectionner des personnages » ; consultation libre et progression personnelle affichée seulement avec indication claire de son référent.
- [ ] P2 : A a fini fiches 1–5, B a fini fiches 6–10 => avancement commun 0/10, pas 5/10 ; anneau d'équipe et portraits individuels concordants.
- [ ] P3 : A a déjà la preuve automatique d'une fiche, B ne l'a pas => interface décrit la différence et n'écrit **que** la validation manuelle pertinente si autorisée.
- [ ] P4 : fiche courante de chaque personnage et fiche consultée distinctes ; ouvrir fiche passée/aller à l'actuelle ne provoque pas de validation accidentelle.
- [ ] P5 : toutes les fiches terminées => état de fin explicite, pas de « première fiche à faire » artificielle, navigation historique toujours accessible.
- [ ] P6 : ajout/retrait de B alors que la fiche est à l'écran => action Valider régénérée pour les nouveaux destinataires avant tout clic.
- [ ] P7 : interruption après sauvegarde / deux instances / migration ancienne clé => état durable et idempotent, aucun mélange entre `guide_complet`, `catalog_manual:dofus_sylvestre` et Ganymède.

**Frontières :** définition de la barre Route = fiches validées avec preuve ou check individuel ; barre Préparation = besoins `Prêt` documentés dans PR #251 ; barre Succès = preuves de succès certifiées. **Ne pas faire passer un clic manuel pour un succès automatique.** Réutiliser les opérations de batch atomique vérifiées de `GuideProgressService` sans convertir des ID historiquement indépendants.

**Jeux de tests futurs :** `test_guide_progress_persistence.py`, `test_guide_progress_batching.py`, `test_guide_progress_manual_cache.py`, `test_guide_continuous_navigation.py`, `test_guide_ultime_manual_ui_navigation.py`, `test_doctor_ui_qt.py`. Tester de vrais signaux/clics Qt avec JSON avant/après, en plus des contrats de service.

## Processus de livraison
- [ ] Cette PR est ouverte en brouillon pour CADRAGE : ce commit ne contient aucun correctif applicatif et ne doit pas être fusionné seul.
- [ ] Développer les PR dans l'ordre des dépendances, UNE SEULE à la fois. Avant chaque lot, repartir de main actualisé, vérifier HEAD et git status, ne pas intégrer la branche accidentelle non validée.
- [ ] Pas de FULL ni de certification répétée pendant les commits : seules les vérifications rapides et ciblées nécessaires au développement sont autorisées.
- [ ] Quand le lot entier fonctionne, passer Ready for review et déclencher la certification adaptative finale une seule fois, sur le SHA exact du candidat. Doctor ciblé, sécurité, Windows et mesures RAM selon l'impact.
- [ ] Un échec impose correction, nouvelles vérifications ciblées et certification finale actualisée ; ne jamais déclarer PASS une preuve ancienne ou non exécutée.
- [ ] Conserver les sauvegardes, les identités vérifiées, les interfaces Quêtes/Succès, le chargement paresseux et les données des étapes. Ne pas élargir le périmètre sans nécessité documentée.
- [ ] Certifier sur un vrai client Windows tout ce qui nécessite Npcap/Unity ou une capture UI réelle ; en absence de preuve, afficher BLOQUÉ plutôt qu'inventer un succès.
