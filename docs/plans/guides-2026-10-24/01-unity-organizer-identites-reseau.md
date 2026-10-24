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

## Processus de livraison
- [ ] Cette PR est ouverte en brouillon pour CADRAGE : ce commit ne contient aucun correctif applicatif et ne doit pas être fusionné seul.
- [ ] Développer les PR dans l'ordre des dépendances, UNE SEULE à la fois. Avant chaque lot, repartir de main actualisé, vérifier HEAD et git status, ne pas intégrer la branche accidentelle non validée.
- [ ] Pas de FULL ni de certification répétée pendant les commits : seules les vérifications rapides et ciblées nécessaires au développement sont autorisées.
- [ ] Quand le lot entier fonctionne, passer Ready for review et déclencher la certification adaptative finale une seule fois, sur le SHA exact du candidat. Doctor ciblé, sécurité, Windows et mesures RAM selon l'impact.
- [ ] Un échec impose correction, nouvelles vérifications ciblées et certification finale actualisée ; ne jamais déclarer PASS une preuve ancienne ou non exécutée.
- [ ] Conserver les sauvegardes, les identités vérifiées, les interfaces Quêtes/Succès, le chargement paresseux et les données des étapes. Ne pas élargir le périmètre sans nécessité documentée.
- [ ] Certifier sur un vrai client Windows tout ce qui nécessite Npcap/Unity ou une capture UI réelle ; en absence de preuve, afficher BLOQUÉ plutôt qu'inventer un succès.
