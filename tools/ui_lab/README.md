# Dofus Atlas — UI Lab

UI Lab est un outil développeur autonome pour inspecter et capturer visuellement les écrans de Dofus Atlas sans lancer tout le shell de l'application ni parcourir le code.

## Contrat

- Les aperçus `LIVE` instancient les vrais widgets produit.
- Aucune seconde implémentation visuelle de l'application ne doit être créée ici.
- Les données métier canoniques restent lues depuis le dépôt.
- Les fichiers de progression susceptibles d'être modifiés sont redirigés vers un dossier temporaire.
- Les écrans non encore raccordés restent visibles comme `SQUELETTE` afin de montrer la couverture actuelle du catalogue.
- Les captures automatisées doivent être reproductibles : écran, scénario, viewport et délai de stabilisation sont déclarés explicitement.

## Viewer local

Depuis la racine du dépôt :

```powershell
py -3.13 -m tools.ui_lab
```

Le bouton `Capture PNG` reste disponible pour une capture manuelle du widget produit affiché.

## Capture automatisée

La voie canonique pour ChatGPT/CI est :

```powershell
py -3.13 -m tools.ui_lab.capture --request tools/ui_lab/capture_request.json --output-dir artifacts/ui_lab
```

La requête JSON contient la liste des écrans/scénarios à capturer. Le moteur :

1. crée une `QApplication` isolée ;
2. instancie le vrai widget via le registre UI Lab ;
3. redirige les fichiers mutables dans un dossier temporaire ;
4. applique le viewport demandé ;
5. attend la stabilisation du rendu ;
6. enregistre le PNG ;
7. écrit `manifest.json` avec la source, le scénario et le fichier produit.

Le fichier `tools/ui_lab/capture_request.json` est volontairement versionné : le modifier constitue une demande explicite de nouvelles captures pour l'automatisation GitHub.

## Squelette initial

Le premier aperçu `LIVE` est `Encyclopédie > Guide Succès` et instancie directement `GuidesView`.

Les entrées suivantes sont déjà déclarées mais pas encore raccordées : Quêtes, Succès, Bestiaire, Accueil, Organizer, Équipement et Zaap.

## Ajouter un écran ou un scénario

1. Ajouter une factory très fine dans `tools/ui_lab/screens.py` qui instancie le widget produit existant.
2. Isoler tout fichier mutable dans `PreviewContext.sandbox_root`.
3. Passer l'entrée correspondante du registre à `status=LIVE` et renseigner `factory_path`.
4. Déclarer ses scénarios dans `PreviewSpec.scenarios`.
5. Utiliser `PreviewContext.scenario` uniquement pour préparer l'état de démonstration, jamais pour recopier le layout produit.
6. Ajouter ou adapter un test ciblé.

Le but final est que l'agent puisse demander une capture d'un écran/état précis et récupérer directement les PNG produits par la CI, sans action manuelle de l'utilisateur.
