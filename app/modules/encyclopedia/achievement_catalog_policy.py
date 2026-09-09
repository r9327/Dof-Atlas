from __future__ import annotations


# Only these top-level game categories were explicitly retained for Lot 7.
# The provider still reads their actual display order from the local game data.
RETAINED_TOP_CATEGORY_IDS = (8, 3, 25, 9)

# Quest-success ordering overrides validated for the current in-game structure.
# "Premier temps" and "Second temps" are intentionally pinned first in
# Quêtes > Général, while Quêtes mondiales follows the current game/web order.
QUEST_GENERAL_SUBCATEGORY_ID = 118
QUEST_GENERAL_PINNED_ACHIEVEMENT_IDS = (8518, 8519)

QUEST_WORLD_SUBCATEGORY_ID = 40
QUEST_WORLD_ACHIEVEMENT_IDS = (
    1036,  # Mais où sont les Dofus ?
    1048,  # Vert émeraude
    1101,  # Pourpre profond
    1385,  # Bleu turquoise
    5220,  # Ocre d'ambre
    565,   # La fin de l'éternité
    1543,  # Quatre sur six
    1622,  # Blanc ivoire
    1704,  # Noir d'ébène
    1705,  # Six sur six
    5222,  # Le secret des Dofus : Prologue
    7761,  # En attendant le printemps
    1650,  # La Fratrie des Oubliés
    2198,  # Rêves de dragons
    559,   # Le tour du monde en 27 donjons
    560,   # Première édition de donjons
    561,   # Donjons avancés
    562,   # Donjons trois point cinq
    563,   # Le siège des donjons
    564,   # La tornade des donjons
    556,   # La bonne attitude
    586,   # Faire le keke
    585,   # L'osmose
)

# The game exposes two variants for each Order-rank achievement. Both variants
# point to the same rank in the single branch selected for the character.
ALIGNMENT_ORDER_ACHIEVEMENT_RANKS = {
    1213: 1,
    1392: 1,
    1214: 2,
    1393: 2,
    1215: 3,
    1394: 3,
    1216: 4,
    1395: 4,
    1217: 5,
    1396: 5,
}

ALIGNMENT_GUIDE_IDS = {
    "bonta": "alignement_bonta",
    "brakmar": "alignement_brakmar",
}
