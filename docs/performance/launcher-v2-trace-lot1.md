# PR #285 — lot 1, traces de démarrage (préparation de baseline)

Statut : **instrumentation uniquement**, aucune optimisation ni performance certifiée.

Sur un PC Windows avec l'exécutable réel du SHA étudié :

```powershell
$env:DOFUS_ATLAS_STARTUP_PROFILE = '1'
$env:DOFUS_ATLAS_STARTUP_PROFILE_FILE = "$env:LOCALAPPDATA\DofusAtlas\logs\startup_profile.jsonl"
# Lancer DofusAtlas.exe normalement puis fermer Atlas ; répéter avec le même SHA.
py -3.13 -m tools.startup_trace_report "$env:DOFUS_ATLAS_STARTUP_PROFILE_FILE"
py -3.13 -m tools.startup_trace_report "$env:DOFUS_ATLAS_STARTUP_PROFILE_FILE" --json
```

Le launcher transmet l'identifiant de session au processus Atlas. Les timestamps `t_ns`
utilisent `time.perf_counter_ns` sur la même machine et les segments sont calculés
seulement lorsque les deux événements existent. Les événements `qt_event_loop` et
`app_health_ack` correspondent à la boucle Qt et à la santé du processus, **pas** à
Home réellement utilisable. `home_visible` est enregistré après `show()` et
`home_event_loop` lors d'un callback ultérieur ; un test de réactivité et de paint
Windows reste indispensable pour attester Home interactive. Le premier événement
commence à l'entrée Python du launcher, **pas au double-clic natif** ; il manque
encore l'instrumentation de la phase bootstrap/packaging pour le temps complet.

Les traces sont limitées à 2 MiB, n'enregistrent ni chemin, ni token, ni données
personnelles dans les lignes JSONL et ne sont pas utilisées pour le succès du
healthcheck. Pour refaire une campagne, archiver le fichier expurgé puis le vider
à la main ; le programme ne touche jamais aux journaux anciens. Faire des campagnes
séparées « sans mise à jour », « patch 1–3 fichiers », « installation vierge »,
« cache froid/chaud », en notant CPU, disque, antivirus et version du build.

Le rapport affiche p50/p95 pour chaque segment et le nombre de sessions. Les
segments incomplets sont `NOT RUN`, pas des succès. Comparer exclusivement des
runs Windows sur même machine et mêmes conditions ; aucune cible absolue n'est
prouvée par l'ajout de ces points de mesure.

## Extension de la baseline : I/O, install et premier paint

La sonde `home_first_paint` est liée au vrai `QEvent.Paint` de Home, après
l'affichage de la fenêtre ; `home_event_loop` reste distinct et ne prouve
ni un clic utilisateur ni l'absence de blocage ultérieur. Les sondes de
l'installateur enregistrent les **octets réutilisés/copied dans le staging**
et les octets décompressés, ainsi que les fichiers dans chaque catégorie.
Le différentiel évite des octets réseau inchangés mais **recopie encore**
les fichiers inchangés dans le nouveau slot : cette mesure permettra de
chiffrer le coût réel, sans prétendre qu'il est nul.

`download_archive_ready.network_bytes` compte uniquement les octets lus
pendant les téléchargements mono-archive terminés. Les archives multipart comptabilisent maintenant les octets réseau réellement
lus pendant chaque tentative, y compris après retry ou reprise, indépendamment
de la progression logique. Le compteur cached_bytes rapporte les octets déjà
présents et réellement réutilisés. Une archive entière préalablement vérifiée
produit network_bytes=0. Aucun zéro n'est déduit d'un marqueur absent. Les téléchargements interrompus ne sont pas comptés
comme complets. `process_cpu_ms` est un temps CPU propre au processus,
et `process_rss_bytes` sa mémoire résidente sur Windows (si accessible) :
ni l'un ni l'autre ne représente tout l'arbre de processus.

Le rapport `--json` (schéma 1) fournit les effectifs, p50, p95 et extrema
des segments et compteurs effectivement présents. L'analyseur historique
`tools.analyze_startup` continue de lire ses profils anciens dans le même
JSONL sans confondre les nouvelles lignes de trace avec des profils achevés.
Pour les comparaisons avant/après, collecter sur le **même Windows** et
archiver un échantillon expurgé : aucune baseline Windows n'a été produite
par ce commit.

