from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import LOGO_PATH, QUEST_PROGRESS_FILE, ROOT_DIR
from app.modules.encyclopedia.models import Guide, GuideStep
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import (
    ACHIEVEMENT_PROGRESS_FILE,
    GUIDE_PROGRESS_FILE,
    AchievementProgressService,
    GuideProgressCalculator,
    GuideProgressService,
    QuestProgressService,
)
from app.network.application_coordinator import NetworkApplicationStatus
from app.quest_catalog import QuestCatalog
from app.ui.network_bridge import network_ui_bridge


HOME_GUIDE_BANNER_PATH = Path(LOGO_PATH).parent / "home_guide_banner.png"
GUIDE_ULTIME_LEGACY_ID = "guide_complet"
_HOME_PROGRESS_CACHE_PATH = ROOT_DIR / ".cache" / "dofus_atlas" / "home_progress_v1.json"
_MANUAL_ROUTE_MANIFEST_PATH = (
    ROOT_DIR / "data" / "routes" / "guide_ultime_manual" / "manifest_v1.json"
)
_GUIDE_PROGRESS_ID = "guide_ultime_v5"


def _file_stamp(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    return int(stat.st_mtime_ns), int(stat.st_size)


def _saved_progress_signature() -> tuple[tuple[int, int], ...]:
    # Import the canonical paths lazily without loading Encyclopedia providers.
    from app.constants import QUEST_PROGRESS_FILE as quest_progress_file
    from app.modules.encyclopedia.services import (
        ACHIEVEMENT_PROGRESS_FILE as achievement_progress_file,
    )

    return (
        _file_stamp(Path(quest_progress_file)),
        _file_stamp(Path(achievement_progress_file)),
        _file_stamp(Path(GUIDE_PROGRESS_FILE)),
    )


def _read_home_progress_cache() -> dict[str, Any]:
    try:
        payload = json.loads(_HOME_PROGRESS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "characters": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "characters": {}}
    if not isinstance(payload.get("characters"), dict):
        payload["characters"] = {}
    payload["version"] = 1
    return payload


def _write_home_progress_cache(payload: dict[str, Any]) -> None:
    try:
        _HOME_PROGRESS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _HOME_PROGRESS_CACHE_PATH.with_suffix(
            _HOME_PROGRESS_CACHE_PATH.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(_HOME_PROGRESS_CACHE_PATH)
    except OSError:
        # This cache is reconstructible display data, never progression truth.
        return


def _cached_home_progress(character_key: str) -> dict[str, Any] | None:
    row = _read_home_progress_cache().get("characters", {}).get(character_key)
    if not isinstance(row, dict):
        return None
    expected = [list(value) for value in _saved_progress_signature()]
    if row.get("progress_signature") != expected:
        return None
    try:
        percent = max(0, min(100, int(row.get("percent") or 0)))
    except (TypeError, ValueError):
        return None
    return {
        "percent": percent,
        "chapter": str(row.get("chapter") or "Progression sauvegardée"),
        "step": str(row.get("step") or "Progression locale disponible"),
        "zone": str(row.get("zone") or "—"),
        "guide_id": str(row.get("guide_id") or GUIDE_ULTIME_LEGACY_ID),
    }


def _save_home_progress(page: "HomePage") -> None:
    character_key = str(page.character_key or "").strip()
    if not character_key:
        return
    try:
        percent = max(0, min(100, int(page.progress_bar.value())))
    except Exception:
        return
    payload = _read_home_progress_cache()
    characters = payload.setdefault("characters", {})
    if not isinstance(characters, dict):
        characters = {}
        payload["characters"] = characters
    characters[character_key] = {
        "progress_signature": [list(value) for value in _saved_progress_signature()],
        "percent": percent,
        "chapter": str(page.chapter_value.text() or ""),
        "step": str(page.step_value.text() or ""),
        "zone": str(page.zone_value.text() or ""),
        "guide_id": str(page.current_guide_id or GUIDE_ULTIME_LEGACY_ID),
    }
    _write_home_progress_cache(payload)


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
    percent = int(round((completed / total) * 100)) if total else 0
    return {
        "percent": max(0, min(100, percent)),
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
        self.setMinimumHeight(145)
        self.setMaximumHeight(205)
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
    def __init__(self, icon: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HomeTrackingRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        icon_label = QLabel(icon)
        icon_label.setObjectName("HomeTrackingIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedWidth(20)
        layout.addWidget(icon_label)

        name = QLabel(label)
        name.setObjectName("HomeTrackingLabel")
        name.setMinimumWidth(92)
        layout.addWidget(name)

        self.bar = QProgressBar()
        self.bar.setObjectName("HomeTrackingBar")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setMinimumWidth(62)
        layout.addWidget(self.bar, 1)

        self.value = QLabel("0 %")
        self.value.setObjectName("HomeTrackingValue")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setMinimumWidth(46)
        layout.addWidget(self.value)

    def set_progress(self, completed: int, total: int, *, show_count: bool = False) -> None:
        completed = max(0, int(completed))
        total = max(0, int(total))
        percent = int(round((completed / total) * 100)) if total else 0
        percent = max(0, min(100, percent))
        self.bar.setValue(percent)
        if show_count and total:
            self.value.setText(f"{completed} / {total}")
        else:
            self.value.setText(f"{percent} %")


class HomePage(QWidget):
    """Accueil léger : les données lourdes sont injectées par AtlasWindow."""

    continueRequested = Signal(str, object)
    changeCharacterRequested = Signal()

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
        self.character_icon_path = ""
        self.current_guide_id = ""
        self.current_quest_id: int | None = None
        self._last_progress_signature: tuple[object, ...] | None = None
        self.network_bridge = network_ui_bridge()
        self.network_bridge.statusChanged.connect(self._on_network_status)
        self.network_bridge.progressChanged.connect(self._on_network_progress_changed)

        root = QHBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        root.setSpacing(18)

        self.left_column = QWidget()
        self.left_column.setObjectName("HomeLeftColumn")
        self.left_column.setMinimumWidth(286)
        self.left_column.setMaximumWidth(350)
        left_layout = QVBoxLayout(self.left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        self.character_card = self._card("HomeCharacterCard")
        char_layout = self.character_card.layout()
        self._add_card_title(char_layout, "Personnage sélectionné")

        identity = QHBoxLayout()
        identity.setContentsMargins(0, 4, 0, 2)
        identity.setSpacing(14)
        self.character_portrait = QToolButton()
        self.character_portrait.setObjectName("HomeCharacterPortrait")
        self.character_portrait.setFixedSize(98, 98)
        self.character_portrait.setIconSize(QSize(88, 88))
        self.character_portrait.setEnabled(False)
        identity.addWidget(self.character_portrait, 0, Qt.AlignVCenter)

        identity_text = QVBoxLayout()
        identity_text.setContentsMargins(0, 0, 0, 0)
        identity_text.setSpacing(8)
        identity_text.addStretch(1)
        self.character_name = QLabel(self.character_label)
        self.character_name.setObjectName("HomeCharacterName")
        self.character_name.setWordWrap(True)
        identity_text.addWidget(self.character_name)
        self.character_progress = QLabel("Guide terminé : 0 %")
        self.character_progress.setObjectName("HomeCharacterProgress")
        self.character_progress.setWordWrap(True)
        identity_text.addWidget(self.character_progress)
        identity_text.addStretch(1)
        identity.addLayout(identity_text, 1)
        char_layout.addLayout(identity)

        change_button = QPushButton("Changer de personnage")
        change_button.setObjectName("HomeChangeCharacterButton")
        change_button.clicked.connect(self.changeCharacterRequested)
        char_layout.addWidget(change_button)
        left_layout.addWidget(self.character_card, 0)

        self.tracking_card = self._card("HomeTrackingCard")
        tracking_layout = self.tracking_card.layout()
        self._add_card_title(tracking_layout, "Progression globale")
        tracking_layout.addSpacing(3)
        self.tracking_rows: dict[str, HomeTrackingRow] = {}
        for key, icon, label in (
            ("quests", "◆", "Quêtes"),
            ("achievement_quests", "✦", "Succès (Quêtes)"),
            ("achievement_monsters", "●", "Succès (Monstres)"),
            ("achievement_dungeons", "▥", "Succès (Donjons)"),
            ("dungeons", "▣", "Donjons"),
            ("dofus", "◉", "Dofus"),
            ("alignment", "★", "Alignement"),
        ):
            row = HomeTrackingRow(icon, label)
            self.tracking_rows[key] = row
            tracking_layout.addWidget(row)

        tracking_layout.addStretch(1)
        left_layout.addWidget(self.tracking_card, 1)

        self.guide_card = self._card("HomeGuideCard")
        self.guide_card.setMinimumWidth(500)
        guide_layout = self.guide_card.layout()
        self._add_card_title(guide_layout, "Guide progression")

        self.guide_title = QLabel("Aventure 0 → Sylvestre")
        self.guide_title.setObjectName("HomeGuideTitle")
        self.guide_title.setWordWrap(True)
        guide_layout.addWidget(self.guide_title)

        self.guide_banner = HomeBannerLabel(HOME_GUIDE_BANNER_PATH)
        guide_layout.addWidget(self.guide_banner)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 7, 0, 0)
        progress_row.setSpacing(8)
        progress_label = QLabel("Progression générale")
        progress_label.setObjectName("HomeGuideProgressLabel")
        self.progress_percent = QLabel("0 %")
        self.progress_percent.setObjectName("HomeGuideProgressPercent")
        self.progress_percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(progress_label, 1)
        progress_row.addWidget(self.progress_percent)
        guide_layout.addLayout(progress_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("HomeProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        guide_layout.addWidget(self.progress_bar)
        guide_layout.addSpacing(10)

        self.chapter_value = self._add_guide_detail_row(guide_layout, "▤", "Chapitre en cours :")
        self.step_value = self._add_guide_detail_row(guide_layout, "▱", "Quête en cours :")
        self.zone_value = self._add_guide_detail_row(guide_layout, "●", "Zone actuelle :")
        guide_layout.addStretch(1)

        self.continue_button = QPushButton("Continuer")
        self.continue_button.setObjectName("HomeContinueButton")
        self.continue_button.setEnabled(False)
        self.continue_button.clicked.connect(self._emit_continue)
        guide_layout.addWidget(self.continue_button)

        self.almanax_card = self._card("HomeAlmanaxCard")
        self.almanax_card.setMinimumWidth(250)
        self.almanax_card.setMaximumWidth(330)
        almanax_layout = self.almanax_card.layout()
        self._add_card_title(almanax_layout, "Almanax")
        almanax_layout.addStretch(1)

        self.almanax_icon = QToolButton()
        self.almanax_icon.setObjectName("HomeAlmanaxPlaceholderIcon")
        self.almanax_icon.setFixedSize(150, 150)
        self.almanax_icon.setIconSize(QSize(126, 126))
        self.almanax_icon.setEnabled(False)
        if Path(LOGO_PATH).exists():
            self.almanax_icon.setIcon(QIcon(str(LOGO_PATH)))
        almanax_layout.addWidget(self.almanax_icon, 0, Qt.AlignHCenter)

        badge = QLabel("En travaux")
        badge.setObjectName("HomePlaceholderBadge")
        badge.setAlignment(Qt.AlignCenter)
        almanax_layout.addWidget(badge, 0, Qt.AlignHCenter)

        almanax_text = QLabel("Le module Almanax sera intégré ici.")
        almanax_text.setObjectName("HomeAlmanaxText")
        almanax_text.setAlignment(Qt.AlignCenter)
        almanax_text.setWordWrap(True)
        almanax_layout.addWidget(almanax_text)
        almanax_layout.addStretch(1)

        almanax_button = QPushButton("Voir l’Almanax")
        almanax_button.setObjectName("HomeAlmanaxButton")
        almanax_button.setEnabled(False)
        almanax_layout.addWidget(almanax_button)

        self.right_column = QWidget()
        self.right_column.setObjectName("HomeRightColumn")
        self.right_column.setMinimumWidth(250)
        self.right_column.setMaximumWidth(330)
        right_layout = QVBoxLayout(self.right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.network_card = QFrame()
        self.network_card.setObjectName("HomeNetworkMiniCard")
        self.network_card.setMinimumHeight(64)
        self.network_card.setMaximumHeight(72)
        network_layout = QHBoxLayout(self.network_card)
        network_layout.setContentsMargins(15, 10, 15, 10)
        network_layout.setSpacing(10)
        self.network_indicator = QLabel("●")
        self.network_indicator.setObjectName("HomeNetworkIndicator")
        self.network_indicator.setProperty("state", "pending")
        self.network_indicator.setAlignment(Qt.AlignCenter)
        network_layout.addWidget(self.network_indicator, 0, Qt.AlignVCenter)

        network_text = QVBoxLayout()
        network_text.setContentsMargins(0, 0, 0, 0)
        network_text.setSpacing(1)
        network_title = QLabel("Suivi automatique")
        network_title.setObjectName("HomeNetworkMiniTitle")
        network_text.addWidget(network_title)
        self.network_status = QLabel("Préparation…")
        self.network_status.setObjectName("HomeNetworkMiniStatus")
        network_text.addWidget(self.network_status)
        network_layout.addLayout(network_text, 1)

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
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
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
        row_layout.setContentsMargins(5, 9, 5, 9)
        row_layout.setSpacing(10)

        icon_label = QLabel(icon)
        icon_label.setObjectName("HomeGuideDetailIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedWidth(28)
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

    def set_character(self, character_key: str, character_label: str, icon_path: str = "") -> None:
        next_key = str(character_key or "")
        next_label = str(character_label or "Personnage")
        next_icon_path = str(icon_path or "")
        if (
            next_key == self.character_key
            and next_label == self.character_label
            and next_icon_path == self.character_icon_path
        ):
            return
        self.character_key = next_key
        self.character_label = next_label
        self.character_icon_path = next_icon_path
        self.character_name.setText(self.character_label)
        self._update_character_icon()
        self.refresh_progress()

    def apply_encyclopedia_context(
        self,
        catalog: QuestCatalog | None = None,
        guide_provider: GuideProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
    ) -> None:
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

    def _on_network_progress_changed(self, character_key: str) -> None:
        if str(character_key or "") == self.character_key:
            self.refresh_progress()

    def _on_network_status(self, status: object) -> None:
        if not isinstance(status, NetworkApplicationStatus):
            return
        text, state = self._network_summary(status)
        self.network_status.setText(text)
        if self.network_indicator.property("state") != state:
            self.network_indicator.setProperty("state", state)
            self.network_indicator.style().unpolish(self.network_indicator)
            self.network_indicator.style().polish(self.network_indicator)

    @staticmethod
    def _network_summary(status: NetworkApplicationStatus) -> tuple[str, str]:
        if status.running:
            return "Actif", "active"
        reason = str(status.reason or "")
        if status.calibrating or reason in {
            "calibrating",
            "awaiting_character_identity",
            "awaiting_quest_journal",
            "awaiting_distinct_quest_completions",
            "mapping_installed_not_started",
            "mapping_already_installed",
            "mapping_already_ready",
        }:
            return "Connexion…", "pending"
        if reason == "no_window_handles":
            return "En attente de Dofus", "idle"
        if (
            reason == "capture_elevation_cancelled"
            or reason == "build_changed"
            or reason.startswith("capture_helper")
            or "admin" in reason
            or "permission" in reason
            or "failed" in reason
            or "error" in reason
            or "ambiguous" in reason
        ):
            return "Attention requise", "error"
        return "Préparation…", "pending"

    def _rebuild_guide_ultime_service(self) -> None:
        self.guide_ultime_service = None
        if not self._guide_ultime_runtime_allowed:
            self.guide_ultime_error = "Ouvrez Guide pour charger la progression détaillée."
            return
        self.guide_ultime_error = ""
        if self.catalog is None:
            return
        try:
            from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
                GuideUltimeManualRuntimeService,
            )

            quest_provider = QuestProvider(catalog=self.catalog)
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
    def _progress_file_stamp(path: Path) -> tuple[int, int]:
        try:
            stat = Path(path).stat()
        except OSError:
            return (0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _progress_input_signature(self) -> tuple[object, ...]:
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
        if character_key and (self.catalog is None or self.guide_provider is None):
            summary = _cached_home_progress(character_key)
            if summary is None:
                summary = _persisted_manual_summary(character_key)
            _apply_saved_progress(self, summary)
            return

        self._refresh_rich_progress()
        if character_key and self.catalog is not None and self.guide_provider is not None:
            _save_home_progress(self)

    def _refresh_rich_progress(self) -> None:
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
        percent = int(round((progress.completed / progress.total) * 100)) if progress.total else 0
        percent = max(0, min(100, percent))

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
        percent = int(round((completed / total) * 100)) if total else 0
        percent = max(0, min(100, percent))

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
        if self.guide_provider is None:
            return None
        guide = self.guide_provider.get_by_id(GUIDE_ULTIME_LEGACY_ID)
        if guide is not None:
            return guide
        guides = [
            candidate
            for candidate in self.guide_provider.load_all()
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
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        return " ".join(
            "".join(character for character in normalized if not unicodedata.combining(character))
            .casefold()
            .replace("’", "'")
            .replace("-", " ")
            .split()
        )

    def _emit_continue(self) -> None:
        if not self.current_guide_id:
            return
        self.continueRequested.emit(self.current_guide_id, self.current_quest_id)

    def _update_character_icon(self) -> None:
        path = Path(self.character_icon_path)
        fallback = Path(LOGO_PATH)
        selected = path if path.exists() else fallback if fallback.exists() else None
        if selected is None:
            self.character_portrait.setIcon(QIcon())
            return
        self.character_portrait.setIcon(QIcon(str(selected)))
