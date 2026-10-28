## Objectif et limites
Décrire le comportement demandé et ce qui n'est **pas** livré. Garder la PR en Draft pendant le développement.

## Issue source du contrat
Créer d'abord une issue (distincte de la PR) avec un bloc ATLAS_DELIVERY_CONTRACT contenant TOUS les critères d'acceptation, y compris tests Windows/DOFUS manuels. Ne pas retirer un critère pour obtenir un PASS.

## Livraison et preuve (remplacer tous les champs)
Après le dernier commit, remplacer head_sha par le SHA exact de la branche. Toute nouvelle modification impose sa mise à jour. Pour chaque critère de l'issue, ajouter exactement une ligne JSON ci-dessous. Voir docs/delivery/DELIVERY_GUARD.md.

<!-- ATLAS_DELIVERY_REPORT_START -->
{
  "schema_version": 1,
  "delivery_issue": 0,
  "head_sha": "0000000000000000000000000000000000000000",
  "requirements": [
    {
      "id": "REQ-001",
      "status": "DONE",
      "evidence_files": ["tools/replace_me.py"],
      "test_files": ["tests/test_replace_me.py"]
    },
    {
      "id": "REQ-002",
      "status": "DEFERRED",
      "followup_issue": 0,
      "safety_evidence": "This feature remains disabled/not certified until the manual check is performed."
    }
  ]
}
<!-- ATLAS_DELIVERY_REPORT_END -->

## Tests réels et limites de preuve
- Tests exécutés **sur le SHA exact** : liens vers runs/actions + résultats (pas seulement des noms de tests).
- Tests impossibles en CI (DOFUS, Npcap, UAC, multi-fenêtres, perception visuelle) : état NOT_TESTED ou liens vers validation humaine datée. Jamais de faux PASS.
- Mode Stable/Bêta : indiquer toute fonction laissée non certifiée et comment elle reste désactivée/confinée.
- Travaux reportés : issues ouvertes liées à l'ID exact, responsables et prochaines étapes.

## Revue
- [ ] Tous les IDs de l'issue figurent dans le rapport (sans changement implicite de portée).
- [ ] Toute fonctionnalité annoncée DONE a ses fichiers, tests et preuves Doctor.
- [ ] Les rapports CI ne confondent pas validations ciblées, FULL et essais manuels.
- [ ] Les reports sont visibles et vérifiables après fusion.
- [ ] Dernier commit comparé, pas de tests SKIPPED/NOT_RUN transformés en PASS.
