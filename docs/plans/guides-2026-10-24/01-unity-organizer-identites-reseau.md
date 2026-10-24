# [PLAN 01/07] Guides : Unity, Organizer, personnages et réseau

**STATUT : BROUILLON DE CADRAGE — aucune implémentation. NE PAS FUSIONNER CE COMMIT SEUL.**

Objectif : Réparer et certifier la chaîne fenêtres Unity → Organizer → identités réseau vérifiées → profils et Guides, sans faux rapprochements.

Base analysée : 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Diagnostic et causes
- [ ] Le scanner de fenêtres utilise UnityWndClass, HWND/PID et normalise les titres Windows ; les releases Unity peuvent changer les titres.
- [ ] Organizer exporte index clients et character_key ; GuideParticipantService reconstruit la liste à partir des bindings réseau, et ne reprend pas simplement les fenêtres.
- [ ] Le protocole réseau exige une empreinte exacte du build client pour sélectionner un mapping compatible ; la version locale réelle n'est pas attestée.

## À réaliser intégralement
- [ ] Reconstituer le flux complet des données et des signaux de rafraîchissement entre scan Windows, Organizer, client_index, bindings, Encyclopédie, Guide, Quêtes et Succès.
- [ ] Corriger la détection des titres après release sans perdre raw_title, HWND, PID ni confondre plusieurs fenêtres semblables ; tester redémarrage, renommage, comptes multiples, changement de personnage et PID recyclé.
- [ ] Respecter les mécanismes de retry pour noms génériques et l'absence de nom sûr ; ne jamais assimiler un nom générique, numéro de slot ou PID à une identité métier.
- [ ] Réconcilier un character_key déjà VÉRIFIÉ provenant d'Organizer avec les bindings réseau et l'index sans contournement de la preuve de propriété.
- [ ] Afficher les personnages hors ligne déjà connus et vérifier leur disponibilité pour les commandes de déplacement ; jamais déplacer un personnage hors ligne.
- [ ] Utiliser class_key vérifié pour les portraits, le nom de classe et les info-bulles, avec fallback sans attribution abusive ; valider le packaging des icônes.
- [ ] Persister/restaurer la sélection et l'ordre des personnages, gérer disparition et réapparition de fenêtre sans fusion de comptes.
- [ ] Diagnostiquer distinctement l'état fenêtre, capture Npcap, helper administrateur, calibration, empreinte GameAssembly/metadata, mapping exact, événements et identité.
- [ ] Contrôler kvi/kva pour l'identité et les événements quêtes/succès ; toute adaptation de mapping doit reposer sur des traces vérifiées du build réel, jamais sur une version supposée.
- [ ] Préserver les limites de confiance des événements réseau, déduplication, journal en attente et snapshot, récupération de session connue, impossibilité de progression auto sans preuve.
- [ ] Prévoir un état dégradé : Guide manuel lisible malgré réseau indisponible, diagnostic détaillé et aucune fausse validation.

## Connexions et fichiers à protéger
- [ ] app/windows_embed.py ; app/pages/organizer/character_sessions.py et common.py ; app/services/guide_participant_service.py ; app/quest_catalog.py ; app/modules/encyclopedia/views/encyclopedia_page.py.
- [ ] app/network/application_coordinator.py, build_fingerprint.py, protocol_status.py, current_protocol_profile.py, character_resolver.py, known_session_recovery.py et progress_bridge.py.

## Critères de réception et tests ciblés
- [ ] 0, 1, 6+ fenêtres, titres anciens/génériques/nouveaux, identité unique vs ambiguë, PID recyclé, classe correctement affichée, hors ligne conservé.
- [ ] Reconnaître un personnage vérifié sans jamais promouvoir une identité inconnue ; synchronisation Guide/Quêtes/Succès et sélection persistante après relancement.
- [ ] Preuves Windows : empreinte et mapping du client installé, état Npcap, logs et tests ciblés network_* / organizer_* / character_* / windows_embed ; résultat BLOQUÉ si sans capture fiable.
- [ ] Aucun effet secondaire sur les sauvegardes ou performance de démarrage.

