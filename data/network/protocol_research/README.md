# Dofus Atlas — Protocol research registry

Ce dossier conserve les informations réseau utiles découvertes pendant le chantier Dofus Atlas afin de pouvoir implémenter progressivement le reste du protocole sans perdre la provenance ni le niveau de confiance.

## Règle absolue

**Ce dossier n'est jamais une source de vérité runtime.**

Le runtime automatique ne charge que les mappings explicitement validés dans :

- `data/network/protocol_mappings/`

Une entrée présente ici peut être :

- une observation réseau publique ;
- une structure extraite du client ;
- un nom sémantique historique ;
- un candidat à confirmer ;
- une piste rejetée.

Elle ne donne jamais, à elle seule, le droit de modifier la progression utilisateur.

## Niveaux de confiance

- `verified_current_wire` : observé sur le réseau réel de la version indiquée et structure recoupée avec le proto extrait de cette même version.
- `verified_current_schema` : structure directement extraite du client de la version indiquée, sans sémantique complète nécessairement connue.
- `current_public_catalog` : catalogue public récent et versionné, utile pour guider l'implémentation mais pas suffisant seul pour une mutation de progression.
- `historical_semantic` : nom/champs provenant d'un ancien proto clair. Sert à comprendre la sémantique, jamais à attribuer un opcode actuel sans preuve supplémentaire.
- `candidate` : piste à recouper.
- `rejected` : piste explicitement invalidée ; ne pas réutiliser.

## Fichiers

- `dofus_3.6.10.10_v1.json` : faits et candidats spécifiques au protocole Dofus 3.6.10.10.
- `backlog_v1.json` : fonctionnalités réseau intéressantes à implémenter plus tard, avec leur état et leurs prérequis de preuve.

## Politique de conservation

Le dépôt ne doit pas contenir :

- captures `.pcap/.pcapng` ;
- payloads bruts de sessions utilisateur ;
- noms de personnages capturés ;
- identifiants de comptes ou de sessions ;
- adresses IP/ports issus de captures ;
- fichiers binaires du client Dofus.

On conserve uniquement des métadonnées de protocole publiques, des chemins de champs, des hashes/revisions de sources et les décisions d'ingénierie associées.

## Promotion vers le runtime

Pour promouvoir une information de ce dossier en mapping exécutable :

1. vérifier la version du jeu ;
2. lier le mapping au `build_sha256` exact du client local ;
3. recouper type URL + chemin protobuf + sémantique ;
4. passer les audits réseau existants ;
5. installer explicitement le mapping dans `protocol_mappings/` ;
6. ne démarrer le runtime que si le bootstrap exact-build le déclare `ready`.

Le dossier de recherche ne doit jamais être ajouté aux racines de `ProtocolMappingRegistry`.
