from __future__ import annotations

# Network runtime is intentionally disabled until the stack is repaired and
# explicitly re-certified. Keep the implementation in the repository for audit
# and repair work, but do not start capture, calibration, workers or polling.
NETWORK_RUNTIME_ENABLED = False
NETWORK_RUNTIME_DISABLED_REASON = "disabled_until_network_repair"


__all__ = [
    "NETWORK_RUNTIME_ENABLED",
    "NETWORK_RUNTIME_DISABLED_REASON",
]
