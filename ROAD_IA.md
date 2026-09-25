# Dofus Atlas — ROAD IA

Cette roadmap est le chantier permanent qui améliore la qualité de travail des agents IA sur Dofus Atlas sans remplacer les règles projet existantes.

## Commande de reprise

Quand l'utilisateur dit **`go road ia`**, reprendre le premier lot qui n'est pas `DONE`. Ne pas redemander le contexte déjà présent dans le dépôt. Commencer par vérifier le HEAD, la branche, le statut Git et exécuter `py -3.13 -m tools.ai_context status`.

La ROAD IA est indépendante de la ROAD V3 produit : elle améliore la manière de travailler sur toute l'application, pas une fonctionnalité métier précise.

## Principes

- `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md` et `PHASE_CERTIFICATION.md` restent les contrats permanents.
- Le contexte IA doit être **court, routé et vérifiable**, jamais un deuxième cahier des charges géant.
- Le dépôt réel, les tests et le code courant restent la source de vérité.
- Toute donnée de contexte automatiquement dérivable du dépôt doit être générée automatiquement plutôt que maintenue à la main.
- Une amélioration du système IA ne doit pas affaiblir la CI, les audits, les tests ou les règles anti-régression.
- Les changements se font en micro-lots cohérents et testables.
- `IMPLEMENTED — VALIDATION PENDING` signifie que le code du lot est présent mais qu'il ne doit pas être considéré fermé tant que la preuve machine prévue n'existe pas sur le SHA exact.

## Lots

### IA-0 — Baseline et non-régression des règles — DONE

Objectif : conserver les règles existantes et les utiliser comme socle au lieu de les remplacer.

Preuve : le dépôt possède déjà `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, `PHASE_CERTIFICATION.md` et les hooks Git locaux.

### IA-1 — Routeur de contexte compact + index automatique — IMPLEMENTED — VALIDATION PENDING

Objectif : qu'un agent sache immédiatement où regarder sans charger tout le dépôt.

Livrables présents :

- `AI_CONTEXT.md` : carte courte des sources de vérité et routage par zone ;
- `tools/ai_context.py` : état live du dépôt, classification, routage et synchronisation ;
- `.ai/context_index.json` : empreintes compactes de toutes les entrées racine, sauf `.ai/` pour éviter l'auto-référence ;
- mise à jour automatique de l'index au `pre-commit` à partir de l'arbre staged ;
- `.github/workflows/ai-context-ci.yml` : validation ciblée légère ;
- tests empêchant de considérer comme courant un index périmé ;
- tests Git temporaires couvrant création, modification, renommage, suppression et synchronisation staged.

Critère de sortie restant : exécution machine réussie de ces tests sur le SHA exact candidat.

### IA-2 — Instructions locales par zone — IMPLEMENTED — VALIDATION PENDING

Objectif : donner à l'agent seulement les règles locales utiles au code qu'il touche.

Livrables présents :

- `app/AGENTS.md` ;
- `data/AGENTS.md` ;
- `tools/AGENTS.md` ;
- `tests/AGENTS.md`.

Règle permanente : ajouter un `AGENTS.md` plus local uniquement lorsqu'une zone possède de vraies contraintes propres et stables. Éviter les doublons et les fichiers d'instructions partout.

Critère de sortie restant : validation ciblée confirmant que les règles globales restent au root et qu'aucune instruction locale ne contredit le contrat global.

### IA-3 — Carte d'impact et tests ciblés — IMPLEMENTED — VALIDATION PENDING

Objectif : avant une modification, proposer les validations et sources de vérité les plus probables.

État implémenté :

- `status` et `route` recommandent des documents de contexte ;
- ils proposent des ancres canoniques existantes selon le domaine ;
- ils proposent des modules de tests ciblés existants ;
- un test portant directement le nom d'un fichier Python modifié est détecté automatiquement lorsqu'il existe ;
- les recommandations absentes du dépôt sont filtrées au lieu d'être inventées.

Les recommandations restent une aide au ciblage et ne remplacent jamais la recherche réelle des imports, appels, consommateurs et contrats.

Critère de sortie restant : validation ciblée sur plusieurs domaines du dépôt.

### IA-4 — Détection de dérive architecturale — IMPLEMENTED — VALIDATION PENDING

Objectif : détecter les nouveaux fichiers ou nouvelles zones qui ne rentrent dans aucune catégorie utile.

État implémenté :

- tout nouveau fichier ou répertoire racine est automatiquement couvert par l'index Git compact ;
- `py -3.13 -m tools.ai_context drift` signale les chemins modifiés que le routeur ne sait pas classifier ;
- un chemin non classé produit un warning et ne bloque pas une évolution légitime ;
- un index manquant ou périmé reste une erreur de cohérence.

Critère de sortie restant : validation machine d'un ajout connu et d'un ajout volontairement non classé.

### IA-5 — Handoff agent / reprise de chantier — IMPLEMENTED — VALIDATION PENDING

Objectif : rendre une reprise ChatGPT/Codex fiable sans énorme prompt manuel.

État implémenté :

- `py -3.13 -m tools.ai_context handoff` produit un handoff compact ;
- il contient branche, SHA, base, objectif, fichiers réellement modifiés, état vérifié, tests déclarés, blocages, prochaine action et tests ciblés suggérés ;
- aucun log massif ni copie de dépôt n'est inclus ;
- le format texte est couvert par un test ciblé.

Critère de sortie restant : exécution machine du test et essai réel de reprise depuis un handoff généré.

### IA-6 — Certification ROAD IA — IN PROGRESS

Objectif : prouver que la couche IA aide sans dégrader le produit.

Validation finale :

- tests ciblés ROAD IA ;
- intégrité FAST ;
- full suite adaptée au changement ;
- vérification que le hook met bien à jour l'index ;
- vérification d'un ajout, d'une modification, d'un renommage et d'une suppression ;
- aucun changement de comportement produit Dofus Atlas.

La ROAD IA n'est déclarée terminée qu'avec une preuve machine sur le SHA exact candidat.
