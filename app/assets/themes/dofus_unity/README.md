> **Dépôt public : attention.** Les sprites, TTF et capture de référence sont actuellement consultables dans l'historique Git de ce dépôt public. Les exclure des exports App/EXE ne supprime pas leur diffusion via Git. Un retrait du simple HEAD ne suffit pas : une purge d'historique coordonnée et une décision sur la visibilité du dépôt seraient nécessaires si les droits ne sont pas confirmés. Aucune réécriture de l'historique n'a été effectuée automatiquement.

# DOFUS Unity – assets extractés pour l'étude du thème Atlas

Ce dossier provient du ZIP d'assets originaux fourni par l'utilisateur le 24 octobre 2026 (47 PNG et 10 TTF). Le dossier `sprites` contient 46 textures de composants ; `references/logoDofus.png` est **une référence d'identité uniquement**, jamais un logo de substitution pour Atlas.

Les polices du dossier `fonts` sont les copies extraites du client, **pas** des packages de polices officiellement distribués avec leur licence. Certaines familles (notamment Lexend, Rowdies, Noto Sans, Roboto) existent sous licence OFL dans leurs dépôts officiels, mais la licence des **copies exactes** extraites du jeu et de `NotInter` n'a pas été vérifiée. Avant publication d'un installateur ou synchronisation vers Atlas App, remplacer les copies par les builds amont accompagnés de leur texte de licence, et vérifier les droits de réutilisation des sprites DOFUS, du fond original et du logo.

Ne pas activer ces ressources par défaut dans la distribution publique tant que les droits ne sont pas clarifiés. Ne pas traiter la présence de ces fichiers comme une implémentation ni une certification du thème global.

Références métier : `docs/plans/guides-2026-10-24/06b-theme-dofus-unity-global.md` et `06b-dofus-unity-asset-manifest.csv`.

Le script local `py -3.13 -m tools.assets.clean_unity_wallpaper` prépare
une version dérivée non destructive quand les trois rectangles exacts sont
relevés. Ce PNG dérivé reste une **référence locale non redistribuable**
jusqu'à décision sur les droits. Voir `06c-theme-unity-validation-locale.md`.

**Fond vérifié sur les octets d'origine :** le bandeau des trois icônes
touche le coin haut droit. Utiliser la commande locale
`py -3.13 -m tools.assets.clean_unity_wallpaper --corner-toolbar`
pour générer `background_selection_clean.png` sans modifier l'original.
Ce dérivé est ignoré par Git et exclu des distributions ; l'audit
d'intégrité n'établit aucune licence de redistribution.


## Installation personnelle persistante (sans modifier l'EXE)

Le theme Unity est maintenant la presentation par defaut. Les images et polices
personnelles restent hors de la distribution publique ; leur absence n'empeche
pas Atlas de demarrer et laisse la palette Unity sans fond image.

Depuis un checkout du depot DEV sur le PC Windows (avec Python et Pillow) :

```powershell
powershell -ExecutionPolicy Bypass -File tools/assets/import_dofus_unity_ui.ps1 -InstallPersonalTheme
```

Le script copie les sprites et les polices dans
`%LOCALAPPDATA%\DofusAtlas\themes\dofus_unity`, produit uniquement en
local `background_selection_clean.png` a partir du fond controle (sans
modifier l'original), puis cree `.enabled` seulement si les ressources
attendues sont installees. Les mises a jour EXE ne touchent pas ce repertoire.
Fermer et relancer Atlas pour charger le fond, les sprites et les polices.

La presentation Unity est maintenant la seule interface active. Les anciens
styles restent uniquement des roles de conversion CSS internes, pas un
mode utilisateur alternatif. Le dossier personnel n'entre jamais dans une
Release publique.

En l'absence de copie personnelle, Atlas affiche un degrade bleu nuit/violet
integralement dessine par Qt, pas l'ancienne interface ni une image du jeu.
Le fond personnel nettoye remplace ce degrade des qu'il est present. Le script
d'installation exige maintenant les 46 sprites, les 10 polices et un PNG
nettoye non vide. Si `py -3.13` echoue, il essaie `python` deja installe
(avec Pillow). Aucun test sur le PC de l'utilisateur n'est implicite.
