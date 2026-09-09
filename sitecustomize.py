from __future__ import annotations

import os
from time import perf_counter


_TRUTHY = {"1", "true", "yes", "on"}
_PROFILE_ENV = "DOFUS_ATLAS_STARTUP_PROFILE"
_BASELINE_ENV = "DOFUS_ATLAS_PYTHON_STARTED_PERF"


if os.environ.get(_PROFILE_ENV, "").strip().casefold() in _TRUTHY:
    os.environ.setdefault(_BASELINE_ENV, repr(perf_counter()))
