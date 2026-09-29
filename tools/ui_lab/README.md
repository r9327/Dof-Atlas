# Dofus Atlas — UI Lab

UI Lab est l'appareil photo UI de Dofus Atlas. Il permet à l'agent de charger un vrai écran produit, de le placer dans un état précis, de le rendre sur Windows et de récupérer les PNG sans demander à l'utilisateur de lancer quoi que ce soit.

## Contrat de fidélité

- Les aperçus `LIVE` instancient les vrais widgets produit.
- Chaque aperçu est enveloppé par la vraie navigation de `AtlasWindow` : `build_top_nav()`, sélection du groupe actif et, pour Outils/Stuffs, la vraie sous-navigation produit.
- Pour Encyclopédie et Bestiaire, le Lab instancie le vrai `EncyclopediaPage` puis utilise la logique de regroupement/visibilité de `AtlasWindow.finish_pending_encyclopedia_tab()`.
- Aucune seconde implémentation visuelle de l'application ne doit être créée ici.
- Un scénario peut piloter une API produit existante pour placer l'écran dans un état déterministe, mais il ne doit jamais recopier ou réinterpréter le layout.
- Les données métier canoniques restent lues depuis le dépôt.
- Les fichiers de progression susceptibles d'être modifiés sont redirigés vers un dossier temporaire.
- Si une cible demandée n'existe pas, est ambiguë ou n'est pas ouvrable par l'API produit, la capture échoue au lieu de choisir arbitrairement ou de fabriquer une fausse vue.

## Capture automatisée

La voie canonique pour ChatGPT/CI est :

```powershell
py -3.13 -m tools.ui_lab.capture --request tools/ui_lab/capture_request.json --output-dir artifacts/ui_lab
```

Le workflow `.github/workflows/ui-lab-capture.yml` exécute le rendu sous Windows avec Qt natif, matérialise le catalogue Dofus nécessaire, lance les tests ciblés, génère les PNG et publie l'artefact.

Le fichier `tools/ui_lab/capture_request.json` est versionné : le modifier constitue une demande explicite de nouvelles captures pour l'automatisation GitHub.

## Navigation produit couverte

Le catalogue suit la hiérarchie visible réelle de Dofus Atlas :

- `home` — Accueil.
- `organizer` — Organizer ; le Zaap reste dans Organizer, comme dans le produit.
- Encyclopédie : `encyclopedia.guides`, `encyclopedia.quests`, `encyclopedia.achievements`.
- Bestiaire : `bestiary.dungeons`, `bestiary.monsters`, `bestiary.archmonsters`, `bestiary.wanted`.
- Outils : `tools.crafts`, `tools.world_map`, `tools.treasure_hunt`, `tools.ocre`.
- Stuffs : `stuffs.pvm`, `stuffs.pvp`, `stuffs.builders`.
- `almanax`.
- Tutoriels : `tutorials.default`, `tutorials.dofus_noob`.

Quand le produit lui-même affiche encore un placeholder, le Lab capture ce vrai placeholder au lieu d'inventer le futur écran.

## Ciblage précis et ciblage par nom

Le scénario `target` peut recevoir les IDs canoniques :

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

Il accepte aussi des noms humains :

```json
{
  "screen": "encyclopedia.guides",
  "scenario": "target",
  "params": {
    "guide_name": "Dofus Émeraude",
    "quest_name": "Les principes d'Archie m'aident"
  }
}
```

Quêtes accepte `quest_id` ou `quest_name`. Succès accepte `achievement_id` ou `achievement_name`. Guide accepte `guide_id`/`guide_name` et `quest_id`/`quest_name`. La résolution par nom privilégie une égalité normalisée puis un unique résultat contenant le texte ; plusieurs résultats provoquent une erreur explicite.

Home dispose du scénario `saved_progress` avec notamment `character_label`, `percent`, `chapter`, `step`, `zone` et `guide_id`.

## Guide GPS / Guide Ultime

`encyclopedia.guides` expose en plus des états réels de la vue manuelle canonique :

- `gps_active` — première fiche active/incomplète selon le service produit.
- `gps_page` — page précise, avec `params.page` en base 1.
- `gps_prepare` — première vraie fiche contenant une section `À PRÉPARER`, cadrée directement sur cette section.
- `gps_combat` — première vraie fiche contenant un combat/boss, cadrée directement sur la ligne de combat.

Ces scénarios sélectionnent le vrai `guide_complet`, utilisent `GuideUltimeManualRuntimeService` et pilotent le vrai `GuideUltimeManualView`. Les sections, checkboxes, positions, couleurs, progression, verrouillage et navigation proviennent donc du code produit.

## Vues longues : segments + full

Une capture peut demander :

```json
{
  "capture_segments": true,
  "capture_full_scroll": true,
  "segment_overlap": 80
}
```

Si le contenu dépasse la zone visible, le moteur produit :

- `nom-01.png`, `nom-02.png`, etc. — écrans complets successifs avec chevauchement ;
- `nom-full.png` — assemblage vertical de ces écrans complets.

Le `full` conserve volontairement tout le contexte à chaque segment : vraie barre principale, sous-navigation, colonnes latérales et contenu. Il ne se limite pas à la colonne centrale du scroll.

Si la vue ne dépasse pas l'écran, aucun découpage artificiel n'est créé ; le `-full.png`, lorsqu'il est demandé, correspond simplement au cadre produit complet.

## Viewer local optionnel

Le viewer local reste disponible pour le développement, mais il n'est pas nécessaire au workflow utilisateur :

```powershell
py -3.13 -m tools.ui_lab
```

Son panneau gauche est uniquement le catalogue du UI Lab. Il ne fait pas partie de l'application Dofus Atlas.

## Ajouter un écran ou un scénario

1. Instancier ou piloter le widget produit existant dans une factory fine sous `tools/ui_lab/`.
2. Isoler tout fichier mutable dans `PreviewContext.sandbox_root`.
3. Déclarer la surface `LIVE` dans `registry.py` avec sa vraie hiérarchie produit.
4. Déclarer les scénarios supportés dans `PreviewSpec.scenarios`.
5. Utiliser `PreviewContext.scenario` et `PreviewContext.params` uniquement pour des comportements produit existants.
6. Ajouter le cas dans les tests et, lorsqu'il s'agit d'un état important, dans `capture_request.json` afin qu'il soit réellement rendu sur Windows.

Le résultat attendu est qu'une demande telle que « montre l'onglet Succès », « montre la quête X », « montre Dofus Émeraude sur telle quête », « montre une fiche À préparer » ou « montre un combat du Guide GPS » puisse être satisfaite par des captures réelles, segmentées et complètes si nécessaire, sans action manuelle de l'utilisateur.
