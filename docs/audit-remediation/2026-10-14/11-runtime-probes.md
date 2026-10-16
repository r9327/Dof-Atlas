# [PLAN 11] Probes runtime : performance Guide/Craft, warmup et lifecycle (PC-01 à PC-05)

> **Implémentation et probes du 16 octobre 2026.** Deux comportements ont été
> reproduits et corrigés. Les preuves locales Qt et les limites Win32 sont
> séparées ; aucun budget de RAM ni scénario en jeu n'est inventé.

## Verdicts et preuves

[Registre des cinq probes](11-runtime-probe-results.json). Base applicative
inspectée : `e109913698ed84b25c7873d70303d83391732cce`, dataset public
`dofusdude/dofus3-main@3.7.10.10`, Python 3.13 / Qt 6.12. Les chiffres locaux
ci-dessous ne sont pas des mesures Windows ni une certification générale.

### PC-01 — recherches répétées Guide : CONFIRMÉ, répétitions corrigées

Les trois vrais appels `QuestGraphService.guide_ids(2464)` ont été exécutés
avec le **MemoryBoundGuideProvider de production**, pas la façade historique
GuideProvider dont l'index en mémoire est différent. Sans fichier compact,
le premier appel matérialise les détails (~16,3 s dans ce relevé) et les deux
suivants rescannent les 26 guides (~79,7/89,8 ms). Trois tentatives d'ouverture
du cache absent sont observées ; ce ne sont pas trois lectures réussies.

Le propriétaire existant `_by_entity` mémorise maintenant les seuls résultats
explicitement demandés, positifs et négatifs, avec une capacité de 64 clés.
Home conserve son index initial vide ; aucun index global n'est recréé.
Les résultats ne retiennent que les résumés déjà présents dans `_by_id` et
sont rendus par copie. `release_catalogue`/rechargement vident le même owner.
Sur les mêmes appels après correctif : première recherche encore coûteuse
(~13,8 s), puis 0,011/0,003 ms ; une seule tentative de cache et 26 demandes
de détails au total. La première matérialisation n'est **pas** résolue ici et
doit rester mesurée dans les parcours Windows, sans extrapoler un gain RAM.

### PC-02 — limite appliquée avant catégorie Craft : CONFIRMÉ et corrigé

Une base SQLite de 181 recettes correspondantes place une ressource après
180 équipements. Avant correctif, les 160 premiers candidats sont tous des
équipements et l'onglet Ressources affiche zéro résultat. Après correctif,
la même ressource est trouvée. Une variante ajoute un trophée au-delà de la
même limite et protège aussi cette catégorie.

La catégorie sélectionnée traverse les façades existantes jusqu'au repository.
SQLite applique le prédicat canonique **avant LIMIT**, puis le curseur fournit
un résultat borné ; aucune liste du catalogue complet n'est matérialisée.
Les deux fonctions de classement précédentes donnaient la même catégorie sur
les 21 554 objets publics (zéro divergence) : leur unique propriétaire est
désormais `local_dofus_data.normalizer`, réexporté par les anciens modules.
Recherche et affichage utilisent donc la même règle, sans nouvelle colonne,
migration, cache ou version de base.

La fixture donne 0 résultat avant et 1 après. Le relevé initial avant est
3,447 ms ; trois passages du correctif SQL final sur la vraie page donnent
3,046 / 1,392 / 1,302 ms. Le relevé intermédiaire de 7,962 ms est conservé
et identifié comme tel dans le registre. C'est une correction fonctionnelle,
pas une promesse d'accélération. Six recherches sur le vrai seed public sont relevées dans le
registre (environ 4–64 ms selon requête/catégorie), sans certificat de latence UI.

### PC-03 — concurrence de lancement : preuve Win32 séparée

Le code normal acquiert `SingleInstanceGuard` avant QApplication et tout
préchargement. Un nouveau probe utilise le **vrai mutex Windows** et deux
processus proches, avec un nom de test isolé : ils doivent être refusés tant
que le premier handle existe, puis un troisième doit pouvoir acquérir après
libération. Les enfants sont bornés et nettoyés même sur échec.

En local Linux, le contrat portable est testé et la preuve native affiche
explicitement `BLOCKED / Windows required`. La FULL Windows exécute la branche
Win32 et imprime son résultat réel. Ce probe et l'ordre du point d'entrée
ne prétendent pas avoir lancé deux sessions interactives complètes, ni testé
Npcap/UAC ; #175 conserve cette limite. Aucun conflit `.tmp` n'est inventé.

### PC-04 — quitter pendant le chargement : rétention transitoire observée

