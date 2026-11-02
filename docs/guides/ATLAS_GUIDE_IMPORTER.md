# Atlas Guide Importer — dépendance PR #337

Contrat source : [#361](https://github.com/r9327/Dof-Atlas/issues/361). Recette manuelle : [#362](https://github.com/r9327/Dof-Atlas/issues/362).

## Principe

Cette commande est une **chaîne de contrôle et d'import**, pas un nouveau moteur de guides. Elle travaille **hors de l'application** : aucune exécution au démarrage, aucun widget nouveau et aucune consommation permanente en RAM.

Elle s'appuie sur les composants existants de la PR #337 :

- `guide_library_sources.load_ganymede_local_instructions` : identité, droits déclarés, 95 guides et règles de contenu ;
- `tools.import_ganymede_authored_routes.import_authored_routes` : prévalidation, écriture explicite, idempotence et anti-écrasement ;
- `guide_catalog_manual_runtime_service.project_ganymede_authored_cards` : conversion vers les données des **fiches universelles** existantes ;
- `SharedGuideManualView/Card`, `GuideUltimeManualCard` et `PALETTE` restent les seuls propriétaires de l'en-tête, du clic /travel, de la copie des objets, des couleurs PNJ et du rendu ;
- la validation, les prérequis, le contenu de combats et la progression `character:<id_dofus>` restent **propres à chaque guide**. Le CLI n'écrit jamais de progression.

**Dépendance Git :** PR empilée sur la branche de #337, à rebaser/vérifier quand cette branche évolue. Fusionner #337 avant la PR d'importeur. Les guides optimisés `guide_complet` et `dofus_sylvestre` ne sont pas modifiés.

## Prérequis

Un répertoire d'exports JSON **dont la rédaction ou la redistribution est autorisée**, conformes à `docs/guides/GANYMEDE_AUTHORING.md`. Aucun aspirateur de texte Ganymède, aucun endpoint privé ni téléchargement implicite. Pour les guides d'autres auteurs, la preuve d'autorisation réelle doit être vérifiée séparément.

Un fichier de **référence externe** est constitué à partir d'une copie indépendante, déjà vérifiée, de ces exports. Il atteste seulement la fidélité des octets et des étapes ; un SHA n'établit ni la justesse des quêtes, ni l'accord des auteurs, ni le fonctionnement dans DOFUS.

`reference.json` :

```json
{
  "schema_version": 1,
  "guides": [
    {
      "source_guide_id": 2203,
      "source_url": "https://ganymede-app.com/guides/2203",
      "file_sha256": "64 caractères hexadécimaux SHA-256 du JSON de référence",
      "step_sha256": [
        "SHA-256 de chaque étape, sérialisée comme indiqué ci-dessous"
      ]
    }
  ]
}
```

La chaîne ci-dessus est illustrative : les empreintes sont obligatoires et doivent être de véritables SHA-256 (minuscules). Pour chaque étape, l'empreinte se calcule sur `json.dumps(step, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')`. Les fichiers JSON sont quant à eux hachés **octet par octet**. L'inventaire du manifeste doit être exactement celui des routes importées, sans doublon.

Ne pas construire la référence automatiquement depuis les fichiers **que l'on cherche précisément à vérifier** : cela signerait sa propre erreur. Stocker les références avec leur provenance, date et personne ayant examiné la source, dans le dossier de revue, sans inclure de contenu tiers non autorisé.

## Utilisation

```powershell
# Revue sans écriture : la référence est obligatoire pour un verdict PREFLIGHT_PASS
py -3.13 -m tools.atlas_guide_importer --source-dir "C:\guides-autorises" --reference-manifest "C:\preuves\reference.json"

# Publication future : commande actuellement BLOQUÉE (sans preuves sémantiques,
# autorisations et recette métier indépendante, aucun --apply n'est autorisé).
# py -3.13 -m tools.atlas_guide_importer --source-dir "C:\guides-autorises" --reference-manifest "C:\preuves\reference.json" --apply

# Sous-lot en prévalidation lecture seule, sans masquer les guides absents
py -3.13 -m tools.atlas_guide_importer --source-dir "C:\guides-autorises" --reference-manifest "C:\preuves\reference.json" --allow-partial
```

Le CLI renvoie un rapport JSON avec ID, SHA, nombre d'étapes/actions, fiches projetées et état de comparaison. `--allow-overwrite` ne contourne pas les preuves obligatoires. Le mode normal reste **lecture seule** et signale `REFERENCE_REQUIRED` en absence de manifeste. **Le mode `--apply` est actuellement fail-closed**, même si le hash correspond : la chaîne de preuves sémantiques, droits et recette métier n'est pas encore intégrée. La CLI basse couche `tools.import_ganymede_authored_routes --apply` retourne `BLOCKED` (diagnostic seul). Aucune route ne peut être déclarée certifiée sur cette base.

## Contrôles et limites

- Toute action doit conserver **son ordre**, son type combat/non-combat et sa position dans la fiche commune ; les objets structurés doivent apparaître dans la liste des ressources.
- Les `copy_values` et `items` structurés sont conservés sans perte dans les données des fiches communes ; le contrôleur **bloque** toute régression de projection. Le comportement effectif des liens, couleurs, quantités et du presse-papiers reste à tester dans le renderer de #337 sous Qt/Windows.
- Le manifeste SHA doit correspondre **au fichier ET à chacune des étapes** ; tout écart bloque l'ensemble du lot avant import.
- Après `--apply`, les empreintes des fichiers publiés sont revérifiées.
- Les contrôles d'exécution réelle Windows/Qt, couleurs, copie réelle du presse-papiers, persistance par personnage, parité éditoriale avec chaque page source et autorisations restent `NOT_RUN/NOT_VERIFIED` tant qu'une preuve externe n'est pas fournie. Aucun `CERTIFIED` automatique.
- Le publieur existant a été renforcé : **préparation complète sur disque puis publication fichier par fichier avec rollback** en cas d'erreur récupérable, y compris restauration des anciens fichiers. Une panne système ou une coupure électrique **pendant** la publication n'est pas une transaction ACID multi-fichiers ; une sauvegarde reste nécessaire avant un écrasement en masse. Un journal de reprise durable serait nécessaire pour promettre une reprise automatique après coupure.

## Tests ciblés

```powershell
py -3.13 -X utf8 -m unittest tests.test_atlas_guide_importer tests.test_import_ganymede_authored_routes tests.test_ganymede_local_instructions tests.test_ganymede_local_copy_links
```

Pendant la Draft : tests ciblés et revue par commit. La Phase Certification globale ne se lance qu'à la fin du développement, sur le SHA exact, conformément à `AGENTS.md`. Le rapport du contrat Delivery Guard doit être complété avant Ready.
