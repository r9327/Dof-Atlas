"""Qt-free presentation of verified capture states."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.network.application_coordinator import NetworkApplicationStatus


def network_summary(status: NetworkApplicationStatus) -> tuple[str, str]:
    reason = str(status.reason or "")
    # A worker can still be running when stopping or capture fails.
    # Never paint a green "Actif" badge over an explicit error.
    if (
        reason in {
            "capture_elevation_cancelled",
            "build_changed",
            "quest_snapshot_missed",
            "mapping_invalid",
            "network_context_load_failed",
        }
        or reason.startswith("capture_helper")
        or "admin" in reason
        or "permission" in reason
        or "failed" in reason
        or "error" in reason
        or "ambiguous" in reason
    ):
        return "Attention requise", "error"
    if reason in {"waiting_context", "stopped", "runtime_stopped"}:
        # No verified capture is active. Never describe a disconnected
        # network bridge as merely "preparing" indefinitely.
        return "Hors ligne", "idle"
    if reason in {"no_window_handles", "build_fingerprint_unavailable"}:
        return "En attente de Dofus", "idle"
    if reason == "network_context_loading":
        return "Chargement Réseau…", "pending"
    if reason == "capture_ready_waiting_context":
        return "En attente de données", "pending"
    if status.calibrating or reason in {
        "calibrating",
        "calibration_running",
        "awaiting_character_identity",
        "awaiting_quest_journal",
        "awaiting_distinct_quest_completions",
        "mapping_installed_not_started",
        "mapping_already_installed",
        "mapping_already_ready",
        "mapping_no_exact_match",
        "mapping_missing_required_events",
        "mapping_current_profile_noncanonical",
    }:
        return "Connexion…", "pending"
    if status.running:
        return "Actif", "active"
    return "Préparation…", "pending"


def capture_retry_allowed(reason: object) -> bool:
    """An unconfirmed shutdown must not be followed by another capture."""
    return not any(marker in str(reason or "") for marker in ("stop_failed", "cleanup_failed"))
