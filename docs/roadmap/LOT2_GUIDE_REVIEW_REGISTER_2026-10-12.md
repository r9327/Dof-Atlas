# Lot 2 — Registre des 18 conditions à qualifier

Source : artefact certifié du lot 1 `phase-certification-38268360659-1`, fichier `action_quality.json`, SHA de production `9c32a0130f83de74c5510631d6447dc5450e7ec8`. Ce relevé **n'est pas un nouvel audit** du HEAD du lot 2.

Les 18 détections ci-dessous sont des **observations de rédaction**, pas 18 bugs prouvés. Tant que l'état réel du personnage, les prérequis QuestProvider et la branche narrative ne sont pas reproduits, le statut est `UNVERIFIED`. Aucune déclaration `TRUE` / `FALSE` n'est déduite du seul mot « si nécessaire ». Aucune modification automatique du manifest, des locks ou des scripts de route.

| # | Fiche | Observation | Nature plausible | Preuve nécessaire | État |
| ---: | --- | --- | --- | --- | --- |
| 1 | `INC-04` | 5 Viandes Intangibles « si possible » | Stock de quête / exigence de sortie | Vérifier si le stock est obligatoire avant de quitter la forêt | `UNVERIFIED` |
| 2 | `INC-06` | Aléha / Espoirs et tragédies « si nécessaire » | Progression conditionnelle | Établir l'état de quête exigé par la macro-fiche | `UNVERIFIED` |
| 3 | `INC-08` | La Halte Efkat « si nécessaire » | Craft conditionnel | Définir quand le craft doit être exécuté ou déjà possédé | `UNVERIFIED` |
| 4 | `INC-08` | Bounihimée « si nécessaire » | Craft conditionnel | Définir quand le craft doit être exécuté ou déjà possédé | `UNVERIFIED` |
| 5 | `AST-03` | Rathrosk / Ça sent le gaz « si nécessaire » | Rendu conditionnel | Rendre explicite l'état antérieur et la condition de retour | `UNVERIFIED` |
| 6 | `AST-15` | Le rebelle de la forêt « si nécessaire » | Rendu conditionnel | Prouver le prérequis de clôture Astrub | `UNVERIFIED` |
| 7 | `L70-07` | Combat longue distance « si nécessaire » | Combat conditionnel | Identifier l'état déclenchant le combat | `UNVERIFIED` |
| 8 | `L100-01` | Trois bandits « si nécessaire » | Combat conditionnel | Déterminer si victoire et écailles sont déjà acquises | `UNVERIFIED` |
| 9 | `L120-00` | La terre banquise « si nécessaire » | Prérequis conditionnel | Vérifier obligation avant La maire de glace | `UNVERIFIED` |
| 10 | `L120-19` | Foluk / futur passage « si nécessaire » | Arc ultérieur conditionnel | Vérifier l'ordre causal sans avancer Foluk | `UNVERIFIED` |
| 11 | `L150-16V` | Voyage, voyage « si nécessaire » | Arc transversal | Identifier si quête déjà fermée lors de l'entrée Enutrosor | `UNVERIFIED` |
| 12 | `L171-02` | Le disparu « si nécessaire » (prise) | Rendu conditionnel | Vérifier clôture avant Rendez-vous avec la mort | `UNVERIFIED` |
| 13 | `L171-02` | Le disparu de Sufokia « si nécessaire » (route) | Rendu conditionnel | Comparer les deux mentions au même état de quête | `UNVERIFIED` |
| 14 | `L180-13S` | Tour de force « si nécessaire » | Rendu conditionnel | Définir condition de prise de Tour nage | `UNVERIFIED` |
| 15 | `L190-08` | Passe Estitch « si nécessaire » | Objet conditionnel | Définir acquisition préalable ou achat | `UNVERIFIED` |
| 16 | `L200-15` | Équipement adapté « au besoin » | Préparation de combat | Contrôler exigences de mobilité contre Hyrkul | `UNVERIFIED` |
| 17 | `L200-15E6` | Nécronyx « si nécessaire » | Sort conditionnel | Vérifier présence du sort avant Tour de Solar | `UNVERIFIED` |
| 18 | `P200-25` | 2–3 Gnauls « si possible » | Conseil de combat non bloquant | Ne pas transformer conseil tactique en prérequis ferme | `UNVERIFIED` |

Bilan source du même run : `action_quality` 0 erreur dure, 141 avertissements (18 conditions et 123 formulations d'auteur) ; `prerequisite_order` 0 erreur dure, 199 avertissements (172 ordres intra-fiche non démontrés, 19 routes conditionnelles, 6 quêtes actives même fiche, 2 critères opaques). Le statut « aucun bug confirmé » signifie uniquement que l'audit **n'a pas produit de preuve de défaut dur**, pas que toute instruction a été vérifiée fonctionnellement.

**Suite de validation :** réexécuter les audits canoniques avec le catalogue sur le SHA final de certification ; conserver les sorties JSON et la distinction `PROVEN_DEFECT` / `UNVERIFIED`. Revoir les instructions avec leur contexte avant tout changement narratif.
