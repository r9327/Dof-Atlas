# Dofus Atlas — UI Lab

UI Lab est un outil développeur autonome pour inspecter et capturer visuellement les écrans de Dofus Atlas sans parcourir le code ni demander une action manuelle à l'utilisateur.

## Contrat de fidélité

- Les aperçus `LIVE` instancient les vrais widgets produit.
- Pour l'Encyclopédie, une capture d'onglet instancie le vrai `EncyclopediaPage` puis sélectionne le vrai onglet demandé. Elle inclut donc le vrai `QTabWidget`, la vraie barre de recherche, les vrais espacements et le vrai contenu d'onglet.
- Aucune seconde implémentation visuelle de l'application ne doit être créée ici.
- Un scénario peut piloter une API produit existante pour placer l'écran dans un état déterministe, mais il ne doit jamais recopier ou réinterpréter le layout.
- Les données métier canoniques restent lues depuis le dépôt.
- Les fichiers de progression susceptibles d'être modifiés sont redirigés vers un dossier temporaire.
- Les écrans non encore raccordés restent visibles comme `SQUELETTE` afin de montrer la couverture actuelle du catalogue.
- Les captures automatisées doivent être reproductibles : écran, scénario, paramètres, viewport et délai de stabilisation sont déclarés explicitement.
- Si une cible demandée n'existe pas dans les données ou n'est pas ouvrable par l'API produit, la capture échoue : aucune fausse vue de remplacement n'est produite.

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
4. applique éventuellement les paramètres de cible via les APIs produit ;
5. applique le viewport demandé ;
6. attend la stabilisation du rendu ;
7. enregistre le PNG ;
8. écrit `manifest.json` avec la source, le scénario, les paramètres et le fichier produit.

Le fichier `tools/ui_lab/capture_request.json` est versionné : le modifier constitue une demande explicite de nouvelles captures pour l'automatisation GitHub.

## Couverture LIVE actuelle

- `encyclopedia.guides` : vrai `EncyclopediaPage`, onglet `GUIDES` ; scénarios `default`, `guide_first`, `target`.
- `encyclopedia.quests` : vrai `EncyclopediaPage`, onglet `QUÊTES` ; scénarios `default`, `detail_first`, `target`.
- `encyclopedia.achievements` : vrai `EncyclopediaPage`, onglet `SUCCÈS` ; scénarios `default`, `detail_first`, `target`.
- `home` : vraie `HomePage` ; scénarios `default`, `saved_progress`.

Restent à raccorder sans imitation : Bestiaire/Monstres, Organizer, Équipement et Zaap selon leur hôte produit canonique.

## Ciblage précis

Le scénario `target` accepte des paramètres qui pilotent directement les méthodes produit :

```json
{
  "screen": "encyclopedia.guides",
  "scenario": "target",
  "params": {
    "guide_id": "dofus_emeraude",
    "quest_id": 1958
  }
}
```

Pour Quêtes, `quest_id` ouvre directement la vraie fiche de cette quête. Pour Succès, `achievement_id` ouvre directement le vrai détail du succès. Pour Guide, `guide_id` ouvre le guide et `quest_id`, s'il est fourni, ouvre la vraie fiche Quête dans ce guide. Si seul `quest_id` est fourni au Guide, le provider canonique cherche un guide qui référence cette quête.

Le scénario Home `saved_progress` accepte notamment `character_label`, `percent`, `chapter`, `step`, `zone` et `guide_id`, toujours en alimentant la vraie `HomePage` et ses helpers produit.

`output_name` peut être fourni pour nommer explicitement le PNG et éviter toute collision entre plusieurs captures du même scénario.

## Ajouter un écran ou un scénario

1. Ajouter une factory très fine dans `tools/ui_lab/screens.py` qui instancie le widget produit existant.
2. Isoler tout fichier mutable dans `PreviewContext.sandbox_root`.
3. Passer l'entrée correspondante du registre à `status=LIVE` et renseigner `factory_path`.
4. Déclarer ses scénarios dans `PreviewSpec.scenarios`.
5. Utiliser `PreviewContext.scenario` et `PreviewContext.params` uniquement pour appeler des comportements produit existants et préparer l'état demandé.
6. Ajouter ou adapter un test ciblé.

Le but final est que l'agent puisse recevoir « montre l'onglet Succès », « montre la quête 1958 », « ouvre Dofus Émeraude sur telle quête » ou une cible équivalente, demander la capture correspondante à la CI Windows et renvoyer directement le PNG, sans action manuelle de l'utilisateur.
