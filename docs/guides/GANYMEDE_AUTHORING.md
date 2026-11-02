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

La priorité est de terminer **tous les guides**, non de développer
davantage le Guide Ultime. Les données de travail sont rédigées avec
des actions originales d'après les pages sources accessibles, des
observations locales et les quêtes indépendamment documentées. Les
observations de coordonnées ne sont **pas** une preuve de parité
Ganymède. Les fichiers restent dans
`replacement_drafts/authoring/ganymede_<id>_partial.json` :
**ils ne sont pas chargés dans l'application**, même complets.

| Guide | Étapes rédigées | Étapes attendues | État |
| --- | ---: | ---: | --- |
| 2204 — Mais où sont les Dofus ? | 26 | 26 | Brouillon complet, non certifié |
| 2206 — Valonia 1 | 30 | 30 | Brouillon complet, non certifié |
| 2228 — Sufokia | 39 | 39 | Brouillon complet, non certifié |
| 2229 — Nimaltopia | 67 | 67 | Brouillon complet, non certifié |
| 2235 — Sidimote 3 | 31 | 31 | Brouillon complet, non certifié |
| **Total** | **193** | **193** | **Aucun n'est activé** |

Les **193 étapes rédigées** comportent **812 actions typées** et
**378/378 actions positionnées** mentionnées dans le relevé local de
**la même étape** (contrôle statique au HEAD
`68bbcd3bdfec4b19cc335fd84cd932695f3ecafc`).
Cette concordance **ne prouve pas** le chemin original, l'identité de
la carte/dimension, les prérequis réels ou le bon fonctionnement en jeu.

Les cinq guides 2204, 2206, 2228, 2229 et 2235 portent explicitement
`FULL_DRAFT_NOT_PLAYABLE`, `source_parity_certified:false` et
`gameplay_certified:false`.  La publication stricte sous
`ganymede_<id>_instructions.json` reste bloquée jusqu'à la
comparaison 1:1 des **étapes Ganymède d'origine**, aux essais du
lecteur et aux vérifications propres à chaque personnage.

Sources de contrôle des quêtes :

- 2204 : https://www.dofuserie.com/quetes/le-receptacle-des-dofus/
  et les autres liens présents dans le brouillon (Guipol, Dark Vlad,
  Mériana, etc.).
- 2206 : https://www.dofuserie.com/quetes/colonie-de-vaillance/
  et les autres quêtes de Valonia, référencées dans le JSON.
- 2228 : https://ganymede-app.com/guides/2228 et
  https://ganymede-app.com/guides/310 pour le début de route et les
  noms français, puis
  https://www.dofuserie.com/quetes/promenade-sur-les-quais/,
  https://www.dofuserie.com/quetes/investigation-embarquee/,
  https://www.dofuserie.com/quetes/voleurs-en-serie/,
  https://www.dofuserie.com/quetes/distribution-de-pains-zizanesques/
  et les autres quêtes du succès. Six barques et quatre collecteurs
  sont inscrits dans l'ordre du relevé local ; les deux succès restent
  deux validations distinctes.
- 2229 : https://ganymede-app.com/guides/2229 pour les étapes 1–10,
  https://www.dofuserie.com/quetes/frais-de-porc-inclus/,
  https://www.dofuserie.com/quetes/nos-amies-les-betes/,
  https://www.dofuserie.com/quetes/shyriiwook/ et
  https://www.dofuserie.com/quetes/a-armes-egales/ pour les
  informations de quêtes ultérieures. Combats seul / en groupe,
  ressources et branches Bonta/Brâkmar restent explicites par étape.

- 2235 : https://ganymede-app.com/guides/2235 pour les dix
  premières étapes, puis les faits de quête indépendants
  https://www.dofuserie.com/quetes/l-entree-des-artistes/,
  https://www.dofuserie.com/quetes/un-salaire-germinable/,
  https://www.dofuserie.com/quetes/au-pied-du-mur/ et
  https://www.dofuserie.com/quetes/rituel-oblige/ pour les étapes suivantes.
  **Cinq combats distincts** dans le brouillon, dont Pwouerk, le Bwork
  mercenaire, les sectateurs, Risa Gregory et Moctar Chitekt démoniaque.
  La correspondance exacte aux étapes originales 11–31 reste à certifier.

**Suite prioritaire :** vérifier la parité des cinq parcours maintenant
entièrement rédigés avec les pages Ganymède originales,
les localisations, les combats et les prérequis ; finaliser ensuite
les **75 autres routes sans rédaction complète**, et certifier chaque
parcours correctement avant son activation. **Aucune migration du
Guide Ultime ni de l'interface en attendant** : les deux optimisés
actuels restent intacts.

**Avancement réel en bibliothèque :** 15/95 fichiers complets déjà
présents (non certifiés), auxquels s'ajoutent **5 brouillons complets
hors runtime** ; 0/95 certifié en jeu/Windows.

Contrôle de structure ajouté :

```powershell
py -3.13 -m unittest tests.test_ganymede_partial_authoring
```

Ce test est distinct de la certification fonctionnelle du guide et de
l'exécution réelle des parcours sous Windows/DOFUS.
