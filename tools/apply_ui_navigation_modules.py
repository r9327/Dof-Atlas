from __future__ import annotations

from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ENC = ROOT / "app" / "modules" / "encyclopedia" / "views" / "encyclopedia_page.py"
THEME = ROOT / "app" / "ui" / "theme.py"

def read(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Fichier introuvable: {path}")
    return path.read_text(encoding="utf-8")

def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")

def backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".before_ui_modules.bak")
    if not bak.exists():
        shutil.copy2(path, bak)

def need(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

main = read(MAIN)
enc = read(ENC)
theme = read(THEME)

if "def module_routes(self, module: str)" in main and "QTabBar#ModuleTabs" in theme:
    print("Déjà appliqué.")
    raise SystemExit(0)

for p in (MAIN, ENC, THEME):
    backup(p)

# QTabBar import
if "from PySide6.QtWidgets import QTabBar" not in main:
    pos = main.find("from PySide6.QtGui import")
    need(pos >= 0, "Imports PySide6 introuvables.")
    eol = main.find("\n", pos)
    main = main[:eol+1] + "from PySide6.QtWidgets import QTabBar\n" + main[eol+1:]

# module state
if 'self.current_module = ""' not in main:
    m = re.search(r'(?m)^(\s*self\.top_nav_groups:\s*dict\[str,\s*set\[str\]\]\s*=\s*\{\}\s*)$', main)
    need(m is not None, "self.top_nav_groups introuvable.")
    repl = m.group(1) + '\n        self.current_module = ""\n        self._module_routes: list[tuple[str, str, str]] = []'
    main = main[:m.start()] + repl + main[m.end():]

# common module tab bar
if "self.module_tabs = QTabBar()" not in main:
    anchor = "        root.addWidget(self.build_top_navigation())\n"
    need(anchor in main, "build_top_navigation introuvable.")
    add = anchor + """
        self.module_tabs = QTabBar()
        self.module_tabs.setObjectName("ModuleTabs")
        self.module_tabs.setDocumentMode(True)
        self.module_tabs.setExpanding(False)
        self.module_tabs.setDrawBase(False)
        self.module_tabs.setVisible(False)
        self.module_tabs.currentChanged.connect(self.on_module_tab_changed)
        root.addWidget(self.module_tabs)
"""
    main = main.replace(anchor, add, 1)

# navbar block
start = main.find("        guide_menu = self._new_hover_menu()")
if start < 0:
    start = main.find("        guide_menu = QMenu(nav)")
end = main.find("        almanax_button = AtlasButton(", start)
if end < 0:
    end = main.find("        almanax = AtlasButton(", start)
need(start >= 0 and end > start, "Bloc Guide/Bestiaire/Outils/Stuffs introuvable.")

nav = """        guide_menu = self._new_hover_menu()
        guide_menu.addAction("Quêtes", lambda: self.open_module("Guide", "Quêtes"))
        guide_menu.addAction("Succès", lambda: self.open_module("Guide", "Succès"))
        guide = self._add_hover_button("Guide", guide_menu, {"Quetes"})
        guide.clicked.connect(lambda: self.open_module("Guide", "Guides"))
        layout.addWidget(guide)

        bestiary_menu = self._new_hover_menu()
        bestiary_menu.addAction("Donjons", lambda: self.open_module("Bestiaire", "Donjons"))
        bestiary_menu.addAction("Monstres", lambda: self.open_module("Bestiaire", "Monstres"))
        bestiary_menu.addAction("Archimonstres", lambda: self.open_module("Bestiaire", "Archimonstres"))
        bestiary_menu.addAction("Avis de recherche", lambda: self.open_module("Bestiaire", "Avis de recherche"))
        bestiary = self._add_hover_button("Bestiaire", bestiary_menu, {"Quetes"})
        bestiary.clicked.connect(lambda: self.open_module("Bestiaire", "Donjons"))
        layout.addWidget(bestiary)

        tools_menu = self._new_hover_menu()
        tools_menu.addAction("Crafts", lambda: self.open_module("Outils", "Crafts"))
        tools_menu.addAction("Map monde", lambda: self.open_module("Outils", "Map monde"))
        tools_menu.addAction("Chasse au trésor", lambda: self.open_module("Outils", "Chasse au trésor"))
        tools_menu.addAction("Ocre", lambda: self.open_module("Outils", "Ocre"))
        layout.addWidget(self._add_hover_button("Outils", tools_menu, {"Craft", "Scan Monde", "TreasureHunt", "Ocre"}))

        stuffs_menu = self._new_hover_menu()
        stuffs_menu.addAction("PvM", lambda: self.open_module("Stuffs", "PvM"))
        stuffs_menu.addAction("PvP", lambda: self.open_module("Stuffs", "PvP"))
        stuffs_menu.addAction("Builders", lambda: self.open_module("Stuffs", "Builders"))
        stuffs = self._add_hover_button("Stuffs", stuffs_menu, {"Equipement"})
        stuffs.clicked.connect(lambda: self.open_module("Stuffs", "PvM"))
        layout.addWidget(stuffs)

"""
main = main[:start] + nav + main[end:]

# helpers
if "def module_routes(self, module: str)" not in main:
    anchor = "    def placeholder_page("
    idx = main.find(anchor)
    need(idx >= 0, "placeholder_page introuvable.")
    helpers = """    def module_routes(self, module: str) -> list[tuple[str, str, str]]:
        routes = {
            "Guide": [
                ("Guides", "encyclopedia", GUIDES_TAB),
                ("Quêtes", "encyclopedia", QUESTS_TAB),
                ("Succès", "encyclopedia", ACHIEVEMENTS_TAB),
            ],
            "Bestiaire": [
                ("Donjons", "encyclopedia", "DONJONS"),
                ("Monstres", "encyclopedia", "MONSTRES"),
                ("Archimonstres", "encyclopedia", "ARCHIMONSTRES"),
                ("Avis de recherche", "encyclopedia", "AVIS DE RECHERCHE"),
            ],
            "Outils": [
                ("Crafts", "page", "Craft"),
                ("Map monde", "page", "Scan Monde"),
                ("Chasse au trésor", "placeholder", "TreasureHunt"),
                ("Ocre", "placeholder", "Ocre"),
            ],
            "Stuffs": [
                ("PvM", "page", "Equipement"),
                ("PvP", "page", "Equipement"),
                ("Builders", "page", "Equipement"),
            ],
        }
        return list(routes.get(module, ()))

    def module_page_names(self, module: str) -> set[str]:
        routes = self.module_routes(module)
        pages = {target for _label, kind, target in routes if kind in {"page", "placeholder"}}
        if any(kind == "encyclopedia" for _label, kind, _target in routes):
            pages.add("Quetes")
        return pages

    def configure_module_tabs(self, module: str, selected_label: str = "") -> int:
        routes = self.module_routes(module)
        if not routes:
            self.current_module = ""
            self._module_routes = []
            self.module_tabs.setVisible(False)
            return -1
        self.current_module = module
        self._module_routes = routes
        self.module_tabs.blockSignals(True)
        try:
            self.module_tabs.clear()
            selected_index = 0
            for index, (label, _kind, _target) in enumerate(routes):
                self.module_tabs.addTab(label)
                if label == selected_label:
                    selected_index = index
            self.module_tabs.setCurrentIndex(selected_index)
            self.module_tabs.setVisible(True)
        finally:
            self.module_tabs.blockSignals(False)
        return selected_index

    def open_module(self, module: str, selected_label: str = "") -> None:
        index = self.configure_module_tabs(module, selected_label)
        if index >= 0:
            self.open_module_route(index)

    def on_module_tab_changed(self, index: int) -> None:
        if index >= 0:
            self.open_module_route(index)

    def open_module_route(self, index: int) -> None:
        if index < 0 or index >= len(self._module_routes):
            return
        label, kind, target = self._module_routes[index]
        if kind == "encyclopedia":
            self.open_encyclopedia_section(target)
            return
        if kind == "page":
            self.show_page(target)
            return
        self.show_placeholder(target, label)

    def module_label_for_target(self, module: str, target: str) -> str:
        for label, _kind, route_target in self.module_routes(module):
            if route_target == target:
                return label
        return ""

"""
    main = main[:idx] + helpers + main[idx:]

# Hide module tabs when leaving
marker = "    def switch_to_page(self, name: str) -> None:\n"
idx = main.find(marker)
need(idx >= 0, "switch_to_page introuvable.")
body = idx + len(marker)
if "valid_pages = self.module_page_names" not in main[body:body+700]:
    inj = """        if self.current_module:
            valid_pages = self.module_page_names(self.current_module)
            if name not in valid_pages:
                self.current_module = ""
                self._module_routes = []
                if hasattr(self, "module_tabs"):
                    self.module_tabs.setVisible(False)

"""
    main = main[:body] + inj + main[body:]

# Active top nav
old = "            active = active_name in self.top_nav_groups.get(label, set())"
if old in main:
    main = main.replace(old, """            if self.current_module and label in {"Guide", "Bestiaire", "Outils", "Stuffs"}:
                active = label == self.current_module
            else:
                active = active_name in self.top_nav_groups.get(label, set())""", 1)

# Sync encyclopedia tab => module
marker = "    def open_encyclopedia_section(self, tab_label: str) -> None:\n"
idx = main.find(marker)
need(idx >= 0, "open_encyclopedia_section introuvable.")
body = idx + len(marker)
if "bestiary_tabs =" not in main[body:body+1000]:
    inj = """        bestiary_tabs = {"DONJONS", "MONSTRES", "ARCHIMONSTRES", "AVIS DE RECHERCHE"}
        module = "Bestiaire" if tab_label in bestiary_tabs else "Guide"
        label = self.module_label_for_target(module, tab_label)
        if self.current_module != module:
            self.configure_module_tabs(module, label)
        elif label:
            current_index = self.module_tabs.currentIndex()
            current_label = self.module_tabs.tabText(current_index) if current_index >= 0 else ""
            if current_label != label:
                self.configure_module_tabs(module, label)

"""
    main = main[:body] + inj + main[body:]

# Direct guide progress
m = re.search(r"(?m)^    def open_guide_progress\([^\n]+\) -> None:\n", main)
if m and 'self.configure_module_tabs("Guide", "Guides")' not in main[m.end():m.end()+400]:
    main = main[:m.end()] + '        self.configure_module_tabs("Guide", "Guides")\n' + main[m.end():]

# Encyclopedia: remove redundant title, hide old technical tab bar
enc = re.sub(
    r'\n\s*title = QLabel\("Encyclopédie"\)\n'
    r'\s*title\.setObjectName\("PageTitle"\)\n'
    r'\s*title\.setAlignment\(Qt\.AlignLeft \| Qt\.AlignVCenter\)\n'
    r'\s*header\.addWidget\(title\)\n',
    "\n",
    enc,
    count=1,
)
if "self.tabs.tabBar().setVisible(False)" not in enc:
    anchor = '        self.tabs.setObjectName("EncyclopediaTabs")\n'
    need(anchor in enc, "EncyclopediaTabs introuvable.")
    enc = enc.replace(anchor, anchor + "        self.tabs.tabBar().setVisible(False)\n", 1)
enc = enc.replace('self.status_callback(f"Encyclopédie : {label}")', 'self.status_callback(label)')

# Theme
if "QTabBar#ModuleTabs" not in theme:
    theme += """

QTabBar#ModuleTabs {
    background: @PANEL;
    border: none;
    border-bottom: 1px solid @BORDER;
    min-height: 38px;
    max-height: 38px;
}
QTabBar#ModuleTabs::tab {
    background: transparent;
    color: @TEXT_MUTED;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 16px 8px 16px;
    margin: 0;
    min-width: 72px;
}
QTabBar#ModuleTabs::tab:hover {
    color: @TEXT;
    background: @PANEL_2;
}
QTabBar#ModuleTabs::tab:selected {
    color: @TEXT;
    background: @PANEL_2;
    border-bottom: 2px solid @GREEN;
}
"""

write(MAIN, main)
write(ENC, enc)
write(THEME, theme)

print("OK - navigation UI modules appliquée.")
print("Backups créés: *.before_ui_modules.bak")
