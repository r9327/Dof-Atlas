# Organizer — Miroir expérimental, issue #321

**État : R&D Draft / non relié au runtime.** Ce document et
`app/macros/mirror_plan.py` ne constituent pas un Miroir fonctionnel.

## État vérifié du dépôt
Le vrai Organizer utilise `app/macros/switch_click.py`,
`app/macros/switch_character.py`, `app/macros/zaap.py`,
`app/core/runtime_state.py`, `MacroLock` et les hooks gérés.
L'actuelle diffusion de clics repose sur des changements de focus et des
entrées Windows. Il faut conserver ces chemins en état de marche.

## Sécurité du prototype actuel

- `delivery_mode` renvoie **toujours `sequential`** à ce stade :
  deux drapeaux booléens n'attestent pas d'un test Windows/Dofus réel.
  Aucun adaptateur de diffusion ciblée n'est raccordé.
- Les handles de clients sont filtrés (invalides, doublons, fermés par
  rapport à la liste configurée) et le meneur n'est jamais inclus une
  deuxième fois. Une liste de plus de huit clients bloque le prototype.
- Le mode séquentiel est une **décision de repli**, pas une nouvelle fonction
  Miroir visible : le runtime actuel reste inchangé.

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


## Contrat d'un geste physique unique
- `mirror_delivery_targets(..., source_was_consumed=...)` est un
  planificateur pur, sans injection, basé sur le signal *réel* du hook.
- Si le hook a laissé passer le geste, il **n'émet pas** une seconde copie
  vers le personnage source.
- Si le hook a intercepté le geste, il prévoit **une seule** émission sur
  la source, en plus des clients explicitement sélectionnés.
- Source inconnue, poignée corrompue, plus de huit clients ou provenance
  de consommation ambiguë : liste vide, aucune diffusion.
- Aucun raccordement runtime : la méthode de passage du signal
  `source_was_consumed` sera revue dans Graphify avant toute connexion
  aux hooks. Aucun `PostMessage` Dofus sans preuve Windows/Unity.