## Comparaison de campagnes avant/après

Sur un même PC et dans un scénario identique, conserver séparément les
fichiers JSONL du build de référence et du candidat, sans concaténer leurs
sessions. La commande ci-dessous crée un rapport consultable et versionné :

```powershell
py -3.13 -m tools.startup_trace_report .\candidate.jsonl --baseline .\baseline.jsonl --json
```

Le comparateur demande au moins **5 échantillons par segment dans chaque
campagne** ; une donnée absente ou un p50/p95 de base nul produit
`INSUFFICIENT_EVIDENCE`. Une variation strictement supérieure à 5 % déclenche
`INVESTIGATE_OVER_5_PERCENT` ; `NO_5_PERCENT_ALERT` ne signifie **jamais**
que la régression est exclue ou qu'une certification est acquise. Contrôler
la dispersion, les conditions de mesure et la significativité avant de conclure.
Une trace synthétique ne remplace pas des résultats sur l'EXE Windows réel.

## Résilience des fragments de cache

Le compteur `cached_bytes` n'inclut maintenant que les octets effectivement
réutilisés et présents **avant le lancement courant**. Les octets téléchargés
puis repris après une erreur dans ce même lancement appartiennent au
`network_bytes`, pas au cache. Si le serveur répond 200 à une requête Range,
le préfixe abandonné n'est pas compté comme réutilisé.

Un fragment de longueur complète mais dont le SHA-256 est invalide est
supprimé, puis retéléchargé dans le même lancement avec le nombre de tentatives
déjà borné. L'archive assemblée reste vérifiée intégralement avant toute
installation. Les tests de corruption de ZIP protègent l'état actif et la
progression externe aux slots.

## Handoff visible Qt et Home (compatibilité)

L'ancien `DOFUS_ATLAS_HEALTH_FILE` reste un ACK **préchargement Qt vivant**.
Pour les nouvelles paires lanceur/application, un marqueur temporaire
`.capable` est publié **avant** cet ACK et un `.home` distinct est émis
uniquement après le premier `QEvent.Paint` de Home et un tour de boucle Qt
supplémentaire, lorsque Home reste visible et actif. Le launcher attend
ce second signal jusqu'à 130 secondes au maximum avant de conclure son
handoff. En cas de fermeture de l'application, l'échec permet le rollback ;
en cas de timeout avec un processus encore vivant, une erreur visible bloque
la relance automatique d'une autre version (pas de deux processus concurrents).
Ces sentinelles sont temporaires et nettoyées par le launcher.

Une ancienne application qui ne publie pas `.capable` conserve le protocole
historique : l'ACK Qt suffit. Ceci préserve la compatibilité après une mise
à jour progressive du launcher. Pendant le lancement de Qt, le Tk launcher
est masqué ; la boîte de préchargement Qt reste l'interface visible.
Le calendrier exact de peinture multi-fenêtres et les cas antivirus doivent
encore être vérifiés sur un vrai PC Windows. Le signal ne constitue pas
à lui seul une preuve de clic/interaction utilisateur réelle.

## Vérification PID des marqueurs Qt/Home

Le launcher vérifie désormais le **PID exact du processus lancé** dans
les sentinelles `.ready`, `.capable` et `.home`. Il ignore les fichiers
vides, partiellement écrits ou issus d'un autre PID. Une capacité V2
présente mais invalide empêche un repli silencieux vers le seul ACK Qt
pendant que le processus est vivant. Le format `.ready` historique
contenait déjà ce PID : la compatibilité reste préservée.
Ce contrôle ne certifie pas à lui seul la réactivité de Home sur Windows.

## Protection entre lancements successifs (mutex existant)

Le launcher vérifie désormais, **avant** toute récupération de pack ou
rollback de slot en attente, le verrou de processus unique que `main.py`
utilise déjà sur Windows. Si une instance Atlas le détient, il n'effectue
ni mise à jour ni second lancement. Aucun nouveau verrou ou état disque
n'est introduit. Si une application reste vivante après 50 s sans ACK,
le lanceur signale un échec sans lancer de rollback concurrent ; un
processus réellement terminé permet toujours la récupération normale.
La course très précoce avant l'acquisition du mutex par le processus
en démarrage et le comportement natif Win32 restent à tester sur PC.
