# PR #254 — finition du thème Unity en local, sans CI

Ce document complète la spécification 06b. Il ne constitue **ni une certification ni une autorisation de redistribution**.

## État du code
- Le shell peint le fond une seule fois ; chaque racine de page, y compris celles chargées à la demande et les écrans d'attente, conserve la transparence en mode `ATLAS_THEME=dofus_unity`.
- Les cartes, menus, groupes, listes, tableaux, onglets, tooltips, champs et états des boutons partagent la palette Unity ; les anciens noms de widgets et les comportements métier sont conservés.
- Les contrôles à sprites utilisent les variantes normal/survol/appuyé/désactivé, les bordures extensibles et un focus clavier visible ; les sprites restent optionnels et locaux.
- Le fond est chargé et dessiné une seule fois dans le shell, sans déformation des proportions. Si `background_selection_clean.png` est présent à côté de la capture originale, il prend priorité. La capture originale n'est jamais modifiée.
- En l'absence de licence de redistribution, les sprites, captures et TTF extraits du jeu restent exclus de l'export App ; le thème Atlas distribué reste le repli sûr.

## Préflight local reproductible — sans lancer de CI

La commande suivante vérifie la présence et la syntaxe des fichiers concernés,
la propreté des changements Git suivis, relève le SHA exact, et exécute en
processus isolés les tests d'intégrité PNG, de packaging et d'export. Elle
contourne volontairement l'import global `tests/__init__.py` (qui requiert
PySide6 même pour les tests standard library). Elle **n'exécute aucune
GitHub Action** et écrit un rapport JSON avec les contrôles exécutés ou non.

```powershell
py -3.13 -m tools.assets.unity_pre_ci --report artifacts/unity-pre-ci.json
```

Sur Windows après installation des dépendances PySide6, pour inclure les
tests Qt offscreen et l'audit d'intégrité réel des assets :

```powershell
py -3.13 -m tools.assets.unity_pre_ci --qt --assets --report artifacts/unity-pre-ci-full.json
```

Pour un préflight d'intégration, épingler le SHA exact affiché en tête
de la PR (et non celui lu automatiquement dans la copie locale) :

```powershell
py -3.13 -m tools.assets.unity_pre_ci --qt --assets --expect-sha "COLLER_SHA_40_CARACTERES_DE_LA_PR" --report artifacts/unity-pre-ci-full.json
```

La vérification `git_revision` échoue en cas de SHA erroné, obsolète ou
mal formé ; le rapport JSON contient le SHA attendu et celui observé.
Un résultat `PASS` est **uniquement** un feu vert pour la portée des
contrôles locaux. Le JSON comporte explicitement les limites de couverture :
il ne certifie ni les droits, ni les captures de moniteurs physiques, ni
l'installateur/EXE, ni les workflows CI. Le lanceur a été testé sur un
dépôt synthétique propre et deux cas d'échec contrôlés ; ce succès de fixture
n'est pas un verdict du code Atlas complet.

## Fond source authentique — audit local du 25 octobre 2026

L'archive originale fournie a été retrouvée et vérifiée **hors CI**.
Le fond PNG 1919×1079 correspond exactement au SHA-256
`3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb`.
Les 46 sprites, le logo de référence et les 10 TTF ont pu être relus depuis
l'archive d'assets : **48 PNG ont des chunks/CRC valides**, et les 10 fichiers
de police ont une signature TrueType valide. Il s'agit d'un audit
d'intégrité local, **pas d'une revue des licences**.

Constat important sur la capture : les trois icônes partagent un fond sombre
continu, collé **aux bords supérieur et droit** du PNG. Les trois
rectangles intérieurs proposés initialement ne conviennent pas : ils laissent
le fond sombre et la troisième icône en bord d'image. Le réparateur accepte
désormais la zone commune exacte du PNG dont le SHA est vérifié :

```powershell
py -3.13 -m tools.assets.clean_unity_wallpaper --corner-toolbar --preview artifacts/unity-mask-review.png
```

Ce mode emploie le rectangle contrôlé `(1818, 0, 101, 39)` et une
interpolation **depuis les bords gauche et bas seulement**, car les deux
autres bords ne possèdent pas de pixels voisins. L'exécution locale sur
la vraie capture a réussi : seule la zone `(1818, 0)–(1919, 39)` change,
l'original reste inchangé. Le résultat est une **référence locale**,
non distribuée via Git ou l'EXE, et doit encore être jugé visuellement
sur le poste cible. Les tests Python, y compris le rectangle de bord
sur ciel synthétique, sont au vert (5 tests).

## Nettoyage local du fond Unity (sans modifier l'original)

Le réparateur `tools/assets/clean_unity_wallpaper.py` (Pillow déjà épinglé
dans les dépendances Windows) est prêt et testé sur un ciel synthétique avec
trois icônes artificielles. Il accepte soit **une zone de bandeau en
coin**, soit trois masques intérieurs, et confirme le SHA-256
canonique de la capture 1919×1079 avant toute opération. Il reconstruit
localement le ciel à partir des quatre bords de chaque zone, sans toucher
aux pixels en dehors des zones ni au PNG d'origine.

Pour ajuster manuellement le bandeau de coin par glisser-déposer,
depuis la racine du dépôt Windows, exécuter :

```powershell
py -3.13 -m tools.assets.clean_unity_wallpaper --interactive --preview artifacts/unity-mask-review.png
```

