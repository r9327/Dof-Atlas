# PR 1 — Réparations Guide Succès + Lanyel Sylvestre

**Statut : cadrage à implémenter — aucun correctif de code n'est encore intégré.**  
**Base :** `main` @ `b8d63e03711c65e5db85c72a5ab64378f5264713` (constat du 16 octobre 2026).  
**Périmètre strict :** anomalies et régressions des guides existants ; **aucune nouvelle fonctionnalité ou refonte visuelle**.

## Constats à reproduire avant de modifier

Captures fournies le 16/10/2026 (ne pas supposer que leur binaire correspond au HEAD courant) :
- **Guide Succès, page 1/267 :** panneau `À FAIRE MAINTENANT` affiché deux fois sur l'une des captures, dont un exemplaire étroit sous la carte principale ; une autre capture de la même page n'affiche pas ce doublon. Anomalie possiblement intermittente.
- **Lanyel Sylvestre, page 8/1672 :** des lignes sur Ganymède / le livre du temple restent visibles hors de la carte active `Fécaline la Sage`. Déterminer si c'est un reliquat d'une ancienne page, un double montage de widgets ou une donnée composée incorrectement.
- **Guide Succès, page 3/267 :** consignes de ressources potentiellement répétées entre `À PRÉPARER` et `À FAIRE MAINTENANT` ; distinguer **redite injustifiée** d'une action réellement nécessaire à deux moments différents.
- Certaines formulations sont anormales (ex. `la quête la quête en cours`) : remonter à la source de composition ; ne pas corriger à l'aveugle dans le widget.
- Cases de suivi parfois ambiguës et multiples sur une ligne ; contrôler le rattachement objectif/preuve/validation, y compris combats requis.
- `Déverrouillé` accompagné visuellement d'un cadenas fermé : vérifier la cohérence du statut et de l'icône, sans changer la politique de verrouillage.

**Important :** un défaut apparent sur capture ne constitue pas à lui seul une preuve de cause. Vérifier les données et le code en production au SHA exact.

## Code et contrats existants à préserver

- Rendu partagé canonique : `app/modules/encyclopedia/views/shared_manual_guide_view.py` (`SharedGuideManualView`, `SharedGuideManualCard`).
- Routeur : `app/modules/encyclopedia/views/manual_route_guides_view.py`.
- Services : `GuideUltimeManualRuntimeService` et `GuideCatalogManualRuntimeService` ; méthode `manual_sections_for_card`.
- Contrat : **Lanyel et Guide Succès gardent le même moteur de rendu, pas de classe UI spécifique Lanyel**.
- Préserver la légende page 1, les six sections existantes, les liens PNJ/coordonnées/quêtes, cases, combats, progression persistante, validation auto/manuelle, navigation, verrouillage et données existantes.
- Examiner la logique `_without_prepare_duplicates` déjà présente : ne pas dupliquer un dédoublonnage qui existe ; distinguer doublons de texte, d'actions et de widgets.

## Ordre d'exécution pour Codex

1. Confirmer le HEAD réel (`git rev-parse HEAD`, `git status --short`) et comparer aux preuves capturées ; démarrer par les règles `AGENTS.md`, `AI_CONTEXT.md`, `DEVELOPMENT_GUARDRAILS.md` et les outils Doctor/Graphify requis par le dépôt.
2. Reproduire pages 1/267, 3/267 et 8/1672, avec aller/retour de pages, changement Lanyel ↔ Succès, ouverture/fermeture, restauration des états, redimensionnement et scroll ; journaliser le nombre de widgets actifs et les sections/rows reçues.
3. Isoler **où naît chaque duplication** : catalogue/route, `manual_sections_for_card`, normalisation, montage `SharedGuideManualCard`, remplacement ou libération des widgets de `_render_window`, rafraîchissement différé/Qt. Vérifier aussi les connecteurs de signal/slot, cache, lazy rendering. Ne pas supposer qu'un CSS `display:none` ou qu'un `clear` opportuniste résout le problème.
4. Corriger **à la source**, avec le changement minimal. Rendre le montage idempotent et ne jamais afficher de section issue de la page précédente. Préserver les vraies répétitions utiles (une ressource à préparer puis une étape à exécuter).
5. Corriger les phrases réellement mal générées et les états de validation/icônes **uniquement si le défaut est confirmé**.
6. Réaliser des régressions automatisées ciblées et un contrôle visuel de l'application Windows si l'environnement le permet. Si non, expliciter ce qui reste non testé.

## Critères d'acceptation (tous à satisfaire avant fusion)

- [ ] Même page reconstruite/réaffichée **une seule fois** : une seule feuille active et pas de panneaux fantômes, y compris en revenant de Lanyel vers Succès.
- [ ] Aucun texte de page N-1 dans N, notamment exemple Ganymède → Fécaline de Lanyel.
- [ ] Chaque section attendue existe une fois, les lignes sont rattachées à la bonne page et les doublons inutiles sont supprimés sans effacer les instructions voulues.
- [ ] Case(s) de validation et combats toujours reliés au bon objectif ; progression inchangée lors des allers-retours.
- [ ] Fonctionnement inchangé pour liens cliquables, coordonnées, `À préparer`, validation automatique/manuelle, boutons Précédent/Valider/Suivant et statuts de verrouillage.
- [ ] Tests ciblés verts : `tests/test_lanyel_shared_manual_ui.py`, `tests/test_shared_guide_single_renderer_contract.py`, `tests/test_shared_guide_visual_flow_contract.py`, `tests/test_guide_manual_long_layout.py`, plus nouveaux tests de non-duplication/idempotence, navigation et libération des widgets.
- [ ] Doctor/Graphify et CI ciblées liées au SHA candidat ; aucune certification déclarée sur la base d'une ancienne preuve.
- [ ] Pas de nouvelle interface, restructuration de JSON, changement de route ou refactorisation non justifiée.

