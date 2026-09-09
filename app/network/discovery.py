from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from app.network.protobuf_fields import ProtobufDecodeError, parse_protobuf_fields
from app.network.transport import CapturedProtocolMessage


@dataclass(frozen=True, slots=True)
class ProtocolFieldCandidate:
    type_url: str
    path: tuple[int, ...]
    kind: str
    matching_message_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_url": self.type_url,
            "path": list(self.path),
            "kind": self.kind,
            "matching_message_count": self.matching_message_count,
        }


class ProtocolTargetDiscoveryCollector:
    """Find protobuf field paths matching caller-supplied known values.

    Expected scalar values are used only in memory and are never returned by
    ``snapshot``. The collector retains only type URL, field path, scalar kind
    and aggregate counts. A candidate is evidence for reverse engineering, not
    authorization to mutate progression; production still requires a reviewed
    exact-build mapping manifest.

    Only field paths that contain exactly one value at every traversed level are
    considered. This mirrors the strict runtime resolver and avoids proposing a
    path that production decoding would later reject as ambiguous.
    """

    def __init__(
        self,
        *,
        expected_positive_ints: Iterable[int] = (),
        expected_strings: Iterable[str] = (),
        max_depth: int = 4,
        max_candidates: int = 4096,
        max_nested_payload_bytes: int = 1024 * 1024,
    ) -> None:
        self._expected_positive_ints = frozenset(
            int(value)
            for value in expected_positive_ints
            if _positive_int(value) is not None
        )
        self._expected_strings = frozenset(
            text
            for value in expected_strings
            if (text := str(value or "").strip())
        )
        self.max_depth = max(1, min(8, int(max_depth)))
        self.max_candidates = max(32, int(max_candidates))
        self.max_nested_payload_bytes = max(1024, int(max_nested_payload_bytes))
        self._lock = threading.RLock()
        self._counts: Counter[tuple[str, tuple[int, ...], str]] = Counter()
        self._observed_message_count = 0
        self._malformed_message_count = 0
        self._dropped_candidate_count = 0

    @property
    def observed_message_count(self) -> int:
        with self._lock:
            return self._observed_message_count

    @property
    def malformed_message_count(self) -> int:
        with self._lock:
            return self._malformed_message_count

    @property
    def dropped_candidate_count(self) -> int:
        with self._lock:
            return self._dropped_candidate_count

    def observe(self, message: CapturedProtocolMessage) -> None:
        if not isinstance(message, CapturedProtocolMessage):
            return
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return
        type_url = str(message.type_url or "").strip()
        if not type_url:
            return

        try:
            matches = _find_matching_paths(
                message.payload,
                expected_positive_ints=self._expected_positive_ints,
                expected_strings=self._expected_strings,
                max_depth=self.max_depth,
                max_nested_payload_bytes=self.max_nested_payload_bytes,
            )
        except ProtobufDecodeError:
            with self._lock:
                self._observed_message_count += 1
                self._malformed_message_count += 1
            return

        with self._lock:
            self._observed_message_count += 1
            for path, kind in matches:
                key = (type_url, path, kind)
                if key not in self._counts and len(self._counts) >= self.max_candidates:
                    self._dropped_candidate_count += 1
                    continue
                self._counts[key] += 1

    def snapshot(self) -> tuple[ProtocolFieldCandidate, ...]:
        with self._lock:
            rows = [
                ProtocolFieldCandidate(
                    type_url=type_url,
                    path=path,
                    kind=kind,
                    matching_message_count=count,
                )
                for (type_url, path, kind), count in self._counts.items()
            ]
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    -row.matching_message_count,
                    row.type_url,
                    row.kind,
                    row.path,
                ),
            )
        )

    def clear(self) -> None:
        with self._lock:
            self._counts.clear()
            self._observed_message_count = 0
            self._malformed_message_count = 0
            self._dropped_candidate_count = 0


def _find_matching_paths(
    payload: bytes,
    *,
    expected_positive_ints: frozenset[int],
    expected_strings: frozenset[str],
    max_depth: int,
    max_nested_payload_bytes: int,
) -> tuple[tuple[tuple[int, ...], str], ...]:
    output: set[tuple[tuple[int, ...], str]] = set()
    _walk_payload(
        bytes(payload),
        prefix=(),
        depth=1,
        output=output,
        expected_positive_ints=expected_positive_ints,
        expected_strings=expected_strings,
        max_depth=max_depth,
        max_nested_payload_bytes=max_nested_payload_bytes,
        root=True,
    )
    return tuple(sorted(output, key=lambda row: (row[1], row[0])))


def _walk_payload(
    payload: bytes,
    *,
    prefix: tuple[int, ...],
    depth: int,
    output: set[tuple[tuple[int, ...], str]],
    expected_positive_ints: frozenset[int],
    expected_strings: frozenset[str],
    max_depth: int,
    max_nested_payload_bytes: int,
    root: bool,
) -> None:
    try:
        fields = parse_protobuf_fields(payload)
    except ProtobufDecodeError:
        if root:
            raise
        return

    for field_number in sorted(fields):
        values = fields[field_number]
        if len(values) != 1:
            continue
        value = values[0]
        path = (*prefix, int(field_number))

        if isinstance(value, int):
            if value > 0 and value in expected_positive_ints:
                output.add((path, "positive_int"))
            continue

        if not isinstance(value, bytes):
            continue

        if expected_strings:
            try:
                decoded = value.decode("utf-8", errors="strict").strip()
            except UnicodeDecodeError:
                decoded = ""
            if decoded and decoded in expected_strings:
                output.add((path, "string"))

        if depth >= max_depth or not value or len(value) > max_nested_payload_bytes:
            continue
        _walk_payload(
            value,
            prefix=path,
            depth=depth + 1,
            output=output,
            expected_positive_ints=expected_positive_ints,
            expected_strings=expected_strings,
            max_depth=max_depth,
            max_nested_payload_bytes=max_nested_payload_bytes,
            root=False,
        )


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


__all__ = ["ProtocolFieldCandidate", "ProtocolTargetDiscoveryCollector"]
