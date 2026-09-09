# GUIDE ULTIME — ÉTAT DE REPRISE

Dernière mise à jour : 27 août 2026 (Europe/Paris)

Repo : `r9327/Dofus-Atlas`  
Branche : `feature/guide-ultime-v5-ui`

## STATUT

Le Guide Ultime manuel reste **BUILDING**.

Ne jamais annoncer `Guide terminé`, `STRICT PASS`, `full succès terminé` ou équivalent tant que les audits structurels + QuestProvider + prérequis + couverture + runtime + contrôle manuel n'ont pas tous été exécutés et observés avec succès.

Ne pas lancer GitHub Actions pour valider ce chantier. Les nouveaux tests écrits/modifiés pendant la passe de contenu actuelle n'ont pas été exécutés dans l'environnement ChatGPT courant.

## SOURCE DE VÉRITÉ

- Manifest : `data/routes/guide_ultime_manual/manifest_v1.json`
- Chargeur/composition : `app/modules/encyclopedia/services/guide_ultime_manual_route.py`
- Runtime : `app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py`
- UI : `app/modules/encyclopedia/views/guide_ultime_manual_view.py`
- Verrou canonique : `data/routes/guide_ultime_manual/canonical_lock_v1.json`

## MANIFESTE CANONIQUE ACTUEL

Le manifeste contient actuellement **13 chapitres / 267 macro-fiches**. **267 est un état courant, pas un plafond** : une future optimisation peut augmenter ou diminuer ce total si cela rend réellement le parcours meilleur.

- Incarnam : `incarnam_v2.json` — 9
- Astrub : `astrub_v5.json` — 16
- Pandala accès : `pandala_access_v1.json` — 2
- Amakna 40-60 : `amakna_40_60_v5.json` — 10
- 51-70 : `level_51_70_v4.json` — 7
- 70-100 : `level_70_100_v10.json` — 17
- 100-120 : `level_100_120_v9.json` — 17
- 120-150 : `level_120_150_v20.json` — 37
- 150-170 : `level_150_170_v21.json` — 24
- 171-180 : `level_171_180_v13.json` — 30
- 181-190 : `level_181_190_v15.json` — 24
- 191-200 : `level_191_200_v20.json` — 62
- 200+ : `level_200_plus_v9.json` — 12

Supports : Bonta `bonta_1_100_v17.json`, Ordres 20/40/60/80/100, temporal `temporal_registry_v15.json`, Ocre `ocre_capture_registry_v1.json` + `ocre_final_route_v2.json`, contrats succès `success_contracts_v2.json`.

## VERROU CANONIQUE

Baseline Git actif après les passes sorties Ivoire + DDG/Nébuleux Comte/Vortex :

`d3578f194eb740c2e316a04906a20ec0726b0914`

Ce baseline contient le correctif canonique Comte/Vortex et son test causal ciblé. Le fichier direct `level_191_200_v20.json` est verrouillé sur le blob :

`74c18928c4e8bf4d2b6868d90a09abed88c54131`

Le validateur `tools/audit_guide_ultime_canonical_lock.py` épingle le même baseline. Le lock compare toute la fermeture active à un vrai baseline Git. Ne jamais contourner le contrat par un simple changement de SHA. Le total `267` n'est pas une contrainte de conception.

## VALIDATIONS OBSERVÉES

Dernier gros run historique observé avant les nouvelles réparations de contenu : **252 tests / 252 OK** sous Python 3.13.5.

Les changements/tests suivants sont **écrits mais non exécutés** depuis ce run :

- `tests/test_guide_ultime_fratrie_necronyx_causality.py`
- `tests/test_guide_auto_validation_minimum_quantity.py`
- `tests/test_guide_ultime_nimotopia_ivoire_causality.py`
- `tests/test_guide_ultime_nordalie_prereq_causality.py`
- `tests/test_guide_ultime_ivoire_sylargh_exit_causality.py`
- `tests/test_guide_ultime_ivoire_exit_interactions.py`
- `tests/test_guide_ultime_ddg_nebuleux_exit_causality.py`
- `tests/test_guide_ultime_manual_boss_fusions.py` réaligné sur les versions canoniques v20/v15/v9

Ne jamais utiliser le 252/252 historique comme preuve que ces nouvelles modifications passent.

## DETTES CAUSALES FERMÉES

### Fratrie / Nécronyx / Ébène

