from __future__ import annotations

from types import SimpleNamespace

from app.modules.encyclopedia.views.guides_view import GUIDE_ULTIME_LEGACY_ID, GuidesView


class _ReloadProbe:
    def __init__(self) -> None:
        self.reload_count = 0
        self.progress = {"version": 1}

    def reload(self):
        self.reload_count += 1
        return self.progress


class _ViewProbe:
    def __init__(self) -> None:
        self.refresh_external_count = 0

    def refresh_external_progress(self) -> None:
        self.refresh_external_count += 1


def test_unchanged_guides_external_progress_returns_before_any_work() -> None:
    calls: list[str] = []
    fake = SimpleNamespace(
        _external_progress_changed=lambda: False,
        current_guide_id=GUIDE_ULTIME_LEGACY_ID,
        quest_progress_service=_ReloadProbe(),
        guide_progress_service=_ReloadProbe(),
        guide_ultime_view=_ViewProbe(),
        _sync_achievement_progress=lambda: calls.append("sync"),
        _refresh_guide_ultime_home_labels=lambda: calls.append("home"),
        _mark_external_progress_refreshed=lambda: calls.append("mark"),
    )

    GuidesView.refresh_external_progress(fake)

    assert fake.quest_progress_service.reload_count == 0
    assert fake.guide_progress_service.reload_count == 0
    assert fake.guide_ultime_view.refresh_external_count == 0
    assert calls == []


def test_changed_guide_ultime_progress_refreshes_once_and_marks_signature() -> None:
    calls: list[str] = []
    quest_progress = _ReloadProbe()
    guide_progress = _ReloadProbe()
    view = _ViewProbe()
    fake = SimpleNamespace(
        _external_progress_changed=lambda: True,
        current_guide_id=GUIDE_ULTIME_LEGACY_ID,
        quest_progress_service=quest_progress,
        guide_progress_service=guide_progress,
        guide_ultime_view=view,
        _sync_achievement_progress=lambda: calls.append("sync"),
        _refresh_guide_ultime_home_labels=lambda: calls.append("home"),
        _mark_external_progress_refreshed=lambda: calls.append("mark"),
    )

    GuidesView.refresh_external_progress(fake)

    assert fake.quest_progress == quest_progress.progress
    assert quest_progress.reload_count == 1
    assert guide_progress.reload_count == 1
    assert view.refresh_external_count == 1
    assert calls == ["sync", "home", "mark"]


def test_external_signature_compares_all_progress_sources_and_character() -> None:
    signature = ("slot:2", (1, 2, 3), (4, 5, 6), (7, 8, 9))
    fake = SimpleNamespace(
        _external_progress_signature=signature,
        _current_external_progress_signature=lambda: signature,
    )
    assert GuidesView._external_progress_changed(fake) is False

    fake._current_external_progress_signature = lambda: (
        "slot:2",
        (1, 2, 3),
        (4, 5, 6),
        (7, 8, 10),
    )
    assert GuidesView._external_progress_changed(fake) is True
