# Pièces complémentaires du même audit DOFUS ATLAS

Source auditée : `r9327/Dof-Atlas`, main au SHA `ac07be9b894718f5e68e7c3a91016d7651e3065b` (14 octobre 2026).

- [Rapport intégré](../AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) : couverture, constats détaillés, plan de correction et annexe JSON.
- [Archive complète](DOFUS_ATLAS_AUDIT_ac07be9b.zip) : rapports originaux, tous les registres, `evidence/`, `probes/` et manifeste. Télécharger puis extraire pour lire les pièces individuellement ; les fichiers ne dépendent plus du workspace de l’agent.
- [Manifeste individuel](MANIFESTE_LIVRABLES.json) : chemin, taille et SHA-256 de chaque pièce de l’archive.
- [Décisions JSON originales](JSON_DECISIONS.md).
- [Registre des anomalies](registres/anomalies.json), [priorités](registres/priorites.csv), [diagnostics Doctor triés](registres/diagnostics-doctor.json), [pistes à confirmer](registres/pistes-a-confirmer.json) : consultables directement sans extraire l’archive.

## Intégrité et extraction

SHA-256 de l’archive :

```text
04d4d1d37ed2cf94643e655ce113ba3af3db96a2c38d9cbb9eca3b22a87d7b6d
```

```bash
sha256sum DOFUS_ATLAS_AUDIT_ac07be9b.zip
python -m zipfile -e DOFUS_ATLAS_AUDIT_ac07be9b.zip audit-extrait
```

Les 270 pièces du manifeste ont été vérifiées contre les octets de l’archive : aucune divergence. L’archive ZIP a également passé son contrôle d’intégrité. Un scan des clés privées, formats usuels de tokens et URLs signées n’a détecté aucun élément sensible ; ce scan ne constitue pas une garantie générale de sécurité.

## Contenu à inspecter

- `registres/` : inventaires Python/symboles, doublons, diagnostics, graphes/nœuds/communautés/candidats, décisions JSON, Guide, signaux/workers et écritures de persistance.
- `evidence/` : diagnostics natifs, reproductions, traces et captures UI de fixtures, mesures ciblées, preuves CI exact-SHA et métadonnées de branches/PR. Les fichiers archivés sont les preuves originales de l’audit ; leur nom n’atteste pas à lui seul un défaut.
- `probes/` : scripts effectivement utilisés, avec leur notice. Adapter leurs chemins `/workspace` avant reproduction ; ils ne sont intégrés ni au runtime ni à la CI.

Ces fichiers sont publiés à la demande explicite de rendre les autres pièces du même audit inspectables, dans un dossier documentaire isolé. Aucune source applicative ni donnée canonique n’est changée. L’archive garde ses rapports originaux, dont les mentions « hors dépôt » décrivent la situation avant cette publication complémentaire.
