from __future__ import annotations

import time
from typing import Callable


def wait_ms(duration_ms: int, should_stop: Callable[[], bool] | None = None) -> bool:
    deadline = time.monotonic() + max(0, int(duration_ms)) / 1000.0
    while time.monotonic() < deadline:
        if should_stop is not None and should_stop():
            return True
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    return bool(should_stop is not None and should_stop())
