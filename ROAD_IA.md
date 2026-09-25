# Dofus Atlas — ROAD IA

Cette roadmap est le chantier permanent qui améliore la qualité de travail des agents IA sur Dofus Atlas sans remplacer les règles projet existantes.

## Commande de reprise

Quand l'utilisateur dit **`go road ia`**, reprendre le premier lot non terminé de ce document. Ne pas redemander le contexte déjà présent dans le dépôt. Commencer par vérifier le HEAD, la branche, le statut Git et exécuter `py -3.13 -m tools.ai_context status`.

La ROAD IA est indépendante de la ROAD V3 produit : elle améliore la manière de travailler sur toute l'application, pas une fonctionnalité métier précise.

## Principes

- `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md` et `PHASE_CERTIFICATION.md` restent les contrats permanents.
- Le contexte IA doit être **court, routé et vérifiable**, jamais un deuxième cahier des charges géant.
- Le dépôt réel, les tests et le code courant restent la source de vérité.
- Toute donnée de contexte automatiquement dérivable du dépôt doit être générée automatiquement plutôt que maintenue à la main.
- Une amélioration du système IA ne doit pas affaiblir la CI, les audits, les tests ou les règles anti-régression.
- Les changements se font en micro-lots cohérents et testables.

## Lots

### IA-0 — Baseline et non-régression des règles — DONE

Objectif : conserver les règles existantes et les utiliser comme socle au lieu de les remplacer.

Preuve : le dépôt possède déjà `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, `PHASE_CERTIFICATION.md` et les hooks Git locaux.

### IA-1 — Routeur de contexte compact + index automatique — IN PROGRESS

Objectif : qu'un agent sache immédiatement où regarder sans charger tout le dépôt.

Livrables :

- `AI_CONTEXT.md` : carte courte des sources de vérité et routage par zone ;
- `tools/ai_context.py` : état live du dépôt, classification des changements, recommandations de contexte et synchronisation ;
- `.ai/context_index.json` : empreintes compactes des grandes zones suivies ;
- mise à jour automatique de l'index au `pre-commit` ;
- test CI empêchant de committer un index périmé.

Critère de sortie : création, modification, suppression ou renommage d'un fichier sous une zone suivie change automatiquement son empreinte sans lister des milliers de fichiers dans le contexte.

### IA-2 — Instructions locales par zone — IN PROGRESS

Objectif : donner à l'agent seulement les règles locales utiles au code qu'il touche.

Livrables initiaux :

- `app/AGENTS.md` ;
- `data/AGENTS.md` ;
- `tools/AGENTS.md` ;
- `tests/AGENTS.md`.

Puis ajouter un `AGENTS.md` plus local uniquement lorsqu'une zone possède de vraies contraintes propres et stables. Éviter les doublons et les fichiers d'instructions partout.

Critère de sortie : les règles globales restent au root, les règles locales ne répètent pas le contrat global et n'introduisent aucune règle contradictoire.

### IA-3 — Carte d'impact et tests ciblés — TODO

Objectif : avant une modification, proposer les consommateurs et validations les plus probables.

Prévoir une table déclarative légère reliant les grandes zones aux tests, audits et fichiers canoniques. La sortie doit rester une aide au ciblage, jamais une excuse pour ne pas rechercher les appels réels.

Critère de sortie : `tools.ai_context status/route` peut recommander les tests et documents pertinents pour les chemins touchés.

### IA-4 — Détection de dérive architecturale — TODO

Objectif : détecter les nouveaux fichiers ou nouvelles zones qui ne rentrent dans aucune catégorie utile.

Le contrôle doit signaler la dérive sans bloquer les simples ajouts légitimes. Bloquer uniquement les incohérences certaines : index périmé, fichier de contexte généré modifié à la main, règle locale contradictoire détectable, etc.

### IA-5 — Handoff agent / reprise de chantier — TODO

Objectif : rendre une reprise ChatGPT/Codex fiable sans énorme prompt manuel.

Créer un format court de handoff contenant uniquement : branche, SHA, objectif, état vérifié, fichiers réellement modifiés, tests exécutés, blocages et prochaine action. Ne jamais y copier le dépôt ou des logs massifs.

### IA-6 — Certification ROAD IA — TODO

Objectif : prouver que la couche IA aide sans dégrader le produit.

Validation finale :

- tests ciblés ROAD IA ;
- intégrité FAST ;
- full suite adaptée au changement ;
- vérification que le hook met bien à jour l'index ;
- vérification d'un ajout, d'une modification, d'un renommage et d'une suppression ;
- aucun changement de comportement produit Dofus Atlas.

La ROAD IA n'est déclarée terminée qu'avec une preuve machine sur le SHA exact candidat.
