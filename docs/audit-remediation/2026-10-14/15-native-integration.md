# [PLAN 15] Validation native Windows de bout en bout après correctifs

> **DRAFT — intégration native complète non certifiée.** Mise à jour du
> 16 octobre 2026 : les preuves Windows existantes sont rapprochées ci-dessous ;
> les scénarios interactifs manquants restent BLOCKED, sans inventer un PASS.

## Preuves Windows déjà obtenues

Le déploiement Windows est implémenté et #159 / #199 sont fusionnées. Il ne
faut pas refaire leur développement ni annoncer que l’installation est absente.

La [run publique 38868370636](https://github.com/r9327/Dof-Atlas/actions/runs/38868370636)
du 16 octobre a réellement exécuté sur Windows :

- job **116866368190 SUCCESS** : EXE publics sans Python dans PATH, installation
  propre en chemin personnalisé, interruption/reprise, hashes des fichiers et
  JSON verrouillés, workers Quêtes/Succès/objets, smokes Guide/Craft/SQLite,
  navigation Équipement, Quitter natif, zéro worker survivant, relance, réglages
  conservés et réparation après corruption de l’EXE et d’un JSON ;
- job **116866368384 SUCCESS** : ancienne distribution publique vérifiée,
  lancement du vrai updater public, activation de la nouvelle version, slot
  précédent conservé et paramètres préservés.

Binaire testé : **source `204daf85ace85ea7501ab0bc6618d08588fc0ea4`**, release
`sha-204daf85ace8`. Pilote : `2187072e77fe67fb15c6c699b1413119aa7b62d3`,
intégré par #199. Ces preuves ne sont pas réattribuées au code plus récent de
#170/#171 ni à Qt 6.12. Les deux jobs skipped de cette run ne comptent pas comme
PASS ; leurs exécutions réelles sont dans la
[run 38866987912](https://github.com/r9327/Dof-Atlas/actions/runs/38866987912).

Le slot précédent disponible n’est **pas** une preuve de retour arrière
interactif exécuté. Le fingerprint global des 28 entrées avant/après n’était
pas capturé par cette ancienne run ; les vérifications des locks restent
distinctes de ce nouveau contrat de provenance livré par #172.

## Scénarios natifs à exécuter après le candidat cumulatif

Le poste disponible pour cette reprise est Linux. Les runners Windows de CI
exécutent de vrais tests Qt/Win32, mais aucune session Dofus avec personnage,
capture Npcap et bureau utilisateur n’est disponible ici. Les identités et
profils personnels ne sont ni inventés ni copiés dans le dépôt.

| Flux | Parcours requis et preuve attendue | État intégration complète |
|---|---|---|
| Source / démarrage | `DOFUS.bat` → Home, mutex avant QApplication, deuxième lancement refusé, fermeture normale et relance | BLOCKED bureau/session utilisateur ; mutex multi-processus distinct dans #171 |
| Quêtes / Guide / Succès | Personnage réel identifié ; ouvrir une quête depuis Guide, cocher/décocher, vérifier la propagation et le profil après relance | BLOCKED identité et session Dofus ; contrats Qt distincts en CI |
| Guide manuel et compact | Parcourir les deux modes, carte longue en petite fenêtre, navigation clavier, liens, conditions et ordre réels | BLOCKED revue interactive et progression réelle ; GP-001…200 de #170 ne sont pas déclarés résolus par un test de layout |
| Références des données | Vérifier les 37 objectifs de Succès retenus mais absents du raw et les quatre objectifs de quête orphelins ; garder les avertissements si indécidable | BLOCKED source métier complète ; inventaire exact #172 conservé, aucune donnée fabriquée |
| Craft | Dataset public vérifié ; recherche ressource et trophée au-delà de 160 correspondances, détail recette, composants, changement d’onglet puis Home | BLOCKED parcours bureau du candidat final ; défaut SQL et tests réels protégés par #171 |
| Organizer / profils | Créer un profil temporaire, modifier ordre/options, changer de profil, relancer et vérifier séparation et conservation | BLOCKED bureau du candidat final ; aucun vrai profil existant modifié |
| Zaap | Navigation, saisie, retour Home et relance ; ordre/persistance et action autorisée dans le client | BLOCKED client Dofus et interaction native |
| Scan Monde | Charger une vue, modifier un état temporaire, Home, relance ; état conservé ; quitter pendant le chargement | BLOCKED parcours bureau ; tests transactionnels et worker existants ne sont pas un RSS global |
| Équipement externe | Ouvrir la vue réelle, navigation disponible/indisponible, réseau coupé puis rétabli, fermeture WebEngine sans worker survivant | BLOCKED parcours complet du candidat final ; seule l’entrée de l’ancienne EXE a été testée publiquement |
| Capture / UAC | Session Dofus, Npcap installé, accepter/refuser l’élévation, démarrage/arrêt capture, identité et progression sans doublons | BLOCKED environnement Npcap/UAC et personnage |
| Lifecycle et mémoire | Répéter les changements de vues puis Home, attendre les workers, relever objets/threads/RSS/latences et comparer au même scénario avant correction | BLOCKED mesures Windows comparables du candidat final ; pas de plafond Home arbitraire ni de gain RAM déduit |
| EXE final / mise à niveau / rollback | Build du SHA stabilisé, installer hors checkout, mise à niveau, échec contrôlé, rollback effectivement joué, paramètres conservés | BLOCKED binaire final non encore certifié par ce lot ; anciennes preuves ci-dessus conservées |

### Protocole commun de preuve

1. Noter le **SHA du produit** et celui du pilote, versions Python/Qt ou version
   de l’EXE, version Windows et origine de la release. Aucune réutilisation
   automatique de la preuve d’un autre SHA.
2. Avant les parcours, exécuter `py -3.13 -m tools.atlas_json_inventory
   --raw-inputs --candidate-sha <SHA> --output <inputs_before.json>` sur le
   checkout source exact ; refaire après avec `--verify-against <inputs_before.json>`.
   Sur EXE indépendante, consommer le manifeste et la provenance du build,
   et vérifier les fichiers installés ; ne pas prétendre y avoir lancé les outils source.
3. Utiliser un profil de validation isolé ; enregistrer seulement une identité
   anonymisée dans les preuves publiques. Consigner les actions réellement
   effectuées, erreurs, captures utiles et résultat PASS/FAIL/BLOCKED par ligne.
4. Pour les coûts, noter machine, scénario, état des caches et moment de mesure ;
   mesurer après stabilisation, comparer les mêmes étapes, conserver aussi les
   premiers chargements coûteux. PC-01 de #171 laisse le chargement froid coûteux.
5. Réutiliser la FULL exacte-SHA finale et les scénarios existants lorsqu’ils
   couvrent réellement le besoin ; ils ne remplacent pas le parcours avec client
   Dofus. Conserver cette PR ouverte tant que cette matrice reste bloquée.

Code audit source : `main@ac07be9b894718f5e68e7c3a91016d7651e3065b`. Rapport/probes : [PR #160](https://github.com/r9327/Dof-Atlas/pull/160).

## Pourquoi ce lot est distinct
Doctor/Graphify/AI Context attestent la structure, pas les parcours natifs de bout en bout. #168 vérifie la **politique** de certification et #159 prépare la **distribution**. Ce lot vérifie le **produit réel**, sans redévelopper les autres lots.

## Travail prévu
1. Créer des scénarios de validation representatifs sur Windows/Python/PySide réel, sans assimiler une trace Qt synthétique à l'application complète.
2. Tester le parcours source DOFUS.bat → Home → Quêtes → Guide compact et Guide manuel → Succès, avec identité personnage réelle et propagation/décochage.
3. Tester Craft avec recettes/dataset complet, Organizer avec profils/ordre, Zaap navigation et retours Home, Scan Monde avec persistance, Équipement externe et ses échecs contrôlés.
4. Capturer flux UI réels, destruction des vues différées et workers aux frontières Home ; quantifier mémoire et latence après stabilisation des modules, sans remettre un gate artificiel Home<100 Mo.
5. Pour réseau/capture Npcap et EXE, exécuter scénarios Win32/UAC seulement en environnement autorisé ; worker IPC et stdout --windowed sont propriétaires #159, pas de modification doublonnée.
6. Tester un build indépendant du checkout et une installation propre + mise à niveau + rollback uniquement une fois #159 prête ; journaliser présence des datasets et provenance exact-SHA.
7. Exécuter validation Guide/Quêtes/Succès/Craft avec les données brutes exactes et versionnées ; faute de dataset, marquer BLOCKED et ne pas annoncer PASS.
8. Rendre publiquement lisibles la matrice des scénarios, tests réellement joués, skipped, erreurs, limitations natives et preuves re-lançables ; pas de FULL en boucle.
9. Réaliser une certification cumulative unique uniquement lorsque les patchs préalables sont stabilisés et que la policy la justifie.

## Critères de sortie
- [ ] Un scénario produit réel par flux majeur (Quêtes/Guide/Succès, Craft, Scan, Organizer, Zaap, Equipment) avec résultat et preuve.
- [ ] Quitter chaque écran pour Home sans objet/thread permanent non expliqué ; comparer valeurs plutôt que supposer un budget arbitraire.
- [ ] Chaque blocage Windows/Npcap/données externes est affiché, pas transformé en certificat vert.
- [ ] EXE install/rollback, binaire compilé et Qt lock restent explicitement sous responsabilité #159 et #138, avec preuves consommées, pas dupliquées.
- [ ] Preuves rattachées au SHA de code et au fingerprint des données ; aucun merge de cette PR de plan comme si produit certifié.

## Dépendances
Après code des PR #161/#162/#163/#164 et #159 ; coordination #138 Qt et #168 gate ; preuves complémentaires #170/#171/#172/#173/#174. Aucun test de production ne peut être déclaré PASS sans installation/autorisation/dataset correspondants.

**Aucun code applicatif modifié par ce plan.** Commencer au HEAD réel après les merges, puis tests ciblés et certification adaptée.