Une fenêtre ouvre la zone supérieure droite de la capture à résolution
native. Glisser **un rectangle englobant tout le bandeau** jusqu'aux
bords supérieur et droit, ou trois rectangles intérieurs, puis valider.
La fenêtre
refuse une sélection hors limites ou chevauchante ; « Quitter sans
enregistrer » ne génère aucun dérivé. Le mode console avec trois `--box
x,y,w,h` reste disponible pour la reproduction exacte de la retouche.
Les tests de sélection (coordonnées inversées/clampées) et de réparation
sur ciel synthétique passent localement ; l'interface graphique elle-même
n'est pas testée sous Windows ici.

Le résultat est un PNG local `background_selection_clean.png` utilisé en
priorité par le thème Unity. **Examiner la capture et la réparation avant
utilisation** ; l'interpolation de ciel n'est pas une garantie de suppression
invisible sur n'importe quelle texture. Ne pas publier ce dérivé dans Git
ou un EXE tant que les droits des assets DOFUS ne sont pas confirmés.
Aucun rectangle n'a été inventé, et aucune retouche de la vraie image
n'est revendiquée ici faute d'accès aux octets originaux.

## Contrôles locaux à faire avant toute fusion

### Sonde locale réelle des cycles Qt (sans GitHub Actions)

Sur Windows, une fois les dépendances **déjà prévues** par le dépôt installées, cette commande ouvre les vrais widgets Encyclopédie/Guides en environnement utilisateur temporaire isolé, clique la carte puis le vrai bouton de retour du Guide. Elle répète ce parcours 30 fois, relève le nombre de QWidget et le working set résident Windows (incluant éventuellement des pages partagées), capture trois PNG Qt et écrit un JSON. Elle **ne valide ni l'EXE ni le rendu sur des moniteurs physiques**.

```powershell
$env:ATLAS_THEME = "dofus_unity"
Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
py -3.13 -m tools.assets.unity_local_cycle_probe --output artifacts/unity-local-100
$env:QT_SCALE_FACTOR = "1.25"
py -3.13 -m tools.assets.unity_local_cycle_probe --output artifacts/unity-local-125
$env:QT_SCALE_FACTOR = "1.5"
py -3.13 -m tools.assets.unity_local_cycle_probe --output artifacts/unity-local-150
Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
Remove-Item Env:ATLAS_THEME -ErrorAction SilentlyContinue
```

Les captures proviennent de vraies vues Qt, **pas d'une maquette**. La sonde consigne également la croissance du nombre de QWidget après cinq cycles d'échauffement : si elle dépasse 5, elle rend `WIDGET_GROWTH` et échoue. Les écarts de mémoire restent des mesures à examiner, pas une certification automatique. L'état écrit `MEASURED_NOT_CERTIFIED` signifie seulement que les cycles ont été exécutés ; il faut examiner les graphiques/valeurs et les vrais affichages Windows. `QT_SCALE_FACTOR` simule la mise à l'échelle Qt en offscreen et ne remplace pas une vérification sur moniteurs 100/125/150 %.

Audit d'intégrité des ressources (local et sans Qt/CI) :

```powershell
py -3.13 tools/assets/inspect_unity_assets.py --json
```

L'audit vérifie les en-têtes PNG, les CRC de **tous** les blocs, la présence des blocs IDAT/IEND, les tailles, la présence de transparence, les doublons éventuels et l'identité SHA du fond original. Il n'est **pas** un contrôle des licences, du rendu visuel ni du décodage complet des PNG.

Sur Windows, après installation des dépendances déjà prévues par le projet, depuis la racine du dépôt :

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
py -3.13 -m unittest -v tests.test_unity_skin tests.test_distribution_export tests.test_guide_library_home tests.test_guide_home_two_columns
Remove-Item Env:QT_QPA_PLATFORM
$env:ATLAS_THEME = "dofus_unity"
py -3.13 main.py
```

Observer le **vrai** QWidget sur fenêtres normale, réduite et agrandie, aux DPI 100 %, 125 % et 150 %. Capturer l'accueil, les Guides et les pages du shell ; vérifier que les surfaces ne masquent pas le fond, que les cartes restent lisibles et que souris, hover, pressed, disabled, focus et navigation clavier fonctionnent. Refaire trente fois Accueil → Guide Succès ou Sylvestre → retour, puis mesurer nombre de widgets encore vivants et mémoire RAM. Examiner l'installateur/EXE réel, et non une simple liste de fichiers.

## Blocages extérieurs au code
1. **Nettoyage du fond :** le dépôt contient la capture originale avec les trois icônes natives. La priorité du dérivé est implémentée, mais un fichier `background_selection_clean.png` réellement retouché et visuellement vérifié doit être fourni pour les supprimer sans reconstituer au hasard le ciel. Ne jamais écraser l'original.
2. **Droits :** la présence des assets dans Git ne confère aucun droit de redistribution. Les sprites et la capture requièrent les autorisations appropriées ; remplacer les TTF extraits par des builds amont légalement redistribuables, avec fichiers de licence vérifiés. Ne pas copier le logo DOFUS dans l'identité Atlas.
3. **Preuves :** aucun contrôle Qt/Windows, DPI, RAM, EXE ni certification exacte du SHA final n'est déclaré PASS sans exécution et artefacts correspondants.

Ne pas fusionner cette PR tant que ces points ne sont pas validés ou que le périmètre n'a pas été officiellement réduit. Aucun workflow GitHub Actions/Doctor n'est lancé dans le cadre de cette intervention.
