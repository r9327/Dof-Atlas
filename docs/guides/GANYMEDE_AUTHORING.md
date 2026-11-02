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
  **et a été vérifiée par le responsable**. Ce champ ne prouve pas à lui
  seul que l'autorisation existe. Ne pas importer en masse des textes
  communautaires sans droits.
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

## Importer les 95 parcours avec autorisation

L'importateur n'aspire pas Ganymède et ne copie aucune œuvre tierce.
Constituer dans `<dossier>` les 95 JSON rédigés et vérifiés selon le
contrat ci-dessus, avec une autorisation de redistribution pour chaque
contenu provenant d'un autre auteur.

```powershell
# 1. Prévalidation intégrale sans écriture
py -3.13 -m tools.import_ganymede_instruction_pack "C:\\mes-guides-autorises"

# 2. Après 95/95 PASS seulement : importer dans Atlas
py -3.13 -m tools.import_ganymede_instruction_pack "C:\\mes-guides-autorises" --install

# 3. Preuve de disponibilité locale
py -3.13 -m tools.audit_ganymede_instruction_coverage --strict
```

- La validation se fait sur les 95 fichiers avant écriture ; aucune installation
  partielle volontaire n'est acceptée.
- L'import préserve les guides présents : il refuse les remplacements silencieux.
- En cas d'erreur durant la publication, les fichiers déjà publiés **dans
  cette même invocation** sont supprimés, sans toucher aux fichiers précédents.
- Une opération sur des fichiers réellement vérifiés reste nécessaire :
  **aucune source de texte Ganymède n'est importée automatiquement**.
- Le contrôle technique de schéma ne remplace ni la permission effective des
  auteurs, ni la vérification en jeu, ni le benchmark Windows.


## Préparer le croisement des guides — PR #337 / issue #360

Diagnostic offline **en lecture seule** pour préparer le prochain Guide Succès,
sans remplacer le Guide optimisé existant :

```powershell
py -3.13 -m tools.audit_ganymede_crosswalk --cross-guide-candidates
```

API Python : `tools.audit_ganymede_crosswalk.analyze_cross_guide_candidates(root)`.
Les outils Atlas/Doctor peuvent appeler cette API pour obtenir un JSON
déterministe avant de décider d'une intégration. L'outil réutilise les validateurs canoniques
`load_ganymede_local_instructions` et `load_ganymede_local_observations`
(y compris les noms historiques de snapshots). Le scan des 95 guides ne
s'effectue que lors de la commande explicite, jamais au chargement de l'accueil
PySide6. Il retourne les références externes communes entre les guides,
leur type (quête, objet, monstre, donjon), leur ID, chaque guide et numéro
d'étape source : une référence répétée **ne signifie pas** une action en
commun. Les données externes n'acquièrent pas le statut d'ID Atlas canonique.

- Deux actions avec les mêmes coordonnées X/Y sont des **collisions à
  examiner**, pas une preuve de carte identique : l'identifiant de carte et le
  monde/dimension doivent être recoupés avant de parler de co-localisation,
  et les prérequis restent bloquants. Aucune validation ni réorganisation.
- Seuls les identifiants de quêtes Atlas déjà canoniques peuvent prouver une
  identité de quête entre `guide_complet` et `dofus_sylvestre`.
  Les liens Ganymède/DofusDB et les noms ressemblants n'ont pas ce statut.
