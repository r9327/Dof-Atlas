# Atlas — ingestion documentalist : contrat V1 (22/10/2026)

## Objet
Relier le Documentaliste IA de Holding aux données Quêtes, Succès, Guides, objets et prérequis, **sans modifier la logique des parcours** ni introduire une nouvelle base concurrente.

## Sources et vérité
- Exploiter les identifiants canoniques existants, les schémas et outils Atlas. Conserver DPLN, Ganymède et les sources secondaires **avec provenance** ; les divergences sont remontées en revue et jamais résolues arbitrairement.
- Pour les guides Dofus/Alignement, les parcours sources Ganymède doivent être restitués en **suivi continu**. Toute optimisation de route reste réservée au « Guide Succès Opti ».
- Respecter les travaux des PR #225/#226 et les données déjà collectées ; ne pas recoller un second catalogue et ne pas régénérer la totalité pour une seule entrée corrigée.
- Compatibilité des règles d'identités Quêtes/Succès, dépendances, prérequis, nombres par personnage et persistance de progression.

## Contrat d'import
1. Entrées immuables : document brut, URL/source, horodatage, SHA-256 et référence de version.
2. Parsing déterministe -> format d'échange versionné ; aucun accès DB pendant le parsing.
3. Validation : champs requis, IDs non ambigus, références croisées, cycles/doublons, anomalies de source et diff précis.
4. Prévisualisation rapport de changements par ID avec catégories AJOUT/MODIFICATION/SUPPRESSION/CONFLIT.
5. Publication atomique après validation indépendante, sauvegarde/rollback et absence de suppression silencieuse.
6. Cache et mises à jour incrémentales ; une collecte interrompue ne remplace pas les données actives.

## Vérifications
- Fixtures réelles anonymisées + fixtures synthétiques ; jeux >5000 étapes, variantes 0/1/2/5 personnages.
- Tests liens guide->quête->succès, prérequis, structures inconnues, source contradictoire, stabilité IDs, diff et reprise.
- Test de non-régression sur progression sauvegardée et navigation continue ; performance/RAM comparées avant/après.
- L'intégration ne se lance pas automatiquement au démarrage de l'UI.

## Dépendances
- Documentaliste dans Holding, contrats actuels Atlas, et PR #225/#226.
- Draft tant que l'adaptateur, les fixtures, les tests et les preuves sur SHA exact ne sont pas intégrés.
