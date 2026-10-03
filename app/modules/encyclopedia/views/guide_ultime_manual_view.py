from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote, unquote

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.services.guide_quest_view_model import (
    COMBAT_OBJECTIVE_TYPES,
    quest_items_from_objectives,
)
from app.modules.encyclopedia.views.guide_ultime_universal_view import GuideUltimeUniversalView
from app.quest_catalog import normalize_text
from app.ui.components import AtlasButton
from app.ui.theme import PALETTE


NPC_COLOR = PALETTE["YELLOW"]
RESOURCE_COLOR = PALETTE["GREEN"]
POSITION_COLOR = PALETTE["TEXT_SOFT"]
_COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")
_COMBAT_QUANTITY_RE = re.compile(r"\bx\s*(\d+)\b", re.IGNORECASE)
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*"
_NPC_NAME = rf"{_NAME_WORD}(?:\s+(?:(?:de|des|du|d['’]|of|le|la|l['’])\s+)?{_NAME_WORD}){{0,3}}"
_NPC_PATTERNS = (
    re.compile(rf"(?:auprès\s+(?:de|d['’])|aupres\s+(?:de|d['’])|avec|vers|chez)\s+(?:l['’]|le\s+|la\s+|les\s+|du\s+|de\s+la\s+|de\s+l['’])?({_NPC_NAME})"),
    re.compile(rf"(?:parler|parle|parlez)\s+(?:à|a|au|aux|à\s+la|a\s+la|à\s+l['’])\s*(?:l['’])?({_NPC_NAME})", re.IGNORECASE),
    re.compile(rf"(?:libérer|liberer|livrer|présenter|presenter|retrouver)\s+({_NPC_NAME})", re.IGNORECASE),
    re.compile(rf"(?:rendre|donner|présenter|presenter|apporter)[^.;]{{0,80}}?\s+(?:à|a|au|aux|à\s+la|a\s+la|à\s+l['’])\s*(?:l['’])?({_NPC_NAME})", re.IGNORECASE),
)
_RESOURCE_STOP_WORDS = {"de", "du", "des", "la", "le", "les", "d", "l", "à", "au", "aux", "et"}
_NPC_CONNECTORS = {"de", "des", "du", "d'", "d’", "of", "le", "la", "l'", "l’"}


class GuideManualProgressBar(QProgressBar):
    """Completion bar that also acts as a route scrubber without mutating progress."""

    navigationRequested = Signal(float)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton and self.width() > 0:
            ratio = max(0.0, min(1.0, float(event.position().x()) / float(self.width())))
            self.navigationRequested.emit(ratio)
            event.accept()
            return
        super().mousePressEvent(event)


