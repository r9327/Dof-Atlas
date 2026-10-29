# Atlas — Contrôle rapide de toute la navigation

Le workflow **Atlas Short Complete App Journey** est un smoke test Windows
de la vraie application PySide6 en une session Qt, et non une simulation
de huit comptes ni un benchmark de FPS desktop.

- Démarrage de `AtlasWindow`, attente de toutes les tâches de
  préchargement, états READY/FAILED et temps de preload.
- Parcours exhaustif des 20 entrées de navigation actuellement exposées
  dans la barre de l'application : Home, Organizer, Encyclopédie
  (Guide/Quêtes/Succès), Bestiaire (Donjons/Monstres/Archimonstres/Avis),
  Outils (Crafts/Map monde/Chasse/Ocre), Stuffs (PvM/PvP/Builders),
  Almanax, Paramètres et Tutoriels.
- Mesure par route : temps vers l'écran prêt, retour Home, RSS de
  processus et d'arbre, pic CPU, délais de la boucle d'événements Qt.
- Chasse, Ocre, Almanax et Tutoriels sont des écrans `PlaceholderPage`
  actuellement « en travaux ». Leur navigation est vérifiée séparément,
  **sans** attribuer un succès fonctionnel à ces fonctionnalités.
- Vérification fail-closed : une route en erreur, une tâche preload en
  échec, un ID attendu manquant ou une preuve invalide donne FAIL.
- Budget de mesure de **540 secondes maximum**, job Windows **20 minutes
  maximum y compris les installations et les données**. Un seul passage
  représentatif, pas de campagne 30-60 minutes.

Commande interne utilisée par CI :

```powershell
python -X faulthandler -m tools.doctor_quick_app_probe --max-seconds 540 --timeout 18 --output artifacts/quick_app/report.json
```

Le rapport `artifacts/quick_app/report.json` garde chaque mesure et les
erreurs, y compris si le job échoue. Cette campagne complète **les**
benchmarks Phase 8/preload et Doctor guides ; elle **ne les remplace pas**.
Elle ne lance pas la version empaquetée du launcher, ne fournit pas de
profil machine faible, ni une preuve exhaustive de toutes les fonctions
à l'intérieur de chaque module.
