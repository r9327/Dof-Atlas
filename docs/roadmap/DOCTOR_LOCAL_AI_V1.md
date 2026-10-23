# Doctor Atlas — IA locale consultative (22/10/2026)

## Position
**Un seul Doctor.** Garder intacts les contrats `agent plan/check/validate`, les verdicts déterministes, les reçus exact-SHA et les gates de CI. Ajouter une capacité IA **locale et optionnelle** d'enquête, sans lui transmettre les droits de certifier, merger ni pousser.

## Capacités
- Choisir un LLM local déjà provisionné par Holding ; sinon exécuter Doctor classique normalement.
- Lire les logs bornés, captures UI, résultats de tests, AI Context et Graphify sur le même SHA.
- Proposer la cause probable et une reproduction exacte d'un bug ; produire des scénarios de tests adaptés à la modification.
- UI Windows PySide6/Qt : `pytest-qt` et `pywinauto` pour interaction réelle, mesures de boutons débordants/menus/focus, screenshots avant/après.
- Playwright uniquement pour les vues navigateur/web où il est pertinent ; Hypothesis pour des cas limites génératifs.
- Enregistrer les régressions diagnostiquées + correctifs **validés par tests déterministes**, réutilisables sans nouvelle IA.

## Frontières
- L'IA peut *proposer* des tests et diagnostics, jamais altérer un verdict PASS/FAIL/REVIEW ni supprimer des tests en échec.
- Les tests auto-générés s'exécutent dans environnement/worktree isolé avec plafonds RAM/durée/processus et sans privilèges GitHub.
- Refuser captures contenant secrets/personnel sans redaction ; aucune capture de données utilisateur par défaut.
- Ne pas dupliquer le code de certif/Graphify/AI Context ; utiliser leurs interfaces existantes.

## Gates de fin
- Doctor sans Ollama = comportement inchangé.
- Bug UI volontaire réellement détecté sur Windows ; correction puis test vert indépendant.
- Échec IA (hallucination/timeout) = rapport non concluant, **jamais PASS certifié**.
- Preuves sur SHA, tests négatifs de spoofing, compatibilité PR Atlas #234, PR Holding #17 et hooks sécurisés #236.
- Draft jusqu'aux tests Windows natifs et à l'intégration du rôle Doctor côté Holding.
