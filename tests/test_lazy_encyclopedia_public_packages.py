from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class LazyEncyclopediaPublicPackagesTests(unittest.TestCase):
    def test_models_package_defers_unrequested_models(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.models import Guide, GuideStep
print(json.dumps({
    "guide": Guide.__name__,
    "step": GuideStep.__name__,
    "achievement": "app.modules.encyclopedia.models.achievement" in sys.modules,
    "reward": "app.modules.encyclopedia.models.reward" in sys.modules,
    "progress": "app.modules.encyclopedia.models.progress_state" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["guide"], "Guide")
        self.assertEqual(payload["step"], "GuideStep")
        self.assertFalse(payload["achievement"])
        self.assertFalse(payload["reward"])
        self.assertFalse(payload["progress"])

    def test_providers_package_defers_achievement_guide_and_dofus_modules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
print(json.dumps({
    "achievement": AchievementProvider.__name__,
    "guide": GuideProvider.__name__,
    "quest": QuestProvider.__name__,
    "achievement_provider": "app.modules.encyclopedia.providers.achievement_provider" in sys.modules,
    "guide_provider": "app.modules.encyclopedia.providers.guide_provider" in sys.modules,
    "dofus_provider": "app.modules.encyclopedia.providers.dofus_item_provider" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["achievement"], "AchievementProvider")
        self.assertEqual(payload["guide"], "GuideProvider")
        self.assertEqual(payload["quest"], "QuestProvider")
        self.assertFalse(payload["achievement_provider"])
        self.assertFalse(payload["guide_provider"])
        self.assertFalse(payload["dofus_provider"])

    def test_lazy_achievement_provider_constructs_real_instance_and_preserves_isinstance(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.providers import AchievementProvider
before = "app.modules.encyclopedia.providers.achievement_provider" in sys.modules
provider = AchievementProvider()
from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider as RealAchievementProvider
print(json.dumps({
    "before": before,
    "real_instance": isinstance(provider, RealAchievementProvider),
    "proxy_instance": isinstance(provider, AchievementProvider),
    "after": "app.modules.encyclopedia.providers.achievement_provider" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["before"])
        self.assertTrue(payload["real_instance"])
        self.assertTrue(payload["proxy_instance"])
        self.assertTrue(payload["after"])

    def test_lazy_guide_provider_constructs_real_instance_and_preserves_isinstance(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.providers import GuideProvider
before = "app.modules.encyclopedia.providers.guide_provider" in sys.modules
provider = GuideProvider()
from app.modules.encyclopedia.providers.guide_provider import GuideProvider as RealGuideProvider
print(json.dumps({
    "before": before,
    "real_instance": isinstance(provider, RealGuideProvider),
    "proxy_instance": isinstance(provider, GuideProvider),
    "after": "app.modules.encyclopedia.providers.guide_provider" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["before"])
        self.assertTrue(payload["real_instance"])
        self.assertTrue(payload["proxy_instance"])
        self.assertTrue(payload["after"])

    def test_lazy_exports_still_resolve_to_original_classes(self) -> None:
        from app.modules.encyclopedia.models import Reward
        from app.modules.encyclopedia.models.reward import Reward as RealReward
        from app.modules.encyclopedia.providers import DofusItemProvider
        from app.modules.encyclopedia.providers.dofus_item_provider import (
            DofusItemProvider as RealDofusItemProvider,
        )

        self.assertIs(Reward, RealReward)
        self.assertIs(DofusItemProvider, RealDofusItemProvider)


if __name__ == "__main__":
    unittest.main()
