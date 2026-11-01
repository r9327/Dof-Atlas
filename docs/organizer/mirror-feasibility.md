# Organizer — Miroir expérimental, issue #321

**État : R&D Draft / non relié au runtime.** Ce document et
`app/macros/mirror_plan.py` ne constituent pas un Miroir fonctionnel.

## État vérifié du dépôt
Le vrai Organizer utilise `app/macros/switch_click.py`,
`app/macros/switch_character.py`, `app/macros/zaap.py`,
`app/core/runtime_state.py`, `MacroLock` et les hooks gérés.
L'actuelle diffusion de clics repose sur des changements de focus et des
entrées Windows. Il faut conserver ces chemins en état de marche.

## Conditions de faisabilité
- Tester sur Windows si Dofus Unity accepte réellement les messages de souris
  et clavier ciblés lorsqu'il ne possède pas le focus.
- `PostMessage` est une hypothèse à tester, **pas** une compatibilité établie.
- Ne pas injecter du code dans Dofus, ne pas utiliser son protocole réseau,
  ne pas contourner de protection ni ajouter de périphérique trompeur.
- Respecter les règles de jeu applicables avant d'activer une diffusion
  automatique; en cas de doute, conserver le contrôle manuel.
- Une preuve isolée Win32 n'est pas une preuve sur Dofus; il faut
  les deux pour envisager le ciblage d'arrière-plan.

## Fonctionnalités prévues mais absentes
- Contrôle Miroir temporaire dans Organizer, affichage d'état réel.
- Réutilisation des raccourcis / touches maintenues, clic, molette, clavier.
- Mapping propre à chaque fenêtre, distinction physique / synthétique.
- Aucune double émission sur le meneur.
- Exécution sûre sur 1/2/4/8 clients, annulation/arrêt et journaux.
- Fallback séquentiel et chronométrage p50/p95/p99 sans délai arbitraire.
- Tests des interactions et des cas d'erreur, compatibilité réelle Windows.

## Preuves requises
Graphify exact-SHA avant travaux structurels des hooks ; Doctor/tests ciblés ;
test utilisateur réel sur Windows/Dofus suivi dans #322 (MIRR-005).
Aucun `PASS` ni `CERTIFIED` supposé.
