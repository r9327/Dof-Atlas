# Atlas Launcher V2 — contrat de performance et livraison

État : spécification de travail, **pas une implémentation ni une certification**.

## Périmètre
Deux lots de développement séparables : (A) installation, mises à jour, launcher et continuité de fenêtre ; (B) démarrage de l'application, Home, preload et imports. Ne pas réécrire le moteur existant sans preuve. Conserver rollback, données utilisateur, propriétaire de domaine, tests et certification intelligente. Ne pas ajouter de mode hors ligne comme nouvelle fonctionnalité.

### A — Launcher professionnel
- Une seule fenêtre pendant vérification → téléchargement éventuel → installation → préparation → lancement. Ne fermer qu'après Home utilisable ; éviter un second splash/launcher visible.
- Logo, police Lexend si disponible, couleurs et composants cohérents avec le thème Unity Atlas ; repli sûr si police absente ; DPI 100/125/150 %.
- Dossier d'installation sélectionnable avant installation et modifiable proprement ; préserver données et état existants ; vérifier permissions et espace.
- Prérequis : inventorier ceux réellement requis par le packaging Windows, détecter leur présence et n'installer que ce qui manque. Ne pas installer arbitrairement Python/Qt si embarqués.
- Détecter une version identique sans réinstallation ni téléchargement. Manifeste versionné, SHA, cache validé persistant, invalidation sûre ; ne jamais omettre une vérification nécessaire à l'intégrité.
- Différentiel réel : fichiers inchangés réutilisés, pas de double extraction/copie/hash, téléchargement ciblé, vérification avant bascule atomique, parallélisme borné disque/réseau, rollback et récupération de corruption. Conserver les profils et la progression.
- Garder une UI minimaliste (logo, titre, barre de progression, état, réglage du dossier), sans menus superflus.

### B — Démarrage et preload
- Instrumenter horodatages : clic launcher, vérification, téléchargement, décompression, copie, validation, spawn process, imports Python/PySide6, création QApplication, Home visible, Home interactive, preload post-Home.
- Auditer imports coûteux, accès disque, JSON, images, création widgets, initialisations et doublons. Vérifier le mode de packaging Windows et le coût de l'antivirus avant de conclure.
- Initialiser seulement le chemin critique de Home ; Guides, Quêtes, Succès et autres modules lourds en lazy loading contrôlé. Préchargement adaptatif uniquement s'il ne dégrade ni Home interactive ni la RAM ; annulation et priorités.
- Pas de changement d'architecture non motivé ; corriger les causes vérifiées et préserver la navigation, les états et les données.

## Mesures et portes de validation
- Scénarios Windows réels : première installation, lancement sans changement, patch 1–3 fichiers, grosse mise à jour, reprise d'échec, corruption, migration du dossier, antivirus, DPI 100/125/150.
- Bench séparés : Home visible **et** Home utilisable ; temps par phase, octets téléchargés, octets copiés, nombre de fichiers hachés, CPU, I/O, RAM process-tree et RAM stabilisée après retour Home.
- Cibles initiales (à recalibrer sur machine de référence) : vérification locale <1 s ; lancement sans mise à jour 3–5 s ; Home <3 s après spawn ; patch léger <5 s hors réseau ; aucun octet inchangé téléchargé ; RAM Home <100 Mo, pic process-tree ≤250 Mo.
- Répétitions, médiane et dispersion ; comparer au baseline sur même machine et même cache. Détecter régression >5 % seulement si statistiquement significative, sans masquer les checks de sécurité.
- Tests unitaires ciblés + intégration launcher/install + build Windows complet exact SHA + Atlas Delivery Guard, Phase Certification, Public PR / Safe Validation, Certification Policy / Merge Gate. Audit de chaque commit puis audit global.
- Rapports reproductibles dans la PR avec mesures avant/après et logs anonymisés ; maintenir .ai/context_index.json et rapport HEAD si les règles du dépôt l'exigent.
- Aucun asset DOFUS extrait redistribué. Validation humaine Windows/launcher/image avant Release stable. Synchronisation DEV→APP uniquement après certification ; ne jamais fermer la PR APP permanente #4.

## Ordre de travail
1. Capturer baseline et reproduire les lenteurs ; identifier causes racines.
2. Corriger le chemin critique et les doubles traitements mesurés, avec tests.
3. Unifier la fenêtre et l'UI sans régression du mécanisme de mise à jour.
4. Mesurer les gains, certifier SHA exact, puis organiser la validation Windows et la livraison APP.

**Ce document n'affirme aucun gain de performance ni correction livrée.**
