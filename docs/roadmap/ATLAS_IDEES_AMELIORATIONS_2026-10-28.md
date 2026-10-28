# Registre de 36 pistes d'amélioration Atlas — 28 octobre 2026

> **Statut : inventaire de propositions, pas une roadmap active ni un diagnostic de 36 défauts.**
> Référence de départ : `main` au SHA `31e3ec3b4189be7276f49e9873b648329a717149`.
> Une hypothèse ci-dessous ne devient un travail qu'après vérification sur le HEAD courant, identification du propriétaire canonique et mesure de l'écart réel.

## Portée et autorité

Ce document rassemble **les 36 pistes évoquées** dans les échanges sur Doctor, IA, Guide, persistance, UX, Windows et publication. Il évite de créer des issues/agents/gates parallèles et **ne change ni les priorités ni les états de `ROAD_IA.md`**. Le seul lot IA `NEXT` reste IA-1 ; IA-3 reste `QUEUED`. Toute éventuelle implémentation passe par un micro-lot unique et les contrats `AGENTS.md`, `DEVELOPMENT_GUARDRAILS.md`, `ZERO_TRUST_RULES.md` et `PHASE_CERTIFICATION.md`.

Les priorités indiquent la **gravité potentielle si un écart est confirmé**, et non un bug constaté ni l'autorisation de changer de phase. Les fonctions déjà présentes doivent être réutilisées et leur couverture mesurée avant tout ajout. Une proposition sans écart démontré est à classer sans suite.

## A. Doctor, certification et outillage IA (01–06)

| ID | Piste | Vérification / valeur attendue |
| --- | --- | --- |
| A01 | **Certification FULL fiable** (P0) | Isoler l'échec primaire sur le SHA exact, aligner uniquement les contrats réellement obsolètes, sans assouplir `FULL_SUITE` ni les baselines. Tenir compte de la PR #270 avant toute correction. |
| A02 | **Doctor : cause racine vs cascade** (P1) | Évaluer si les rapports CI existants distinguent déjà première erreur, dépendances bloquées et actions ciblées ; enrichir la restitution plutôt que créer un nouveau moteur. |
| A03 | **Précontrôle intelligent avant FULL** (P1) | Identifier les contrats rapides capables de détecter un échec certain avant la suite lourde ; ne jamais assimiler ce précontrôle à une certification ni supprimer des tests obligatoires. |
| A04 | **Consolidation des outils et skills** (IA-1) | Traiter seulement le lot officiel IA-1 : consommateurs de `tools/install_rtk.ps1`, comparaison v4/v5 du scope Guide, puis décision fondée sur preuves. Pas de suppression sur simple absence d'import. |
| A05 | **Routage IA/skills/contextes** (P2) | Vérifier la sélection actuelle via `AI_CONTEXT.md`, `.agents/skills` et les profils de tâche ; expliciter le skill et les tests retenus sans second routeur. |
| A06 | **Synchronisation des contrats et documentations** (P1) | Rechercher des divergences avérées entre README, règles agent, workflows et paramètres hébergés ; corriger la source ou le document fautif avec un contrôle ciblé. |

## B. Fiabilité, sécurité et expérience développeur (07–18)

