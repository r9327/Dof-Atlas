from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import LOGO_PATH, QUEST_PROGRESS_FILE, ROOT_DIR
from app.core.file_stamp import mtime_ctime_size_stamp_or_zero, mtime_ctime_size_stamp
from app.core.numbers import clamped_percent, format_grouped_int
from app.core.text import clean_auto_group_name, strip_accents
from app.network.application_coordinator import NetworkApplicationStatus
from app.ui.components import AtlasButton, AtlasStatusBadge, atlas_application_icon, configure_unity_progress_bar, configure_unity_tool_button, set_unity_widget_property
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_SIZES_PX

HOME_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["home"]
from app.ui.unity_skin import apply_unity_panel_shadow, unity_original_preview_icon
from app.ui.network_bridge import network_ui_bridge

if TYPE_CHECKING:
    from app.modules.encyclopedia.models import Guide, GuideStep
    from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider
    from app.modules.encyclopedia.services import (
        AchievementProgressService,
        GuideProgressCalculator,
        GuideUltimeManualRuntimeService,
    )
    from app.quest_catalog import QuestCatalog


def local_character_preview(title: str) -> tuple[str, str]:
    from app.pages.organizer_icon_cache import cached_class_icon_path_for_window_name

    _, _, class_name = title.partition(" - ")
    return clean_auto_group_name(title), str(cached_class_icon_path_for_window_name(class_name) or "")


HOME_GUIDE_BANNER_PATH = Path(LOGO_PATH).parent / "home_guide_banner.png"
GUIDE_ULTIME_LEGACY_ID = "guide_complet"
_MANUAL_ROUTE_MANIFEST_PATH = (
    ROOT_DIR / "data" / "routes" / "guide_ultime_manual" / "manifest_v1.json"
)
_GUIDE_PROGRESS_ID = "guide_ultime_v5"

# Lazy compatibility patch point kept for focused Home tests. The concrete
# provider remains outside the module import path until Guide is authorized.
QuestProvider: Any = None


def _resolve_quest_provider() -> type:
    global QuestProvider
    if QuestProvider is None:
        from app.modules.encyclopedia.providers import QuestProvider as resolved

        QuestProvider = resolved
    return QuestProvider