- Astrub ferme `Mieux vaut ne pas se fier à la première impression` puis `Aventure miniature` pendant l'unique Kankreblath.
- 70-100 ferme `À plus dans l'muldobus` puis la Fratrie jusqu'à `Sombres desseins`; `Le fléau de Burin` passe réellement par Volkaragnar.
- Niveau200 : `La colère des dieux` → `L'arme fatale` → Nécronyx permanent → trois branches de `Les coeurs livides` → `Le jour des assassins` + `Le piège se referme`.
- Bethel et Solar sont mutualisés avec l'Ébène; leurs coeurs livides sont traités avant sortie.

### Bonta95 — `Faire le mort`

`Le mort dort` + `Faire le mort` sont absorbées dans la campagne Sidimote `L70-10H`. Le contrat d'auto-validation normalise aussi `minimum_quantity`.

### Nimotopia / Ivoire

`La chasse aux chasseurs` est fermée avant `Le bonheur est dans le spray` : six quêtes restantes regroupées dans `L190-09`, un seul Comte Razof, tonneau + dialogue post-boss avant sortie, aucun Razof supplémentaire.

### Nordalie — causalité corrigée

Trois gates externes :

- `Allumer le feu` réellement fermé au niveau100 sur l'unique Meulou partagé ;
- `Malédiction !` réellement fermée dans le prologue DDG ;
- `La garde meurt mais ne se rend pas` exécutée dans `L200-10` pendant le même passage Frigost, avant le Poiskaille fantôme.

Correction majeure supplémentaire : **Tal Kasha appartient aux trois démonstrations de Nordalie avant l'ouverture des quatre missions**.

`L200-10` fait donc désormais :

1. démonstrations Nordalie ;
2. `La garde meurt mais ne se rend pas` + Poiskaille ;
3. Tal Kasha ;
4. **Hem le Maudit parlé AVANT sortie** ;
5. chef ouginak/Cronan ;
6. retour Astrokulda ;
7. seulement alors ouverture de `Le bonheur est dans le spray`, `Une voix de crystal`, `Le mort dans l'âme`, `Le guerrier noir`.

`L200-14` ne contient plus de Tal Kasha : il place le fil de Dardondakal, ferme Hyrkul avec les Centorors, parle à Menalt et termine Nordalie.

### Ivoire — salles de sortie verrouillées

La passe complète des interactions post-boss a confirmé/corrigé :

- Chaloeil : salle secrète + Dardondakal avant sortie ;
- Protozorreur : bénédiction Kidibom avant sortie ;
- Nidas : interactions post-boss déjà conservées ;
- Tal Kasha : Hem le Maudit avant sortie ;
- Anerice : Anerice + Funestaro avant sortie ;
- Nileza : dialogue de `Une voix de crystal` avant sortie ;
- Meno : dialogue de `Une voix de crystal` avant sortie, puis retour via Pichon kloune sans troisième Meno ;
- Sylargh / `Il est temps de mourir` : Nékoléreux instable → destruction du brikoléreux → mort automatique → résurrection → retour Agonie, sans second Transporteur.

### DDG / Nébuleux — Comte et Vortex verrouillés

Le passage Comte final est désormais explicitement séquencé avant toute sortie :

1. Comte unique pour `Le givre des révélations` + `Un comte de faits divers` + Totem Surprise + éclat de `S'armer contre le destin` ;
2. parler au Comte, donner/reprendre la montre enchantée ;
3. cliquer le socle du Dofus des Glaces et prélever le Liquide de la Clepsydre ;
4. reparler au Comte et déclencher la scène Djaul/Jiva ;
5. parler à Djaul pour `S'armer contre le destin` ;
6. prendre/avancer auprès de Jiva `Mille et un jours, un destin` et `Le Dofus des Glaces` lorsqu'ils sont disponibles ;
7. aucun second Comte causé par une interaction de salle finale oubliée.

Le Vortex unique est désormais explicitement séquencé :

1. `La vérité est au fond du puits` + `Les sables du temps` actives avant entrée ;
2. Vortex unique + second éclat de `S'armer` avec le Troisième Œil ;
3. **parler au Vortex dans la salle finale avant toute sortie** pour `La vérité` et suivre la téléportation vers le puits des âmes ;
4. fermer le fil `La vérité` ;
5. revenir devant l'Œil de Vortex **sans refaire le boss** et parler à Tessie Oude pour poursuivre les Égarés / `Les sables du temps` ;
6. aucun rerun Vortex créé par inversion des dialogues post-boss.

### Totems / reruns

Le rerun Koutoulou pour le Totem de peur a été réaudité et **reste causalement justifié** :

