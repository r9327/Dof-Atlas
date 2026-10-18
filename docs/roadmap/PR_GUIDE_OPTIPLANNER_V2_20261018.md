# PR Guide Tools — Guide Opti V2 : planificateur intégral

Date : 18 octobre 2026. Base : main SHA 6a52522d1bd7e501a5c3b4d6d58253bfec755fdc.
Statut : contrat fonctionnel et plan de développement, **non implémenté**. Pas de fusion tant que les comportements ne sont pas testés.

## Mission
Produire un parcours COMPLET et cohérent (Quêtes / Succès / Guide Lanyel / Guide Succès), non une succession de lignes isolées, en minimisant les passages de zone, déplacements, retours PNJ et donjons, sans franchir un prérequis, perdre une étape ou contredire une quête. L'affichage garde les décisions de la PR UI.

## Entrées canoniques
- Données locales DOFUS / Doduda, quêtes-objectifs par ID, succès, bestiaire, drops, captures, donjons, métiers, ressources, maps, Zaaps accessibles.
- Guides DPLN (priorité), Tougli et JOL pour contrôle croisé : ordre dialogues, PNJ, positions, prérequis, situations spéciales. Conserver liens/provenance, version, degré de confiance dans la donnée interne ; ne pas recopier les sites en intégralité. Divergences => REVIEW, jamais faux fait positif.
- Sources existantes : `tools/build_guide_ultime_gps_route.py`, `tools/guide_action_model.py`, `tools/guide_action_normalizer.py`, `tools/guide_action_contract.py`, `app/modules/encyclopedia/services/guide_ultime_manual_route.py`, `guide_auto_validation_contract.py`. Une seule source de vérité ; ne pas dupliquer les générateurs.

## Planification structurée
1. Inventaire intégral des nœuds / actions : quête et objectif ID exact, PNJ, carte/coordonnées/monde, métier/niveau, item/quantité/type d'acquisition, mob ID, boss, donjon, succès, capture, interlocuteur et retour.
2. Graphe de dépendances explicite : quête commencée/active/terminée, prérequis et critères stricts, branches d'alignement/classe/ordre, niveau, ressources à acquérir naturellement, dangers. Bloquage si preuve insuffisante (pas de prise en charge abusive d'un événement `actif` comme `terminé`).
3. Regrouper par zone/carte et phase : activer les quêtes avant le même combat ; cumuler les objectifs compatibles et drops, quantités exactes, conditions et limites ; planifier les rencontres de PNJ sur une seule carte ; prévoir les retours obligatoires.
4. Donjons : rassembler les quêtes à activer AVANT entrée, boss à capturer, succès compatibles/incompatibles, clés, captures après boss, quêtes à valider avant de quitter ; distinguer un passage inévitable supplémentaire.
5. Captures : boss / archimonstres, puissance de pierre, éligibilité réelle DOFUS 3.7, nombre requis par personnage, stock saisi par l'utilisateur, stock déjà acquis, déjà capturé, besoins restants `50/150 => 100` ; les objectifs de zone et drops ne créent PAS faussement une obligation de pierre d'âme.
6. Préparation : liste globale dédupliquée ; acquisition naturelle vs achat/récolte, évite l'achat abusif de drops exclusifs de quête et les préparations devenues inutiles.
7. Zaap / Travel : chaque position cliquable garde exactement son rendu texte, mais porte en DONNÉES un plan typé `direct` ou `zaap_then_travel` avec coordonnées Zaap et cible ; optimiser depuis position estimée fiable, mondes/conditions, coût/détour ; si incertitude, pas de téléportation hasardeuse. Format supporté DOFUS 3.7 : `/travel x,y` ou `/zaap zx,zy ; /travel x,y`. Aucun contrôle Zaap visible dans le guide.
8. Multicomptes : personnages participant au guide (sélection persistante Organizer), prérequis individuels, étapes/succès déjà faits, sessions online/offline ; recommander le meilleur groupement d'activités sans confondre les progressions. Ne pas supposer qu'une quête se valide pour toute l'équipe.
9. Plan stable : IDs persistants par chapitre / étape, migrer sans perte ; recalcul incrémental à changement réseau, choix utilisateur et stock déclaré ; éviter de réordonner brutalement les fiches déjà validées.
10. Explicabilité interne : pour chaque choix, garder les dépendances, quêtes, résultats escomptés, alternative et preuves ; UI n'affiche pas les sources ni des explications non désirées.

