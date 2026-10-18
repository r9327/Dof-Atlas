# Programme de remédiation DOFUS Atlas — 51/51 tâches affectées

**État : PLANIFICATION / PR DRAFT. Aucune de ces cases n'atteste la correction.**

Photographie d'audit : `main` SHA `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` du 17/10/2026 ; reconfirmer le HEAD avant chaque travail.

## Preuve mécanique de couverture du registre

- Registre source : 51 tâches identifiées : P0=4, P1=14, P2=21, P3=12.
- Propriétaires : une PR principale par ID ; **51 IDs uniques, aucun manquant, aucun doublon**.
- 8 nouvelles PR en brouillon (#216–#223) + la PR de réparations existante #201. Total 9 PR responsables.
- #202 reste uniquement une réservation pour les fonctionnalités non spécifiées ; aucun chantier d'audit n'y est placé.
- #175 est **fermée, non fusionnée**, et n'est PAS un propriétaire actif. #223 reprend les trois exigences de certification native.
- Les documents de chaque PR contiennent les actions, scénarios négatifs et critères de sortie détaillés ; ne pas fusionner une PR qui contient seulement son document préparatoire.

## Ordre de réalisation et domaines séparés

| PR | Domaine | IDs | Étape | Dépendances/règles |
|---|---|---:|---|---|
| [#201](https://github.com/r9327/Dof-Atlas/pull/201) | Réparer Guides/Succès — PR existante | 15 | 1A | Synchroniser #201 avec main, preuves UI réelles; recevoir les signaux du lot #219. |
| [#216](https://github.com/r9327/Dof-Atlas/pull/216) | Doctor UI — oracles visuels/interaction | 7 | 1A | Peut avancer en parallèle de #201, sans corriger le produit. |
| [#217](https://github.com/r9327/Dof-Atlas/pull/217) | Doctor Runtime — Qt, CPU/RAM, baseline | 5 | 1A | Mesurer sans couplage fort; les fixes produits restent #201. |
| [#218](https://github.com/r9327/Dof-Atlas/pull/218) | Parcours cold/hot & persistance | 2 | 2 | Intégrer #201 et oracles #216 ; observer Qt avec #217 quand pertinent. |
| [#219](https://github.com/r9327/Dof-Atlas/pull/219) | Audit sémantique Guides | 2 | 1A | Audit et classification seuls; renvoyer les corrections prouvées à #201. |
| [#220](https://github.com/r9327/Dof-Atlas/pull/220) | Graphify structurel, cycles, hubs, fonctions | 7 | 1B | Analyse initiale read-only; éviter les refontes sans preuve. |
| [#221](https://github.com/r9327/Dof-Atlas/pull/221) | Graphify nœuds faibles, orphelins, communautés | 6 | 2 | Réutiliser le graphe exact-SHA et la taxonomie du lot #220. |
| [#222](https://github.com/r9327/Dof-Atlas/pull/222) | Doctor 18 capacités, CI intelligente, agents | 4 | 1A puis final | Définir témoins et oracles dès le début; dernières certifications après les autres PR. |
| [#223](https://github.com/r9327/Dof-Atlas/pull/223) | Dofus/Npcap + EXE natif Windows | 3 | 3 | Remplace la #175 fermée; réutiliser #201 et #218, bloque sur vrai environnement Dofus non disponible. |

Les travaux initiaux **1A** peuvent avancer en parallèle uniquement sur des zones de code indépendantes. Éviter les agents concurrents dans le même module et réévaluer les SHA/deps après fusion. Ordre conseillé : #222 (contrats de preuve), #216 (oracles UI), #201 (fixes visibles), #219 (qualité Guides), #217 (instrumentation), #220 (analyse architecturale), #218 (intégration), #221 (triage complet), #223 (native). Les dépendances imposent les validations finales dans cet ordre logique, pas nécessairement une succession de développements stricts.

## Affectation exhaustive par ID

### PR #201 — Réparer Guides/Succès — PR existante

- [ ] `P0-01` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P0-02` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P0-03` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P0-04` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P1-09` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P1-10` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P1-11` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P1-12` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P1-13` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P1-14` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P2-03` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P2-04` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P2-05` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P2-06` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)
- [ ] `P2-07` — [responsable #201](https://github.com/r9327/Dof-Atlas/pull/201)

### PR #216 — Doctor UI — oracles visuels/interaction

- [ ] `P1-01` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)
- [ ] `P1-02` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)
- [ ] `P1-03` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)
- [ ] `P1-04` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)
- [ ] `P1-06` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)
- [ ] `P1-08` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)
- [ ] `P2-17` — [responsable #216](https://github.com/r9327/Dof-Atlas/pull/216)

### PR #217 — Doctor Runtime — Qt, CPU/RAM, baseline

- [ ] `P1-07` — [responsable #217](https://github.com/r9327/Dof-Atlas/pull/217)
- [ ] `P2-08` — [responsable #217](https://github.com/r9327/Dof-Atlas/pull/217)
- [ ] `P2-09` — [responsable #217](https://github.com/r9327/Dof-Atlas/pull/217)
- [ ] `P2-10` — [responsable #217](https://github.com/r9327/Dof-Atlas/pull/217)
- [ ] `P2-16` — [responsable #217](https://github.com/r9327/Dof-Atlas/pull/217)

### PR #218 — Parcours cold/hot & persistance

- [ ] `P1-05` — [responsable #218](https://github.com/r9327/Dof-Atlas/pull/218)
- [ ] `P2-14` — [responsable #218](https://github.com/r9327/Dof-Atlas/pull/218)

### PR #219 — Audit sémantique Guides

- [ ] `P2-01` — [responsable #219](https://github.com/r9327/Dof-Atlas/pull/219)
- [ ] `P2-02` — [responsable #219](https://github.com/r9327/Dof-Atlas/pull/219)

### PR #220 — Graphify structurel, cycles, hubs, fonctions

- [ ] `P2-19` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)
- [ ] `P3-01` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)
- [ ] `P3-02` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)
- [ ] `P3-07` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)
- [ ] `P3-08` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)
- [ ] `P3-09` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)
- [ ] `P3-11` — [responsable #220](https://github.com/r9327/Dof-Atlas/pull/220)

### PR #221 — Graphify nœuds faibles, orphelins, communautés

- [ ] `P2-20` — [responsable #221](https://github.com/r9327/Dof-Atlas/pull/221)
- [ ] `P3-03` — [responsable #221](https://github.com/r9327/Dof-Atlas/pull/221)
- [ ] `P3-04` — [responsable #221](https://github.com/r9327/Dof-Atlas/pull/221)
- [ ] `P3-05` — [responsable #221](https://github.com/r9327/Dof-Atlas/pull/221)
- [ ] `P3-06` — [responsable #221](https://github.com/r9327/Dof-Atlas/pull/221)
- [ ] `P3-10` — [responsable #221](https://github.com/r9327/Dof-Atlas/pull/221)

### PR #222 — Doctor 18 capacités, CI intelligente, agents

- [ ] `P2-15` — [responsable #222](https://github.com/r9327/Dof-Atlas/pull/222)
- [ ] `P2-18` — [responsable #222](https://github.com/r9327/Dof-Atlas/pull/222)
- [ ] `P2-21` — [responsable #222](https://github.com/r9327/Dof-Atlas/pull/222)
- [ ] `P3-12` — [responsable #222](https://github.com/r9327/Dof-Atlas/pull/222)

### PR #223 — Dofus/Npcap + EXE natif Windows

- [ ] `P2-11` — [responsable #223](https://github.com/r9327/Dof-Atlas/pull/223)
- [ ] `P2-12` — [responsable #223](https://github.com/r9327/Dof-Atlas/pull/223)
- [ ] `P2-13` — [responsable #223](https://github.com/r9327/Dof-Atlas/pull/223)


## Règles transversales non négociables

1. `git rev-parse HEAD` et `git status --short` au début ; un seul clone canonique, sources et preuves au SHA exact.
2. Reproduire les défauts réels et les cas négatifs. `REVIEW`/arête inférée/communauté isolée ne sont jamais des bugs confirmés.
3. Ne jamais fusionner/supprimer des modules par seul score Graphify ; préserver les API partagées et respecter Qt/threading/ownership.
4. Doctor/Graphify/CI doivent utiliser des preuves exécutées, de vrais tests d'interaction en UI et un statut explicite `BLOCKED/NOT_COVERED` quand le contrôle manque.
5. CI par impact, puis FAST/Full/bench/Windows seulement si obligations. Ne pas relancer de longues suites sur chaque petit commit ni créer de faux PASS.
6. Ne pas confondre problème de runner Qt offscreen avec problème de binaire Windows installé ; distinguer le vrai jeu de tests synthétiques.
7. #201 ne doit pas migrer les guides Dofus vers Lanyel ni changer leur pagination sans nouvelle spécification. #202 inchangée.
8. Les corrections doivent être accompagnées d'une preuve précise, d'un effet utilisateur attendu, d'une couverture fonctionnelle et d'un plan rollback.

## Vérification de clôture du programme

- [ ] 51/51 tâches requalifiées sur l'état courant (PASS/NO_CHANGE_JUSTIFIED/BLOCKED et preuve associée).
- [ ] Les changements produits ont passé leurs scénarios UI, tests ciblés et contrôles de données.
- [ ] Les outils Doctor possèdent des tests négatifs qui les empêchent de transformer une absence d'observation en PASS.
- [ ] La CI complète requise et les preuves cumulées exact-SHA ont été validées au bon moment.
- [ ] Les parcours Windows et Dofus/Npcap non vérifiables sont clairement distingués des parcours certifiés.
