# Lot 7 - Audit WORK des Succes

Genere le `2026-08-21T13:53:39.337933+00:00` depuis le catalogue local actuellement utilise par Dofus Atlas.

## Decision de perimetre

Ordre definitif du jeu pour les categories conservees : **Donjons -> Monstres -> Quetes -> Evenements**.
Aucune autre categorie n'est retenue, faute de validation explicite dans le Lot 7.

## Inventaire

- 2774 succes charges par le fournisseur actuel.
- 270 succes seulement etaient affichables par l'ancien ecran (filtre Qf direct).
- 1412 succes composent le catalogue cible des quatre categories.
- 1362 succes sont ecartes car leur categorie n'est pas retenue.

## Categories conservees et ordre des zones

| Ordre | Categorie | Succes | Sous-categories / zones dans l'ordre du jeu |
| ---: | --- | ---: | --- |
| 2 | Donjons | 743 | Général, Niveaux 1 à 50, Niveaux 51 à 100, Niveaux 101 à 150, Niveaux 151 à 190, Niveaux 191 à 200 |
| 3 | Monstres | 228 | Général, Dopeuls, Astrub, Amakna, Bonta & Brâkmar, Montagne des koalaks, Île de Moon, Île de la cawotte, Cania, Archipel de Valonia, Landes de Sidimote, Île de Pandala, Île d'Otomaï, Île de Frigost, Île de Saharach, Sufokia, Dimensions, Eliocalypse, Shukrute, Îles diverses |
| 4 | Quêtes | 292 | Général, Quêtes mondiales, Alignement, Almanax, Avis de recherche, Eliocalypse, Justiciers, Tours de la Fratrie, Dimensions Divines, Archipel des Écailles, Archipel de Valonia, Astrub, Atoll des Possédés, Bonta et Brâkmar, Camps des Bworks et des Gobelins, Cania, Cauchemar des Ravageurs, Forêt Maléfique, Île de Frigost, Île de Moon, Île de Pandala, Île d'Otomaï, Île des Wabbits, Incarnam, Montagne des Koalaks, Nimotopia, Royaume d'Amakna, Saharach, Sidimote, Sufokia |
| 7 | Événements | 149 | Archipel de Vulkania, Île de Nowel, Île de Pwâk, Halouine |

## Categories supprimees

| Ordre source | Categorie | Succes ecartes |
| ---: | --- | ---: |
| 0 | Général | 40 |
| 1 | Exploration | 256 |
| 5 | Métiers | 15 |
| 6 | Élevage | 38 |
| 8 | Kolizéum | 15 |
| 9 | Anomalies Temporelles | 71 |
| 10 | Songes Infinis | 32 |
| 11 | Guilde | 39 |
| 12 | Compagnons | 77 |
| 14 | La Source : L'Héritage des Dofus | 25 |
| 16 | Temporis | 754 |

## Ordres d'alignement

Les six Ordres sont conserves comme branches exclusives. Un personnage selectionne Bonta ou Brakmar puis un Ordre; le suivi utilise exactement ses cinq quetes, dans les rangs 1 a 5.

| Cite | Ordre | Quetes 1 a 5 | Verification locale |
| --- | --- | --- | --- |
| bonta | Ordre du Cœur Vaillant | Apprentissage : Disciple de Ménalt (#433) -> Apprentissage : Écuyer (#109) -> Apprentissage : Chevalier de l'Espoir (#120) -> Apprentissage : Champion Merveilleux (#421) -> Apprentissage : Héros Légendaire (#1916) | OK |
| bonta | Ordre de l'Esprit Salvateur | Apprentissage : Disciple de Jiva (#434) -> Apprentissage : Apprenti Éclairé (#111) -> Apprentissage : Adepte des Écrits (#121) -> Apprentissage : Maître des Parchemins (#423) -> Apprentissage : Gardien du Savoir (#1917) | OK |
| bonta | Ordre de l'Œil Attentif | Apprentissage : Disciple de Silvosse (#435) -> Apprentissage : Espion Silencieux (#110) -> Apprentissage : Chasseur de Renégats (#122) -> Apprentissage : Assassin Suprême (#425) -> Apprentissage : Maître des Illusions (#1918) | OK |
| brakmar | Ordre du Cœur Saignant | Apprentissage : Disciple de Djaul (#436) -> Apprentissage : Surineur (#112) -> Apprentissage : Chevalier du Désespoir (#123) -> Apprentissage : Champion du Chaos (#422) -> Apprentissage : Héros de l'Apocalypse (#1919) | OK |
| brakmar | Ordre de l'Esprit Malsain | Apprentissage : Disciple d'Hécate (#437) -> Apprentissage : Apprenti Sombre (#114) -> Apprentissage : Adepte des Douleurs (#124) -> Apprentissage : Maître des Sévices (#424) -> Apprentissage : Gardien des Tortures (#1920) | OK |
| brakmar | Ordre de l'Œil Putride | Apprentissage : Disciple de Brumaire (#438) -> Apprentissage : Espion Sombre (#113) -> Apprentissage : Chasseur d'Âmes (#125) -> Apprentissage : Psychopathe (#426) -> Apprentissage : Maître des Ombres (#1921) | OK |

## Controles et donnees incoherentes

- Appartenances absentes ou non listees : 0.
- Appartenances dans une mauvaise categorie : 0.
- Ordres de succes dupliques dans une meme sous-categorie : 7.
- References d'objectifs declarees mais absentes du fichier source : 37 succes concernes.
- Listes d'objectifs dont l'ordre charge diverge de l'ordre declare : 0.
- Six choix d'Ordre avec cinq quetes locales uniques : oui.

Le fichier JSON voisin contient la liste exhaustive des succes conserves et ecartes, chaque objectif, son critere brut, les quetes/monstres/donjons resolus et sa position source.

## Cas particuliers

- L'ancien ecran ne retenait que les succes ayant une quete Qf directement resolue; les meta-succes OA et les contenus Monstres/Donjons etaient donc masques.
- Les criteres Pr des Ordres expriment des branches alternatives et ne sont pas des identifiants de quetes.
- Les objectifs techniques non resolus restent conserves textuellement; ils ne sont pas inventes ni transformes en quetes.
- Les Lots 8 et 9 devront completer les interactions specialisees Monstres et Donjons sans changer cette organisation source.