## Compléments explicites — points oubliés de l'enquête
- [ ] Corriger la **perte de sélection des favoris Organizer** déjà signalée : favoris persistants malgré scan, nouvel ordre, changement de fenêtre, reconnexion et relancement ; ne pas confondre favori UI, personnage principal et destinataire de commande.
- [ ] Supprimer les numéros de slots présentés comme identifiants de personnages dans les surfaces remaniées ; garder slot/HWND/PID seulement comme détails techniques nécessaires à Organizer.
- [ ] Vérifier explicitement les caches de signatures de sources des personnages et la propagation du changement de **fichier bindings réseau** jusque dans le Guide/Encyclopédie ; un binding modifié sans changement de fenêtre ne doit pas laisser les portraits anciens affichés.
- [ ] Ne jamais utiliser directement le champ exporté `character_key` comme preuve autonome : valider qu'il appartient toujours au registre d'identités réseau, avec provenance, unicité et correspondance de session.
- [ ] Vérifier la capacité de l'EXE distribué à charger les portraits/icônes de classes et le diagnostic réseau sans chemin de développement local ni Python installé.
- [ ] Contrat transversal : chaque personnage connu hors ligne reste **consultable** et progressable manuellement selon sa sélection, mais seules les fenêtres effectivement rattachées et disponibles reçoivent les commandes de déplacement.

## Audit préalable détaillé — cache de classe et registre des personnages
- [ ] **Cause source identifiée :** `app/pages/quest_character_cache.py::_clone_characters` et `cached_load_quest_characters` reconstruisent `QuestCharacter` sans copier le champ `class_key`. Le chargeur d'origine `app/quest_catalog.py::load_quest_characters` fournit bien ce champ uniquement à partir de `source == "verified_network_identity"`. Prévoir propagation du `class_key` vérifié sans élargir les sources de confiance.
- [ ] **Cause affichage distincte :** `SharedGuideManualView._participant_icon` tente une résolution par nom de fenêtre depuis Organizer, au lieu de privilégier `character.class_key` vérifié. Corriger les deux chemins conjointement, et refuser les classes non répertoriées / chemins d'icônes arbitraires.
- [ ] **Contrat du cache :** copie défensive des personnages, pas de mutation de la source par le consommateur ; signature incluant déjà le timestamp/taille du fichier bindings quand applicable ; sélection globale seule ne doit pas déclencher un rechargement coûteux.
- [ ] **Cohérence des sources :** `EncyclopediaPage._current_character_sources_signature` utilise `quest_character_source_signature`; vérifier que le changement de binding provoque un rafraîchissement efficace. Les profils synthétiques `Personnage N` ne constituent jamais une identité fiable.
- [ ] **Tests de développement à écrire au moment autorisé :** `tests/test_quest_character_cache.py` couvre préservation de la classe au premier chargement, au cache-hit, après changement du fichier bindings et après copie isolée ; `tests/test_quest_character_class_icon_identity.py` prouve le refus de classes non vérifiées ; `tests/test_guide_participant_service.py` couvre offline/online ; `tests/test_encyclopedia_character_refresh_cache.py` protège l'invalidation ciblée ; test Qt de portrait dans `test_guide_ultime_manual_ui_navigation.py`.
- [ ] **Contrôles fonctionnels futurs :** Feca hors ligne classe correcte ; deux personnages au même nom mais aux classes contradictoires = absence d'attribution ; écran Guide initialement vide puis identité validée par le réseau = apparition sans redémarrage ; personnage disparu/revenu sans faux changement de compte.
- [ ] **Interdiction de développement à ce stade :** ce point est un diagnostic de planification et ne correspond pas à un correctif intégré. Toute implémentation devra attendre le lancement explicite des travaux.

## Verrous de passage et scénarios transversaux (préparation)