- Anerice et Ilyzaelle Ivoire sont consommés avant l'ouverture des Totems ;
- Misère est également combattue avant que `Les totems de Maïmane` puisse être prise ;
- l'Ilyzaelle Valonia est trop tardive, car le Totem de l'équilibre est nécessaire pour continuer `Un héritage tourmenté` ;
- les cinq autres émotions sont absorbées dans les boss DDG post-Totems prévus.

Ne pas supprimer le Koutoulou post-Totems sans nouvelle preuve d'une cible Peur causalement disponible au bon moment.

## SWEEP ANTI-RÉGRESSION

- `test_guide_ultime_nordalie_prereq_causality.py` verrouille Tal Kasha/Hem avant les quatre missions et l'absence de Tal Kasha dans `L200-14` ;
- `test_guide_ultime_ivoire_exit_interactions.py` verrouille les sorties Tal Kasha/Anerice/Nileza/Meno/Sylargh ;
- `test_guide_ultime_ddg_nebuleux_exit_causality.py` verrouille l'ordre de salle finale du Comte, le dialogue Djaul de `S'armer`, puis l'ordre Vortex → puits des âmes → Tessie sans second Vortex ;
- `test_guide_ultime_manual_prerequisites.py` est aligné sur v20/v15/v9 ;
- `test_guide_ultime_manual_structured_domain.py` est aligné ;
- `test_guide_ultime_manual_preview.py` suit dynamiquement le manifeste ;
- `test_guide_ultime_walkthrough.py` est indépendant de cet ordre ;
- `test_guide_ultime_manual_boss_fusions.py` était stale sur v18/v13/v7 dans ses assertions `current` et a été corrigé vers v20/v15/v9 ; ses scénarios historiques v7/v5 restent volontairement historiques.

## AUDITS ENCORE À EXÉCUTER RÉELLEMENT

1. `tools/audit_guide_ultime_manual_transversal_hooks.py --strict`
2. `tools/audit_guide_ultime_manual_prerequisites.py --strict --output artifacts/guide_ultime_prerequisites.json`
3. QuestProvider complet sans `--skip-catalog`
4. `tools/audit_guide_ultime_manual_final_coverage.py --strict --output artifacts/guide_ultime_final_coverage.json`
5. `tools/audit_guide_ultime_manual_runtime.py --strict-fields`
6. audit action quality / action review
7. audit auto-validation contract
8. succès Monde / Monstres / Donjons / Événements hors contrats structurés
9. audit global des reruns boss restant à poursuivre sur Ébène / Nébuleux / DDG
10. audit GPS/micro-walkthrough avec coordonnées actuelles vérifiées
11. walkthrough/UI PySide6 sur checkout complet
12. audit canonical lock réel sur checkout contenant le baseline

## MÉTHODE DE REPRISE

1. Vérifier le HEAD réel de `feature/guide-ultime-v5-ui`.
2. Lire `AGENTS.md` et `DEVELOPMENT_GUARDRAILS.md`.
3. Résoudre les chapitres avant de modifier leur compte ou leur causalité.
4. Chercher `déjà terminé`, `garanti`, `vérifier`, `doit être prêt` et prouver où chaque prérequis est réellement construit.
5. Chercher les interactions de salle de sortie avant de considérer un donjon optimisé.
6. Aucun rerun de boss sans cause explicite ; aucun rerun supprimé si cela casse un ordre causal.
7. Réviser le lock avec un vrai baseline Git contenant données + tests concernés.
8. Ne jamais passer hors `BUILDING` sans PASS réellement observé.

## RÈGLES À CONSERVER

- DPLN prioritaire pour les informations Dofus actuelles ; recouper QuestProvider / données locales et officiel si nécessaire.
- Ne jamais inventer une coordonnée ou un nom de monstre non vérifié.
- Préparer métiers, ressources, pods, aides, captures et timers avant les déplacements.
- Une répétable n'est répétée que pour un objectif réel.
- Progression Quêtes/Succès/Guide = mêmes stores runtime ; aucune seconde vérité de progression.
- Une fiche = une validation globale stable par `manual_stage_id`.

## POINT DE REPRISE COURT

Le Guide contient actuellement **267 fiches, sans plafond imposé**. Les dettes Fratrie/Nécronyx, Bonta95, Nimotopia/Ivoire, Nordalie/Tal Kasha, les sorties Ivoire et les sorties Comte/Vortex sont maintenant fermées causalement. Le rerun Koutoulou Totem de peur reste justifié.

Prochaine étape : poursuivre l'audit des interactions post-boss et reruns **Ébène**, en priorité Dazak/Klime/Koutoulou, puis revenir aux audits complets dès qu'un checkout local complet est disponible.
