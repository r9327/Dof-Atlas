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

## Processus de livraison
- [ ] Cette PR est ouverte en brouillon pour CADRAGE : ce commit ne contient aucun correctif applicatif et ne doit pas être fusionné seul.
- [ ] Développer les PR dans l'ordre des dépendances, UNE SEULE à la fois. Avant chaque lot, repartir de main actualisé, vérifier HEAD et git status, ne pas intégrer la branche accidentelle non validée.
- [ ] Pas de FULL ni de certification répétée pendant les commits : seules les vérifications rapides et ciblées nécessaires au développement sont autorisées.
- [ ] Quand le lot entier fonctionne, passer Ready for review et déclencher la certification adaptative finale une seule fois, sur le SHA exact du candidat. Doctor ciblé, sécurité, Windows et mesures RAM selon l'impact.
- [ ] Un échec impose correction, nouvelles vérifications ciblées et certification finale actualisée ; ne jamais déclarer PASS une preuve ancienne ou non exécutée.
- [ ] Conserver les sauvegardes, les identités vérifiées, les interfaces Quêtes/Succès, le chargement paresseux et les données des étapes. Ne pas élargir le périmètre sans nécessité documentée.
- [ ] Certifier sur un vrai client Windows tout ce qui nécessite Npcap/Unity ou une capture UI réelle ; en absence de preuve, afficher BLOQUÉ plutôt qu'inventer un succès.
