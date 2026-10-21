# PR — Parcours réel Guides / Quêtes / Succès / sauvegarde Windows

## Objectif
Fermer le trou entre les nombreux tests isolés et l'usage utilisateur.
Réutiliser les tests/oracles Doctor existants : aucun nouveau runner de test
UI, aucune nouvelle source de vérité ni duplication des moteurs de progression.

## Ordre obligatoire
Travail applicatif **après intégration complète et certification de #226 puis
#225** (ou vérifier l'ordre effectif de leurs dépendances). Avant cela, ne
préparer que la fixture et les assertions qui ne touchent pas à leurs fichiers.

## Scénario minimal contrôlé
1. Ouverture à froid de l'EXE Windows installé avec profil de test isolé ;
   ouvrir Guide, Quêtes, Succès et revenir Home.
2. Sélection d'un guide Dofus Ganymède, plusieurs étapes consécutives,
   étapes répétant le même ID quête, prérequis différés et préparation objets
   ventilée par personnage.
3. Avancer manuellement pour 0/1/2/5 personnages (sans validation réseau
   inventée), changer de module et revenir à **l'étape actuelle**.
4. Relancer l'application : vérification exacte de l'identité des étapes,
   des quêtes et des succès, de l'absence de pages fantômes/doublons et
   de la progression sauvegardée.
5. Refaire le trajet en mode chaud, puis avec arrêt/reprise pendant
   une lecture ; vérifier l'intégrité et la récupération des écritures.
6. Tests d'interaction et captures lisibles provenant des oracles Doctor,
   rattachés au bon SHA, pas à des rectangles ou à des tests sautés.

## Contraintes non négociables
- Parcours Ganymède : **ordre des étapes source conservé**. L'optimisation
  géographique appartient exclusivement aux Guides optimisés distincts.
- IDs/quantités/prérequis canoniques, aucune validation automatique de quête.
- Fichiers de progression isolés, jamais altérer de vraies sauvegardes.
- Réutiliser les tests `tests/test_application_runtime_characterization.py`,
  `tests/test_atlas_doctor_encyclopedia_smoke.py` et les mécanismes de
  `doctor-ui.yml` lorsque adaptés ; pas de deuxième système UI.
- Aucun changement de `guides_view.py` / `encyclopedia_page.py` pendant
  leur développement dans #225/#226.

## Critères de sortie
- [ ] Une fixture/exécution déterministe sur Windows réel (cold/hot).
- [ ] Vérification UI + persistance intermodules + crash/reprise exécutée.
- [ ] Rapport détaillé PASS/FAIL/BLOCKED sur le SHA final, avec captures et
  preuves de non-régression de progression.
- [ ] Si un bug est trouvé, corriger sa cause dans le composant canonique
  via lot isolé et ne pas transformer la PR en refonte de l'UI.
- [ ] Certification finale unique après code terminé, Draft avant.

**État initial : spécification uniquement, aucun PASS revendiqué.**
