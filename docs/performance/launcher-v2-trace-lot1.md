# PR #285 — lot 1, traces de démarrage (préparation de baseline)

Statut : **instrumentation uniquement**, aucune optimisation ni performance certifiée.

Sur un PC Windows avec l'exécutable réel du SHA étudié :

```powershell
$env:DOFUS_ATLAS_STARTUP_PROFILE = '1'
$env:DOFUS_ATLAS_STARTUP_PROFILE_FILE = "$env:LOCALAPPDATA\DofusAtlas\logs\startup_profile.jsonl"
# Lancer DofusAtlas.exe normalement puis fermer Atlas ; répéter avec le même SHA.
py -3.13 -m tools.startup_trace_report "$env:DOFUS_ATLAS_STARTUP_PROFILE_FILE"
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
