"""Targeted Success deep-link prewarm stays inside the existing stage worker."""
from __future__ import annotations

import importlib
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

page_module = importlib.import_module(
    "app.modules.encyclopedia.views.encyclopedia_page"
)


def page_probe(*, pending_id: int | None):
    sequence = []
    provider = Mock()
    provider.load_runtime.side_effect = lambda: sequence.append("catalog")
    provider.get_detail_by_id.side_effect = lambda detail_id: sequence.append(
        ("detail", detail_id)
    )
    stage_result = Mock()
    receiver = Mock()
    receiver.emit.side_effect = lambda _result: sequence.append("emitted")
    page = SimpleNamespace(
        _achievement_ready=False,
        _achievement_load_started=False,
        _success_runtime_requested=False,
        _pending_achievement_id=pending_id,
        _pending_lazy_tab="",
        _guide_runtime_ready=False,
        _quest_graph=stage_result,
        quest_provider=SimpleNamespace(get_catalog=Mock()),
        service=SimpleNamespace(achievement_provider=provider, guide_provider=None),
        current_character_key="",
        achievement_progress_service=Mock(),
        quest_progress_path=Path("progress.json"),
        achievementRuntimeFinished=receiver,
        status_callback=Mock(),
    )
    return page, provider, receiver, sequence


class SuccessDetailPrewarmTests(unittest.TestCase):
    def _start(self, page, *, open_success: bool):
        # This test executes the captured worker synchronously to check call
        # ordering; it does not claim native Qt-thread responsiveness.
        with (
            patch.object(page_module, "background_io_priority", return_value=nullcontext()),
            patch.object(
                page_module, "_start_runtime_thread",
                side_effect=lambda _page, target, _name: target(),
            ) as launch,
        ):
            page_module.EncyclopediaPage._start_achievement_stage(
                page, open_success=open_success,
            )
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[2], "DofusAtlasAchievementStage")

    def test_deep_link_prewarms_one_detail_before_runtime_signal(self):
        page, provider, receiver, events = page_probe(pending_id=20)
        self._start(page, open_success=True)
        self.assertEqual(events, ["catalog", ("detail", 20), "emitted"])
        provider.get_detail_by_id.assert_called_once_with(20)
        receiver.emit.assert_called_once()
        self.assertTrue(page._achievement_load_started)

    def test_regular_success_tab_does_not_prefetch_unrequested_details(self):
        page, provider, receiver, events = page_probe(pending_id=None)
        self._start(page, open_success=True)
        self.assertEqual(events, ["catalog", "emitted"])
        provider.get_detail_by_id.assert_not_called()
        receiver.emit.assert_called_once()

    def test_background_related_warmup_does_not_prefetch_pending_deep_link(self):
        page, provider, receiver, events = page_probe(pending_id=20)
        self._start(page, open_success=False)
        self.assertEqual(events, ["catalog", "emitted"])
        provider.get_detail_by_id.assert_not_called()

    def test_failed_one_detail_keeps_success_catalogue_stage_available(self):
        page, provider, receiver, events = page_probe(pending_id=20)
        provider.get_detail_by_id.side_effect = RuntimeError("bad detail")
        self._start(page, open_success=True)
        self.assertEqual(events, ["catalog", "emitted"])
        receiver.emit.assert_called_once()
        self.assertFalse(isinstance(receiver.emit.call_args.args[0], Exception))

    def test_inflight_runtime_stage_never_launches_second_worker(self):
        page, provider, receiver, events = page_probe(pending_id=20)
        page._achievement_load_started = True
        with patch.object(page_module, "_start_runtime_thread") as launch:
            page_module.EncyclopediaPage._start_achievement_stage(
                page, open_success=True,
            )
        launch.assert_not_called()
        provider.get_detail_by_id.assert_not_called()
        self.assertEqual(events, [])
        self.assertFalse(receiver.emit.called)


if __name__ == "__main__":
    unittest.main()
