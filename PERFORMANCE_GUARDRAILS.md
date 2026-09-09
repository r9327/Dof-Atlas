# Dofus Atlas — Performance Guardrails

Ce document complète les garde-fous généraux avec les invariants de performance à préserver.

## Quêtes

Pour un gros catalogue Dofus :

- l'ouverture de Quêtes ne doit pas matérialiser toutes les lignes de toutes les suites ;
- la hiérarchie charge d'abord catégories + suites, puis les quêtes d'une suite seulement à son expansion ou à la sélection d'une quête ;
- l'historique de la dernière quête ne doit pas forcer le rendu complet d'une fiche pendant la construction de la page ;
- une recherche riche sur le catalogue doit être debouncée et son document normalisé mis en cache, au lieu d'être reconstruit pour chaque quête à chaque frappe ;
- une mutation de progression ciblée ne doit pas reconstruire toute la page si la quête concernée suffit ;
- le rendu natif visible est prioritaire : un rendu HTML caché de compatibilité ne doit être construit que si un consommateur le demande explicitement ;
- tout cache d'images/icônes doit rester borné ;
- la direction cible du catalogue reste : liste/index léger -> détail à la demande -> images au besoin.

## Démarrage

- La fenêtre et l'accueil doivent pouvoir être peints avant les travaux lourds non indispensables.
- Les pages Encyclopédie et Équipement restent des placeholders/factories jusqu'à leur ouverture réelle.
- Les préchargements lourds doivent rester hors du thread UI Qt.
- Ajouter une donnée au preload doit répondre à un coût mesuré ou à une interaction imminente ; précharger davantage n'est pas une optimisation en soi.
- Le démarrage ne doit pas charger QtWebEngine/Chromium uniquement pour préparer Équipement.

## QtWebEngine

- Aucun import `PySide6.QtWebEngine*` au niveau module d'Équipement.
- Chromium est créé uniquement lorsque la page Équipement devient nécessaire/visible.

## Images

- Le décodage lourd évitable ne doit pas revenir sur le thread UI.
- Ne pas conserver un nombre non borné de pixmaps/images décodés.
- Réutiliser les loaders et caches existants avant de créer un chemin parallèle.

## Refresh UI

- Préférer invalidation et refresh ciblés à la reconstruction d'un écran complet.
- Un changement de progression d'une quête doit mettre à jour la quête et les surfaces réellement dépendantes, pas rebâtir arbitrairement tout le catalogue.
- Les recherches/filtres continus qui parcourent un gros catalogue doivent être debouncés.

## Mesure

Le benchmark canonique est `app/modules/encyclopedia/tools/benchmark_guides_performance.py`.

Les mesures minimales à conserver sont :

- construction / premier affichage ;
- démarrage stabilisé ;
- RAM au démarrage stabilisé ;
- ouverture Quêtes ;
- RAM après ouverture Quêtes ;
- ouverture Guide et Succès ;
- RAM après les grosses vues ;
- CPU au repos ;
- réutilisation des caches Encyclopédie.

Les seuils temporels absolus ne doivent pas devenir des tests CI fragiles entre machines différentes. Les comparaisons de temps/RAM se font contre une baseline capturée dans le même environnement.

Une optimisation n'est pas considérée comme un gain si elle déplace simplement le blocage visible ailleurs ou augmente fortement la RAM sans bénéfice mesuré.
