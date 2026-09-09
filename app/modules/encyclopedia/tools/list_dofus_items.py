from __future__ import annotations

import sys
from pathlib import Path

from app.modules.encyclopedia.providers import DofusItemProvider, GuideProvider


def main() -> int:
    dofus_provider = DofusItemProvider()
    guide_provider = GuideProvider(dofus_item_provider=dofus_provider)
    guides = guide_provider.load_all()
    guides_by_item: dict[int, list[str]] = {}
    for guide in guides:
        for item_id in (guide.reward_item_id, guide.illustration_item_id):
            if item_id is None:
                continue
            guides_by_item.setdefault(int(item_id), [])
            if guide.id not in guides_by_item[int(item_id)]:
                guides_by_item[int(item_id)].append(guide.id)

    print("ID | Nom | Niveau | Type | Image | Guide")
    for item in dofus_provider.load_all():
        image_status = "OK" if item.image_path and Path(item.image_path).exists() else "Manquante"
        guide_text = ", ".join(guides_by_item.get(item.id, [])) or "Aucun"
        level = item.level if item.level is not None else "?"
        print(f"{item.id} | {item.name} | {level} | {item.type_name} | {image_status} | {guide_text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
