SCHEMA_VERSION = 1


CREATE_TABLES_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    last_seen TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(type, path)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    family TEXT NOT NULL DEFAULT '',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'resource',
    type TEXT NOT NULL DEFAULT '',
    job_id INTEGER,
    job_name TEXT NOT NULL DEFAULT '',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'equipment',
    type TEXT NOT NULL DEFAULT '',
    family TEXT NOT NULL DEFAULT '',
    set_id INTEGER,
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    level INTEGER,
    item_ids_json TEXT NOT NULL DEFAULT '[]',
    effects_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consumables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'consumable',
    type TEXT NOT NULL DEFAULT '',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER,
    result_item_id INTEGER,
    result_ankama_id INTEGER UNIQUE,
    result_name_fr TEXT NOT NULL DEFAULT '',
    result_name_en TEXT NOT NULL DEFAULT '',
    job_id INTEGER,
    job_name TEXT NOT NULL DEFAULT '',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    ingredient_item_id INTEGER,
    ingredient_ankama_id INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1,
    type TEXT NOT NULL DEFAULT '',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(recipe_id, ingredient_ankama_id, name_fr),
    FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'job',
    level INTEGER,
    is_recolt INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    class_id INTEGER,
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'spell',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'class',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monsters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    family_id INTEGER,
    area_id INTEGER,
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'monster',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monster_families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'monster_family',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'area',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    gid INTEGER,
    area_id INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'subarea',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id INTEGER UNIQUE NOT NULL,
    x INTEGER,
    y INTEGER,
    area_id INTEGER,
    subarea_id INTEGER,
    neighbours_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id INTEGER NOT NULL,
    cell_id INTEGER NOT NULL,
    walkable INTEGER,
    los INTEGER,
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(map_id, cell_id)
);

CREATE TABLE IF NOT EXISTS interactive_elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER,
    gid INTEGER,
    map_id INTEGER,
    cell_id INTEGER,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'interactive',
    level INTEGER,
    source TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_id INTEGER,
    lang TEXT NOT NULL DEFAULT 'fr',
    text TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(text_id, lang)
);

CREATE TABLE IF NOT EXISTS image_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER,
    item_ankama_id INTEGER,
    name TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'item',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS effects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ankama_id INTEGER UNIQUE,
    name_fr TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    description_fr TEXT NOT NULL DEFAULT '',
    description_en TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'effect',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_effects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_ankama_id INTEGER,
    effect_id INTEGER,
    effect_ankama_id INTEGER,
    effect_name_fr TEXT NOT NULL DEFAULT '',
    value_int INTEGER,
    min_int INTEGER,
    max_int INTEGER,
    raw_order INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(item_ankama_id, effect_ankama_id, raw_order)
);

CREATE TABLE IF NOT EXISTS monster_spells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monster_ankama_id INTEGER NOT NULL,
    spell_ankama_id INTEGER NOT NULL,
    raw_order INTEGER NOT NULL DEFAULT 0,
    grade_info TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(monster_ankama_id, spell_ankama_id, raw_order)
);

CREATE TABLE IF NOT EXISTS class_spells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_ankama_id INTEGER NOT NULL,
    spell_ankama_id INTEGER NOT NULL,
    raw_order INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(class_ankama_id, spell_ankama_id, raw_order)
);

CREATE TABLE IF NOT EXISTS conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL DEFAULT '',
    owner_ankama_id INTEGER,
    condition_type TEXT NOT NULL DEFAULT '',
    expression TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    UNIQUE(owner_type, owner_ankama_id, condition_type, expression)
);

CREATE TABLE IF NOT EXISTS raw_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT '',
    object_type TEXT NOT NULL DEFAULT '',
    object_id TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    counts_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_items_name_fr ON items(name_fr);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_level ON items(level);
CREATE INDEX IF NOT EXISTS idx_items_image_path ON items(image_path);
CREATE INDEX IF NOT EXISTS idx_resources_name_fr ON resources(name_fr);
CREATE INDEX IF NOT EXISTS idx_resources_job ON resources(job_id, job_name);
CREATE INDEX IF NOT EXISTS idx_resources_image_path ON resources(image_path);
CREATE INDEX IF NOT EXISTS idx_equipment_image_path ON equipment(image_path);
CREATE INDEX IF NOT EXISTS idx_equipment_set_id ON equipment(set_id);
CREATE INDEX IF NOT EXISTS idx_item_sets_name_fr ON item_sets(name_fr);
CREATE INDEX IF NOT EXISTS idx_consumables_image_path ON consumables(image_path);
CREATE INDEX IF NOT EXISTS idx_recipes_result ON recipes(result_ankama_id);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ing ON recipe_ingredients(ingredient_ankama_id, name_fr);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_image_path ON recipe_ingredients(image_path);
CREATE INDEX IF NOT EXISTS idx_jobs_name_fr ON jobs(name_fr);
CREATE INDEX IF NOT EXISTS idx_spells_name_fr ON spells(name_fr);
CREATE INDEX IF NOT EXISTS idx_monsters_name_fr ON monsters(name_fr);
CREATE INDEX IF NOT EXISTS idx_maps_position ON maps(x, y);
CREATE INDEX IF NOT EXISTS idx_maps_subarea ON maps(subarea_id);
CREATE INDEX IF NOT EXISTS idx_cells_map ON cells(map_id);
CREATE INDEX IF NOT EXISTS idx_texts_text ON texts(text);
CREATE INDEX IF NOT EXISTS idx_effects_ankama ON effects(ankama_id);
CREATE INDEX IF NOT EXISTS idx_item_effects_item ON item_effects(item_ankama_id);
CREATE INDEX IF NOT EXISTS idx_item_effects_effect ON item_effects(effect_ankama_id);
CREATE INDEX IF NOT EXISTS idx_monster_spells_monster ON monster_spells(monster_ankama_id);
CREATE INDEX IF NOT EXISTS idx_monster_spells_spell ON monster_spells(spell_ankama_id);
CREATE INDEX IF NOT EXISTS idx_class_spells_class ON class_spells(class_ankama_id);
CREATE INDEX IF NOT EXISTS idx_class_spells_spell ON class_spells(spell_ankama_id);
CREATE INDEX IF NOT EXISTS idx_conditions_owner ON conditions(owner_type, owner_ankama_id);
"""
