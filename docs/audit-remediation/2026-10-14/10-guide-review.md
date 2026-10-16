# [PLAN 10] Revue Guide : 141 observations, 200 prérequis, UI et images

> **Implémentation et revue nominative du 16 octobre 2026.** Les 341 remarques
> sont rapprochées des étapes et IDs actuels. Une décision de revue ne constitue
> pas une preuve de parcours en jeu : les 200 avertissements GP restent actifs.

## Travail réalisé

- [Registre des 341 décisions](10-guide-decisions.json), sans IDs supprimés :
  86 remarques de présentation corrigées, 18 conditions de gameplay conservées
  avec une justification propre, 37 références/consignes encore à revoir et
  200 avertissements d'ordre ou de critère à confirmer sur un parcours réel.
  Les 200 quêtes GP sont toutes reliées à leur ID dans le catalogue actuel.
  Le registre inclut les prérequis, critères bruts et preuves d'ordre disponibles.
- Les sources proviennent du dataset public versionné `3.7.10.10`, fingerprint
  `71082672c6e4bc43b6c4f529702a26483cb80b4cb50c1c0a227957768274d2af`,
  audité dans #172. L'audit actuel conserve zéro erreur dure et 200 warnings GP.
  Ils ne deviennent ni PASS ni autorisation de réordonner une route canonique.
- La politique de présentation déjà canonique remplace les termes techniques
  « runtime », « blocker », « rerun », « cleanup », « pending »,
  « startCriterion » et « walkthrough » par des libellés joueur. Seules deux
  notes exactes exclusivement destinées aux auteurs sont masquées, sur les
  cinq occurrences constatées. Les avertissements gameplay restent visibles.
  Aucun JSON de route, nom de quête, ID, progression ou ordre n'est modifié.
  L'audit de formulation passe de 141 à 55 remarques, dont les 18 conditions
  opportunistes/état de quête et 37 références encore signalées.
- PC-06 confirmé sur une vraie image PNG et sa copie tronquée : la signature
  est valide dans les deux cas, le décodage échoue sur la copie. L'audit accepte
  maintenant `--decode-images`, réutilise le décodeur borné de l'application et
  signale une erreur critique de décodage. Le mode léger reste explicitement
  `SIGNATURE_ONLY` ; une signature et un pointeur LFS ne prouvent pas le rendu.
- PC-08 : scénario avec le vrai `QuestProvider` (>1 900 quêtes), le service
  manuel canonique (267 fiches) et la fiche longue `P200-23`, aux tailles
  900×600 et 1180×720. Vérifications : largeur du contenu, absence de débordement
  horizontal, défilement PageDown, accès/focus du bouton Suivant et une seule
  fiche rendue. Exécution locale Qt offscreen PASS ; le résultat Windows
  exact-SHA est fourni par la CI, distinct du bureau interactif et du jeu.

Graphify 0.9.72 a été généré sur le candidat propre
`7b03fc92fa5b26621b1cf307926acee422b1f2ac` avant modification ; les 61 nœuds et
275 arêtes liés aux propriétaires de présentation/audit/décodage ont été
examinés puis confrontés aux appels actuels. Les tests protègent les données
source inchangées, les IDs, les avertissements réels et les probes bornées.

## Limites encore ouvertes

Les warnings ne sont pas tous des bugs. Les macros regroupent parfois des
quêtes sans démontrer leur ordre d'exécution dans les seuls champs joueur.
Le tutoriel guidé, les branches conditionnelles, `PZ=1` et `Qo=18502` ne sont
pas réinterprétés à partir d'une hypothèse. Le registre garde les preuves
manquantes et la responsabilité de validation native dans #175.

Les 37 objectifs de succès conservés dont la cible brute est absente restent
des observations du registre de #172 : aucune donnée de jeu n'est fabriquée
pour les remplir. Le décodage de l'ensemble des images et une campagne
interactive avec personnages réels exigent leurs ressources/environnement ;
les tests ciblés décrits ici ne prétendent pas avoir joué ces parcours.

**Référence audit :** PR #160, main audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Mission
Faire le triage exhaustif des 141 notes de formulation et 200 avertissements de prérequis contre données canoniques et parcours Guide réel, puis corriger seulement les anomalies prouvées.

## Couverture sans doublons
141 observations Guide GA, 200 avertissements GP, PC-06 et PC-08

## Sources à lire
- registres/guide-ga.json et guide-gp.json dans l'archive #160
- app/modules/encyclopedia/views/shared_manual_guide_view.py:588
- app/modules/encyclopedia/tools/audit_quests_guides.py:848
- Guide/Quêtes/Succès actifs, canonical_lock et datasets nécessaires

## Enchaînement de vérification
1. Relier chaque remarque GA/GP à un ID stable de guide/quête/succès et à la version exacte-SHA, sans assimiler un warning à un bug.
2. Trier toutes les 141 remarques et 200 avertissements : erreur prouvée, à confirmer, comportement voulu ou faux positif ; capturer preuve minimale.
3. Exécuter des scénarios réels de guides longs et scrolling/focus/accessibilité aux tailles Windows 900×600 et 1180×720 ; PC-08 reste NON CONFIRMÉ avant ces tests.
4. Prober la corruption d'images réelles modifiées et distinguer un en-tête valide d'un décodage effectif ; PC-06 reste NON CONFIRMÉ.
5. Pour toute correction Guide, protéger les chemins d'identité et les verrouillages canoniques ; ne pas rouvrir le contenu métier sans preuve.
6. Documenter les items bloqués par données Doduda raw absentes plutôt que les déclarer PASS.

## Critères de sortie
- [x] 341 remarques individuellement triées, avec IDs et décisions, y compris les preuves encore à confirmer
- [x] Aucun ajustement de route/ordre manuel ; tests d'intégrité Guide conservés
- [x] UI et décodage testés sur scénarios ciblés ; limites interactives explicites
- [x] Registre et tests consultables ; FULL finale seulement après stabilisation du code

## Dépendances
Coordonner avec #161 pour les succès d'alignement, #164 pour le shell UI, #172 pour les données raw ; ne pas fusionner Guide renderer.

## Méthode commune
- Commencer par HEAD réel et git status. Ne pas inventer de défaut à partir d'un graphe inferred.
- Diff minime, test ciblé, vérification des consumers et impacts, AI Context régénéré après code.
- Conserver les contrats JSON, la progression utilisateur et le lazy-loading ; no FULL en boucle.
- Aucun merge tant que corrections effectives et preuves exact-SHA n'existent.

[Rapport](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) | [Index des preuves](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/README.md).