| ID | Piste | Vérification / valeur attendue |
| --- | --- | --- |
| B07 | **Sauvegarde et récupération après interruption** (P0 si manque) | Tester coupure d'écriture, JSON corrompu, relecture concurrente et récupération sans perte silencieuse ; préserver le contrat atomique existant. |
| B08 | **Identité canonique des personnages** (P0 si manque) | Tester permutation, renommage, suppression/réaffectation de slots : toute donnée métier reste liée exclusivement à `character:<id_dofus>`. |
| B09 | **Synchronisation Guide / Quêtes / Succès / Home** (P1) | Vérifier un scénario métier bout en bout et des invalidations ciblées, sans recalculer tous les catalogues. |
| B10 | **Audit borné des règles d'agents** (P1) | Détecter contradictions et duplications dans les fichiers d'autorité et leurs consommateurs directs ; ne pas instaurer une seconde policy. |
| B11 | **Preuve complète des tests CI** (P1) | Afficher SHA, base, environnement, modules lancés, sorties, groupes non exécutés et raison du verdict ; aucun `SKIPPED` compté comme `PASS`. |
| B12 | **Concordance protection GitHub / documentation** (P1) | Comparer périodiquement les règles actives avec `GITHUB_PROTECTION.md` : le ruleset consulté le 28/10 n'avait aucun bypass, contrairement au texte actuel. |
| B13 | **Scénarios runtime Windows réels** (P1) | Vérifier lancement, fermeture, update et arrêt de workers/timers/WebViews, sur machine Windows adaptée et sans démarrage lourd systématique. |
| B14 | **Provenance et versionnement des données Dofus** (P1) | Associer quêtes, prérequis, coordonnées et succès aux sources et versions réellement vérifiées ; signaler les inconnues plutôt qu'inventer des valeurs. |
| B15 | **Tests UI ciblés** (P2) | Mesurer redimensionnement, DPI, navigation clavier, focus, scroll et clipping ; respecter `app/ui/theme.py` et `app/ui/components.py`. |
| B16 | **Tendances de performance comparables** (P2) | Suivre CPU au repos, RAM, ouverture des pages et premier rendu sur un environnement identique ; comparer aux baselines sans seuil intermachines fragile. |
| B17 | **Confidentialité des logs/rapports IA** (P1) | Contrôler l'absence de secrets, chemins privés et données de progression inutiles dans les journaux et artefacts. |
| B18 | **Explication des décisions Doctor** (P2) | Afficher pourquoi tel test/skill/guardian a été choisi et pourquoi le résultat est `REVIEW` ou `BLOCKED`, sur le plan existant. |

## C. Intelligence de changement et de test (19–24)

| ID | Piste | Vérification / valeur attendue |
| --- | --- | --- |
| C19 | **Doctor prédictif** (P2) | Avant édition, produire des impacts probables et invariants à surveiller à partir d'Agent/Graphify, avec incertitudes explicites ; pas de prédiction présentée comme preuve. |
| C20 | **Comparaison comportementale avant/après** (P1) | Comparer deux traces d'un même scénario (progression, persistence, UI, coûts) et vérifier si `scenario-diff` couvre déjà le cas. |
| C21 | **Carte des zones fragiles** (P2) | Corréler régressions démontrées, consommateurs Graphify et coûts des tests ; ne pas réduire la couverture sur un simple score. |
| C22 | **Simulateur d'actions utilisateur multi-personnages** (P1) | Combiner actions, sauvegardes, redémarrages et conflits sur fixtures isolées ; vérifier identité, atomicité et invariants métier sans toucher aux profils réels. |
| C23 | **Résistance à l'injection d'instructions IA** (P1) | Tester commentaires, sorties de commandes et faux fichiers de consignes non fiables ; seul le contrat d'autorité connu décide des actions. |
| C24 | **Coût réel des outils** (IA-3) | Mesurer scans, temps et répétitions Work Spec/Agent/Doctor/Graphify/Integrity ; ne traiter que dans le lot IA-3 avec gains et invariants prouvés. |

## D. Expérience Guide et métier (25–30)

| ID | Piste | Vérification / valeur attendue |
| --- | --- | --- |
| D25 | **Guide qui explique l'ordre de ses étapes** (P2) | Afficher prérequis et raison du prochain jalon à partir des données structurées canoniques, pas de texte explicatif inventé. |
| D26 | **Détection de parcours impossibles** (P1) | Repérer cycles, exigences manquantes ou étapes inaccessibles sur les données réellement disponibles ; l'absence de données n'est pas un parcours impossible prouvé. |
| D27 | **Préparation de ressources contextualisée** (P2) | Agréger métiers, consommables et ressources à garder pour une séquence du Guide ; vérifier les fonctionnalités déjà prévues dans `PR_GUIDE_OPTIPLANNER_V2_20261018.md`. |
| D28 | **Reprise exacte de session** (P1) | Tester fermeture/crash/réouverture sur la bonne fiche et le bon personnage ; conserver les ID stables du Guide et la progression. |
| D29 | **Recherche universelle progressive** (P2) | Explorer une recherche commune Guide/Quêtes/Succès/ressources, avec index léger et détails à la demande, sans second catalogue. |
| D30 | **Historique explicable des mutations métier** (P2) | Évaluer la traçabilité bornée d'une validation (qui, quel état, quelles surfaces invalidées), sans EventBus ni journal non borné. |

