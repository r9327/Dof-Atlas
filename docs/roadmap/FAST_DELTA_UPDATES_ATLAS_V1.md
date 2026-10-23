# DOFUS Atlas — mise à jour rapide (22/10/2026)

## Objectif
Réutiliser le protocole de publication/installation défini dans Holding, sans importer le moteur IA dans Atlas. Éliminer la vérification coûteuse de dizaines de milliers de fichiers à **chaque** démarrage (voir PR #228), sans sacrifier l'intégrité.

## Deux couches
1. **Application :** manifeste versionné, téléchargements différentiels optionnels, vérification cryptographique des fichiers *transférés*, staging hors version active, bascule et rollback.
2. **Données :** paquets distincts par ensemble (Quêtes, Succès, Guides, équipements) avec version/schema/IDs, remplacement atomique du paquet concerné seulement, contrôle des relations et prérequis.

## Contrats d'intégrité
- Démarrage courant : vérification légère de version/manifest local fiable, pas de hash exhaustif du dossier à chaque lancement.
- Réparation ou mise à jour : contrôle cryptographique renforcé des changements avec états persistés, audit intégral programmé/à la demande si nécessaire.
- Aucun téléchargement et aucune opération de masse bloquante sur thread UI.
- Séparer installation EXE, caches, fichiers utilisateur et progression (ne jamais effacer les favoris, personnages ni les données locales).
- Choix disque maintenu. Pas de remplacement de l'exécutable actif sans processus extérieur.
- Internet absent, manifest erroné, rollback, serveur répondant 200 à une requête Range et ancien schéma gérés explicitement.

## Tests et preuves
- Bench cold/hot et octets téléchargés sur Windows réel ; mesurer et publier les gains sans fabriquer de durée.
- Reprise après coupure, fichiers verrouillés et rollback de données + EXE.
- Test parcours Guides/Quêtes/Succès + favoris, cohérent avec PR #234, et ram/perf avec PR #233.
- Tests contre les conflits avec correctif launcher #228 et release en cours ; ne jamais remplacer ses protections.

## Dépendances
- Holding updater partagé (protocole), PR Atlas #228/#233/#234 ; pas de nouvelle dépendance IA runtime.
- Draft jusqu'au code, tests et preuve SHA final.
