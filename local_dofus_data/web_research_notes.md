# Recherche web - sources Dofus locales

Date: 2026-05-29

## Sources consultees

### D2Data / AnkaBot

URL: https://doc.ankabot.dev/ankabot-pc/methodes/d2data

Ce que la source fournit:
- Acces scriptable aux donnees D2O du client Dofus PC via `d2data`.
- Export JSON d'un D2O avec `d2data:exportD2O("Items")`.
- Lecture directe d'un objet par identifiant avec `d2data:objectFromD2O("Items", id)`.
- Lecture de tous les objets d'un D2O avec `d2data:allObjectsFromD2O("Breeds")`.
- Resolution de textes via `d2data:text(nameId)`.
- Export et lecture de donnees de map avec `d2data:exportMapData(mapId)` et `d2data:mapData(mapId)`.
- Donnees utiles de map: voisins, `SubAreaId`, cellules, `walkable`, `Los`.

Formats disponibles:
- JSON exporte depuis les D2O.
- JSON de map exporte depuis un mapId.
- Objets sous forme de champs heterogenes, souvent structures autour de `Fields`.

Limites:
- Depend d'AnkaBot et de l'etat des fichiers du client local.
- Les exports sont des instantanes, pas une source live garantie.
- La structure exacte varie selon le fichier D2O et la version du jeu.

Utilisation dans ce projet:
- Considerer les exports D2Data comme source d'import placee dans `data/raw/d2data/`.
- Ne pas appeler AnkaBot au runtime.
- Garder les objets inconnus dans `raw_objects`.

### doduda

URL: https://github.com/dofusdude/doduda

Ce que la source fournit:
- CLI pour telecharger et depacker les donnees Dofus 3.
- Conversion des parties utiles en JSON developpeur.
- Commandes documentees: `doduda` puis `doduda map`.
- Les releases `dofusdude/dofus3-main` peuvent fournir des sorties deja generees.

Formats disponibles:
- JSON de donnees Dofus 3.
- Sorties de maps via la commande `map`.

Limites:
- Outil d'import externe, a executer volontairement hors runtime.
- Certains modes peuvent necessiter Docker ou un backend specifique.

Utilisation dans ce projet:
- Les sorties doduda vont dans `data/raw/json/` ou `data/raw/maps/`.
- Import offline ensuite via SQLite.
- Source utile pour Dofus 3 en priorite par rapport a Datafus, qui cible surtout Dofus 2.

### dodumap

URL: https://github.com/dofusdude/dodumap

Ce que la source fournit:
- Librairie/outillage Go pour transformer les donnees brutes de map Dofus en format plus exploitable.

Formats disponibles:
- Pas un format applicatif unique impose par le README; il sert surtout de couche de transformation.

Limites:
- Documentation publique courte.
- A utiliser comme outil de pre-traitement si les maps brutes ne sont pas directement exploitables.

Utilisation dans ce projet:
- Importer ses sorties JSON dans `data/raw/maps/`.
- Ne pas en faire une dependance Python runtime.

### Datafus

URL: https://github.com/bot4dofus/Datafus

Ce que la source fournit:
- Extraction de fichiers Dofus historiques.
- Extraction D2O en JSON.
- Extraction D2I pour traductions/textes.
- Base JSON d'entites statiques.
- Releases contenant des donnees locales.

Formats disponibles:
- JSON de D2O.
- JSON de D2I / traductions.
- Entites statiques.

Limites:
- Depot archive et deprecie depuis Dofus 3.
- Le README indique que Dofus 3 a change la structure des fichiers avec Unity.
- Utile surtout pour compatibilite, tests de schema et donnees Dofus 2.

Utilisation dans ce projet:
- Accepter ses sorties dans `data/raw/d2o/`, `data/raw/d2i/` et `data/raw/json/`.
- Priorite inferieure a doduda/D2Data pour Dofus 3.

### dofusdude / doduapi

URLs:
- https://github.com/dofusdude/doduapi
- https://docs.dofusdu.de/dofus3/v1/
- https://raw.githubusercontent.com/dofusdude/api-docs/main/openapi-3.0.yaml

Ce que la source fournit:
- API encyclopedique Dofus 3.
- Endpoints items: resources, equipment, consumables, cosmetics, quest items.
- Recherche globale, recherche par type, listes paginees et endpoints `all`.
- Schemas utiles: `Recipe`, `Effect`, `Images`, `Condition`, `Resource`, `Equipment`, `Weapon`, `Version`.
- Support multilingue dont `fr` et `en`.

Formats disponibles:
- JSON HTTP selon OpenAPI.
- SDKs generes, dont Python.

Limites:
- Source distante, donc interdite comme source runtime pour cette migration.
- Peut etre utilisee seulement pour synchronisation/import controle.
- Ne couvre pas forcement toutes les donnees bas niveau de maps/cellules.

Utilisation dans ce projet:
- Eventuelle source de comparaison/import manuel, marquee `api_static_import`.
- Les resultats doivent etre persistés localement dans SQLite et exports JSON avant usage par l'app.

### DofusDB

URLs:
- https://github.com/DofusDB
- https://api.dofusdb.fr
- https://dofusdb.fr

Ce que la source fournit:
- Encyclopedie communautaire Dofus avec API publique, site et renderer.
- L'ancien cache local utilise deja `https://api.dofusdb.fr/recipes`.

Formats disponibles:
- JSON HTTP.
- Images via URLs.

Limites:
- Source distante non controlee par le projet.
- Ne doit pas etre source de verite runtime.
- Peut diverger selon version/beta.

Utilisation dans ce projet:
- Garder uniquement les donnees deja cachees/importees localement.
- Toute synchronisation future devra ecrire dans `data/raw/` puis SQLite.

## Decision finale d'implementation

La nouvelle source de verite runtime est `data/local/dofus_data.sqlite`.

Ordre d'import local:
1. Exports D2Data dans `data/raw/d2data/`.
2. Exports D2O/D2I dans `data/raw/d2o/` et `data/raw/d2i/`.
3. Maps/cellules dans `data/raw/maps/`.
4. JSON locaux generiques dans `data/raw/json/`.
5. Cache historique deja present dans `data/raw/legacy/`.
6. Images locales dans `data/images/`.

Regles:
- Aucune API publique n'est appelee au runtime.
- Les donnees inconnues ne sont pas perdues: elles vont dans `raw_objects`.
- La compatibilite avec `session_manager.py` passe par `local_dofus_data.compatibility_adapter`.
- `app/local_data_cache.py` expose un wrapper offline vers l'adapter local.
- Les exports lisibles sont generes dans `data/exports/`.
