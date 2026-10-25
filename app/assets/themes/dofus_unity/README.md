> **Dépôt public : attention.** Les sprites, TTF et capture de référence sont actuellement consultables dans l'historique Git de ce dépôt public. Les exclure des exports App/EXE ne supprime pas leur diffusion via Git. Un retrait du simple HEAD ne suffit pas : une purge d'historique coordonnée et une décision sur la visibilité du dépôt seraient nécessaires si les droits ne sont pas confirmés. Aucune réécriture de l'historique n'a été effectuée automatiquement.

# DOFUS Unity – assets extractés pour l'étude du thème Atlas

Ce dossier provient du ZIP d'assets originaux fourni par l'utilisateur le 24 octobre 2026 (47 PNG et 10 TTF). Le dossier `sprites` contient 46 textures de composants ; `references/logoDofus.png` est **une référence d'identité uniquement**, jamais un logo de substitution pour Atlas.

Les polices du dossier `fonts` sont les copies extraites du client, **pas** des packages de polices officiellement distribués avec leur licence. Certaines familles (notamment Lexend, Rowdies, Noto Sans, Roboto) existent sous licence OFL dans leurs dépôts officiels, mais la licence des **copies exactes** extraites du jeu et de `NotInter` n'a pas été vérifiée. Avant publication d'un installateur ou synchronisation vers Atlas App, remplacer les copies par les builds amont accompagnés de leur texte de licence, et vérifier les droits de réutilisation des sprites DOFUS, du fond original et du logo.

Ne pas activer ces ressources par défaut dans la distribution publique tant que les droits ne sont pas clarifiés. Ne pas traiter la présence de ces fichiers comme une implémentation ni une certification du thème global.

Références métier : `docs/plans/guides-2026-10-24/06b-theme-dofus-unity-global.md` et `06b-dofus-unity-asset-manifest.csv`.
