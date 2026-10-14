# [PLAN 02] Transactions anti-écrasement Guide/Succès/Zaap (AT-002/003/024)

> PLAN PRÉPARATOIRE — aucun correctif applicatif implémenté ici. PR DRAFT à compléter en code et tests ciblés avant revue/fusion.

Audit source : PR #160, SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`. Branche de base : `main` ; éviter de mélanger les modifications de PR #159 et #138.

## Objectif
Empêcher les snapshots obsolètes et les écritures de paramètres concurrents d’écraser des changements utilisateur.

## Dépendances et ordre
Après/avec plan 01 pour intégrer les nouvelles preuves de progression ; préalable à la finalisation EXE #159.

## Constat et preuves détaillées
### AT-002 — Guide save() écrase un changement publié par un autre processus
- Priorité / état : P1 / CONFIRMÉ / main.
- Localisation : app/modules/encyclopedia/services/guide_progress_service.py:145 GuideProgressService.save.
- Cause : Le verrou interprocessus sérialise l’écriture mais la validation de fraîcheur ne compare que generation, qui est locale au processus. Une écriture externe reste invisible à save() alors que _disk_signature existe déjà.
- Preuve audit : reproductions.json/external_snapshot_guide : parent chargé vide, enfant utilisant le vrai setter enregistre une étape, parent save() remet characters à {}. Aucun conflit de verrou ni JSON invalide : perte logique du changement externe.
- Correction du registre : Sous le verrou, vérifier aussi la signature disque avant toute écriture de snapshot ; refuser et recharger le snapshot obsolète. Continuer à utiliser les setters ciblés pour les mutations ; ne pas fusionner aveuglément deux arbres complets.

### AT-003 — Succès save() présente le même conflit interprocessus
- Priorité / état : P1 / CONFIRMÉ / main.
- Localisation : app/modules/encyclopedia/services/serialized_achievement_progress_service.py:168 AchievementProgressService.save.
- Cause : Le service coordonné compare uniquement la génération locale avant de publier le snapshot ; le verrou ne constitue pas une détection de modification antérieure par un autre processus.
- Preuve audit : reproductions.json/external_snapshot_achievement : un succès écrit par le setter enfant disparaît après save parent. La perte de snapshot est prouvée ; une fréquence de perte en session normale n’est pas mesurée.
- Correction du registre : Même garde disque sous verrou que AT-002. Examiner aussi sync_from_quest_progress : sa lecture à génération locale ne suffit pas à certifier la fraîcheur face à un écrivain externe. Conserver l’optimisation des lectures chaudes, faire le refresh au point de transaction.

### AT-024 — Favoris et calibration Zaap peuvent écraser leurs modifications
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/storage.py:579 save_zaap_favorites; app/storage.py:592 save_zaap_button_ratios.
- Cause : Ces deux fonctions relisent puis réécrivent le même document sans transaction coordonnée ; l’atomicité du replace ne protège pas le read-modify-write. Les événements Qt normaux sont séquentiels : une collision en session ordinaire n’est pas mesurée.
- Preuve audit : reproductions.json/zaap_interleaved_writes : une calibration 0.7/0.8 effectuée entre lecture et sauvegarde des favoris revient à 0.1/0.2. Interleaving déterministe isolé, pas un signal de fréquence en production.
- Correction du registre : Réutiliser coordinator_for(path).lock, recharger sous verrou et ne muter que le champ attendu avant write atomique/generation. Conserver les paths injectables et les frontières de compatibilité.

## Implémentation attendue
1. Sous coordinator_for(path).lock, comparer signature disque et génération au moment de publier un snapshot ; refuser/recharger les snapshots obsolètes.
2. Préserver les setters ciblés, l’écriture atomique et la règle identité personnage ; distinguer progression manuelle et dérivée.
3. Adapter GuideProgressService.save, Serialized AchievementProgressService.save et synchronisation Quêtes→Succès sans relire le JSON à chaque consultation.
4. Zaap : recharger sous verrou puis muter seulement favoris ou ratios, pas tout le document.
5. Ne pas fusionner aveuglément deux snapshots ni masquer une corruption/version inconnue.

## Validations ciblées
- [ ] tests.test_guide_progress_persistence
- [ ] tests.test_progress_concurrent_instances
- [ ] tests.test_network_character_id_progress_storage
- [ ] tests ciblés storage/Zaap et scénario 2 processus

## Critères de sortie
- [ ] Deux processus concurrents ne perdent aucune validation.
- [ ] save obsolète échoue explicitement sans effacer la modification externe.
- [ ] Suppression externe d’un personnage non ressuscitée.
- [ ] Favoris et ratios Zaap se composent avec écriture intercalée.
- [ ] Lecture chaude et frontières lazy conservées.

## Garde-fous communs
- Conserver toutes les fonctionnalités, les sources JSON et le comportement lazy sauf correction justifiée.
- Vérifier HEAD réel, git status et diff avant de coder. Aucun refactor de masse fondé sur le seul degré Graphify.
- Faire tests ciblés pendant le développement ; FULL uniquement à la certification si la policy l'exige.
- Recouper les observations avec les preuves de PR #160 ; distinguer CONFIRMÉ, PROBABLE, NON CONFIRMÉ.
- Mettre à jour AI Context avec son générateur après code, puis preuve exacte-SHA.
- Pas de merge automatique de cette PR préparatoire.

Sources : [rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) ; [registre anomalies](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
