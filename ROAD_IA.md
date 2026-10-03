# Dofus Atlas — ROAD IA active

Dernière mise à jour : 2 octobre 2026 (Europe/Paris)

## Rôle

Cette roadmap pilote uniquement les prochains travaux d’outillage IA, Doctor,
Graphify, sécurité de contribution et anti-régression. Elle ne remplace jamais
`AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`,
`PERFORMANCE_GUARDRAILS.md` ni `PHASE_CERTIFICATION.md`.

Le dépôt courant, les tests et les rapports du SHA exact restent les sources de
vérité. Les détails historiques appartiennent à Git et aux pull requests, pas à
ce fichier.

## Commande de reprise

Quand l’utilisateur dit `go road ia`, reprendre le seul lot marqué `NEXT` :

```powershell
py -3.13 -m tools.ai_context status
py -3.13 -m tools.agent_task_profiles --task structural --quality best --structural --json
```

Lire ensuite les contrats et sources réellement concernés, construire ou
vérifier le graphe exact-SHA si le lot est structurel, puis travailler par
micro-lot.

## États autorisés

- `NEXT` : prochain lot exécutable ; il doit y en avoir exactement un.
- `QUEUED` : lot ordonné mais pas encore commencé.
- `BLOCKED` : précondition externe ou choix produit explicitement manquant.
- `DONE` : résultat intégré avec les validations requises sur son SHA.

`IMPLEMENTED`, `PASS` local ou PR verte ne signifient jamais qu’une phase est
certifiée. Seul le contrat de `PHASE_CERTIFICATION.md` autorise ce vocabulaire.

## Acquis à préserver

- AI Context route les domaines, contrats et tests ciblés.
- Agent possède le contexte, l’ownership, l’impact et le plan de travail.
- Doctor porte les diagnostics et Atlas Integrity reste l’autorité de validation.
- Graphify 0.9.72 fournit la carte AST explicite des travaux structurels.
- Les résultats d’audit locaux sont bornés et les artefacts CI ordinaires expirent.
- Les hooks et la méta-intégrité empêchent l’affaiblissement silencieux des gates.
- Doctor DEEP orchestre mutation ciblée, fault injection, ordre reproductible,
  lifecycle long monolithique et mesures, sans alourdir chaque FULL.

## Cadence DEEP

Commande opérateur unique :

```powershell
py -3.13 -m tools.atlas_doctor verify --gate deep --base-ref origin/main
```

Le propriétaire du dépôt l’exécute manuellement sur `main` au minimum avant la
certification d’une phase, puis après toute modification des contrats de
persistance, démarrage, concurrence/lifecycle ou des outils DEEP eux-mêmes. Le
workflow sensible reste manuel et réservé au runner Windows isolé tant qu’un
runner public sûr n’est pas démontré. Ses preuves machine sont conservées 30
jours ; un nouvel SHA invalide toute preuve précédente.

## Lots actifs

### IA-1 — NEXT — Consolider les candidats d’outillage prouvés

Objectif : réduire la surface des outils sans supprimer un contrat utile.

Périmètre initial mesuré par `tools.tool_audit` :

- établir si `tools/install_rtk.ps1` possède un consommateur externe ou un contrat
  d’installation encore valide ; le documenter ou le retirer avec preuve ;
- comparer les consommateurs et contrats de `tools/guide_ultime_scope_v4.py` et
  `tools/guide_ultime_scope_v5.py` ; consolider seulement si l’équivalence est
  démontrée ;
- ne jamais supprimer un outil sur le seul signal « zéro consommateur ».

Sortie attendue : Tool Audit sans candidat inexpliqué, consommateurs confirmés,
tests ciblés verts, Graphify avant/après si suppression, Atlas Integrity au niveau
requis et diff intégré par PR.

### IA-3 — QUEUED — Réduire le coût de l’outillage IA sans perdre de couverture

Objectif : mesurer puis retirer les doublons d’exécution entre Work Spec, Agent,
Doctor, Graphify et Atlas Integrity.

Périmètre : temps par commande, scans répétés, cache indexé par HEAD + worktree et
réutilisation des résultats uniquement lorsque leurs contrats sont compatibles.
Aucun second routeur, aucune policy parallèle et aucun cache de verdict de tests.

Sortie attendue : gain mesuré sur un scénario SOFT et un scénario HARD, mêmes
groupes obligatoires, mêmes blockers, tests de non-régression et FULL vert.

## Entretien de cette roadmap

- Maximum 160 lignes.
- Un seul lot `NEXT`.
- Un lot terminé devient une ligne dans « Acquis à préserver » ; son journal
  détaillé reste dans Git et la PR.
- Toute nouvelle proposition doit partir d’un écart mesuré, d’un incident ou
  d’un contrat produit, jamais d’une abstraction hypothétique.
- Mettre à jour cette roadmap dans la même PR que le changement qui ferme ou
  reprogramme un lot.
