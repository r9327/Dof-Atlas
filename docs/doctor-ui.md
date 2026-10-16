# Doctor UI (PR #203)

Entrée unique, explicite et bornée :

```sh
python -m tools.atlas_doctor ui guides --json
python -m tools.atlas_doctor ui guides --select guides-success --mode verify --repeats 2 --json
python -m tools.atlas_doctor ui guides --select guides-lanyel --mode capture --json
python -m tools.atlas_doctor ui guides --mode inspect --json
```

`all` est le défaut : interactions, captures Qt réelles et arbre de widgets de
la même scène. `verify` conserve assertions/arbre sans PNG ; `capture` et
`inspect` produisent `RECORDED`, jamais un PASS fonctionnel. Les anciennes
commandes `capture-ui qt|equipment|encyclopedia|webengine` restent inchangées.

L'exécuteur lance un seul processus Qt offscreen, avec les vrais
`EncyclopediaPage`, `SharedGuideManualView`, `SharedGuideManualCard`,
`LinkService`, services de progression et détail Quêtes. Il charge le catalogue
public local existant ; il ne télécharge rien. Tous les chemins utilisateur et
la progression sont redirigés vers un dossier temporaire. Un catalogue absent
ou un crash natif produit `BLOCKED` ; aucun catalogue fictif de secours n'est
utilisé par les scénarios de production. Les données synthétiques des tests
d'injection sont explicitement limitées aux tests du validateur.

## Couverture V1 et coût

| Scénario | Contrats exécutés |
| --- | --- |
| `guides-success` | Pages canoniques 1/3, lignes et feuille actives, deux dimensions, navigation réelle, destruction Qt, refresh, verrouillage, validation manuelle, isolation personnage, combat, catalogue et changement de guide |
| `guides-lanyel` | Même moteur, pages 1/8 et provenance du guide `dofus_sylvestre` |
| `guide-quests` | Bouton inline réel sur chaque guide, signal exact, onglet Quêtes actif, fin du chargement lazy, bonne sélection et vrai détail visible ; second clic après retour |
| `validator-smoke` | Une page Guide Succès, navigation, progression/verrouillage et retour catalogue ; pas de construction Lanyel |

Les campagnes ne parcourent pas tout le produit. Maximum : 5 répétitions,
120 étapes de preuve, 5 000 widgets par arbre, 32 pages inspectées pour trouver
un combat, 240 secondes par session. Le timeout est imposé par le parent même
si Qt ne rend pas la main. Les contrôles de géométrie utilisent les régions
visibles dans un repère commun, puis scroll et hit-test ; les descendants et
les contrôles normalement hors viewport ne sont pas assimilés à des collisions.
Le texte attendu vient des lignes de la carte canonique, avec le même ordre de
sections et la politique de coordonnées du rendu. Une répétition légitime entre
pages n'est pas une duplication de widgets.

Un inventaire distingue les familles avec oracle des contrôles `NOT_COVERED`.
La qualité sémantique du texte, les liens PNJ/objet/travel, les vrais signaux
Dofus/Npcap et l'EXE Windows installé restent explicitement hors couverture.
Un PASS V1 ne certifie pas ces fonctions ni l'ensemble des pages du produit.

Le parcours étendu peut légitimement être rouge sur un bug du produit. Une
exécution sur le code de départ de #203 a notamment exposé le débordement de la
page de combat Lanyel `dofus_sylvestre:gps:dofus_sylvestre_quest_657:18` : contenu
plus large que le viewport et interaction de combat sans validation observée.
Le validateur ne corrige pas cette page et ne transforme pas son échec en PASS ;
les réparations de guides appartiennent à #201. Les tests d'injection du
validateur et son smoke minimal sont des preuves distinctes de ce parcours.

## Preuves et verdict

Chaque session est conservée dans
`.ai/runtime/atlas_doctor/ui/<sha>-<session>/` (ignoré par Git) :

- manifeste : SHA, clean/dirty, empreinte du diff, Python/PySide6/Qt, plateforme,
  DPI, mode et empreintes SHA-256 des fichiers ;
- `ui_verdict.json` : assertions requises indépendamment de leur exécution,
  couverture, erreurs, limites, durée et verdict ;
- `actions.json` : action, attente, observation, guide/carte, widget source et
  IDs des preuves pour chaque assertion ;
- arbres JSON avant/après et PNG de la même session, aux deux dimensions et
  aux positions de scroll contrôlées ; une surimpression numérotée renvoie à
  `overlay_index` dans l'arbre ;
- log du processus et échantillon borné du traceur Doctor existant sur une
  interaction de verrouillage. Cette trace ne prétend pas couvrir toute la scène.

Les assertions sont `PASS`, `FAIL`, `BLOCKED`, `REVIEW` ou `NOT_COVERED`.
Le verdict exige une liste fixe de contrôles obligatoires par scénario ; un
contrôle omis, un scénario absent, une image manquante ou une preuve modifiée
ne peut pas être accepté comme vert. Les modes sans validation n'ont pas ce
verdict. La réutilisation en CI exige le même SHA, un arbre propre et les
preuves hachées ; une ancienne capture seule n'est jamais réutilisable.

## CI par impact

Le point d’entrée automatique est `Doctor / CI Plan` dans
`.github/workflows/phase-certification.yml`. Doctor appelle le workflow
réutilisable `doctor-ui.yml` selon les consommateurs modifiés. Les moteurs
FAST/FULL restent les autorités de validation ; la sélection n’est jamais une
certification. Voir `PHASE_CERTIFICATION.md` pour le routage PR/main, le cas
documentation seule et les preuves nécessaires avant publication.

Le plan standard-library réutilise le parseur `base...HEAD` de `ci_scope_gate`
et AI Context. Il combine les liens runtime Qt explicitement maintenus avec
les dépendances d'imports AST (y compris imports relatifs). Graphify sert au
préflight structurel, jamais de preuve d'absence de consommateur dynamique.

Le job léger écrit `ui_ci_selection.json` sans installer Qt/LFS. Docs seules,
auditeurs JSON indépendants connus et tests non UI vérifiés donnent
`NOT_APPLICABLE`, avec `tests_executed=false`. Les vues/styles partagés ciblent
les deux guides ; LinkService cible le pont Quêtes ; un changement du
validateur cible ses tests d'injection et un smoke réel. Les scénarios sont
réunis dans une seule session, sans captures en double. Les fichiers inconnus,
suppressions/renommages et cartes d'import incomplètes imposent
`REVIEW_REQUIRED`, jamais un skip implicite.

Windows ne démarre que si le plan sélectionne un scénario. Le verdict final
contrôle le plan, le résultat du job, les assertions fixes, les captures et leurs
empreintes au SHA exact. Un job nécessaire sauté ou échoué bloque le verdict.
`workflow_dispatch` permet de forcer une famille bornée ; il ne contourne pas
une incertitude du plan.

Tests légers sans Qt :

```sh
python -m unittest discover -s tests -p test_doctor_ui.py -v
python -m unittest discover -s tests -p test_doctor_ui_ci.py -v
```

Tests Qt sains/cassés, sans préparation Doduda :

```sh
python -m unittest discover -s tests -p test_doctor_ui_qt.py -v
```