class GuideUltimeManualCard(QFrame):
    """A single hand-authored road-book sheet. No per-line validation."""

    questRequested = Signal(int, str, int)

    def __init__(self, service, character_key: str, card: dict[str, Any], index: int, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.character_key = character_key
        self.card = card
        self.index = index
        self._quest_rows = self._canonical_quest_rows()
        self._shown_quest_map_links: set[tuple[int, str]] = set()
        self._resource_names = self._clickable_resource_names(service, card)
        self.setObjectName("GuideManualSheet")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(9)

        if index == 0:
            self._add_legend(root)

        title = QLabel(str(card.get("manual_title") or "Fiche de route"))
        title.setObjectName("GuideManualStageTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        location = str(card.get("destination") or "").strip()
        if location:
            where = QLabel()
            where.setObjectName("GuideManualLocation")
            where.setWordWrap(True)
            self._set_clickable_text(where, self._format_line_html("", "", location, [], []))
            root.addWidget(where)

        self._add_quest_combats(root)

        line_provider = getattr(service, "manual_lines_for_card", None)
        manual_lines = line_provider(character_key, card) if callable(line_provider) else card.get("manual_lines", []) or []
        section_provider = getattr(service, "manual_sections_for_card", None)
        sections = (
            section_provider(character_key, card)
            if callable(section_provider)
            else {"now": manual_lines}
        )
        if not isinstance(sections, dict) or not any(sections.values()):
            sections = {"now": manual_lines}
        sections = self._without_prepare_duplicates(sections)

        self._add_line_section(
            root,
            "À PRÉPARER",
            sections.get("prepare"),
            "GuideManualResourceSection",
            "prepare",
        )
        self._add_line_section(
            root,
            "À FAIRE MAINTENANT",
            sections.get("now"),
            "GuideManualActionSection",
            "now",
        )
        self._add_line_section(
            root,
            "À PROFITER ICI",
            sections.get("opportunity"),
            "GuideManualActionSection",
            "opportunity",
        )
        self._add_line_section(
            root,
            "À CONSERVER POUR PLUS TARD",
            sections.get("keep"),
            "GuideManualResourceSection",
            "keep",
        )
        self._add_line_section(
            root,
            "BOSS / CAPTURES",
            sections.get("boss"),
            "GuideManualDungeonSection",
            "boss",
        )
        self._add_line_section(
            root,
            "AVANT DE PARTIR",
            sections.get("before_leave"),
            "GuideManualWarningSection",
            "before_leave",
        )

        automatic = service.card_auto_complete(character_key, card)
        manual = service.page_checked(character_key, card, index)
        blocking = bool(
            callable(getattr(service, "manual_order_choice_blocking", None))
            and service.manual_order_choice_blocking(character_key, card)
        )
        trigger_ready = bool(
            callable(getattr(service, "manual_order_choice_required", None))
            and service.manual_order_choice_required(character_key, card)
        )
        if blocking:
            label = "CHOISIR L’ORDRE" if trigger_ready else "RANG 20 REQUIS"
        elif automatic:
            label = "VALIDÉE AUTOMATIQUEMENT"
        else:
            label = "VALIDER LA FICHE"
        self.page_check = QCheckBox(label)
        self.page_check.setObjectName("GuideManualPageCheck")
        self.page_check.setChecked(bool((automatic or manual) and not blocking))
        self.page_check.setEnabled(not automatic and not blocking)
        if not automatic and not blocking:
            self.page_check.setToolTip("Secours temporaire tant que la validation automatique n'est pas branchée.")
            self.page_check.toggled.connect(self._page_toggled)

    def _add_legend(self, root: QVBoxLayout) -> None:
        frame = QFrame()
        frame.setObjectName("GuideManualLegendCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        title = QLabel("LÉGENDE")
        title.setObjectName("GuideManualLegendTitle")
        layout.addWidget(title)

        rows = (
            "Coordonnée en gras : cliquer copie la commande /travel x,y.",
            "Objet en vert : cliquer copie son nom. PNJ en jaune : interlocuteur à trouver.",
            "Case de combat : objectif partagé avec l’onglet Quêtes, avec monstre et quantité.",
            "Validation : automatique quand Atlas dispose de la preuve, manuelle seulement en secours.",
        )
        for text in rows:
            label = QLabel(f"• {text}")
            label.setObjectName("GuideManualLegendText")
            label.setWordWrap(True)
            layout.addWidget(label)
        root.addWidget(frame)

    @staticmethod
    def _section_row_fingerprint(row: Any) -> str:
        if not isinstance(row, dict):
            return ""
        position = " ".join(str(row.get("position") or "").split()).casefold()
        text = " ".join(str(row.get("text") or "").split()).casefold()
        return f"{position}\n{text}" if text else ""

    @classmethod
    def _without_prepare_duplicates(cls, sections: dict[str, Any]) -> dict[str, list[Any]]:
        """Do not repeat in preparation an instruction already executed now."""
        visible = {
            str(key): list(rows or []) if isinstance(rows, (list, tuple)) else []
            for key, rows in sections.items()
        }
        now_fingerprints = {
            cls._section_row_fingerprint(row)
            for row in visible.get("now", [])
        }
        now_fingerprints.discard("")
        visible["prepare"] = [
            row
            for row in visible.get("prepare", [])
            if cls._section_row_fingerprint(row) not in now_fingerprints
        ]
        return visible

    def _canonical_quest_rows(self) -> list[tuple[int, str]]:
        provider = getattr(self.service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        result: list[tuple[int, str]] = []
        seen: set[int] = set()
        for raw in self.card.get("manual_quest_ids", []) or []:
            try:
                quest_id = int(raw)
            except (TypeError, ValueError):
                continue
            if quest_id in seen:
                continue
            seen.add(quest_id)

            name = ""
            if callable(getter):
                try:
                    quest = getter(quest_id)
                except (KeyError, LookupError, TypeError, ValueError):
                    quest = None
                name = str(getattr(quest, "name", "") or "").strip()
            result.append((quest_id, name or f"Quête #{quest_id}"))
        return result

    @staticmethod
    def _position_key(position: str) -> str:
        value = " ".join(str(position or "").split()).strip()
        match = _COORD_RE.search(value)
        if match:
            return f"{int(match.group(1))},{int(match.group(2))}"
        return value.casefold()

    @staticmethod
    def _quest_name_key(value: str) -> str:
        return " ".join(str(value or "").split()).strip().casefold()

    def _waypoint_quest_ids_for_row(self, row: dict[str, Any]) -> list[int]:
        stage = self.card.get("manual_stage_data")
        if not isinstance(stage, dict) or not self._quest_rows:
            return []
        row_position = self._position_key(str(row.get("position") or ""))
        if not row_position:
            return []

        quest_ids_by_name = {
            self._quest_name_key(name): quest_id
            for quest_id, name in self._quest_rows
        }
        result: list[int] = []
        for waypoint in stage.get("waypoints", []) or []:
            if not isinstance(waypoint, dict):
                continue
            try:
                coordinates = f"{int(waypoint.get('x'))},{int(waypoint.get('y'))}"
            except (TypeError, ValueError):
                coordinates = ""
            waypoint_position = coordinates or self._position_key(
                str(waypoint.get("label") or "")
            )
            if waypoint_position != row_position:
                continue
            for quest_name in waypoint.get("quests", []) or []:
                quest_id = quest_ids_by_name.get(self._quest_name_key(quest_name))
                if quest_id is not None and quest_id not in result:
                    result.append(quest_id)
        return result

    def _quest_ids_for_row(self, row: dict[str, Any]) -> list[int]:
        waypoint_ids = self._waypoint_quest_ids_for_row(row)
        if waypoint_ids:
            return waypoint_ids
        return [quest_id for quest_id, _name in self._quest_rows]

    def _add_inline_quest_links(
        self,
        row_layout: QHBoxLayout,
        row: dict[str, Any],
    ) -> None:
        if not self._quest_rows:
            return
        position = str(row.get("position") or self.card.get("destination") or "").strip()
        map_key = self._position_key(position) or "__stage__"
        names = {quest_id: name for quest_id, name in self._quest_rows}
        stage_id = str(self.card.get("manual_stage_id") or "")
        for quest_id in self._quest_ids_for_row(row):
            dedupe_key = (int(quest_id), map_key)
            if dedupe_key in self._shown_quest_map_links:
                continue
            name = names.get(int(quest_id))
            if not name:
                continue
            self._shown_quest_map_links.add(dedupe_key)
            button = QToolButton()
            button.setObjectName("GuideManualQuestInlineButton")
            button.setText("↗")
            button.setAutoRaise(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedSize(18, 18)
            button.setToolTip(name)
            button.clicked.connect(
                lambda _checked=False, qid=quest_id, sid=stage_id: self.questRequested.emit(
                    int(qid),
                    sid,
                    self.index,
                )
            )
            row_layout.addWidget(button, 0, Qt.AlignTop)

    def _add_quest_combats(self, root: QVBoxLayout) -> None:
        targets = self._quest_combat_targets()
        if not targets:
            return

        frame = QFrame()
        frame.setObjectName("GuideManualDungeonSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel("COMBATS DE QUÊTE")
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        progress = getattr(self.service, "quest_progress", None)
        for target in targets:
            quest_id = int(target["quest_id"])
            objective_id = int(target["objective_id"])
            quantity = int(target["quantity"])
            monster = str(target["monster"])
            quest_name = str(target["quest_name"])
            text = f"{quantity} × {monster}"
            if quest_name:
                text += f" — {quest_name}"
            checkbox = QCheckBox(text)
            checkbox.setObjectName("GuideManualCombatCheck")
            checked = bool(
                progress is not None
                and callable(getattr(progress, "is_objective_completed", None))
                and progress.is_objective_completed(
                    self.character_key,
                    quest_id,
                    objective_id,
                )
            )
            checkbox.setChecked(checked)
            checkbox.setProperty("state", "done" if checked else "todo")
            checkbox.setToolTip("Progression partagée avec l’objectif de la fiche Quête.")
            checkbox.toggled.connect(
                lambda value, qid=quest_id, oid=objective_id, box=checkbox: self._combat_toggled(
                    qid,
                    oid,
                    box,
                    value,
                )
            )
            layout.addWidget(checkbox)

        root.addWidget(frame)

    def _quest_combat_targets(self) -> list[dict[str, Any]]:
        provider = getattr(self.service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        if not callable(getter):
            return []

        card_text = " ".join(
            f"{row.get('position', '')} {row.get('text', '')}"
            for row in self.card.get("manual_lines", []) or []
            if isinstance(row, dict)
        )
        normalized_card_text = normalize_text(card_text)
        card_coords = set(_COORD_RE.findall(card_text))
        result: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for raw in self.card.get("manual_quest_ids", []) or []:
            try:
                quest_id = int(raw)
                quest = getter(quest_id)
            except (KeyError, LookupError, TypeError, ValueError):
                continue
            quest_name = str(getattr(quest, "name", "") or "").strip()
            for step in getattr(quest, "steps", ()) or ():
                for objective in getattr(step, "objectives", ()) or ():
                    objective_id = self._safe_positive_int(getattr(objective, "id", None))
                    type_id = self._safe_positive_int(getattr(objective, "type_id", None))
                    is_combat = bool(getattr(objective, "is_combat", False))
                    if objective_id is None or not (
                        is_combat or type_id in COMBAT_OBJECTIVE_TYPES
                    ):
                        continue
                    objective_text = str(getattr(objective, "text", "") or "").strip()
                    monster = str(
                        getattr(objective, "image_label", "")
                        or objective_text
                        or ""
                    ).strip()
                    objective_coords = set(
                        _COORD_RE.findall(
                            str(getattr(objective, "map_label", "") or "")
                        )
                    )
                    if not monster or not (
                        normalize_text(monster) in normalized_card_text
                        or bool(card_coords & objective_coords)
                    ):
                        continue
                    key = (quest_id, objective_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    quantity = self._combat_quantity(objective, objective_text)
                    result.append(
                        {
                            "quest_id": quest_id,
                            "objective_id": objective_id,
                            "quest_name": quest_name,
                            "monster": monster,
                            "quantity": quantity,
                        }
                    )
        return result

    @classmethod
    def _combat_quantity(cls, objective: Any, objective_text: str) -> int:
        match = _COMBAT_QUANTITY_RE.search(objective_text)
        if match is not None:
            return cls._safe_positive_int(match.group(1)) or 1
        return cls._safe_positive_int(getattr(objective, "item_quantity", None)) or 1

    @staticmethod
    def _safe_positive_int(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _combat_toggled(
        self,
        quest_id: int,
        objective_id: int,
        checkbox: QCheckBox,
        checked: bool,
    ) -> None:
        progress = getattr(self.service, "quest_progress", None)
        setter = getattr(progress, "set_objective_completed", None)
        if not callable(setter):
            return
        setter(
            self.character_key,
            int(quest_id),
            int(objective_id),
            bool(checked),
        )
        checkbox.setProperty("state", "done" if checked else "todo")
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        parent = self.parentWidget()
        while parent is not None:
            handler = getattr(parent, "_manual_objective_changed", None)
            if callable(handler):
                handler(int(quest_id))
                return
            parent = parent.parentWidget()

    @staticmethod
    def _clickable_resource_names(service, card: dict[str, Any]) -> list[str]:
        names = [
            str(value).strip()
            for value in card.get("manual_resource_names", []) or []
            if str(value).strip()
        ]
        provider = getattr(service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        if callable(getter):
            for raw in card.get("manual_quest_ids", []) or []:
                try:
                    quest_id = int(raw)
                    quest = getter(quest_id)
                except (KeyError, LookupError, TypeError, ValueError):
                    continue
                try:
                    items = quest_items_from_objectives(quest)
                except (AttributeError, TypeError, ValueError):
                    continue
                for item in items:
                    name = str(getattr(item, "name", "") or "").strip()
                    if name:
                        names.append(name)

        result: list[str] = []
        seen: set[str] = set()
        for name in names:
            key = name.casefold()
            if key and key not in seen:
                seen.add(key)
                result.append(name)
        return sorted(result, key=len, reverse=True)

    def _add_line_section(
        self,
        root: QVBoxLayout,
        title: str,
        rows,
        object_name: str,
        section_key: str,
    ) -> None:
        visible = [
            row for row in rows or []
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
        if not visible:
            return

        frame = QFrame()
        frame.setObjectName(object_name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        for row in visible:
            text = str(row.get("text") or "").strip()
            position = str(row.get("position") or "").strip()
            kind = str(row.get("kind") or "")
            prefix = "⚠ " if kind == "warning" else "• "

            row_widget = QFrame()
            row_widget.setObjectName("GuideManualLineRow")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(7)
            line = QLabel()
            self._set_clickable_text(
                line,
                self._format_line_html(
                    prefix,
                    position,
                    text,
                    self._npc_names(text),
                    self._resource_names,
                ),
            )
            line.setObjectName(self._line_object_name(kind, text))
            line.setWordWrap(True)
            row_layout.addWidget(line, 1)
            if section_key == "now":
                self._add_inline_quest_links(row_layout, row)
            layout.addWidget(row_widget)

        root.addWidget(frame)

    def _set_clickable_text(self, label: QLabel, rendered: str) -> None:
        label.setTextFormat(Qt.RichText)
        label.setText(rendered)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._copy_link_target)

    @staticmethod
    def _copy_text_for_link(href: str) -> str | None:
        value = str(href or "")
        if value.startswith("item-copy:"):
            name = unquote(value.removeprefix("item-copy:")).strip()
            return name or None
        if value.startswith("travel-copy:"):
            raw = value.removeprefix("travel-copy:")
            match = re.fullmatch(r"(-?\d+),(-?\d+)", raw)
            if not match:
                return None
            return f"/travel {int(match.group(1))},{int(match.group(2))}"
        return None

    def _copy_link_target(self, href: str) -> None:
        value = self._copy_text_for_link(href)
        if not value:
            return
        QApplication.clipboard().setText(value)
        QToolTip.showText(QCursor.pos(), "Copié", self)
        QTimer.singleShot(800, QToolTip.hideText)

    def _contract_row(self) -> dict[str, Any]:
        contract = getattr(self.service, "auto_validation_contract", None)
        if not isinstance(contract, dict):
            return {}
        contract_id = id(contract)
        cached = getattr(self.service, "_manual_contract_row_index_cache", None)
        if not (
            isinstance(cached, tuple)
            and len(cached) == 2
            and cached[0] == contract_id
            and isinstance(cached[1], dict)
        ):
            index: dict[str, dict[str, Any]] = {}
            for row in contract.get("cards", []) or []:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("card_key") or "").strip()
                if key and key not in index:
                    index[key] = row
            cached = (contract_id, index)
            self.service._manual_contract_row_index_cache = cached
        card_key = self.service.card_key(self.card, self.index)
        return cached[1].get(str(card_key or "").strip(), {})

    def _page_toggled(self, checked: bool) -> None:
        self.service.set_page_checked(self.character_key, self.card, self.index, bool(checked))
        parent = self.parentWidget()
        while parent is not None:
            handler = getattr(parent, "_manual_page_changed", None)
            if callable(handler):
                handler()
                return
            parent = parent.parentWidget()

    @staticmethod
    def _line_object_name(kind: str, text: str) -> str:
        if str(kind or "") == "warning":
            return "GuideManualWarning"
        value = str(text or "").casefold()
        if any(token in value for token in ("donjon", "boss", "combat", "vaincre", "battre")):
            return "GuideManualCombat"
        if any(token in value for token in ("quête spéciale", "quete speciale", "choisir le dialogue", "choisis le dialogue")):
            return "GuideManualSpecial"
        return "GuideManualLine"

    @staticmethod
    def _npc_names(text: str) -> list[str]:
        value = str(text or "")
        found: list[str] = []
        seen: set[str] = set()
        for pattern in _NPC_PATTERNS:
            for match in pattern.finditer(value):
                raw = " ".join(str(match.group(1) or "").split()).strip(" ,.;:!")
                tokens = raw.split()
                kept: list[str] = []
                for token in tokens:
                    clean = token.strip(" ,.;:!")
                    lowered = clean.casefold()
                    if lowered in _NPC_CONNECTORS:
                        if kept:
                            kept.append(clean)
                        continue
                    if clean and clean[0].isupper():
                        kept.append(clean)
                        continue
                    break
                while kept and kept[-1].casefold() in _NPC_CONNECTORS:
                    kept.pop()
                name = " ".join(kept).strip()
                key = name.casefold()
                if name and key not in seen:
                    seen.add(key)
                    found.append(name)
        return sorted(found, key=len, reverse=True)

    @classmethod
    def _format_line_html(
        cls,
        prefix: str,
        position: str,
        text: str,
        npc_names: list[str],
        resource_names: list[str],
    ) -> str:
        prefix_text = str(prefix or "")
        plain = prefix_text + (f"{position} — " if position else "") + str(text or "")
        spans: list[tuple[int, int, str, str]] = []

        def add_span(start: int, end: int, kind: str, payload: str = "") -> None:
            if start >= end:
                return
            if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end, _, _ in spans):
                return
            spans.append((start, end, kind, payload))

        for match in _COORD_RE.finditer(plain):
            add_span(
                match.start(),
                match.end(),
                "position",
                f"{int(match.group(1))},{int(match.group(2))}",
            )

        for name in sorted({value for value in npc_names if value}, key=len, reverse=True):
            pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
            for match in pattern.finditer(plain):
                add_span(match.start(), match.end(), "npc")

        for name in sorted({value for value in resource_names if value}, key=len, reverse=True):
            pattern = cls._resource_regex(name)
            for match in pattern.finditer(plain):
                add_span(match.start(), match.end(), "resource", name)

        if not spans:
            return html.escape(plain)

        spans.sort(key=lambda row: row[0])
        rendered: list[str] = []
        cursor = 0
        for start, end, kind, payload in spans:
            if start < cursor:
                continue
            rendered.append(html.escape(plain[cursor:start]))
            value = html.escape(plain[start:end])
            if kind == "npc":
                rendered.append(f'<span style="color:{NPC_COLOR};"><b>{value}</b></span>')
            elif kind == "resource":
                href = html.escape(f"item-copy:{quote(payload, safe='')}", quote=True)
                rendered.append(
                    f'<a href="{href}" style="color:{RESOURCE_COLOR};text-decoration:none;"><b>{value}</b></a>'
                )
            else:
                href = html.escape(f"travel-copy:{payload}", quote=True)
                rendered.append(
                    f'<a href="{href}" style="color:{POSITION_COLOR};text-decoration:none;"><b>{value}</b></a>'
                )
            cursor = end
        rendered.append(html.escape(plain[cursor:]))
        return "".join(rendered)

    @staticmethod
    def _resource_regex(name: str) -> re.Pattern[str]:
        parts = re.split(r"(\s+|['’])", str(name or "").strip())
        pattern_parts: list[str] = []
        for part in parts:
            if not part:
                continue
            if part.isspace():
                pattern_parts.append(r"\s+")
                continue
            if part in {"'", "’"}:
                pattern_parts.append(r"['’]")
                continue
            escaped = re.escape(part)
            normalized = part.casefold().strip(".,;:!?")
            if normalized not in _RESOURCE_STOP_WORDS and len(part) > 2 and not normalized.endswith(("s", "x", "z")):
                escaped += "s?"
            pattern_parts.append(escaped)
        return re.compile(rf"(?<!\w){''.join(pattern_parts)}(?!\w)", re.IGNORECASE)


class GuideUltimeManualView(GuideUltimeUniversalView):
    """Manual Guide Ultime with one focused navigation control."""

    def _build_ui(self) -> None:
        self.filter_mode = "Tout"
        self.navigate_entity = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        progress = QFrame()
        progress.setObjectName("GuideManualProgressFrame")
        progress_layout = QHBoxLayout(progress)
        progress_layout.setContentsMargins(8, 3, 8, 3)
        progress_layout.setSpacing(8)
        self.route_bar = GuideManualProgressBar()
        self.route_bar.setObjectName("GuideManualProgress")
        self.route_bar.setTextVisible(False)
        self.route_bar.setFixedHeight(7)
        self.route_bar.setCursor(Qt.PointingHandCursor)
        self.route_bar.setToolTip("Cliquer dans la barre pour naviguer directement dans le Guide GPS.")
        self.route_bar.navigationRequested.connect(self._jump_from_progress)
        progress_layout.addWidget(self.route_bar, 1)
        self.route_progress_label = QLabel()
        self.route_progress_label.setObjectName("GuideManualPercent")
        progress_layout.addWidget(self.route_progress_label)
        self.route_lock_check = QCheckBox("Verrouiller")
        self.route_lock_check.setObjectName("GuideManualProgressLock")
        self.route_lock_check.setToolTip(
            "Empêcher les sauts accidentels par clic dans la barre de progression."
        )
        self.route_lock_check.toggled.connect(self._route_lock_toggled)
        progress_layout.addWidget(self.route_lock_check)
        root.addWidget(progress)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("GuideManualScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(8, 2, 8, 8)
        self.cards_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

        nav = QFrame()
        nav.setObjectName("GuideManualNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 4, 8, 6)
        self.prev_button = QPushButton("← Précédent")
        self.prev_button.setObjectName("GuideManualPrev")
        self.prev_button.clicked.connect(lambda: self.navigate_relative(-1))
        nav_layout.addWidget(self.prev_button)
        self.nav_page_label = QLabel()
        self.nav_page_label.setObjectName("GuideManualNavPage")
        nav_layout.addWidget(self.nav_page_label)
        nav_layout.addStretch(1)
        self.validation_host = QFrame()
        self.validation_host.setObjectName("GuideManualValidationHost")
        self.validation_layout = QHBoxLayout(self.validation_host)
        self.validation_layout.setContentsMargins(0, 0, 0, 0)
        self.validation_layout.setSpacing(0)
        nav_layout.addWidget(self.validation_host)
        nav_layout.addStretch(1)
        self.guide_button = AtlasButton("Guide")
        self.guide_button.setObjectName("GuideManualGuideButton")
        self.guide_button.clicked.connect(lambda _checked=False: self._guide_button_clicked())
        nav_layout.addWidget(self.guide_button)
        self.next_button = QPushButton("Suivant →")
        self.next_button.setObjectName("GuideManualNextButton")
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        root.addWidget(nav)

        self.progress_details = QLabel()
        self.progress_details.setVisible(False)
        self.position_label = QLabel()
        self.position_label.setVisible(False)

    def _sync_order_combo(self) -> None:
        return

    def _route_lock_toggled(self, locked: bool) -> None:
        self.route_bar.setCursor(Qt.ArrowCursor if locked else Qt.PointingHandCursor)
        self.route_bar.setToolTip(
            "Barre verrouillée : décochez Verrouiller pour naviguer par clic."
            if locked
            else "Cliquer dans la barre pour naviguer directement dans le Guide GPS."
        )

    def _refresh_header(self) -> None:
        completed, total = self.service.route_sheet_progress(self.character_key)
        if total <= 0:
            self.route_bar.setRange(0, 0)
            self.route_progress_label.setText("")
            self.nav_page_label.setText("")
            return
        self.route_bar.setRange(0, total)
        self.route_bar.setValue(min(completed, total))
        percent = min(100, round(completed * 100 / total))
        page = max(1, min(total, int(self.view_index) + 1))
        self.nav_page_label.setText(f"Page {page} / {total}")
        self.route_progress_label.setText(f"{percent} %")

    def _show_index(self, index: int) -> None:
        if not self.service.cards:
            return
        self.view_index = max(0, min(len(self.service.cards) - 1, int(index)))
        self._refresh_header()
        self._render_window(reset_scroll=True)

    def _jump_from_progress(self, ratio: float) -> None:
        if self.route_lock_check.isChecked():
            return
        total = len(self.service.cards)
        if total <= 0:
            return
        index = int(round(max(0.0, min(1.0, float(ratio))) * max(0, total - 1)))
        self._show_index(index)

    def navigate_relative(self, delta: int) -> None:
        if not self.service.cards:
            return
        self._show_index(self.view_index + int(delta))

    def go_active(self) -> None:
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._show_index(self.active_index)

    def _guide_button_clicked(self) -> None:
        if self.view_index != self.active_index:
            self.go_active()
            return
        self._return_to_guides_catalog()

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        self._clear_cards()
        if not self.service.cards:
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._add_manual_order_choice(card)
        widget = GuideUltimeManualCard(self.service, self.character_key, card, index)
        widget.questRequested.connect(self._open_quest_from_card)
        self._set_validation_widget(widget.page_check)
        self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 1
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self.guide_button.setToolTip(
            "Revenir à la fiche Guide active."
            if index != self.active_index
            else "Retour au choix des Guides."
        )
        if reset_scroll:
            self._reset_scroll_to_top()

    def _open_quest_from_card(self, quest_id: int, stage_id: str, index: int) -> None:
        navigator = self.navigate_entity
        if not callable(navigator):
            return
        navigator(
            "quest",
            int(quest_id),
            source="guide_gps",
            guide_id="guide_complet",
            guide_stage_id=str(stage_id or ""),
            guide_index=int(index),
        )

    def _set_validation_widget(self, checkbox: QCheckBox) -> None:
        while self.validation_layout.count():
            item = self.validation_layout.takeAt(0)
            previous = item.widget()
            if previous is not None:
                previous.setParent(None)
                previous.deleteLater()
        self.validation_layout.addWidget(checkbox)

    def _add_manual_order_choice(self, card: dict[str, Any]) -> None:
        required = getattr(self.service, "manual_order_choice_required", None)
        options_for_card = getattr(self.service, "manual_order_options_for_card", None)
        if not callable(required) or not required(self.character_key, card) or not callable(options_for_card):
            return
        options = tuple(options_for_card(card))
        if not options:
            return

        frame = QFrame()
        frame.setObjectName("GuideManualOrderChoice")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(8)
        title = QLabel("Choisis ton Ordre Bonta")
        title.setObjectName("GuideManualOrderTitle")
        layout.addWidget(title)
        detail = QLabel("Ce choix sera conservé automatiquement aux rangs 40, 60, 80 et 100. Les deux autres branches disparaîtront du parcours.")
        detail.setObjectName("GuideManualOrderDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for option in options:
            button = QPushButton(option)
            button.setObjectName("GuideManualOrderButton")
            button.clicked.connect(lambda _checked=False, value=option: self._select_manual_order(value))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.cards_layout.addWidget(frame)

    def _select_manual_order(self, order_name: str) -> None:
        self.service.set_bonta_order(self.character_key, order_name)
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._show_index(self.active_index)

    def refresh_external_progress(self) -> None:
        self.service.reload_progress()
        if not self.service.available:
            self._render_missing_data()
            return
        self._follow_active_after_progress_change()

    def _follow_active_after_progress_change(self) -> None:
        previous = self.active_index
        self.active_index = self.service.first_incomplete_index(self.character_key)
        moved = self.view_index == previous and self.active_index != previous
        if moved:
            self.view_index = self.active_index
        self._refresh_header()
        self._render_window(reset_scroll=moved)

    def _manual_page_changed(self) -> None:
        self._follow_active_after_progress_change()

    def _manual_objective_changed(self, quest_id: int) -> None:
        self.questProgressChanged.emit(int(quest_id))
        self._follow_active_after_progress_change()

    def _reset_scroll_to_top(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.minimum())
        QTimer.singleShot(
            0,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().minimum()
            ),
        )
