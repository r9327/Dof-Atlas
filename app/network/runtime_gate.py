from __future__ import annotations

# TEMPORARILY DISABLED.
#
# The network stack is kept in the repository for repair/audit work, but no
# product runtime may start capture, calibration, protocol workers or polling
# until the network feature has been repaired and explicitly re-certified.
# Keep Atlas Doctor observations visible while this gate is disabled: this is a
# runtime safety switch, not a suppression/allowlist mechanism.
NETWORK_RUNTIME_ENABLED = False
NETWORK_RUNTIME_DISABLED_REASON = "disabled_until_network_repair"


__all__ = [
    "NETWORK_RUNTIME_ENABLED",
    "NETWORK_RUNTIME_DISABLED_REASON",
]