Le test utilise la vraie page mémoire de l'Encyclopédie, le vrai provider Guide
de production et les données Quêtes publiques. Une barrière bornée tient le
chargement réel, puis la page est masquée et détruite par `deleteLater`.
Le QObject est détruit immédiatement ; le wrapper Python reste temporairement
possédé par le worker `Thread` actif. Après libération de la barrière, vrai
chargement terminé et collecte GC : worker arrêté, weakref vide.

Ce scénario ne reproduit pas de fuite permanente. Aucun cancel/cache ni
suppression de worker n'est ajouté. Il couvre ce worker Python, pas tous les
QThread, le RSS global ou le bureau interactif ; les caches disque peuvent
être chauds même si l'instance de provider/widget est neuve.

### PC-05 — anciens préloaders : CONSERVER

Graphify et l'AST des Python suivis ne trouvent aucun appel direct aux deux
fonctions historiques de `main`. Les tests/introspections de
`test_shell_reliability.py` sont cependant des consommateurs réels de l'API.
L'absence de callers dynamiques/externes n'est pas prouvée. Le lancement normal
et ses gardes de performance restent testés ; aucune fonction ni `app.preload`
n'est supprimée sur la base d'une arête absente.

## Validation et portée

Graphify 0.9.72 généré avant changement sur
`76a1115f04f5eff79cbe70d5ecdfca8155b6aa3a` : propriétaires Craft (226 nœuds,
884 arêtes) et Guide/graph (90 nœuds, 296 arêtes) examinés puis recoupés avec
le code. Tests de régression : catégorie au-delà de 160, vrais chemins UI →
façades → SQLite, résultats bornés, cache positif/négatif et libération,
destruction Qt pendant worker réel, mutex natif/contrat portable et préloaders.
Les preuves finales exact-SHA proviennent de la CI, les observations locales
du registre restent préliminaires. Aucun changement de données utilisateur.

**Référence audit :** PR #160, main audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Mission
Mesurer les coûts et risques dans de vrais parcours avant de prescrire cache, thread cancel ou suppression d'un préloader.

## Couverture sans doublons
PC-01, PC-02, PC-03, PC-04, PC-05 (toutes NON CONFIRMÉES)

## Sources à lire
- memory_bound_guide_provider.py:256 et consumers Quest UI
- app/pages/craft_page.py:773
- DOFUS.bat:82 et app/startup_cache_warmup.py:145
- app/modules/encyclopedia/views/encyclopedia_page.py:950
- main.py:510/530 et app/preload.py:30

## Enchaînement de vérification
1. PC-01 : spy réel des requêtes relations sur une session Guide/Quêtes ; conserver search-text cache déjà en place, indexer seulement si un coût est mesuré.
2. PC-02 : fixture SQLite avec correspondances métier au-delà de limit=160, puis refaire une recherche avec filtrage catégorie ; mesurer ordre SQL/filter vs affichage.
3. PC-03 : deux lancements Windows proches, traces mono-instance, collision de fichiers .tmp et workers ; un soupçon de concurrence ne vaut pas preuve d'écrasement.
4. PC-04 : fermer Encyclopédie/Home pendant un chargement froid, observer weakrefs, QThread, deleteLater et stabilisation en fin de worker ; distinguer rétention transitoire et fuite.
5. PC-05 : lister consommateurs source et externes de run_startup_preload/build_preload_payload, tests et CLI avant toute suppression, tracer chemins hérités.
6. Conserver le bilan NON CONFIRMÉ lorsque Windows/data manque ; corriger uniquement un comportement reproduit ; relier les corrections prouvées aux PR #163/#164/#167 si elles sont déjà propriétaires.

## Critères de sortie
- [x] 5 pistes avec reproduction ou limite native explicite, verdict et preuves consultables
- [x] Réutilisation de l'owner de relations existant après mesure ; aucune suppression sur graphe seul
- [x] Régressions prouvées protégées par tests ; mesures locales et limites sans gain RAM inventé

## Dépendances
Coordonner #163 caches, #164 UX Craft, #167 performance ; Win32 native requis pour PC-03, session Qt réelle pour PC-04.

## Méthode commune
- Commencer par HEAD réel et git status. Ne pas inventer de défaut à partir d'un graphe inferred.
- Diff minime, test ciblé, vérification des consumers et impacts, AI Context régénéré après code.
- Conserver les contrats JSON, la progression utilisateur et le lazy-loading ; no FULL en boucle.
- Aucun merge tant que corrections effectives et preuves exact-SHA n'existent.

[Rapport](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) | [Index des preuves](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/README.md).
