# PR #310 — Exploitation par occurrence des alertes Doctor

**Méthode :** exploitation du rapport Doctor `full_scope.json` en conservant son SHA Git, tous ses chemins, sa provenance, ses pointeurs JSON, ses ambiguïtés et l'intégralité de la liste des candidats. **Une classification automatique n'est pas une preuve de correction ni une décision de suppression.**

## État de référence : run 41213928382, source Git 7700b906d26be9aee3568977a8cf6b4d808c9245

- **1 583 références candidates**, chacune dans `worklist/link_reviews.csv`. Sous-groupes : **536** images de métadonnées Quêtes, **194** références vers preuves de construction, **92** sources de cartographie historiques, **315** autres références des modules `app/`, **280** outils, **58** dans les JSON de données, **53** scripts Windows, **29** motifs glob, **25** chemins utilisateur/installation, **1** endpoint de release. Les classes et leur somme sont vérifiées par CI, sans faire disparaître les références source originales.
- **33 400 ressources sans consommateur statique** dans `worklist/asset_reviews.csv` : **33 240 EXCLUDED** et **160 INCLUDED** selon `scripts/windows/export_app_repository.py:selected_runtime_path`. Ce contrôle prouve exclusivement le choix du miroir App, **pas** les contenus de l'installateur, du pack en release ou leur utilisation dans le processus Atlas.
- Les **160 fichiers inclus** demandent un soin particulier : `replacement_drafts` contient des routes Ganymède potentiellement utilisées dynamiquement par `app/modules/encyclopedia/services/guide_ganymede_cutover.py:select_verified_replacement_path`. Ce lecteur construit les chemins à partir des identifiants et des manifests. Un scanner de chaînes littérales les laisse donc orphelins alors qu'ils peuvent être nécessaires au fonctionnement.
- Fichiers `*_observed_links.json`, `*_action_candidates.json`, `*_evidence.json` : traces de construction Ganymède **à qualifier au niveau génération/packaging**, non supprimées. Portraits de classes et routes manuelles : à préserver en l'absence de preuve de remplacement et de parité UI.
- Contrat de scan : aucune décision `FIXED_VERIFIED` / `KEEP_VERIFIED` ne se déduit d'une catégorie, du seul nom de fichier ni de la liste blanche. Colonnes `review_status`, `reviewer_decision`, `evidence` et `packaged_in_exe_verified` permettent de distinguer le tri automatique de l'examen réel.

[Run et artefacts sources 41213928382](https://github.com/r9327/Dof-Atlas/actions/runs/41213928382) : `full_scope.json`, `worklist/link_reviews.csv`, `worklist/asset_reviews.csv`, `worklist/summary.json`. **La CI reconstruit ces quatre fichiers pour chaque nouveau HEAD** ; elle vérifie les cardinalités et refuse toute liste tronquée.

## Travail de réparation encore ouvert, sans exception silencieuse

| Contrat / famille | Décision déjà étayée | Preuve requise pour clôturer |
|---|---|---|
| Ganymède `replacement_drafts` | Sélecteur dynamique réel confirmé, suppression **interdite** sans analyse des dépendances | Test runtime de sélection, cohérence manifest/route, progression manuel, intégrité Windows App |
| 160 fichiers inclus au miroir | Inclusion déterminée par la liste blanche, revue source en cours | Mesure du poids réel, dépendances + contenu dans le paquet livré |
| 33 240 fichiers exclus du miroir | Exclusion par cette liste blanche uniquement | Vérifier les autres packs/EXE et les consommateurs dynamiques avant tout nettoyage |
| 536 métadonnées image Quêtes | Référence de provenance, pas nécessairement un fichier local | Contrat de source, correspondance ID→image affichée, tests de rendu |
| 194 liens rapports d'audit | Références documentaires de génération | Ne pas les résoudre comme fichiers distribués sans contrat explicite |
| 92 chemins cartographiques historiques | Provenance distincte des champs actifs `asset_path` | Test des vraies images actives, validité image et taille ; une vue Astrub manquante demeure ouverte |
| 760+ références non classées au scan de départ | Réparties par propriétaire `app/tools/scripts/data`, motifs et état utilisateur | Contrats runtime individuels, pas de correction massive des chemins |
| AST 213 groupes, exceptions 253 | Signaux non qualifiés dans ce lot | Analyse cas par cas, origine, effet réel, tests avant et après |
| RAM, UI, Graphify, release | Non certifiés par ce scan | Bench sur bon SHA, test Windows distribué et verdict global |

## Règles de certification

1. Une entrée ne passe `FIXED_VERIFIED` qu'avec correctif, SHA et test correspondant ; `KEEP_VERIFIED` exige un consommateur et un invariant établis.
2. Toute donnée de production consommée dynamiquement est conservée. Les références générées/externes restent traçables, même si l'audit ne prouve pas leur présence dans le dépôt.
3. Le rapport doit correspondre à l'**exact SHA** testé ; les nouveaux commits invalident les conclusions de certification antérieures.
4. Aucun export de listes candidates n'est une autorisation de suppression. La PR #310 reste en Draft jusqu'à preuve Windows/bench/Graphify finale.


## Durabilité des vérifications individuelles

Le générateur `tools/doctor_candidate_worklist.py` conserve un identifiant stable pour une même occurrence `(source, ligne/pointeur JSON, texte, type, occurrence locale)`. Une nouvelle alerte insérée dans un autre fichier **ne doit pas renuméroter tous les constats existants**. Les doublons réellement distincts conservent des identifiants différents. Deux tests de non-régression couvrent ces cas.

Les preuves doivent toujours être contrôlées à l'exact SHA de la source ; la stabilité d'un ID ne suffit pas à conserver un statut « validé » après changement de code. Les candidats sans preuves restent `OPEN_REQUIRES_RUNTIME_OR_CONSUMER_EVIDENCE` ou `OPEN_REQUIRES_RUNTIME_OR_PACKAGING_EVIDENCE`.

**Point à ne pas perdre :** le commit #303 `661890a7` ajouté pendant le développement est inclus dans la branche #310 par un merge commit `8e58028a`. Toute nouvelle avance de #303 impose une nouvelle réconciliation et de nouveaux checks sur l'HEAD réellement fusionnable. La revue sémantique, les mesures RAM, Graphify et l'EXE complet restent des travaux ouverts.
