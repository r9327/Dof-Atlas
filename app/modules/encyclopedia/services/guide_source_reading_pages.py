"""Continuous original-source Guide reading with viewport-sized pages.

A reading page is ONLY presentation. The untouched source cards keep their
original IDs, complete authored blocks, prerequisites, and progress contract.
No generated step headings, guessed Quest order, or sentence splitting.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

SOURCE_PAGE_TARGET_LINES = 18


def _remaining_runs(runs: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """Strip an explicitly indexed prerequisite prefix without altering runs."""
    size = len(prefix)
    remaining = []
    for run in runs:
        if size >= len(run["text"]):
            size -= len(run["text"])
            continue
        item = dict(run)
        item["text"] = item["text"][size:]
        size = 0
        remaining.append(item)
    if size or not remaining:
        raise ValueError("Invalid source prerequisite prefix")
    return remaining


def authored_reading_blocks(cards: Any) -> tuple[dict[str, Any], ...]:
    """All visible source blocks, once each, in original author order."""
    result: list[dict[str, Any]] = []
    for source_index, card in enumerate(cards):
        original = (card.get("manual_runtime_metadata") or {}).get("source_step")
        if not isinstance(original, dict):
            raise ValueError(f"Source fiche {source_index + 1} has no original step")
        actions = original.get("actions")
        if not isinstance(actions, list) or len(actions) != 1:
            raise ValueError("One authored fiche must retain exactly one source action")
        rich = actions[0].get("rich_blocks")
        if not isinstance(rich, list):
            raise ValueError("Missing original source rich blocks")
        excluded = set(card.get("manual_prerequisite_block_indexes", ()))
        excluded.update(card.get("manual_preparation_block_indexes", ()))
        inline = {
            entry["block_index"]: entry["prefix"]
            for entry in card.get("manual_prerequisite_inline_leads", ())
        }
        for block_index, block in enumerate(rich):
            if block_index in excluded:
                continue
            current = copy.deepcopy(block)
            if block_index in inline:
                if current["type"] != "paragraph":
                    raise ValueError("Prerequisite prefix is not original prose")
                current["runs"] = _remaining_runs(
                    current["runs"], inline[block_index]
                )
            if current["type"] == "checklist":
                # Editorial checkboxes are NOT progress controls. One item is
                # a paginatable full sentence; keep source order and original
                # text/links/checked metadata, never draw selection squares.
                for item in current["items"]:
                    result.append({
                        "source_index": source_index,
                        "source_block_index": block_index,
                        "block": {"type": "checklist_item", "item": item},
                    })
            else:
                result.append({
                    "source_index": source_index,
                    "source_block_index": block_index,
                    "block": current,
                })
    return tuple(result)


def review_candidate_reading_blocks(cards: Any) -> tuple[dict[str, Any], ...]:
    """Read-only Cawotte pilot pages using its existing source action labels.

    Prerequisites/materials remain in their own tabs. No candidate action
    gains gameplay authority; original source IDs and 64 cards remain intact.
    """
    result: list[dict[str, Any]] = []
    for source_index, card in enumerate(cards):
        if card.get("manual_review_only") is not True or not card.get("source_step_id"):
            raise ValueError("Preview pagination requires typed review-only source IDs")
        sections = card.get("manual_sections") or {}
        rows = sections.get("now", ()) if isinstance(sections, dict) else ()
        if not isinstance(rows, (tuple, list)):
            raise ValueError("Invalid authored preview actions")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid authored preview action")
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            position = str(row.get("position") or "").strip()
            runs: list[dict[str, Any]] = []
            match = re.fullmatch(r"\[(-?\d{1,5}),\s*(-?\d{1,5})\]", position)
            if match:
                target = f"{match.group(1)},{match.group(2)}"
                runs.append({
                    "text": position, "role": "position",
                    "href": "travel-copy:" + target,
                })
                runs.append({"text": " · ", "role": "plain"})
            runs.append({"text": text, "role": "plain"})
            result.append({
                "source_index": source_index,
                "source_step_id": str(card["source_step_id"]),
                "block": {"type": "paragraph", "runs": runs},
            })
    return tuple(result)


def _visual_line_cost(block: dict[str, Any], chars_per_line: int) -> int:
    kind = block["type"]
    if kind == "image":
        return 7  # Shared thumbnail <=160px at ~20px per line.
    if kind == "checklist_item":
        text = block["item"]["text"]
    else:
        text = "".join(run["text"] for run in block["runs"])
    # Author-owned hard returns remain intact; Qt handles actual wrapping.
    return max(1, sum(
        max(1, math.ceil(len(line) / max(24, chars_per_line)))
        for line in text.split("\n")
    ))


def paginate_authored_blocks(
    blocks: tuple[dict[str, Any], ...],
    *,
    chars_per_line: int,
    target_lines: int = SOURCE_PAGE_TARGET_LINES,
) -> tuple[tuple[dict[str, Any], ...], ...]:
    """Balance whole authored blocks near 18 lines; never leave a 1-line tail.

    Up to two extra visual lines per page let an otherwise orphaned final
    block fit earlier. One long authored paragraph may exceed this budget:
    it scrolls intact rather than being cut between pages.
    """
    if not isinstance(chars_per_line, int) or chars_per_line < 24:
        raise ValueError("Viewport must provide an estimated reading width")
    if not 8 <= target_lines <= 32:
        raise ValueError("Invalid reading line budget")
    if not blocks:
        return ()
    max_lines = target_lines + 2
    # A large paragraph owns one scrollable page; it must not create a
    # fictitious backlog of empty pages when estimating page count.
    costs = [
        min(max_lines, _visual_line_cost(entry["block"], chars_per_line))
        for entry in blocks
    ]
    remaining_cost = sum(costs)
    remaining_pages = min(len(blocks), max(1, math.ceil(remaining_cost / max_lines)))
    pages: list[tuple[dict[str, Any], ...]] = []
    current: list[dict[str, Any]] = []
    current_cost = 0
    for index, (entry, cost) in enumerate(zip(blocks, costs)):
        # Recalculate the ideal average after EVERY finished page. A fixed
        # per-page budget would leave one lonely action on the final page.
        if current and remaining_pages > 1:
            ideal = remaining_cost / remaining_pages
            entries_after = len(blocks) - index
            may_close = entries_after >= remaining_pages - 1
            if may_close and (
                current_cost >= ideal
                or abs(current_cost - ideal) <= abs(current_cost + cost - ideal)
            ):
                pages.append(tuple(current))
                remaining_cost -= current_cost
                remaining_pages -= 1
                current = []
                current_cost = 0
        current.append(entry)
        current_cost += cost
    if current:
        pages.append(tuple(current))
    return tuple(pages)

def source_page_for_index(
    pages: tuple[tuple[dict[str, Any], ...], ...], source_index: int
) -> int:
    """Find an original step's page without losing stable source IDs."""
    for page_number, page in enumerate(pages):
        if any(entry["source_index"] == source_index for entry in page):
            return page_number
    # A source fiche may consist exclusively of dedicated prerequisites.
    # Its identity maps to the first following page (or the final page).
    for page_number, page in enumerate(pages):
        if page[0]["source_index"] > source_index:
            return page_number
    return max(0, len(pages) - 1)
