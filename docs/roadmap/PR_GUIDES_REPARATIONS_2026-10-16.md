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
