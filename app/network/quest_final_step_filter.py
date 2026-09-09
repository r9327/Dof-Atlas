from __future__ import annotations

from typing import Any

from app.network.normalizer import DecodedClientMessage
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder
from app.quest_catalog import QuestCatalog


class FinalQuestStepEvidenceDecoder:
    """Fail closed unless reviewed step evidence is the quest's final step.

    The current Dofus profile maps ``idz`` to ``quest_completed`` evidence with
    both ``quest_id`` and ``validated_step_id``. Real captures establish idz as
    a server-side step validation, not a one-shot quest completion. Atlas can
    therefore promote it only when the validated step is exactly the last step
    in the local ordered quest definition.

    Direct reviewed completion events without ``validated_step_id`` are passed
    through unchanged for protocol-agnostic compatibility. The current profile
    never uses that path.
    """

    def __init__(self, inner: ProtocolMessageDecoder, quest_catalog: QuestCatalog) -> None:
        self.inner = inner
        self.quest_catalog = quest_catalog

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        decoded = self.inner.decode(message)
        if decoded is None or str(decoded.event_type or "").strip().casefold() != "quest_completed":
            return decoded
        fields = decoded.fields
        if "validated_step_id" not in fields:
            return decoded

        quest_id = _positive_int(fields.get("quest_id"))
        step_id = _positive_int(fields.get("validated_step_id"))
        if quest_id is None or step_id is None:
            return None
        quest = self.quest_catalog.by_id.get(quest_id)
        if quest is None or not quest.steps:
            return None
        final_step_id = _positive_int(getattr(quest.steps[-1], "id", None))
        if final_step_id is None or step_id != final_step_id:
            return None
        return decoded

    def session_closed(self, session_id: str) -> None:
        hook = getattr(self.inner, "session_closed", None)
        if callable(hook):
            hook(session_id)

    def reset(self) -> None:
        hook = getattr(self.inner, "reset", None)
        if callable(hook):
            hook()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


__all__ = ["FinalQuestStepEvidenceDecoder"]