## Contexte / limites

PR de cadrage préparée à la demande du propriétaire, **pas une réparation déjà effectuée**. Les preuves sont les cinq captures partagées dans la conversation du 16 octobre ; ne pas inventer d'URL GitHub pour ces images. Le développement reste à réaliser sur cette branche et la PR doit rester en brouillon jusque-là.

## Complément de périmètre — inspection UI et preuves de non-régression (16/10)

Cette section complète les corrections précédentes ; elle ne transforme pas cette PR en projet d'outillage Doctor général. L'outillage réutilisable est spécifié dans une **PR Doctor UI séparée**, et le correctif doit rester livrable avec les tests Qt ciblés existants si cet outillage n'est pas encore fusionné.

### Points manquants à vérifier

1. **Faire la différence entre nombre déclaré et réalité Qt.** `rendered_card_count == 1` est fixé par le code, il ne prouve pas qu'il n'existe pas d'autres `GuideManualSheet` encore visibles, détachées ou en attente de `deleteLater()`. Compter les vrais `QWidget` visibles, parents, références et entrées de layout ; examiner les créations/destructions et traiter les événements différés. Les erreurs peuvent être un résidu du rendu précédent **ou** une seconde feuille incluse par l'arborescence/layout : tester les deux.
2. **Distinguer 3 niveaux de redondance** : (a) même QWidget/section rendu deux fois, (b) même ligne matérialisée deux fois dans la même section, (c) consigne sémantiquement similaire présente dans `prepare`, `now` ou `keep` mais justifiée par deux moments différents. Ne dédupliquer que les véritables doublons en préservant quantités, ressources, ordre et validation.
3. **Pages et versions des données** : retrouver l'étape par identité canonique (guide/stage/route) et conserver l'index/capture à titre de repère ; ne pas appliquer une correction spécifique aux index 1, 3 ou 8 si le catalogue évolue. Vérifier le `card`/sections/clé de progression de la version exécutée et de l'EXE réellement capturé.
4. **Résilience du cycle de vie** : répétitions `_render_window`, `_follow_active_after_progress_change`, changement de personnage/guide, signal Qt tardif, retour Home puis réouverture, navigation rapide avant libération différée, scroll et redimensionnement ; absence de fuite de widgets et de progression corrompue.
5. **États et associations sémantiques** : chaque bouton/case correspond à une action unique, état visuel et état réel concordent ; liens PNJ/quête/objet et commande `/travel` restent fonctionnels ; combats requis associés aux bonnes quêtes ; absence de validation automatique abusive ou de perte de l'état manuel.
6. **Présentations et géométries** : pas de panneau rémanent sous le conteneur principal, de section en demi-largeur imprévue, de débordement horizontal, de chevauchement entre actions et cases, de boutons masqués sur les pages longues. Comparer au moins deux tailles de fenêtre et vérifier l'accessibilité de navigation et de validation après scroll. Ne pas réaliser de refonte visuelle dans cette PR.
7. **Phrases fautives** : isoler le texte fourni par les données du texte composé par le moteur ; corriger les fautes systématiques à la source sans réécrire les étapes de jeu.

### Vérifications automatisées et preuves obligatoires

- Ajouter un scénario de tests PySide6 sur le **vrai moteur partagé** (pas un QWidget factice) avec services/fixtures isolés, sans toucher au profil ni à la progression utilisateur.
- Tester explicitement Guide Succès première carte, carte avec nombreuses ressources, et Lanyel transition vers Fécaline : séquences `render → page suivante → précédente → autre guide → retour → refresh × N`.
- Mesurer pour chaque point : identifiant de carte attendue, nombre de feuilles, sections, widgets visibles, parent et géométrie, chaînes visibles, état/cible des checkboxes et boutons ; tester aussi après `processEvents()` et `DeferredDelete`.
- Ajouter assertions de non-contamination entre pages, idempotence du rendu et stabilité de la progression persistée après changement/rechargement ; s'assurer que les tests **échouent avant** correction sur un cas qui reproduit réellement la défaillance. Si la reproduction n'est pas obtenue, le signaler et garder un test préventif explicite.
- Produire un paquet de preuves **avant/après** : captures PNG réelles et structure Qt JSON quand un environnement Qt permet de le faire, résolution et version PySide6/Qt indiquées, SHA exact, capture des pages courtes et longues. Le mode offscreen est un contrôle Qt réel **mais ne remplace pas un contrôle desktop Windows du binaire installé** ; qualifier distinctement chaque niveau de preuve.
- Ne pas confondre un rendu PNG avec un scénario utilisateur vérifié : confirmer les changements de pages, clics, callbacks, états et persistance par assertions comportementales.
- Exécuter au minimum les tests de la checklist principale ainsi que `tests/test_guide_ultime_manual_ui_navigation.py` et les contrôles `tests/test_atlas_doctor_capture_ui.py` si le scénario Doctor est utilisé. Aucun FULL ou benchmark lourd systématique hors exigence du routage CI et de la politique de certification.
- Documenter les constats `CONFIRMED`, `NOT_REPRODUCED` ou `BLOCKED`, avec lien à la preuve ; ne jamais interpréter une trace statique Graphify comme une capture visuelle.

### Hors périmètre explicite

Pas de nouvelle navigation par chapitre, de refonte de légende, de redesign, ni de nouveau moteur de vues dans cette PR. La PR #202 demeure **sans spécification**. Ne pas rendre les réparations dépendantes d'un futur outil Doctor si les tests Qt ciblés suffisent à confirmer le correctif.