## Noms des chapitres, fiches et actions : COURTS et compréhensibles
- Le générateur nomme les **chapitres et fiches** avec des intitulés naturels, utiles, distincts et aussi courts que possible ; le titre décrit ce qu'on fait, pas les explications ni la liste entière des quêtes concernées.
- **Objectifs indicatifs contrôlés** : chapitre <= 40 caractères, fiche <= 48 caractères, de préférence 2 à 6 mots. Ne pas couper arbitrairement un nom officiel de PNJ, monstre, donjon ou quête. Si une exception dépasse la limite pour rester exacte, la justifier et la signaler au diagnostic (REVIEW, non suppression silencieuse).
- Commencer par un verbe d'action uniquement quand cela clarifie le but. Éviter les titres génériques (`Étape suivante`, `Faire des choses`), les chaînes de prérequis, les coordonnées redondantes, les noms complets de plusieurs quêtes et les formules artificielles (`Optimisation intelligente des objectifs...`).
- Exemples attendus : `Alignement Bonta` (chapitre) ; `Retour à Amayiro`, `Combats des Scarafeuilles`, `Donjon des Blops`, `Capturer le Bouftou Royal` (fiches). La fiche explique les conditions et les objectifs dans son **contenu**, jamais en surcharge du titre.
- Pour les actions, libellé concis mais **nom exact du monstre / PNJ / objet + quantité si nécessaire** : `×5 Tournesol sauvage`, `Parler à Amayiro`, `Récolter 10 Orties`. Ne pas abréger au point de rendre un objectif ambigu. Garder dans les données les identifiants et les liens complets.
- Si plusieurs fiches auraient le même titre, ajouter un discriminant minimal de zone, type d'action ou donjon, pas un suffixe générique `(2)` sans contexte. Une renumérotation ne doit pas casser les identifiants persistants.
- Créer un module de **naming déterministe partagé** par les outils de génération, les Guides Succès et Lanyel ; une règle unique pour titres/chapitres/actions, au lieu de retouches visuelles ou de chaînes tronquées par CSS.
- Doctor Guide/Integrity vérifie automatiquement la longueur, les titres peu informatifs, les duplications ambiguës, les identifiants perdus, les noms inventés et la lisibilité ; échantillonner des centaines de titres réels et valider les exceptions manuellement.
- **Ne pas injecter d'autres panneaux dans l'UI** pour résoudre un titre trop long. Les prérequis, les quêtes liées et les sources restent des données internes sans affichage systématique dans les fiches.

## Points supplémentaires verrouillés — intégration terrain
- **Captures de zones, pas seulement boss** : détecter séparément les objectifs de capture/collecte spéciaux de zone et les pierres d'âme classiques. Ne jamais écarter silencieusement une capture de zone ni l'assimiler automatiquement à une pierre. Vérifier pour chaque version du jeu les conditions exactes, le nombre de monstres/groupes et si une ressource consommable est réellement nécessaire.
- **Déplacement optimisé au niveau de la route entière** : chaque coordonnée cliquable existante est reliée à un plan de déplacement déterministe, calculé à la génération, jamais à une heuristique d'affichage. Tenir compte du dernier point fiable, de l'accès au Zaap, du monde et des retours obligatoires des quêtes. Si l'information est insuffisante, n'envoyer aucune commande risquée.
- **Participants exacts** : sélectionner dans Organizer des identités distinctes (pas seulement le nombre de personnages) ; étudier qui a déjà validé quoi pour éviter les étapes inutiles. Une capture de boss/zone et une pierre déjà acquise ne sont pas nécessairement équivalentes : traiter stock et validation séparément.
- **Préparation générale réelle** : agréger le total du guide et les besoins RESTANTS selon les participants choisis, avec quantités par puissance/type de pierre, acquisition de ressources au fil du trajet et suivi 50 possédées / 150 nécessaires. Prévoir correction manuelle et historique de stock sans inventer des possessions.
- **Mesure de qualité** : la réussite ne dépend pas seulement du nombre de fiches. Garder les objectifs exhaustifs, les coordonnées exactes, les textes d'action courts, les noms propres exacts et tous les prérequis ; comparer et faire contrôler les trajets, la clarté des fiches, les captures de zone, les doublons de PNJ et la stabilité des sauvegardes. Les sources sont conservées seulement pour l'audit interne.

## Interface vers les autres PRs
- Exposer `GuideTravelPlan(destination, mode, zaap_coords?, world?, eligible_character_keys)` et `GuideParticipantSelection(guide_id, character_keys)` ou contrats équivalents versionnés, sans imposer ces noms de classes.
- La PR Organizer exécute strictement la commande typée, après validation des fenêtres sélectionnées et sans envoyer à d'autres comptes.
- La PR UI rend les textes et anneaux existants, aucun nouveau panneau.

## Audits et tests exigés
- Jeux de cas réels : Bonta/Amayiro, quêtes multi-zone, PNJ répétés, drops partagés, donjons avec succès mutuellement exclusifs, captures boss / archis, mondes différents, Zaap inaccessible, combat bloqué.
- Comparaison ancien/nouveau parcours : nombres de visites de cartes/zones, retours PNJ, donjons, combats, pierres, km/Zaaps estimés **sans inventer de métrique réelle**. Les chemins calculés doivent être prouvés au niveau des IDs et des étapes.
- Doctor Guide/Graphify : objectifs orphelins, doublons, erreurs de quantités, recettes impossibles, mauvais mob, manque capture, transport invalide, prérequis sautés, liens d'identifiants, boucle ou branche bloquante.
- Contre-exemples (fausse alternative HDV, besoin de 2 donjons, un participant déjà terminé, réseau partiel) + régression Guide Lanyel, Quêtes, Succès, intégrité, RAM et certification HEAD exact.
