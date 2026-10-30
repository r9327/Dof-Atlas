# DOFUS ATLAS — Audit RAM exhaustif : 50 pistes suivies (30 octobre 2026)

> **Source de vérité :** [atlas-ram-inventory-v1.json](atlas-ram-inventory-v1.json). Ce document décrit les règles de preuve et l'ordre de réalisation. **Aucune réduction RAM supplémentaire ni certification globale n'est déduite d'une entrée simplement listée.** Doctor est l'unique orchestrateur du benchmark applicatif ; Graphify reste le moteur canonique pour examiner les références statiques.

## Baseline Windows reproductible

| Mesure | Dernière référence | Cible | Portée |
| --- | ---: | ---: | --- |
| Home stabilisé après 3 cycles | 118,62 Mio | <100 Mio, ambition 75–90 | 3 × 20 routes Qt hors écran ; pas un EXE sur poste client |
| Pic processus/arbre parcours global | 209,66 Mio | ≤250, ambition 220 | Même parcours, sans écran Windows natif |
| Pic processus/arbre 52 Guides | 259,36 Mio | ≤250, ambition 190–220 | Runner différent, ne pas comparer comme un A/B matériel |
| Ouverture Guide p50/p95 | 185 / 450 ms | conserver ≤250 ms p95 si possible | Chiffres du dernier runner ; la référence antérieure 97 / 215 ms venait d'une autre exécution |
| Premier saut profond dans Guide complet | 9,86 s observées | supprimer le blocage | À reproduire et mesurer sans masquer les causes |

