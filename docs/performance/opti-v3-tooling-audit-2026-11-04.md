# DOFUS ATLAS — Opti V3 : audit transversal des outils IA/OSS et des limites de charge
_Date : 2026-11-04 — complément du contrat [#366](https://github.com/r9327/Dof-Atlas/issues/366) et du plan [Opti V3](opti-v3-global-2026-11-04.md)._

> **AUDIT STATIQUE / NOT_RUN** : revue de sources et de contrat uniquement ; aucune installation, invocation de modèle, exécution Windows ou certification Doctor ne peut être inférée de ce fichier. Cet audit du 4 novembre ne modifiait pas les 43 exigences de #366. La révision approuvée du 9 novembre précise leurs critères dans le [plan canonique](opti-v3-global-2026-11-04.md#compléments-approuvés-le-9-novembre--critères-concrets-dans-les-12-lots), en conservant les IDs et types.

## Règle centrale

DOFUS ATLAS est un logiciel **Windows local PySide6/SQLite/Qt** ; il doit utiliser ses propriétaires actuels `Atlas Doctor`, `Graphify`, `Atlas Integrity`, `AI_ENTRYPOINT.md`, `AGENTS.md`, `PERFORMANCE_GUARDRAILS.md` et `tools.tool_catalog` plutôt qu'ajouter en bloc des dépendances web ou d'orchestration IA. **L'optimisation principale est le code, la mémoire, les caches, le dessin Qt et la navigation réelle, pas l'ajout de services.**

## Audit des outils et pertinence

| Outil / concept | État constaté ou limite de vérification | Décision pour Opti V3 Atlas | Propriétaire |
| --- | --- | --- | --- |
| **Ponytail** | Adaptation locale **déjà présente** : `tools/ponytail_policy.json` (advisory), `tools/atlas_doctor_lib/ponytail.py`, commande `tools.atlas_doctor ponytail --json`. L'installation du projet externe Ponytail n'est pas démontrée ; l'exécution Doctor sur ce HEAD est **NOT_RUN**. | **REUSE_EXISTING** : vérifier la liaison réelle et le taux de faux positifs. Aucun second moteur ; les conseils de simplification ne peuvent affaiblir tests, permissions, données ni certification. | Doctor, `tools/AGENTS.md` |
| **Addy Osmani Agent Skills** | Pack externe **24 skills de cycle de développement + un méta-skill**, non démontré comme installé dans Atlas. Atlas possède déjà des skills spécialisés, `tools/skills/dofus-atlas-tools/SKILL.md` et des garde-fous propres. | Sélectionner les pratiques manquantes (performance, qualité/review, debug, travail fondé sur sources, contexte) **en évitant de copier les 25 fichiers** ou créer une seconde politique. Vérifier les réels bénéfices/tests. | Skills canoniques et Doctor |
| **OmniRoute** | Gateway/proxy local pour gérer plusieurs modèles/fournisseurs ; intégration non démontrée. Ce n'est pas un profiler CPU/RAM/Qt. | **NOT_APPLICABLE au runtime Atlas** ; évaluer côté [Holding Opti V3 #63](https://github.com/r9327/Atlas-Holding/pull/63), pas ajouter un daemon réseau à l'EXE. | Holding |
| **Perplexity** | Service de recherche IA externe ; aucune intégration runtime Atlas démontrée. | **NOT_APPLICABLE à l'optimisation desktop** ; option éventuelle de recherche documentaire chez Holding sous permissions/quota, sans données utilisateur envoyées. | Holding |
| **PostHog** | Plateforme d'analyse des événements ; aucune intégration constatée dans Atlas. SDK Python possible, mais le suivi des interactions Qt nécessiterait une instrumentation explicite. | **PAS d'activation automatique ni collecte silencieuse**. Préférer logs Doctor locaux anonymisés et éventuellement export volontaire pour les performances PC réelles. Si un service distant est un jour autorisé : opt-in, échantillonnage, rétention, anonymisation et coûts validés. | Doctor, produit |
| **Playwright** | Automatisation Chromium/Firefox/WebKit ; aucune intégration Qt native retrouvée. | **NOT_APPLICABLE aux widgets PySide6**. Préférer `pytest-qt`, `pywinauto`, probes Doctor et recette Windows visuelle ; Playwright uniquement pour une vraie surface web identifiée, hors runtime EXE. | Doctor QA/UI |
| **Agent harness** | Harness conceptuel **partiellement intégré pour le développement** via `AGENTS.md`, `AI_ENTRYPOINT.md`, Doctor `agent plan/check/validate`, Graphify, règles de PR/CI et skills. Ce n'est pas une boucle autonome complète pour tous usages. | **REUSE_EXISTING** : renforcer les tests de garde-fous et l'effectivité de la consommation d'outils ; ne pas ajouter de seconde orchestration du runtime. La suite d'orchestration LLM appartient à Holding. | Atlas Doctor / Holding |
| **Harness.io** | Plateforme commerciale CI/CD différente d'un agent harness ; aucune intégration utile démontrée. | **REJECT par défaut** : doublon probable GitHub Actions + Doctor + certifications existantes. Ne pas migrer CI sans besoin et gain prouvés. | GitHub CI |
| **llmfit et nouveaux fournisseurs API** | Aucun rapport direct avec la perf Qt. llmfit fait l'objet d'une [PR Holding #61](https://github.com/r9327/Atlas-Holding/pull/61) distincte. | **HORS PÉRIMÈTRE ATLAS** ; conserver Ollama/local-first dans Holding et les APIs cloud éventuelles désactivées jusqu'à accord. | Holding |

**Sources et références à relire avant toute adoption** :
- https://github.com/DietrichGebert/ponytail
- https://github.com/addyosmani/agent-skills
- https://github.com/cheaper-inference/OmniRoute
- https://playwright.dev/python/docs/intro
- https://posthog.com/docs/libraries/python
- https://www.perplexity.ai
- https://www.harness.io

**Important :** une référence GitHub ou une entrée dans un catalogue ne prouve ni installation, ni succès d'une commande, ni un benchmark réel. Sous `AI_ENTRYPOINT.md` les scanners OSS autorisés ne sont lancés que lorsqu'ils sont installés et que leur chemin d'exécution a été réellement suivi ; `NOT_AVAILABLE` ne vaut pas PASS.

## Lacunes de couverture à ne pas oublier

Les règles de performance source sont déjà toutes dans le plan Opti V3, avec réconciliation des **31 règles web**, **36 OPT** historiques et **50 RAM**. Les points ci-dessous précisent les preuves attendues sur les exigences OPTV-032, OPTV-036, OPTV-037, OPTV-038, OPTV-039, OPTV-040 et OPTV-041 **sans ajout silencieux au contrat fixe**.

### Backpressure, concurrence et annulation

- Une recherche répétée, une série de clics ou un préload simultané ne doivent pas empiler de jobs inutiles ou de résultats périmés ; contrôler limite de queue/threads, generation IDs, annulation, signal/slot et widget détruit.
- CPU, RSS arbre de processus, cache, objets Qt vivants et p95/p99 avant/après, sur mêmes scénarios. Pas de double travail en arrière-plan qui fait paraître l'UI plus rapide en dégradant Home.
- Aucun thread de calcul/IO ne doit construire ou modifier des `QWidget` hors thread UI.

### Navigation et charge prolongée

- Quêtes, Succès, Guide et Map sous grands catalogues, séquences de retours Home **10/20/50 cycles**, premières ouvertures froides et caches chauds, sauts profonds, fermetures pendant un chargement.
- Mesurer temps clic→premier **contenu complet utile** plutôt que seulement une fenêtre peinte. Conserver les fonctions de progression, textes, combats et prérequis ; **les futurs Guides Ganymède n'ont plus d'images de contenu**. Les images d'autres écrans et les ressources Unity restent distinctes. Aucun contenu fonctionnel ne doit être fictivement réduit pour améliorer la métrique.
- Le stress **1/4/8 processus Atlas** ne remplace pas le vrai test **2 à 8 fenêtres DOFUS** de la [PR Organizer/Macro #325 (fusionnée)](https://github.com/r9327/Dof-Atlas/pull/325) : fonctionnalité du miroir/macro propre à #325 ; V3 vérifie seulement l'absence de régressions transversales CPU/RAM/UI dans ce contexte.

### Garde-fous exécutables pour tout code futur

- À chaque nouvelle page/liste/cache/worker/SQLite/image : invariant pertinent appliqué via le contrat canonique `PERFORMANCE_GUARDRAILS.md` **et** ses validations existantes Doctor/Integrity/CI, tests bornés et réduction des faux positifs.
- Injecter en tests **un exemple de nouveau code régressif** pour montrer que le garde le repère ; pour une règle web sans objet, justifier `NOT_APPLICABLE` au lieu de faux FAIL.
- Ne pas rajouter de workflow FULL à chaque commit : garder les petits tests pendant Draft et certification une fois Ready sur HEAD exact.
- Les outils externes ne sont pas une condition de fonctionnement de l'application ; l'absence de réseau ne doit pas empêcher le parcours local.

## Dépendances avec autres chantiers

- **[Holding Opti V3 #63](https://github.com/r9327/Atlas-Holding/pull/63)** : orchestrateur et future gestion de providers/cloud, tokens, contexte, agents/LLM, recherches externes.
- **[Holding OSS #60](https://github.com/r9327/Atlas-Holding/pull/60)** : 21 outils open source évalués séparément.
- **[Atlas #285](https://github.com/r9327/Dof-Atlas/pull/285)** : launcher/install/update ; métriques de V3 uniquement, pas de double implémentation.
- **[Atlas #325](https://github.com/r9327/Dof-Atlas/pull/325)** : Organizer/Macro/Miroir **fusionnée au 9 novembre** ; fonctions macro hors V3, sans présumer une recette native DOFUS PASS.
- **[Atlas #358](https://github.com/r9327/Dof-Atlas/pull/358)** : outils Doctor OSS existants ; ne pas reconstruire l'orchestrateur.
- **[Atlas #363](https://github.com/r9327/Dof-Atlas/pull/363)** : architecture/import et certification des guides ; contenu Guide hors V3.
- **[Atlas #365](https://github.com/r9327/Dof-Atlas/pull/365)** : harmonisation UI ; V3 mesure performance sans refaire le thème.

## Critère d'acceptation du présent document

**Cadrage écrit, pas fonctionnalité livrée**. La PR #367 doit rester Draft tant que Doctor/Graphify, comparaisons avant/après, tests Windows et protection des futurs ajouts n'ont pas été réellement effectués au SHA candidat. Les 43 exigences de l'issue #366 restent à satisfaire individuellement avant toute fusion.

## Complément ciblé du 9 novembre 2026 — audit réel du routage et de l'observation

**Base du diagnostic :** `main@2ce1f5b4f65f435b5ceabec95590cfd8da02f7dc`. C'est une **lecture du code** ; aucun outil n'a été lancé ici. Les termes `PASS`, `CERTIFIED` et `18/20` sont interdits pour ce lot documentaire.

| Évidence source et risque | État | Décision ciblée, preuve demandée |
| --- | --- | --- |
| `.github/workflows/scoped-pr-ci.yml:1-31,29-78,155-345` : Draft lance les analyses **stdlib** GitHub Ubuntu ; le job Windows ciblé n'est déclenché que par `workflow_dispatch`, tandis que Ready relève des autres certifications. | **CONFIRMED_STATIC / WORKFLOW_NOT_RUN** | Ne pas présenter l'avis Draft comme test Qt/Windows. Vérifier les runs **au SHA exact** avant de compter une seule suite exécutée. Préserver la séparation feedback rapide / certification. |
| `.github/workflows/scoped-pr-ci.yml:62-101` : sélection de l'audit JSON/liens étendu conditionnée à `PR_NUMBER == 303`, alors que #303 a été fusionnée. | **CONFIRMED_STATIC / sélecteur historique** | Au lot C02/C03 avec propriétaire CI, tester un diff JSON réel dans une PR différente et re-router par **chemins/intention prouvés** ; ne pas lancer cet audit coûteux sur tous les commits ni retirer une obligation attestée. |
| `.ai/context-map.yaml:72-80` possède un scope Zaap et un smoke ; `tools/doctor_dev_lot.py:24-59,90-150` exige pourtant un propriétaire direct reconnu (test `tests.test_<nom du fichier>` ou couplage explicite), absent pour Zaap. `tools/ci_scope_gate.py:57-90` applique le même principe fail-closed. | **CONFIRMED_STATIC / couverture directe à prouver** | Ce n'est **pas** une raison pour bypasser FULL. Rejouer un diff Zaap/Encyclopédie/Map et déterminer si un test existant couvre réellement les branches modifiées. Si oui, ajouter seulement le couplage canonique nécessaire et un test de décision. Sinon, créer un test utile **avant** de demander TARGETED. |
| `tools/ci_scope_gate.py:20-25` marque explicitement des fichiers policy/Guide builder `FULL_ONLY_PATHS`, et `:99-132` refuse `TARGETED` si chemin non propriétaire, risque élevé ou couverture directe insuffisante. | **CONFIRMED_STATIC / protection déjà présente** | **KEEP**. Ne pas élargir les exemptions ni supprimer FULL pour faire passer une PR ; les doublons de vérification peuvent être réduits sans affaiblir ce contrat. |
| `tools/atlas_doctor_lib/agent_protocol.py:18-33,156+` interdit de certifier depuis un plan, un Graphify sans preuve ou un test ciblé sans modules réellement exécutés. | **CONFIRMED_STATIC / protocole existant** | **REUSE**. Ajouter la provenance exacte-SHA dans les rapports et démontrer une exécution réelle seulement lorsque le runner est disponible. |
| `tools/atlas_doctor_lib/ci_decision_arena.py:1-115` compare des routes synthétiques via les vrais sélecteurs et se déclare `MATCHED_ADVISORY_NOT_CERTIFIED`. | **CONFIRMED_STATIC / simulation sans exécution** | Réutiliser l'arène pour lier cas Zaap, Mirror, Encyclopédie, Map, Craft, JSON, docs et suppression de fichier ; conserver `NOT_RUN` pour les tests UI/Windows. |
| `tools/atlas_doctor_lib/ponytail.py:1-190` implémente **un détecteur local** (diff Git + AST/règles JSON), pas l'exécutable Ponytail amont ni un diagnostic runtime de performance. | **CONFIRMED_STATIC / outil local existe** | **REUSE** comme advisory anti-surarchitecture ; ne pas présenter une invocation Ponytail locale comme une preuve de test OSS externe ou de gain mémoire. |
| `tools/atlas_doctor_lib/parallel_app.py:1-139` décrit un stress huit **processus Atlas avec Qt offscreen** et profils/données isolés ; ce n'est pas huit fenêtres de jeu DOFUS, ni une recette EXE native. | **CONFIRMED_STATIC / test NON EXÉCUTÉ** | Garder ce banc pour la charge Atlas ; confier la recette DOFUS 2/4/6/8 à son propriétaire, sans fabriquer de PASS natif. |

### Critères de clôture C02/C03 sans ajouter une deuxième CI

1. **Table d'essai fixée** : un diff par domaine (Encyclopédie, Map, Craft, Zaap, Mirror) plus JSON, documentation seule, suppression et règle protégée ; attendu `TARGETED` seulement si la couverture directe existe, sinon `FULL_REQUIRED`.
2. **Vérifier le trajet complet** : contexte `ai_context` → `ci_scope_gate`/Doctor → modules présents → nombre d'essais non nul → exit code → preuve SHA ; ne pas inférer `PASS` d'une simple recommandation.
3. **Une seule autorité** : modifier la politique dans son propriétaire existant (#358/CI selon scope), et garder le plan #367 centré sur la preuve, les temps développeur et les goulots mesurés.
4. **Ne pas intervenir sur les images des futurs Guides Ganymède**. Les écrans Maps/Bestiaire et ressources Unity restent évalués indépendamment.
