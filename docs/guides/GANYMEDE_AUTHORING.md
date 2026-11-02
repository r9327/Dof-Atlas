# Ganymède — vrai contenu local, contrat d'intégration

**Objectif produit : 95 parcours jouables, 7 705 étapes dans l'ordre des sources.**

Les fichiers `ganymede_*_observed_links.json` sont des preuves factuelles
(coordonnées, identifiants et liens). **Ce ne sont pas des consignes de jeu** :
ils ne débloquent plus la validation manuelle du lecteur non natif.

Les 20 `replacement_drafts/cutovers/*.json` sont des lecteurs de séquence
actifs, mais leurs actions dérivées ne certifient pas un suivi complet des
objectifs Ganymède. Ces données ne comptent donc pas comme 20 routes
éditoriales finalisées dans l'audit ci-dessous.

## Contrat des consignes rédigées

Créer, pour chaque parcours réellement vérifié et dont les droits de
redistribution sont établis, un fichier
`data/encyclopedia/guides/ganymede_<source_guide_id>_instructions.json` :

```json
{
  "schema_version": 1,
  "source_guide_id": 1234,
  "source_url": "https://ganymede-app.com/guides/1234",
  "expected_source_step_count": 2,
  "rights_basis": "atlas_original",
  "steps": [
    {
      "source_step_number": 1,
      "title": "Titre court d'une étape effectivement vérifiée",
      "instructions": "Explication originale de ce qu'il faut faire.",
      "actions": [
        {
          "kind": "travel",
          "text": "Destination vérifiée par le rédacteur",
          "coordinates": [1, -2]
        }
      ]
    },
    {
      "source_step_number": 2,
      "title": "Autre étape vérifiée",
      "instructions": "Seconde consigne rédigée et contrôlée.",
      "actions": [
        {
          "kind": "talk",
          "text": "Dialogue avec le PNJ vérifié"
        }
      ]
    }
  ]
}
```

*Les valeurs ci-dessus sont un exemple de contrat, pas une vraie route Dofus.*

**Règles :**
- Identité, URL, nombre d'étapes et ordre strictement égaux au catalogue public.
- Chaque étape possède un titre, une instruction rédigée et des actions
  typées, avec les coordonnées vérifiées si nécessaires. `quest_link` ne
  remplace pas une action `talk`, `fight`, `interact`, etc.
- Un seul fichier incomplet, un type d'action inconnu, un texte `TODO` ou
  une étape hors ordre : toute la route est rejetée, sans fallback aux
  anciennes quêtes.
- `rights_basis` vaut `atlas_original` si rédaction originale, ou
  `redistribution_permission` quand une permission de diffusion existe
  **et a été vérifiée par le responsable**. En cas de redistribution, les
  champs `permission_reference` et `attribution` sont obligatoires. Leur
  présence est une preuve déclarative, pas une vérification juridique
  automatique. Ne pas importer des textes communautaires sans droits.
- Le lecteur charge une seule route au clic (pas de chargement des 7 705
  étapes en RAM à l'accueil). Sans consignes, les relevés restent
  consultables mais leur case de validation est désactivée.
- Ne jamais modifier les deux grands guides optimisés `guide_complet` et
  `dofus_sylvestre`, ni restaurer les archives legacy dans le runtime.

## Preuve et certification

```powershell
py -3.13 -m tools.audit_ganymede_instruction_coverage --strict
py -3.13 -m unittest tests.test_ganymede_local_instructions tests.test_ganymede_instruction_coverage
```

Le premier contrôle ne passe **que si les 95 guides possèdent toutes leurs
étapes rédigées et structurées**. Il doit être complété par une revue humaine
des actions/positions, par les tests Qt/Windows, et par le benchmark Doctor au
HEAD exact. Avoir un JSON valide n'est pas une preuve que les actions sont
correctes dans le jeu.

## Import contrôlé des 95 routes

Les textes vérifiés peuvent être préparés hors du dépôt, dans un dossier
`incoming-guides/` contenant uniquement les fichiers JSON correspondant aux
95 IDs de l'index. Chaque fichier suit le contrat ci-dessus.

```powershell
# Analyse sans écrire : vérifie l'intégralité des 95 parcours.
py -3.13 -m tools.import_ganymede_authored_routes --source-dir incoming-guides

# Après validation des auteurs et des droits, publication locale.
py -3.13 -m tools.import_ganymede_authored_routes --source-dir incoming-guides --apply

# Lot partiel explicitement assumé (ne remplace pas la certification des 95).
py -3.13 -m tools.import_ganymede_authored_routes --source-dir incoming-guides --allow-partial --apply
```

L'import refuse les étapes absentes, les actions inconnues, les liens
d'identifiants pris pour des objectifs, les fichiers inconnus ou les routes
déjà présentes et modifiées (sauf `--allow-overwrite`). Il vérifie
**tout le lot avant écriture** et écrit les JSON via un remplacement
atomique par fichier. Le rapport contient nombre de guides, d'étapes,
empreintes SHA-256, nouveaux/identiques/modifiés et IDs manquants.

Le script ne contacte pas Ganymède, n'essaie pas de contourner un accès,
ne revendique aucune autorisation et ne remplit aucune action manquante.
Un lot validé reste soumis aux tests Qt/Windows, à la revue des positions
et au benchmark Doctor. L'importation locale de contenu personnel n'accorde
pas le droit de redistribuer ce contenu dans Atlas App.