## E. Migrations, distribution et diagnostic produit (31–36)

| ID | Piste | Vérification / valeur attendue |
| --- | --- | --- |
| E31 | **Rejeu reproductible des migrations** (P0 si manque) | Ouvrir d'anciens formats sur fixtures représentatives et vérifier conservation, compatibilité, idempotence et secours après interruption. |
| E32 | **Update et rollback sûrs** (P1) | Tester coupure, verrou Windows et migration de données pendant la mise à jour ; vérifier la PR #248 et `FAST_DELTA_UPDATES_ATLAS_V1.md` avant toute autre initiative. |
| E33 | **Export de diagnostic anonymisé** (P2) | Concevoir un export explicite et opt-in, sans données personnelles inutiles, avec contrôle des fichiers inclus et taille bornée. |
| E34 | **Sobriété en arrière-plan** (P2) | Mesurer les timers, threads, I/O et WebViews lorsque l'application est inactive ; arrêter uniquement les travaux non indispensables. |
| E35 | **Traçabilité des versions distribuées** (P1) | Relier binaire, SHA, dépendances, état exact de certification et compatibilité des données ; ne pas publier sans preuves de release. |
| E36 | **Diagnostic intégré à la demande** (P2) | Examiner un écran technique opt-in basé sur les diagnostics existants, sans polling agressif, nouvelle télémétrie permanente ni surcharge du démarrage. |

## Éléments déjà connus — à ne pas transformer en travaux dupliqués

- Au SHA de référence, plusieurs workflows dépendant de la certification ont échoué ; un échec primaire de contrat RAM a été observé lors de l'audit précédent, sans démonstration que c'était l'unique cause.
- La **PR #270**, ouverte et non Draft lors de la vérification du 28/10, modifie déjà des assertions et contrats RAM : éviter tout correctif concurrent.
- Le ruleset GitHub actif consulté le 28/10 impose une PR et des checks, avec **zéro bypass actor** ; la description dans `GITHUB_PROTECTION.md` est périmée sur ce point. Il ne s'agit pas d'un bypass constaté.
- Doctor dispose déjà d'Agent, de Graphify, des commandes `scenario-*`, `test-costs`, des validations adaptatives et de scénarios UI. Les idées proches sont des **pistes d'amélioration de couverture**, non des fonctionnalités absentes présumées.
- Le Guide dispose déjà de plans spécifiques et l'updater d'un plan de mise à jour différentielle. Consulter ces travaux et PR avant toute suite.

## Critères pour promouvoir une seule idée en micro-lot

1. Relever HEAD, branche et état de travail ; lire les règles et les propriétaires canoniques.
2. Vérifier que le problème existe encore et qu'aucune PR ouverte ne le résout.
3. Fournir un cas reproductible ou une mesure, identifier la cause et préserver les invariants.
4. S'inscrire dans l'ordre de la ROAD concernée ; choisir **un seul objectif**, sans nouvelle abstraction injustifiée.
5. Préparer le diff minimum, exécuter les tests ciblés réellement pertinents et inspecter le diff.
6. En PR Draft pendant le développement ; certification sur SHA exact uniquement au stade prévu. Aucun verdict `CERTIFIED` sans preuve indépendante.
7. Si le comportement est déjà correct ou le gain non démontré, **STOP sans modification**.

**Périmètre de cette PR documentaire :** un inventaire unique, aucune modification de code, configuration, roadmap active, CI ou dépendance.