Sources de mesures : [60 navigations Windows](https://github.com/r9327/Dof-Atlas/actions/runs/41085600072), [52 Guides Windows](https://github.com/r9327/Dof-Atlas/actions/runs/41085599988), [baseline antérieure](https://github.com/r9327/Dof-Atlas/actions/runs/41082400196). Les 27 placeholders sur 60 navigations ne sont **pas** des fonctions prouvées opérationnelles.

## 50 pistes, zéro omission silencieuse

Le fichier JSON couvre exactement `RAM-01` à `RAM-50`. Chaque piste a `priority`, `domain`, `title`, `status`, `evidence` et `owner`. Le test `tests/test_doctor_ram_inventory.py` bloque les oublis, doublons et statuts invalides.

Le statut `measured` signifie **qu'un mécanisme ou une mesure existe**, pas que l'optimisation est terminée ; `instrumented` signifie observabilité nouvelle non certifiée ; `todo` signifie preuve ou développement à réaliser. Le rapport Doctor affiche nécessairement `PARTIAL` tant que des pistes restent sans preuve. Le diagnostic Qt ne permet pas à lui seul d'attribuer chaque octet RSS.

### A. Attribution exacte des allocations — RAM-01 à RAM-12

- RSS processus et arbre, Home, per-route, différencier mémoire privée, partagée, commit, heap Python, allocations Qt natives et cache système.
- À présent : Doctor ajoute des **checkpoints limités** après RAM brute : nombre et familles de `QWidget`, page propriétaire Qt, pages lazy/chargées, QPixmapCache (plafond uniquement), cache image Encyclopédie (usage connu) et taille pixel Map Monde. Les valeurs absentes sont marquées absentes.
- À faire : `tracemalloc` en **campagne séparée** (pour ne pas contaminer les latences), preuves d'objets réellement vivants (`weakref`, `shiboken6.isValid`), profil natif Windows indépendant, durée de vie des workers, tâches et callbacks.
- Un objet Qt toujours vivant après `deleteLater()` n'est une fuite confirmée **que si une référence propriétaire maintient sa durée de vie**. Une hausse de RSS seule n'en est pas une.

### B. Modules visibles et icônes — RAM-13 à RAM-19

- Organizer : surveiller les reconstructions de `CharacterSlotsPanel`, les timers, la liste de fenêtres et les watchers ; conserver les macros, la sélection et la surveillance des fenêtres Dofus.
- Home et sous-navigation : éviter les icônes QIcon, boutons, QSS ou widgets recréés à chaque retour ; préserver les modifications de personnages.
- Map Monde : libérer les pixels cachés tout en préservant monde, sélection et historique ; vérifier le coût et la fluidité de la recharge asynchrone, les listes SQLite et les références des résultats de worker.
- Aucun libellé `page détruite` n'est admissible si le service conserve en réalité ses widgets ou sa grosse image.

### C. Guides et données partagées — RAM-20 à RAM-29

- Évaluer la virtualisation des 267/1672 étapes (seules étapes visibles / voisines), la mise en cache des détails et les mises à jour de progression. Comparer la parité du contenu et des 26 Guides avant/après.
- Reproduire le blocage au saut 134/267, attribuer au décodeur, à la requête, au dessin et/ou à la construction Qt ; jamais de placeholder ou perte de détail pour gagner la métrique.
- Cartographier tous les propriétaires de `QuestProvider`, `AchievementProvider`, `GuideProvider`, `QuestGraphService` ; mesurer duplication/cycles et durée de vie, ne pas partager arbitrairement un objet muté par personnage.
- Images : le cache partagé `ImageService` a déjà 8 Mio / 64 objets et décode à la taille demandée. Mesurer `QImage` + `QPixmap` réels, taux de hits et pertes de perf **avant** de réduire sa capacité.
- Catalogue SQLite Quêtes différé et itinéraire Sylvestre précompilé : conserver ces optimisations, surveiller la mémoire des détails individuels.

### D. Autres familles et processus — RAM-30 à RAM-37

- Crafts : `release_runtime` existe déjà ; vérifier que `IconCache`, result lists, recherche, adaptateurs et dialogues ne retiennent plus de grosses allocations.
- Bestiaire : distinguer les pages provisoires de l'implémentation réelle ; aucune mesure d'un placeholder ne vaut preuve du module.
- Stuffs : Chromium WebEngine n'est pas intégré au runtime de production ; ne pas le réintroduire pour « optimiser ».
- Unity : QSS, ombres `QGraphicsDropShadowEffect`, fonts, GPU et textures ; mesurer sans sacrifier le design officiel.
- Préchargement : mémoire de chaque PID, concurrence avec le processus principal, durée de vie et buffers ; le launcher et l'installation sont **pilotés séparément dans #285**.
- Windows : `Working Set`, `Private Bytes`, GPU et mémoire partagée sont des grandeurs différentes ; ne pas sommer pour expliquer le même RSS deux fois.

### E. Recette et budgets — RAM-38 à RAM-50

- Campagne Doctor/Graphify **exact SHA** : 52 Guides ×2, parcours menu 20 ×3, puis 10/20 cycles ciblés si dérive, première installation Windows vierge, mémoire privée/RSS, CI 8 processus Atlas indépendants (pas 8 clients DOFUS fictifs).
- Écran natif Windows pour valider photos/textes/UI ; offscreen seul ne certifie pas le rendu ou les FPS.
- Budget : Home <100 Mio, pic arbre ≤250 Mio, latence Guides non régressive à machine comparable, succès des interactions et des sauvegardes ; ambition 75–90 Home et 190–220 pic seulement après validation.
- Validation par **commission de preuve** : code, données sources, assets, progression, signaux, UI, startup, réseau, 8 Atlas, benchmarks. L'erreur, le manque d'artefact, le scénario non mesuré ou une dérive > marge bloque le qualificatif `COMPLETE_PASS`. Aucune suppression automatique de code ou données au nom de la RAM.

## Ordre de mise en œuvre

1. **Mesurer sans changer le runtime** : registre + checkpoints Doctor (livrés en lot d'instrumentation ; encore non certifiés au niveau système natif).
2. **Auditer les 4 suspects forts** : Organizer/widgets Qt, Guides profonds, providers partagés, images décodées. Faire un rapport objets vivants vs mémoire réservée.
3. **Corriger uniquement les causes prouvées**, en petits commits : une responsabilité, sa mesure avant/après, test fonctionnel, retour Home, cycle 10.
4. **Nettoyer les pics** : workers/préchargement/mémoire enfant ; pas de trim artificiel des Working Sets.
5. **Certifier** : Doctor exact SHA, Grapĥify, Win GUI véritable, replay des 52 Guides, 8 Atlas, preuves de tests, audit de chaque commit et audit transversal final.

## Conditions de fermeture non négociables

- Aucune ligne `RAM-01..50` perdue, pas de doublon ni de source « non couverte » masquée.
- Toute piste `todo` doit avoir soit une preuve et un verdict, soit un motif documenté et `NOT_APPLICABLE` justifié ; jamais `PASS` par défaut.
- Rapports relatant **ce qui est mesuré et ce qui ne l'est pas** ; graphiques d'évolution, répétition, et même machine/affinité pour tout calcul de gain.
- Profil natif complémentaire : les compteurs QWidget/QPixmap ne sont pas un profiler d'allocations C++.
- Sauvegardes, identités et progression par personnage inchangées ; les ~100 ms d'ouverture Guide ne doivent pas se transformer en secondes.
- PR #303 reste Draft tant que `Scoped PR Feedback`, validation EXE et critères du lot ne sont pas satisfaits.
