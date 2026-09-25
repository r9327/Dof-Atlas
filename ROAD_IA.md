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
- Un lot `DONE` reste valide uniquement si le workflow de certification associé au HEAD courant est vert.

## Lots

### IA-0 — Baseline et non-régression des règles — DONE

Objectif : conserver les règles existantes et les utiliser comme socle au lieu de les remplacer.

Preuve : le dépôt possède déjà `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, `PHASE_CERTIFICATION.md` et les hooks Git locaux.

### IA-1 — Routeur de contexte compact + index automatique — DONE

Objectif : qu'un agent sache immédiatement où regarder sans charger tout le dépôt.

Livrables présents :

- `AI_CONTEXT.md` : carte courte des sources de vérité et routage par zone ;
- `tools/ai_context.py` : état live du dépôt, classification, routage et synchronisation ;
- `.ai/context_index.json` : empreintes compactes de toutes les entrées racine, sauf `.ai/` pour éviter l'auto-référence ;
- mise à jour automatique de l'index au `pre-commit` à partir de l'arbre staged ;
- `.github/workflows/ai-context-ci.yml` : validation ciblée légère ;
- tests empêchant de considérer comme courant un index périmé ;
- tests Git temporaires couvrant création, modification, renommage, suppression et synchronisation staged.

Preuve : validation ciblée réussie sur le SHA candidat certifié.

### IA-2 — Instructions locales par zone — DONE

Objectif : donner à l'agent seulement les règles locales utiles au code qu'il touche.

Livrables présents :

- `app/AGENTS.md` ;
- `data/AGENTS.md` ;
- `tools/AGENTS.md` ;
- `tests/AGENTS.md`.

Règle permanente : ajouter un `AGENTS.md` plus local uniquement lorsqu'une zone possède de vraies contraintes propres et stables. Éviter les doublons et les fichiers d'instructions partout.

Preuve : validation ciblée réussie sans contradiction détectée avec le contrat global.

### IA-3 — Carte d'impact et tests ciblés — DONE

Objectif : avant une modification, proposer les validations et sources de vérité les plus probables.

État implémenté :

- `status` et `route` recommandent des documents de contexte ;
- ils proposent des ancres canoniques existantes selon le domaine ;
- ils proposent des modules de tests ciblés existants ;
- un test portant directement le nom d'un fichier Python modifié est détecté automatiquement lorsqu'il existe ;
- les recommandations absentes du dépôt sont filtrées au lieu d'être inventées.

Les recommandations restent une aide au ciblage et ne remplacent jamais la recherche réelle des imports, appels, consommateurs et contrats.

Preuve : tests ciblés ROAD IA réussis sur le SHA candidat certifié.

### IA-4 — Détection de dérive architecturale — DONE

Objectif : détecter les nouveaux fichiers ou nouvelles zones qui ne rentrent dans aucune catégorie utile.

État implémenté :

- tout nouveau fichier ou répertoire racine est automatiquement couvert par l'index Git compact ;
- `py -3.13 -m tools.ai_context drift` signale les chemins modifiés que le routeur ne sait pas classifier ;
- un chemin non classé produit un warning et ne bloque pas une évolution légitime ;
- un index manquant ou périmé reste une erreur de cohérence.

Preuve : validation machine des cas connus et volontairement non classés réussie.

### IA-5 — Handoff agent / reprise de chantier — DONE

Objectif : rendre une reprise ChatGPT/Codex fiable sans énorme prompt manuel.

État implémenté :

- `py -3.13 -m tools.ai_context handoff` produit un handoff compact ;
- il contient branche, SHA, base, objectif, fichiers réellement modifiés, état vérifié, tests déclarés, blocages, prochaine action et tests ciblés suggérés ;
- aucun log massif ni copie de dépôt n'est inclus ;
- le format texte est couvert par un test ciblé.

Preuve : test ciblé et validation de reprise/handoff réussis.

### IA-6 — Certification ROAD IA — DONE

Objectif : prouver que la couche IA aide sans dégrader le produit.

Validation finale obtenue :

- tests ciblés ROAD IA : PASS ;
- intégrité FAST : PASS ;
- full suite application : PASS ;
- hook/index et cohérence du contexte : PASS ;
- création, modification, renommage et suppression : couverts par tests ;
- aucun changement de comportement produit Dofus Atlas introduit par la ROAD IA.

Preuve machine de fermeture avant synchronisation documentaire finale :

- branche : `road/ai-agent-context-v1` ;
- base de validation : `2c19ce59269773a03a8741af24728299f69723ed` ;
- SHA certifié : `e5a0803f0eb7e66889b7d91b62aab9caf53a18c9` ;
- GitHub Actions run : `36182042785` ;
- catalogue matérialisé : `1976` quêtes ;
- Atlas Integrity FAST : `PASS`, dette critique `0`, blockers `0` ;
- full suite : `1595` tests, `OK`.

La synchronisation finale de `ROAD_IA.md` et `.ai/context_index.json` doit elle-même conserver un workflow vert sur son HEAD exact ; aucune nouvelle modification documentaire n'est nécessaire après cette dernière preuve.
