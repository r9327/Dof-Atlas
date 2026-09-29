from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget


_MODULE_SUBNAV: dict[str, tuple[str, ...]] = {
    "Outils": ("Crafts", "Map monde", "Chasse au trésor", "Ocre"),
    "Stuffs": ("PvM", "PvP", "Builders"),
}


class ProductShellHost(QWidget):
    """Host a real product page under AtlasWindow's canonical navigation chrome.

    The Lab does not redraw the navigation. It calls the production methods that
    build and style the top navigation and module sub-navigation, while replacing
    navigation callbacks with no-ops so captures cannot mutate app state.
    """

    def __init__(self, content: QWidget, *, group: str, active_label: str) -> None:
        super().__init__()
        from main import AtlasWindow, atlas_application_icon

        self.setObjectName("UiLabProductShellHost")
        self.product_content = content
        self.shell_icon = atlas_application_icon()
        self.nav_buttons: list[tuple[QWidget, str]] = []
        self.page_widgets: dict[str, QWidget] = {}
        self.page_nav_group: dict[str, str] = {}
        self.current_character_key = ""
        self.current_character_label = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_nav = AtlasWindow.build_top_nav(self)
        root.addWidget(self.top_nav)

        self.module_subnav = QFrame()
        self.module_subnav.setObjectName("ModuleSubNav")
        self.module_subnav_layout = QHBoxLayout(self.module_subnav)
        self.module_subnav_layout.setContentsMargins(10, 4, 10, 4)
        self.module_subnav_layout.setSpacing(4)
        self.module_subnav.hide()
        root.addWidget(self.module_subnav)

        content.setParent(self)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(content, 1)

        labels = _MODULE_SUBNAV.get(str(group or ""))
        if labels:
            AtlasWindow.configure_module_subnav(
                self,
                str(group),
                labels,
                str(active_label),
                lambda _value: None,
            )
        else:
            self.module_subnav.hide()
            AtlasWindow.refresh_nav_selection(
                self,
                "" if group == "Accueil" else str(group or ""),
            )

        scroll_target = str(content.property("uiLabCaptureScrollTarget") or "").strip()
        if scroll_target:
            self.setProperty("uiLabCaptureScrollTarget", scroll_target)

    def __getattr__(self, name: str) -> Any:
        # Keep capture/readiness helpers compatible with the canonical page API.
        content = self.__dict__.get("product_content")
        if content is not None:
            try:
                return getattr(content, name)
            except AttributeError:
                pass
        raise AttributeError(name)

    # AtlasWindow.build_top_nav() binds these callbacks. They intentionally do
    # nothing in a screenshot host: only production visuals are under test here.
    def show_page(self, *_args, **_kwargs) -> None:
        return

    def open_encyclopedia_tab(self, *_args, **_kwargs) -> None:
        return

    def open_tools_tab(self, *_args, **_kwargs) -> None:
        return

    def open_stuffs_tab(self, *_args, **_kwargs) -> None:
        return

    def show_placeholder(self, *_args, **_kwargs) -> None:
        return

    def on_global_character_changed(self, *_args, **_kwargs) -> None:
        return

    def clear_module_subnav(self) -> None:
        from main import AtlasWindow

        AtlasWindow.clear_module_subnav(self)

    def refresh_nav_selection(self, active_group: str) -> None:
        from main import AtlasWindow

        AtlasWindow.refresh_nav_selection(self, active_group)


def wrap_product_shell(content: QWidget, *, group: str, active_label: str) -> ProductShellHost:
    if isinstance(content, ProductShellHost):
        return content
    return ProductShellHost(content, group=group, active_label=active_label)
