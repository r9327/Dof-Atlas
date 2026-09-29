# Dofus Atlas — UI Lab

UI Lab est un outil développeur autonome pour inspecter visuellement les écrans de Dofus Atlas sans lancer tout le shell de l'application ni parcourir le code.

## Lancer

Depuis la racine du dépôt :

```powershell
py -3.13 -m tools.ui_lab
```

## Contrat

- Les aperçus `LIVE` instancient les vrais widgets produit.
- Aucune seconde implémentation visuelle de l'application ne doit être créée ici.
- Les données métier canoniques restent lues depuis le dépôt.
- Les fichiers de progression susceptibles d'être modifiés sont redirigés vers un dossier temporaire supprimé à la fermeture du UI Lab.
- Les écrans non encore raccordés restent visibles comme `SQUELETTE` afin de montrer la couverture actuelle du catalogue.

## Squelette initial

Le premier aperçu `LIVE` est `Encyclopédie > Guide Succès` et instancie directement `GuidesView`.

Les entrées suivantes sont déjà déclarées mais pas encore raccordées : Quêtes, Succès, Bestiaire, Accueil, Organizer, Équipement et Zaap.

## Ajouter un écran

1. Ajouter une factory très fine dans `tools/ui_lab/screens.py` qui instancie le widget produit existant.
2. Isoler tout fichier mutable dans `PreviewContext.sandbox_root`.
3. Passer l'entrée correspondante du registre à `status=LIVE` et renseigner `factory_path`.
4. Ne jamais recopier le layout ou le style de l'écran dans UI Lab.
5. Ajouter ou adapter un test ciblé du registre.

Le bouton `Capture PNG` capture uniquement le widget produit actuellement affiché et demande explicitement où enregistrer l'image.
