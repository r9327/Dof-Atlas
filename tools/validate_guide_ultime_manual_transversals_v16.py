from __future__ import annotations

"""Compatibility alias for the canonical Guide transversal validator.

New callers must use ``tools.validate_guide_ultime_manual_transversals``. This
module remains temporarily import-safe for repository guardrails that still
reference the historical v16 entry point; it contains no independent policy.
"""

from tools.validate_guide_ultime_manual_transversals import *  # noqa: F401,F403
from tools.validate_guide_ultime_manual_transversals import main


if __name__ == "__main__":
    raise SystemExit(main())