**Entrées vérifiées avant correction :** `scan_unity_sessions` (`app/windows_embed.py`) renvoie `nom`/ `detected_title` tronqués aux deux premiers segments, HWND/PID, mais ne conserve pas le `raw_title` original dans le dictionnaire exposé. `uniquify_session_names` ajoute un suffixe d'affichage aux doublons ; ce suffixe ne doit pas contaminer l'identité. `Organizer.export_client_index` (`character_sessions.py`) produit `character_name`, `class_key`, `character_key`, PID/HWND et rang. `GuideParticipantService.available_characters` lit les identités connues, y compris hors ligne. `quest_character_cache` perd actuellement `class_key` lors de ses copies, correction planifiée mais **non appliquée**.

**Arbre de cas à documenter pendant l'implémentation :**
- [ ] Scénario U1 : 1 client nommé et reconnu par capture réseau ; portrait et sélection en ligne ; fermer sa fenêtre => même identité hors ligne, aucun destinataire de déplacement.
- [ ] U2 : 2 clients portant le même nom, ou le même PID à des instants différents ; ne pas attribuer le mauvais `character_key`.
- [ ] U3 : nom de fenêtre changé par release / fenêtre « Dofus » générique puis corrigée ; identité et classe préservées si preuves concordantes, pas de boucle de retry infinie.
- [ ] U4 : registre des bindings modifié seul, sans changement du fichier client_index => rafraîchissement du Guide sans redémarrer, avec cache de classe mis à jour.
- [ ] U5 : aucune fenêtre, Npcap indisponible ou SHA sans mapping exact => lecture et suivi manuel disponibles, **aucune auto-complétion** ; motif exploitable dans le diagnostic.
- [ ] U6 : redémarrer Atlas avec favoris, ordre, sélection des personnages, iconographie et compte principal enregistrés ; les données personnelles ne se mélangent pas.

**Découplage non négociable :** cette PR répare les producteurs d'identités/réseau et l'affichage des portraits, pas les règles de validation des fiches de la PR #250. Si un mapping Unity ne peut pas être prouvé sur le PC équipé du client réel, laisser le sous-objectif réseau **BLOQUÉ**, ne pas fabriquer un test PASS ni retenir les autres PR de cadrage en otage.

**Recevabilité :** les tests `test_character_pid_ownership.py`, `test_character_binding_recovery.py`, `test_character_class_icon_resolution.py`, `test_quest_character_cache.py`, `test_encyclopedia_character_refresh_cache.py`, `test_guide_participant_service.py` et les contrats réseau sélectionnés passent ; les preuves nécessitant le PC Windows portent leur propre statut. Aucune CI lancée pendant cette préparation.

## Processus de livraison
- [ ] Cette PR est ouverte en brouillon pour CADRAGE : ce commit ne contient aucun correctif applicatif et ne doit pas être fusionné seul.
- [ ] Développer les PR dans l'ordre des dépendances, UNE SEULE à la fois. Avant chaque lot, repartir de main actualisé, vérifier HEAD et git status, ne pas intégrer la branche accidentelle non validée.
- [ ] Pas de FULL ni de certification répétée pendant les commits : seules les vérifications rapides et ciblées nécessaires au développement sont autorisées.
- [ ] Quand le lot entier fonctionne, passer Ready for review et déclencher la certification adaptative finale une seule fois, sur le SHA exact du candidat. Doctor ciblé, sécurité, Windows et mesures RAM selon l'impact.
- [ ] Un échec impose correction, nouvelles vérifications ciblées et certification finale actualisée ; ne jamais déclarer PASS une preuve ancienne ou non exécutée.
- [ ] Conserver les sauvegardes, les identités vérifiées, les interfaces Quêtes/Succès, le chargement paresseux et les données des étapes. Ne pas élargir le périmètre sans nécessité documentée.
- [ ] Certifier sur un vrai client Windows tout ce qui nécessite Npcap/Unity ou une capture UI réelle ; en absence de preuve, afficher BLOQUÉ plutôt qu'inventer un succès.
