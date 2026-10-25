# PR #254 — finition du thème Unity en local, sans CI

Ce document complète la spécification 06b. Il ne constitue **ni une certification ni une autorisation de redistribution**.

## État du code
- Le shell peint le fond une seule fois ; chaque racine de page, y compris celles chargées à la demande et les écrans d'attente, conserve la transparence en mode `ATLAS_THEME=dofus_unity`.
- Les cartes, menus, groupes, listes, tableaux, onglets, tooltips, champs et états des boutons partagent la palette Unity ; les anciens noms de widgets et les comportements métier sont conservés.
- Les contrôles à sprites utilisent les variantes normal/survol/appuyé/désactivé, les bordures extensibles et un focus clavier visible ; les sprites restent optionnels et locaux.
- Le fond est chargé et dessiné une seule fois dans le shell, sans déformation des proportions. Si `background_selection_clean.png` est présent à côté de la capture originale, il prend priorité. La capture originale n'est jamais modifiée.
- En l'absence de licence de redistribution, les sprites, captures et TTF extraits du jeu restent exclus de l'export App ; le thème Atlas distribué reste le repli sûr.

## Contrôles locaux à faire avant toute fusion
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
