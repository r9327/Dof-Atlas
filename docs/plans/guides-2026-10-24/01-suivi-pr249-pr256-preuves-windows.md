# Continuité PR #249 / #256 — preuves Windows, Unity et réseau

Statut initial : **OUVERT / NON CERTIFIÉ**. Cette PR poursuit les validations réelles des corrections déjà intégrées à `main` par [#249](https://github.com/r9327/Dof-Atlas/pull/249) et [#256](https://github.com/r9327/Dof-Atlas/pull/256). Elle ne réintroduit pas leurs commits, ne revient pas sur leurs fusions et ne modifie pas la progression multi-personnages de #250.

## Base déjà livrée (ne pas refaire)

- #249 : détection Unity, contrôles d'identité réseau vérifiée, Organizer, portraits/class_key, caches et export des ressources.
- #256 : lancement du helper de capture depuis l'EXE PyInstaller avec `--atlas-capture-helper`, smoke `--atlas-capture-smoke`, portrait Organizer indicatif depuis le titre Unity **sans** identité vérifiée.
- Les deux PR sont fusionnées. Ces corrections restent sur `main`. Le fait qu'un correctif soit fusionné ne démontre **pas** à lui seul que la capture réelle DOFUS/Npcap fonctionne.

## Preuves restantes — à relever sur un vrai Windows avec DOFUS installé

Consigner pour chaque scénario : **PASS / FAIL / BLOQUÉ**, SHA testé, version exacte de l'EXE, provenance de la release, date, résultat attendu/observé et lien vers les traces expurgées. Ne pas cocher PASS sur une maquette, un mock ou une preuve provenant d'un ancien SHA.

- [ ] **W1 — helper de capture gelé :** vérifier `--atlas-capture-smoke` sur l'EXE publié, puis lancement normal, UAC (si nécessaire), handshake `ready`, arrêt/redémarrage et absence de boucle `capture_helper_timeout`.
- [ ] **W2 — capture/mapping exacts :** sur le client DOFUS réel, relever l'empreinte GameAssembly/metadata, état Npcap, profil de mapping effectivement compatible, puis preuve d'événements et de champs `kvi/kva` sur la version exacte. Si aucun mapping attesté : **BLOQUÉ**, pas de correspondance inventée.
- [ ] **W3 — sessions Unity :** essais avec 0, 1 et 6+ fenêtres ; titres génériques/renommés, doublons, fermeture/réouverture, PID réutilisé, plusieurs comptes. Aucun titre, slot, PID ou portrait indicatif ne devient une identité réseau.
- [ ] **W4 — Organizer :** favoris, ordre, sélection et personnage principal restent stables au scan, après reconnexion et redémarrage. Les titres et portraits indicatifs demeurent clairement distincts des classes vérifiées.
- [ ] **W5 — Guide / Quêtes / Succès :** apparition d'un personnage réellement vérifié sans redémarrage, invalidation à la modification des bindings, conservation des profils hors ligne, consultation et validation manuelle sûres. Aucune auto-validation ni commande de déplacement basée sur une identité non vérifiée ou une fenêtre hors ligne.
- [ ] **W6 — distribution / ressources :** portraits de classe présents dans l'EXE installé (Git LFS matérialisé), aucun chemin de développement requis, diagnostic accessible et budget RAM/démarrage non dégradé.
- [ ] **W7 — contrôle logiciel :** tests ciblés, Doctor Qt/Windows adapté à l'impact, puis certification sur le **SHA final** de cette PR si des correctifs applicatifs sont ajoutés.

### Commandes de tests ciblés à exécuter dans un environnement adapté

```powershell
py -3.13 -m unittest -v tests.test_distribution_worker_dispatch tests.test_network_elevated_capture tests.test_organizer_character_order tests.test_quest_character_class_icon_identity tests.test_guide_participant_service
py -3.13 -m unittest -v tests.test_quest_character_cache tests.test_windows_embed_lazy_binding tests.test_character_pid_ownership tests.test_character_binding_recovery tests.test_distribution_export
```

Ces commandes constituent un **plan de validation** ; leur présence ici n'atteste pas une exécution. Exécuter Doctor et les essais avec les outils/procédures réellement disponibles sur Windows. Ne pas communiquer de tokens IPC, données privées des personnages ou journaux sensibles.

## Décision de clôture

- Conserver cette PR en **Draft** tant que les preuves obligatoires manquent.
- Si un test échoue, corriger uniquement la cause avérée sur **cette branche**, ajouter une régression ciblée et renouveler les preuves sur le nouveau SHA.
- Marquer explicitement **BLOQUÉ** les points impossibles sans client réel/Npcap, sans en déduire un PASS.
- Ne fusionner qu'après vérification des garde-fous pertinents, des effets de bord et du statut des preuves Windows requises. Ne pas déclencher de FULL répétée pendant les commits de préparation.