- Les relations `public_tree_prerequisite_guide_ids` sont des indices
  documentaires. Les dépendances réelles (AND/OR, prérequis, niveaux,
  conditions et branches d'alignement/classe), ressources, quêtes accessibles,
  inventaires et progressions par `character:<id_dofus>` doivent être
  validées par le moteur canonique avant toute fusion d'activités.
- `authored_route_evidence` indique pour chaque guide rédigé son SHA,
  le nombre d'étapes/actions et les comparaisons de coordonnées **à la même
  étape** : `COORDINATE_IN_STEP_SNAPSHOT`,
  `COORDINATE_NOT_IN_STEP_SNAPSHOT` ou `NO_OBSERVATION_FOR_STEP`.
  Ces relevés sont utiles à l'audit individuel, sans affirmer que le jeu ou
  le chemin source complet ont été vérifiés.
- `cross_guide_external_reference_candidates` croise même les sources qui
  n'ont pas encore leurs consignes rédigées, mais conserve l'espace de noms
  `dofusdb`, séparé des IDs de quêtes Atlas.
- Les sorties `REVIEW_ONLY_NOT_OPTIMIZED` sont des **candidats**,
  jamais des parcours certifiés ou des instructions de macro. Toute donnée
  absente ou invalide est signalée ; elle n'est pas reconstruite depuis une
  ancienne liste de quêtes.
- Le planificateur final reste
  `GuideRoutePlanner` / `AdventureRouteEngine`.
  L'adaptation runtime et la substitution future de `guide_complet`
  exigent d'abord la certification réelle 95/95, une preuve d'absence de
  régression de sauvegarde/validation propre à chaque guide et un Graphify
  exact-SHA avant le changement structurel. Les deux guides optimisés
  restent intacts pendant cette préparation.

Test ciblé (ne remplace pas les essais Qt/Windows/jeu) :

```powershell
py -3.13 -m unittest tests.test_guide_cross_route_candidates
```

## Rédaction incrémentale des 80 guides restants — PR #337

Les premières étapes de quatre parcours ont été **réécrites individuellement**
d'après les actions et objectifs visibles dans leurs références publiques, puis
rapprochées des relevés factuels locaux de la même étape. Cette matière est
stockée sous `replacement_drafts/authoring/ganymede_<id>_partial.json` :
**ce n'est pas un guide activable**. Le lecteur ne considère que les
`ganymede_<id>_instructions.json` possédant toutes leurs étapes et une
validation de schéma intégrale.

| Guide | Étapes rédigées | Étapes source | État |
| --- | ---: | ---: | --- |
| 2204 — Mais où sont les Dofus ? | 10 | 26 | Brouillon incomplet |
| 2206 — Valonia 1 | 10 | 30 | Brouillon incomplet |
| 2228 — Sufokia | 10 | 39 | Brouillon incomplet |
| 2229 — Nimaltopia | 10 | 67 | Brouillon incomplet |
| **Total** | **40** | **162** | **Aucun n'est activé** |

Les 40 étapes couvrent désormais **150 actions typées**, dont **73 déplacements
sur 73** avec une position mentionnée dans le relevé de la même étape
(contrôle statique de données, HEAD `7f281184644f5f1d3a703f616fe80c81b69e69c5`). Les consignes d'entrée ont été consolidées contre les dix premières étapes
référencées des quatre sources : niveau 50 et quête du Réceptacle pour 2204,
passage obligatoire au pont de Pandala, absence de prérequis à Valonia
mais 100 kamas de transport, succès et donjons optionnels de Sufokia,
et « Aventure miniature » puis « Ne tirez pas sur le messager » pour
Nimaltopia. Les ressources sont regroupées par trois quêtes, en évitant de
compter deux fois les 20 Eaux potables.

Les quantités, dialogues, niveaux, identités des cartes,
branches et combats demandent une vérification en jeu ainsi qu'une comparaison
intégrale des pages source. Les intitulés d'objets et de PNJ traduits doivent
aussi être confrontés à la version française effective.

**Suite prioritaire** : rédiger et vérifier les étapes restantes de ces quatre
parcours dans l'ordre, puis les faire passer **entièrement** par le contrat des
consignes avant de les ouvrir à la progression manuelle. Poursuivre ensuite
les autres guides. Aucun travail d'optimisation inter-guides ni remplacement
des deux guides optimisés existants ne doit prendre cette priorité.

Contrôle de structure ajouté :

```powershell
py -3.13 -m unittest tests.test_ganymede_partial_authoring
```

Ce test est distinct de la certification fonctionnelle du guide et de
l'exécution réelle des parcours sous Windows/DOFUS.
