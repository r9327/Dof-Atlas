# Sources UI DOFUS Unity — PR #254

Ces fichiers sont les **octets réellement fournis dans la conversation**, ajoutés au dépôt Git au 24/10/2026.

- `sources/atlas_unity_background_original.zip` : capture originale 1919×1079 de sélection des personnages, contenant `selection_perso_original.png` (SHA-256 PNG vérifié).
- `sources/atlas_unity_picto_source_01.zip` à `..._09.zip` : **103 PNG originaux sans conversion**, tirés du ZIP `Atlas-UI-Priorite.zip` de l'utilisateur. Les 9 ZIP sont des sous-archives indépendantes car l'API ne permettait pas de téléverser le ZIP de 7,2 Mo en un seul blob. Ils contiennent surtout des ailes d'alignement et fonds de cartes de personnage, **pas les 47 vrais boutons ciblés**.
- `sources/Atlas_UI_Selection_Prete.zip` : référence visuelle des **47 composants UI** et script d'export pour les récupérer. Cette archive **ne contient pas** les 47 PNG originaux ni les 10 TTF. Les originaux résident sur l'ordinateur Windows sous `Documents/Atlas-Dofus-UI-Composants`.
- `sources_manifest.json` : empreintes SHA-256 des archives et inventaire des 103 PNG.
- `docs/plans/guides-2026-10-24/06b-dofus-unity-asset-manifest.csv` : sélection précise des 47 sprites.
- `tools/assets/import_dofus_unity_ui.ps1` : import local des sprites originaux dans un clone de cette PR, sans toucher au jeu.

**Attention aux droits** : ces ressources proviennent de DOFUS Unity et peuvent appartenir à Ankama. Vérifier les autorisations avant toute publication/distribution EXE. Les ZIP présents dans Git ne sont pas encore utilisés par le runtime et **ne constituent pas l'implémentation du thème**. Ne pas déclarer la PR certifiée.

Les PNG sont stockés dans des archives `.zip` pour préserver les octets sans conflit avec `*.png filter=lfs` du dépôt. Lorsque le thème sera construit, mettre en place l'import/l'empaquetage vérifié, ou la gestion Git LFS correcte, plutôt que référencer directement ces ZIP depuis QSS.