@lru_cache(maxsize=1)
def _manual_route_stage_total() -> int:
    """Read only compact manifest metadata, never route chapter bodies."""

    try:
        payload = json.loads(_MANUAL_ROUTE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    canonical = payload.get("canonical") if isinstance(payload, dict) else None
    chapters = canonical.get("chapters") if isinstance(canonical, dict) else None
    if not isinstance(chapters, list):
        return 0
    total = 0
    for row in chapters:
        if not isinstance(row, dict):
            continue
        try:
            total += max(0, int(row.get("stage_count") or 0))
        except (TypeError, ValueError):
            continue
    return total


def _persisted_manual_summary(character_key: str) -> dict[str, Any]:
    """Build the cheap cold-start projection from persisted manual checks."""

    from app.modules.encyclopedia.services import GUIDE_PROGRESS_FILE, GuideProgressService

    total = _manual_route_stage_total()
    try:
        steps = GuideProgressService(GUIDE_PROGRESS_FILE).manual_steps(
            character_key,
            _GUIDE_PROGRESS_ID,
        )
    except Exception:
        steps = set()
    completed = sum(1 for value in steps if str(value).startswith("page:"))
    completed = min(completed, total) if total else completed
    percent = clamped_percent(completed, total)
    return {
        "percent": percent,
        "chapter": "Progression sauvegardée",
        "step": (
            f"{completed} / {total} fiches validées localement"
            if total
            else "Progression locale disponible"
        ),
        "zone": "—",
        "guide_id": GUIDE_ULTIME_LEGACY_ID,
    }


def _apply_saved_progress(page: "HomePage", summary: dict[str, Any]) -> None:
    percent = max(0, min(100, int(summary.get("percent") or 0)))
    page.current_guide_id = str(summary.get("guide_id") or GUIDE_ULTIME_LEGACY_ID)
    page.current_quest_id = None
    page.progress_bar.setValue(percent)
    page.progress_percent.setText(f"{percent} %")
    page.character_progress.setText(f"Guide terminé : {percent} %")
    page.chapter_value.setText(str(summary.get("chapter") or "Progression sauvegardée"))
    page.step_value.setText(str(summary.get("step") or "Progression locale disponible"))
    page.zone_value.setText(str(summary.get("zone") or "—"))
    page._reset_tracking()
    page.continue_button.setText("Continuer")
    page.continue_button.setEnabled(bool(page.current_guide_id))


class HomeBannerLabel(QLabel):
    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HomeGuideBanner")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(HOME_GEOMETRY["banner_min_height"])
        self.setMaximumHeight(HOME_GEOMETRY["banner_max_height"])
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._source = QPixmap(str(image_path)) if image_path.exists() else QPixmap()
        self.setVisible(not self._source.isNull())
        self._refresh_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        self.setPixmap(
            self._source.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        )


class HomeTrackingRow(QWidget):
    def __init__(
        self, icon: str, label: str, parent: QWidget | None = None,
        *, sprite_key: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HomeTrackingRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(HOME_GEOMETRY["tracking_spacing"])

        icon_label = QLabel(icon)
        icon_label.setObjectName("HomeTrackingIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedWidth(HOME_GEOMETRY["tracking_icon_width"])
        # Reuse the same local-only Unity pictograms as the application shell.
        # An absent or damaged user asset keeps the readable legacy glyph.
        icon_asset = (
            unity_original_preview_icon(sprite_key, UNITY_SIZES_PX["icon_small"])
            if sprite_key else QIcon()
        )
        if not icon_asset.isNull():
            icon_label.setPixmap(icon_asset.pixmap(18, 18))
        layout.addWidget(icon_label)

        name = QLabel(label)
        name.setObjectName("HomeTrackingLabel")
        name.setMinimumWidth(HOME_GEOMETRY["tracking_name_min_width"])
        layout.addWidget(name)

        self.bar = configure_unity_progress_bar(
            QProgressBar(), object_name="HomeTrackingBar",
        )
        self.bar.setValue(0)
        self.bar.setMinimumWidth(HOME_GEOMETRY["tracking_bar_min_width"])
        layout.addWidget(self.bar, 1)

        self.value = QLabel("0 %")
        self.value.setObjectName("HomeTrackingValue")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setMinimumWidth(HOME_GEOMETRY["tracking_value_min_width"])
        layout.addWidget(self.value)

    def set_progress(self, completed: int, total: int, *, show_count: bool = False) -> None:
        completed = max(0, int(completed))
        total = max(0, int(total))
        percent = clamped_percent(completed, total)
        self.bar.setValue(percent)
        if show_count and total:
            self.value.setText(f"{format_grouped_int(completed)} / {format_grouped_int(total)}")
        else:
            self.value.setText(f"{percent} %")


class HomePage(QWidget):
    """Accueil léger : les données lourdes sont injectées par AtlasWindow."""

    continueRequested = Signal(str, object)
    changeCharacterRequested = Signal()
    almanaxRequested = Signal()

    _DOFUS_KEYWORDS = (
        "dofus",
        "emeraude",
        "pourpre",
        "turquoise",
        "ivoire",
        "vulbis",
        "abyssal",
        "cawotte",
        "dokoko",
        "dorigami",
        "domakuro",
        "veilleur",
        "argente",
        "glaces",
        "ocre",
        "nebuleux",
        "tachete",
        "sylvestre",
        "kaliptus",
        "dotruche",
    )
    _ALIGNMENT_KEYWORDS = (
        "alignement",
        "bonta",
        "brakmar",
        "menalt",
        "coeur vaillant",
        "coeur saignant",
        "ordre de",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HomePage")
        self.catalog: QuestCatalog | None = None
        self.guide_provider: GuideProvider | None = None
        self.achievement_provider: AchievementProvider | None = None
        self.guide_ultime_service: GuideUltimeManualRuntimeService | None = None
        self.guide_ultime_error = ""
        self._guide_ultime_runtime_allowed = False
        self.character_key = ""
        self.character_label = "Aucun personnage connecté"
        self._local_dofus_sessions: tuple[str, ...] = ()
        self.character_icon_path = ""
        self._character_icon_signature = None
        self.current_guide_id = ""
        self.current_quest_id: int | None = None
        self._last_progress_signature: tuple[object, ...] | None = None
        self.network_bridge = network_ui_bridge()
        self.network_bridge.statusChanged.connect(self._on_network_status)
        self.network_bridge.progressChanged.connect(self._on_network_progress_changed)
        self.network_bridge.localSessionsChanged.connect(self._on_local_dofus_sessions)

        root = QHBoxLayout(self)
        page_margin = HOME_GEOMETRY["page_margin"]
        root.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        root.setSpacing(HOME_GEOMETRY["column_gutter"])

        self.left_column = QWidget()
        self.left_column.setObjectName("HomeLeftColumn")
        self.left_column.setMinimumWidth(HOME_GEOMETRY["left_column_min_width"])
        self.left_column.setMaximumWidth(HOME_GEOMETRY["left_column_max_width"])
        left_layout = QVBoxLayout(self.left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(HOME_GEOMETRY["left_column_spacing"])

        self.character_card = self._card("HomeCharacterCard")
        char_layout = self.character_card.layout()
        self._add_card_title(char_layout, "Personnage sélectionné")

        identity = QHBoxLayout()
        identity.setContentsMargins(*HOME_GEOMETRY["identity_margins"])
        identity.setSpacing(HOME_GEOMETRY["identity_spacing"])
        portrait_box = HOME_GEOMETRY["portrait_box"]
        self.character_portrait = configure_unity_tool_button(
            QToolButton(), object_name="HomeCharacterPortrait",
            box=(portrait_box, portrait_box), icon_size=HOME_GEOMETRY["portrait_artwork"],
        )
        self.character_portrait.setEnabled(False)
        identity.addWidget(self.character_portrait, 0, Qt.AlignVCenter)

        identity_text = QVBoxLayout()
        identity_text.setContentsMargins(0, 0, 0, 0)
        identity_text.setSpacing(HOME_GEOMETRY["identity_text_spacing"])
        identity_text.addStretch(1)
        self.character_name = QLabel(self.character_label)
        self.character_name.setObjectName("HomeCharacterName")
        self.character_name.setTextFormat(Qt.PlainText)
        self.character_name.setWordWrap(True)
        identity_text.addWidget(self.character_name)
        self.character_progress = QLabel("Guide terminé : 0 %")
        self.character_progress.setObjectName("HomeCharacterProgress")
        self.character_progress.setWordWrap(True)
        identity_text.addWidget(self.character_progress)
        identity_text.addStretch(1)
        identity.addLayout(identity_text, 1)
        char_layout.addLayout(identity)

        change_button = AtlasButton("Changer de personnage")
        change_button.setObjectName("HomeChangeCharacterButton")
        change_button.clicked.connect(self.changeCharacterRequested)
        char_layout.addWidget(change_button)
        left_layout.addWidget(self.character_card, 0)

        self.tracking_card = self._card("HomeTrackingCard")
        tracking_layout = self.tracking_card.layout()
        self._add_card_title(tracking_layout, "Progression globale")
        tracking_layout.addSpacing(3)
        self.tracking_rows: dict[str, HomeTrackingRow] = {}
        for key, icon, label, sprite_key in (
            ("quests", "◆", "Quêtes", "quest"),
            ("achievement_quests", "✦", "Succès (Quêtes)", "success"),
            ("achievement_monsters", "●", "Succès (Monstres)", "success"),
            ("achievement_dungeons", "▥", "Succès (Donjons)", "success"),
            ("dungeons", "▣", "Donjons", None),
            ("dofus", "◉", "Dofus", "dofus"),
            ("alignment", "★", "Alignement", None),
        ):
            row = HomeTrackingRow(icon, label, sprite_key=sprite_key)
            self.tracking_rows[key] = row
            tracking_layout.addWidget(row)

        tracking_layout.addStretch(1)
        left_layout.addWidget(self.tracking_card, 1)

        self.guide_card = self._card("HomeGuideCard")
        self.guide_card.setMinimumWidth(HOME_GEOMETRY["guide_min_width"])
        guide_layout = self.guide_card.layout()
        self._add_card_title(guide_layout, "Guide progression")

        self.guide_title = QLabel("Aventure 0 → Sylvestre")
        self.guide_title.setObjectName("HomeGuideTitle")
        self.guide_title.setWordWrap(True)
        guide_layout.addWidget(self.guide_title)

        self.guide_banner = HomeBannerLabel(HOME_GUIDE_BANNER_PATH)
        guide_layout.addWidget(self.guide_banner)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(*HOME_GEOMETRY["guide_progress_margins"])
        progress_row.setSpacing(HOME_GEOMETRY["guide_progress_spacing"])
        progress_label = QLabel("Progression générale")
        progress_label.setObjectName("HomeGuideProgressLabel")
        self.progress_percent = QLabel("0 %")
        self.progress_percent.setObjectName("HomeGuideProgressPercent")
        self.progress_percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(progress_label, 1)
        progress_row.addWidget(self.progress_percent)
        guide_layout.addLayout(progress_row)

        self.progress_bar = configure_unity_progress_bar(
            QProgressBar(), object_name="HomeProgressBar",
        )
        self.progress_bar.setValue(0)
        guide_layout.addWidget(self.progress_bar)
        guide_layout.addSpacing(10)

        self.chapter_value = self._add_guide_detail_row(guide_layout, "▤", "Chapitre en cours :")
        self.step_value = self._add_guide_detail_row(guide_layout, "▱", "Quête en cours :")
        self.zone_value = self._add_guide_detail_row(guide_layout, "●", "Zone actuelle :")
        guide_layout.addStretch(1)

        self.continue_button = AtlasButton("Continuer")
        self.continue_button.setObjectName("HomeContinueButton")
        self.continue_button.setEnabled(False)
        self.continue_button.clicked.connect(self._emit_continue)
        guide_layout.addWidget(self.continue_button)

        self.almanax_card = self._card("HomeAlmanaxCard")
        self.almanax_card.setMinimumWidth(HOME_GEOMETRY["right_column_min_width"])
        self.almanax_card.setMaximumWidth(HOME_GEOMETRY["right_column_max_width"])
        almanax_layout = self.almanax_card.layout()
        self._add_card_title(almanax_layout, "Almanax")
        almanax_layout.addStretch(1)

        almanax_box = HOME_GEOMETRY["almanax_box"]
        self.almanax_icon = configure_unity_tool_button(
            QToolButton(), object_name="HomeAlmanaxPlaceholderIcon",
            box=(almanax_box, almanax_box), icon_size=HOME_GEOMETRY["almanax_artwork"],
        )
        self.almanax_icon.setToolTip("Ouvrir le calendrier Almanax")
        self.almanax_icon.clicked.connect(self.almanaxRequested.emit)
        almanax_sprite = unity_original_preview_icon(
            "almanax", UNITY_SIZES_PX["icon_xlarge"]
        )
        if not almanax_sprite.isNull():
            self.almanax_icon.setIcon(almanax_sprite)
        elif Path(LOGO_PATH).exists():
            self.almanax_icon.setIcon(atlas_application_icon())
        almanax_layout.addWidget(self.almanax_icon, 0, Qt.AlignHCenter)

        badge = AtlasStatusBadge("Données indisponibles", state="blocked")
        self.almanax_badge = badge
        self.almanax_day_key = ""
        almanax_layout.addWidget(badge, 0, Qt.AlignHCenter)
        self.almanax_item_icon = QLabel()
        self.almanax_item_icon.setObjectName("AlmanaxOfferingIcon")
        self.almanax_item_icon.setFixedSize(
            UNITY_SIZES_PX["icon_xlarge"], UNITY_SIZES_PX["icon_xlarge"]
        )
        self.almanax_item_icon.setAlignment(Qt.AlignCenter)
        self.almanax_item_icon.setVisible(False)
        almanax_layout.addWidget(self.almanax_item_icon, 0, Qt.AlignHCenter)

        almanax_text = QLabel(
            "Calendrier consultable. Offrandes et bonus en attente "
            "de données locales vérifiées."
        )
        almanax_text.setObjectName("HomeAlmanaxText")
        self.almanax_text = almanax_text
        almanax_text.setAlignment(Qt.AlignCenter)
        almanax_text.setWordWrap(True)
        almanax_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        almanax_layout.addWidget(almanax_text)
        almanax_layout.addStretch(1)

        self.almanax_button = AtlasButton("Voir l’Almanax")
        self.almanax_button.setObjectName("HomeAlmanaxButton")
        self.almanax_button.clicked.connect(self.almanaxRequested.emit)
        almanax_layout.addWidget(self.almanax_button)

        self.right_column = QWidget()
        self.right_column.setObjectName("HomeRightColumn")
        self.right_column.setMinimumWidth(HOME_GEOMETRY["right_column_min_width"])
        self.right_column.setMaximumWidth(HOME_GEOMETRY["right_column_max_width"])
        right_layout = QVBoxLayout(self.right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(HOME_GEOMETRY["right_column_spacing"])

        self.network_card = QFrame()
        self.network_card.setObjectName("HomeNetworkMiniCard")
        apply_unity_panel_shadow(self.network_card)
        self.network_card.setMinimumHeight(HOME_GEOMETRY["network_card_min_height"])
        self.network_card.setMaximumHeight(HOME_GEOMETRY["network_card_max_height"])
        network_layout = QHBoxLayout(self.network_card)
        network_layout.setContentsMargins(*HOME_GEOMETRY["network_card_margins"])
        network_layout.setSpacing(HOME_GEOMETRY["network_card_spacing"])
        self.network_indicator = QLabel("●")
        self.network_indicator.setObjectName("HomeNetworkIndicator")
        self.network_indicator.setProperty("state", "pending")
        self.network_indicator.setAlignment(Qt.AlignCenter)
        network_layout.addWidget(self.network_indicator, 0, Qt.AlignVCenter)

        network_text = QVBoxLayout()
        network_text.setContentsMargins(0, 0, 0, 0)
        network_text.setSpacing(HOME_GEOMETRY["network_text_spacing"])
        network_title = QLabel("Suivi automatique")
        network_title.setObjectName("HomeNetworkMiniTitle")
        network_text.addWidget(network_title)
        self.network_status = QLabel("Préparation…")
        self.network_status.setObjectName("HomeNetworkMiniStatus")
        network_text.addWidget(self.network_status)
        network_layout.addLayout(network_text, 1)

        # Explicit recovery after a refused UAC prompt or a failed runtime.
        # Unlike a permanent network control, this uses the indexed Unity
        # button and stays hidden while capture is working normally.
        self.network_retry = AtlasButton("Relancer", variant="secondary", size="compact")
        self.network_retry.setAccessibleName("Relancer le suivi réseau")
        self.network_retry.setToolTip("Relancer la détection ou la capture réseau")
        self.network_retry.clicked.connect(self._retry_network_tracking)
        self.network_retry.setVisible(False)
        network_layout.addWidget(self.network_retry, 0, Qt.AlignVCenter)

        right_layout.addWidget(self.network_card, 0)
        right_layout.addWidget(self.almanax_card, 1)

        root.addWidget(self.left_column, 0)
        root.addWidget(self.guide_card, 1)
        root.addWidget(self.right_column, 0)
        root.setStretch(0, 30)
        root.setStretch(1, 44)
        root.setStretch(2, 26)

        self._update_character_icon()
        self._on_network_status(self.network_bridge.last_status)

    @staticmethod
    def _card(object_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        apply_unity_panel_shadow(card)
        layout = QVBoxLayout(card)
        inset = HOME_GEOMETRY["card_padding"]
        layout.setContentsMargins(inset, inset, inset, inset)
        layout.setSpacing(HOME_GEOMETRY["card_gutter"])
        return card

    @staticmethod
    def _add_card_title(layout: QVBoxLayout, text: str) -> QLabel:
        title = QLabel(text)
        title.setObjectName("HomeCardTitle")
        layout.addWidget(title)
        return title

    @staticmethod
    def _add_guide_detail_row(layout: QVBoxLayout, icon: str, label: str) -> QLabel:
        row = QWidget()
        row.setObjectName("HomeGuideDetailRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(*HOME_GEOMETRY["detail_row_margins"])
        row_layout.setSpacing(HOME_GEOMETRY["detail_row_spacing"])

        icon_label = QLabel(icon)
        icon_label.setObjectName("HomeGuideDetailIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedWidth(HOME_GEOMETRY["detail_row_icon_width"])
        row_layout.addWidget(icon_label)

        label_widget = QLabel(label)
        label_widget.setObjectName("HomeGuideDetailLabel")
        row_layout.addWidget(label_widget)

        value = QLabel("Préparation du guide...")
        value.setObjectName("HomeGuideDetailValue")
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value.setWordWrap(True)
        row_layout.addWidget(value, 1)
        layout.addWidget(row)
        return value

    def set_almanax_day(self, day: object, *, cached: bool = False) -> None:
        """Display actual sourced offering/bonus for today on the Home card."""

        offering = str(getattr(day, "offering", "") or "")
        quantity = int(getattr(day, "quantity", 0) or 0)
        bonus = str(getattr(day, "bonus", "") or "")
        reward = int(getattr(day, "reward_kamas", 0) or 0)
        lines = [
            f"Offrande : {format_grouped_int(quantity)} × {offering}" if offering
            else "Offrande non renseignée par la source",
            f"Bonus : {bonus}" if bonus else "Bonus non renseigné par la source",
        ]
        if reward > 0:
            lines.append(f"Récompense : {format_grouped_int(reward)} kamas")
        self.almanax_item_icon.clear()
        self.almanax_item_icon.hide()
        self.almanax_day_key = str(getattr(day, "date", "") or "")
        self.almanax_text.setText("\n".join(lines))
        self.almanax_badge.setText(
            "Dofusdude · cache local" if cached else "Dofusdude · Dofus 3"
        )
        self.almanax_badge.set_state("info" if cached else "active")

    def set_almanax_item_icon(self, day_key: str, pixmap: QPixmap) -> None:
        if self.almanax_day_key != day_key or pixmap.isNull():
            return
        pixels = UNITY_SIZES_PX["icon_xlarge"]
        self.almanax_item_icon.setPixmap(
            pixmap.scaled(pixels, pixels, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.almanax_item_icon.show()

    def set_almanax_loading(self, day_key: str) -> None:
        # Never display yesterday's offering under today's Home heading.
        if (
            self.almanax_day_key == day_key
            and self.almanax_badge.property("state") in ("active", "info")
        ):
            return
        self.almanax_day_key = ""
        self.almanax_item_icon.clear()
        self.almanax_item_icon.hide()
        self.almanax_badge.setText("Chargement de l'Almanax…")
        self.almanax_badge.set_state("neutral")
        self.almanax_text.setText("Recherche de l'offrande et du bonus du jour…")

    def set_almanax_unavailable(self, day_key: str = "") -> None:
        # A genuine cache for this exact day remains useful offline.
        if (
            day_key == self.almanax_day_key
            and self.almanax_badge.property("state") in ("active", "info")
        ):
            return
        self.almanax_day_key = ""
        self.almanax_item_icon.clear()
        self.almanax_item_icon.hide()
        self.almanax_badge.setText("Données indisponibles")
        self.almanax_badge.set_state("blocked")
        self.almanax_text.setText(
            "Offrande et bonus indisponibles : réessayez depuis le calendrier."
        )

    def set_character(self, character_key: str, character_label: str, icon_path: str = "") -> None:
        next_key = str(character_key or "")
        next_label = str(character_label or "Personnage")
        next_icon_path = str(icon_path or "")
        if (
            next_key == self.character_key
            and next_label == self.character_label
            and next_icon_path == self.character_icon_path
        ):
            self._update_character_identity()
            return
        self.character_key = next_key
        self.character_label = next_label
        self.character_icon_path = next_icon_path
        self._update_character_identity()
        self.refresh_progress()

    def _on_local_dofus_sessions(self, sessions: tuple[str, ...]) -> None:
        self._local_dofus_sessions = sessions
        self._update_character_identity()

    def _update_character_identity(self) -> None:
        label = self.character_label
        icon_path = self.character_icon_path
        named_sessions = tuple(title for title in self._local_dofus_sessions if title)
        if not self.character_key and len(named_sessions) == 1:
            preview_label, icon_path = local_character_preview(named_sessions[0])
            label = preview_label or label
        self.character_name.setText(label)
        self._update_character_icon(icon_path)

    def apply_encyclopedia_context(
        self,
        catalog: QuestCatalog | None = None,
        guide_provider: GuideProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
    ) -> None:
        # A disk-only preload has no live context. Return before the lazy imports
        # so startup warmup cannot permanently raise the parent RSS watermark.
        if catalog is None and guide_provider is None and achievement_provider is None:
            return

        from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider
        from app.quest_catalog import QuestCatalog

        catalog_changed = isinstance(catalog, QuestCatalog) and catalog is not self.catalog
        guide_provider_changed = isinstance(guide_provider, GuideProvider) and guide_provider is not self.guide_provider
        achievement_provider_changed = (
            isinstance(achievement_provider, AchievementProvider)
            and achievement_provider is not self.achievement_provider
        )
        context_changed = catalog_changed or guide_provider_changed or achievement_provider_changed
        needs_service_rebuild = catalog_changed or self.guide_ultime_service is None
        if isinstance(catalog, QuestCatalog):
            self.catalog = catalog
        if isinstance(guide_provider, GuideProvider):
            self.guide_provider = guide_provider
        if isinstance(achievement_provider, AchievementProvider):
            self.achievement_provider = achievement_provider
        if needs_service_rebuild:
            self._rebuild_guide_ultime_service()
        elif self.guide_ultime_service is not None and achievement_provider_changed:
            self.guide_ultime_service.achievement_provider = self.achievement_provider
        if context_changed and self.catalog is not None and self.achievement_provider is not None:
            self.network_bridge.configure_context(
                quest_catalog=self.catalog,
                achievement_provider=self.achievement_provider,
                guide_provider=self.guide_provider,
            )
        if context_changed or needs_service_rebuild:
            self.refresh_progress()

    def release_encyclopedia_context(self, *, preserve_display: bool = True) -> None:
        """Drop rich providers/catalogues; Home keeps only rendered/persisted state."""

        self.catalog = None
        self.guide_provider = None
        self.achievement_provider = None
        self.guide_ultime_service = None
        self._last_progress_signature = None
        if not preserve_display:
            self.refresh_progress()

    def _on_network_progress_changed(self, character_key: str) -> None:
        if str(character_key or "") == self.character_key:
            self.refresh_progress()

    def _on_network_status(self, status: object) -> None:
        if not isinstance(status, NetworkApplicationStatus):
            return
        text, state = self._network_summary(status)
        self.network_status.setText(text)
        self.network_status.setToolTip(self._network_explanation(status))
        # A failed stop/cleanup can leave a privileged capture helper alive:
        # never offer a second capture until the first one is truly stopped.
        reason = str(status.reason or "")
        from app.core.network_presentation import capture_retry_allowed

        safe_to_retry = capture_retry_allowed(reason)
        self.network_retry.setText("Relancer")
        self.network_retry.setVisible(
            safe_to_retry and (
                state == "error"
                or state == "idle" and reason in {
                    "no_window_handles", "build_fingerprint_unavailable", "runtime_stopped",
                }
            )
        )
        set_unity_widget_property(self.network_indicator, "state", state)

    def _retry_network_tracking(self) -> None:
        """User-initiated retry; no expensive catalogue reload in the UI."""
        bridge = self.network_bridge
        reason = str(bridge.last_status.reason or "")
        from app.core.network_presentation import capture_retry_allowed

        if not capture_retry_allowed(reason):
            self.network_status.setText("Arrêt à vérifier")
            self.network_status.setToolTip(
                "Capture précédente non arrêtée : vérifier le processus avant toute relance."
            )
            self.network_retry.setVisible(False)
            return
        # One worker command owns context loading, calibration and UAC.
        # A separate prepare_capture + start_runtime sequence can prompt
        # twice after a cancelled permission and start even if preparation
        # failed. Never report a queue-only capture preparation as "connected".
        accepted = bridge.request_verified_runtime()
        if accepted:
            self.network_retry.setVisible(False)
            self.network_status.setText("Relance demandée…")
            self.network_status.setToolTip(
                "Tentative de connexion demandée ; l'état réseau se mettra à jour."
            )
        else:
            self.network_status.setText("Suivi indisponible")
            self.network_status.setToolTip(
                "Le suivi réseau est arrêté ; les fonctions hors ligne restent accessibles."
            )

    @staticmethod
    def _network_explanation(status: NetworkApplicationStatus) -> str:
        """Make verified capture failures actionable without exposing raw codes."""
        reason = str(status.reason or "")
        known = {
            "capture_elevation_cancelled": "Autorisation Windows de capture annulée.",
            "build_changed": "La version du client DOFUS a changé. Atlas relance le suivi pour la nouvelle build.",
            "awaiting_character_identity": (
                "Client DOFUS détecté. Atlas attend une preuve d’identité pour cette version."
            ),
            "mapping_invalid": "Le profil réseau de cette version de DOFUS est invalide.",
            "mapping_ambiguous_exact_match": "Plusieurs profils réseau correspondent au client : sélection automatique bloquée.",
            "quest_snapshot_missed": "Journal des quêtes non reçu pendant la calibration.",
            "stop_failed": "Arrêt de la capture non confirmé : vérifier le processus avant de réessayer.",
            "capture_helper_cleanup_failed": "Arrêt de la capture non confirmé : le processus Windows doit être vérifié.",
            "coordinator_cleanup_failed": "Arrêt de la capture non confirmé : vérifier les composants réseau avant toute relance.",
            "runtime_stopped": "Suivi automatique hors ligne : relancer la capture si nécessaire.",
            "no_window_handles": "Aucune fenêtre DOFUS suivie détectée.",
            "build_fingerprint_unavailable": "Identification de la version de DOFUS indisponible.",
            "build_fingerprint_error": "Erreur pendant l'identification de la version DOFUS. Réessayer la connexion.",
            "mapping_no_exact_match": "Version DOFUS non reconnue : calibration automatique demandée.",
            "mapping_missing_required_events": "Profil réseau incomplet : calibration automatique demandée.",
            "mapping_current_profile_noncanonical": "Profil réseau incompatible : nouvelle calibration nécessaire.",
            "capture_ready_waiting_context": (
                "Capture Windows préparée. Le suivi démarre automatiquement "
                "dès que le contexte réseau est prêt."
            ),
            "network_context_loading": "Chargement des données Quêtes pour le Réseau en arrière-plan.",
            "network_context_load_failed": "Catalogue réseau indisponible : réessayer ou utiliser Atlas hors ligne.",
        }
        if reason in known:
            return known[reason]
        if reason.startswith("capture_helper") or "permission" in reason or "admin" in reason:
            return "Capture Windows indisponible : vérifier les autorisations et les journaux."
        _label, state = HomePage._network_summary(status)
        if state == "error":
            return "Erreur réseau : consulter les journaux Atlas pour le diagnostic."
        if state == "idle":
            return "Suivi automatique hors ligne."
        if state == "active":
            return "Capture réseau active ; aucune position Zaap n'est déduite."
        return "Connexion et calibration du suivi automatique en cours."

    @staticmethod
    def _network_summary(status: NetworkApplicationStatus) -> tuple[str, str]:
        from app.core.network_presentation import network_summary

        return network_summary(status)

    def _rebuild_guide_ultime_service(self) -> None:
        self.guide_ultime_service = None
        if not self._guide_ultime_runtime_allowed:
            self.guide_ultime_error = "Ouvrez Guide pour charger la progression détaillée."
            return
        self.guide_ultime_error = ""
        if self.catalog is None:
            return
        try:
            from app.modules.encyclopedia.services import (
                ACHIEVEMENT_PROGRESS_FILE,
                GUIDE_PROGRESS_FILE,
                AchievementProgressService,
                GuideProgressService,
                QuestProgressService,
            )
            from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
                GuideUltimeManualRuntimeService,
            )

            quest_provider = _resolve_quest_provider()(catalog=self.catalog)
            service = GuideUltimeManualRuntimeService(
                QuestProgressService(QUEST_PROGRESS_FILE),
                AchievementProgressService(ACHIEVEMENT_PROGRESS_FILE),
                GuideProgressService(GUIDE_PROGRESS_FILE),
                quest_provider=quest_provider,
            )
            if self.achievement_provider is not None:
                service.achievement_provider = self.achievement_provider
            self.guide_ultime_service = service
        except Exception as exc:
            self.guide_ultime_error = f"{type(exc).__name__}: {exc}"

    def allow_guide_ultime_runtime(self) -> None:
        self._guide_ultime_runtime_allowed = True
        self._rebuild_guide_ultime_service()
        self.refresh_progress()

    @staticmethod
    def _progress_file_stamp(path: Path) -> tuple[int, int, int]:
        return mtime_ctime_size_stamp_or_zero(path)

    def _progress_input_signature(self) -> tuple[object, ...]:
        from app.modules.encyclopedia.services import (
            ACHIEVEMENT_PROGRESS_FILE,
            GUIDE_PROGRESS_FILE,
        )

        return (
            self.character_key,
            id(self.catalog),
            id(self.guide_provider),
            id(self.achievement_provider),
            self._progress_file_stamp(Path(QUEST_PROGRESS_FILE)),
            self._progress_file_stamp(Path(ACHIEVEMENT_PROGRESS_FILE)),
            self._progress_file_stamp(Path(GUIDE_PROGRESS_FILE)),
        )

    def refresh_progress(self) -> None:
        character_key = str(self.character_key or "").strip()
        if character_key and (
            self.catalog is None or (
                self.guide_provider is None and not self._guide_ultime_runtime_allowed
            )
        ):
            summary = _persisted_manual_summary(character_key)
            _apply_saved_progress(self, summary)
            return

        self._refresh_rich_progress()

    def _refresh_rich_progress(self) -> None:
        from app.modules.encyclopedia.services import (
            ACHIEVEMENT_PROGRESS_FILE,
            GUIDE_PROGRESS_FILE,
            AchievementProgressService,
            GuideProgressCalculator,
            GuideProgressService,
            QuestProgressService,
        )

        # The canonical manual route only needs the quest catalog. The legacy
        # GuideProvider is optional and must never gate primary Home progression.
        if self.catalog is None:
            self._show_preparing()
            return

        service = self.guide_ultime_service
        if service is not None:
            signature = self._progress_input_signature()
            if signature == self._last_progress_signature:
                return
            self._last_progress_signature = signature
        else:
            self._last_progress_signature = None

        if service is None:
            self._rebuild_guide_ultime_service()
            service = self.guide_ultime_service

        guide = self._legacy_tracking_guide()
        calculator: GuideProgressCalculator | None = None
        achievement_progress_service: AchievementProgressService | None = None
        if guide is not None:
            quest_progress_service = QuestProgressService(QUEST_PROGRESS_FILE)
            guide_progress_service = GuideProgressService(GUIDE_PROGRESS_FILE)
            achievement_progress_service = AchievementProgressService(ACHIEVEMENT_PROGRESS_FILE)
            calculator = GuideProgressCalculator(
                quest_progress_service,
                guide_progress_service,
                achievement_progress_service,
                self.catalog.by_id,
            )
            self._refresh_tracking(guide, calculator, achievement_progress_service)
        else:
            # Tracking rows are still backed by the compatibility guide for now;
            # absence of that optional source must not hide the manual route.
            self._reset_tracking()

        if service is not None and service.available:
            self._refresh_manual_guide_progress(service)
            return

        if guide is None or calculator is None or achievement_progress_service is None:
            self.current_guide_id = ""
            self.current_quest_id = None
            self.progress_bar.setValue(0)
            self.progress_percent.setText("0 %")
            self.character_progress.setText("Guide terminé : 0 %")
            self.chapter_value.setText("Guide Ultime indisponible")
            self.step_value.setText(self.guide_ultime_error or "Aucune fiche de route disponible")
            self.zone_value.setText("—")
            self.continue_button.setEnabled(False)
            return

        # Emergency compatibility fallback only. The manual manifest is the
        # canonical route; this block remains so the Home screen stays usable if
        # a malformed manual bundle prevents the runtime service from loading.
        progress = calculator.guide_progress(guide, self.character_key)
        percent = clamped_percent(progress.completed, progress.total)

        self.current_guide_id = guide.id
        self.progress_bar.setValue(percent)
        self.progress_percent.setText(f"{percent} %")
        self.character_progress.setText(f"Guide terminé : {percent} %")

        current = self._first_incomplete_step(guide, calculator)
        if current is None:
            self.current_quest_id = None
            self.chapter_value.setText("Guide terminé")
            self.step_value.setText("Toutes les étapes obligatoires sont terminées")
            self.zone_value.setText("—")
            self.continue_button.setText("Voir le guide")
            self.continue_button.setEnabled(True)
            return

        chapter_title, step = current
        self.chapter_value.setText(chapter_title or "Progression")
        self.step_value.setText(step.display_title)
        self.current_quest_id = int(step.entity_id) if step.step_type == "quest" and step.entity_id is not None else None

        zone = ""
        if self.current_quest_id is not None:
            quest = self.catalog.by_id.get(self.current_quest_id)
            if quest is not None and quest.zones:
                zone = str(quest.zones[0])
        self.zone_value.setText(zone or "—")
        self.continue_button.setText("Continuer")
        self.continue_button.setEnabled(True)

    def _refresh_manual_guide_progress(self, service: GuideUltimeManualRuntimeService) -> None:
        completed, total = service.route_sheet_progress(self.character_key)
        percent = clamped_percent(completed, total)

        self.current_guide_id = GUIDE_ULTIME_LEGACY_ID
        # The legacy id remains a navigation alias only. Progress and the active
        # sheet always come from the manual runtime service.
        self.current_quest_id = None
        self.progress_bar.setValue(percent)
        self.progress_percent.setText(f"{percent} %")
        self.character_progress.setText(f"Guide terminé : {percent} %")

        if total and completed >= total:
            self.chapter_value.setText("Guide terminé")
            self.step_value.setText("Toutes les fiches de route sont terminées")
            self.zone_value.setText("—")
            self.continue_button.setText("Voir le guide")
            self.continue_button.setEnabled(True)
            return

        _index, card = service.active_route_card(self.character_key)
        if card is None:
            self.chapter_value.setText("Guide Ultime")
            self.step_value.setText("Aucune fiche de route disponible")
            self.zone_value.setText("—")
            self.continue_button.setEnabled(False)
            return

        self.chapter_value.setText(str(card.get("manual_chapter_label") or "Progression"))
        self.step_value.setText(str(card.get("manual_title") or "Fiche de route"))
        self.zone_value.setText(
            str(card.get("destination") or card.get("zone") or card.get("subzone") or "—")
        )
        self.continue_button.setText("Continuer")
        self.continue_button.setEnabled(True)

    def _show_preparing(self) -> None:
        self.current_guide_id = ""
        self.current_quest_id = None
        self.progress_bar.setValue(0)
        self.progress_percent.setText("0 %")
        self.character_progress.setText("Guide terminé : 0 %")
        self.chapter_value.setText("Préparation du guide...")
        self.step_value.setText("Préparation du guide...")
        self.zone_value.setText("—")
        self._reset_tracking()
        self.continue_button.setText("Continuer")
        self.continue_button.setEnabled(False)

    def _legacy_tracking_guide(self) -> Guide | None:
        provider = self.guide_provider
        if provider is None or not bool(getattr(provider, "_loaded", False)):
            # Home must never warm a cold Guide catalogue. The canonical manual
            # route and persisted progress remain sufficient for the dashboard.
            return None
        guide = provider.get_by_id(GUIDE_ULTIME_LEGACY_ID)
        if guide is not None:
            return guide
        guides = [
            candidate
            for candidate in provider.load_all()
            if str(candidate.category or "").strip().casefold() == "aventure"
        ]
        return guides[0] if guides else None

    def _first_incomplete_step(
        self,
        guide: Guide,
        calculator: GuideProgressCalculator,
    ) -> tuple[str, GuideStep] | None:
        for _part_title, chapter_title, _series_title, step in self._iter_guide_steps(guide):
            if not step.counts_for_completion:
                continue
            if not calculator.step_completed(guide, step, self.character_key):
                return chapter_title, step
        return None

    def _iter_guide_steps(self, guide: Guide):
        if guide.parts:
            for part in sorted(guide.parts, key=lambda value: value.order):
                for chapter in sorted(part.chapters, key=lambda value: value.order):
                    if chapter.series:
                        for series in sorted(chapter.series, key=lambda value: value.order):
                            for step in sorted(series.steps, key=lambda value: value.order):
                                yield part.title, chapter.title, series.title, step
                    else:
                        for step in sorted(chapter.steps, key=lambda value: value.order):
                            yield part.title, chapter.title, "", step
            return
        for section in sorted(guide.sections, key=lambda value: value.order):
            for step in sorted(section.steps, key=lambda value: value.order):
                yield "", section.title, "", step

    def _refresh_tracking(
        self,
        guide: Guide,
        calculator: GuideProgressCalculator,
        achievement_progress_service: AchievementProgressService,
    ) -> None:
        counters = {
            "quests": [0, 0],
            "achievement_quests": [0, 0],
            "achievement_monsters": [0, 0],
            "achievement_dungeons": [0, 0],
            "dungeons": [0, 0],
            "dofus": [0, 0],
            "alignment": [0, 0],
        }
        dungeon_state: dict[int, bool] = {}

        for part_title, chapter_title, series_title, step in self._iter_guide_steps(guide):
            if not step.counts_for_completion:
                continue
            completed = calculator.step_completed(guide, step, self.character_key)
            context = self._plain_key(" ".join((part_title, chapter_title, series_title, step.display_title)))

            if step.step_type == "quest":
                self._bump(counters["quests"], completed)
            elif step.step_type == "achievement" and step.entity_id is not None:
                achievement = self.achievement_provider.get_by_id(int(step.entity_id)) if self.achievement_provider is not None else None
                achievement_completed = achievement_progress_service.is_achievement_completed(
                    self.character_key,
                    int(step.entity_id),
                )
                achievement_text = context
                if achievement is not None:
                    achievement_text = self._plain_key(
                        " ".join(
                            (
                                achievement.name,
                                achievement.category_name,
                                achievement.subcategory_name or "",
                            )
                        )
                    )
                if achievement is not None and (achievement.linked_dungeons or "donjon" in achievement_text or "boss" in achievement_text):
                    self._bump(counters["achievement_dungeons"], achievement_completed)
                elif achievement is not None and (achievement.linked_monsters or "monstre" in achievement_text):
                    self._bump(counters["achievement_monsters"], achievement_completed)
                else:
                    self._bump(counters["achievement_quests"], achievement_completed)

                if achievement is not None:
                    for dungeon_ref in achievement.linked_dungeons:
                        dungeon_id = int(dungeon_ref.entity_id)
                        dungeon_state[dungeon_id] = dungeon_state.get(dungeon_id, False) or achievement_completed
            elif step.step_type == "dungeon":
                dungeon_id = int(step.entity_id) if step.entity_id is not None else hash(step.id)
                dungeon_state[dungeon_id] = dungeon_state.get(dungeon_id, False) or completed

            if self._contains_any(context, self._DOFUS_KEYWORDS):
                self._bump(counters["dofus"], completed)
            if self._contains_any(context, self._ALIGNMENT_KEYWORDS):
                self._bump(counters["alignment"], completed)

        counters["dungeons"] = [sum(1 for done in dungeon_state.values() if done), len(dungeon_state)]

        for key, row in self.tracking_rows.items():
            completed, total = counters[key]
            row.set_progress(completed, total, show_count=key == "dofus")

    def _reset_tracking(self) -> None:
        for row in self.tracking_rows.values():
            row.set_progress(0, 0)

    @staticmethod
    def _bump(counter: list[int], completed: bool) -> None:
        counter[1] += 1
        if completed:
            counter[0] += 1

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _plain_key(value: str) -> str:
        return " ".join(
            strip_accents(value).casefold().replace("’", "'").replace("-", " ").split()
        )

    def _emit_continue(self) -> None:
        if not self.current_guide_id:
            return
        self.continueRequested.emit(self.current_guide_id, self.current_quest_id)

    def _update_character_icon(self, icon_path: str | None = None) -> None:
        icon_path = self.character_icon_path if icon_path is None else icon_path
        path = Path(icon_path) if icon_path else None
        fallback = Path(LOGO_PATH)
        selected = path if path is not None and path.is_file() else fallback if fallback.is_file() else None
        signature = (str(selected), mtime_ctime_size_stamp(selected) if selected is not None else None)
        if signature == self._character_icon_signature:
            return
        self._character_icon_signature = signature
        if selected is None:
            self.character_portrait.setIcon(QIcon())
            return
        if selected == fallback:
            self.character_portrait.setIcon(atlas_application_icon())
        else:
            from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
            pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(selected, self.character_portrait.iconSize())
            icon = QIcon(pixmap)
            # This decorative button is disabled, but its artwork needs the
            # original class colors just like the portrait in the selector.
            if not pixmap.isNull():
                icon.addPixmap(pixmap, QIcon.Disabled)
            self.character_portrait.setIcon(icon)
