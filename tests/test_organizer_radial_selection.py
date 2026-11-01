from __future__ import annotations

import math

import pytest

from app.pages.organizer.radial_selection import (
    selected_slice,
    slice_count,
    visible_characters,
)


@pytest.mark.parametrize("count", [2, 3, 4, 6, 8])
def test_radial_slices_match_exact_number_of_included_characters(count: int) -> None:
    sessions = [{"nom": f"Perso {i}", "hwnd": i} for i in range(1, 9)]
    chosen = set(range(1, count + 1))
    result = visible_characters(sessions, chosen)
    assert len(result) == count
    assert slice_count(result) == count
    assert [row["hwnd"] for row in result] == list(range(1, count + 1))


def test_untracked_windows_never_create_empty_or_extra_slices() -> None:
    sessions = [
        {"nom": "Alpha", "hwnd": 11},
        {"nom": "Beta", "hwnd": 22},
        {"nom": "", "hwnd": 33},
        {"nom": "Gamma", "hwnd": 44, "_empty_slot": True},
        {"nom": "Alpha copie", "hwnd": 11},
        {"nom": "Disabled", "hwnd": 55, "enabled": False},
    ]
    assert [row["hwnd"] for row in visible_characters(sessions, {11, 22, 33, 44, 55, 999})] == [11, 22]
    assert visible_characters(sessions, set()) == []


@pytest.mark.parametrize("count", [2, 3, 4, 6, 8])
def test_mouse_vector_selects_all_sectors_from_top_clockwise(count: int) -> None:
    for index in range(count):
        theta = index * math.tau / count
        dx, dy = 100 * math.sin(theta), -100 * math.cos(theta)
        assert selected_slice(dx, dy, count) == index


def test_releasing_at_center_or_without_any_character_cancels() -> None:
    assert selected_slice(0, 0, 8) is None
    assert selected_slice(15, 15, 4) is None
    assert selected_slice(100, 0, 0) is None


def test_direction_changes_target_without_changing_character_order() -> None:
    ordered = visible_characters(
        [{"nom": "Beta", "hwnd": 2}, {"nom": "Alpha", "hwnd": 1}],
        {1, 2},
    )
    assert [row["nom"] for row in ordered] == ["Beta", "Alpha"]
    assert ordered[selected_slice(0, -100, 2)]["nom"] == "Beta"
    assert ordered[selected_slice(0, 100, 2)]["nom"] == "Alpha"
