from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.providers.dofus_item_provider import (
    _EFFECT_CANDIDATE_ROW,
    _selected_effect_instances,
    _read_guide_items_index,
)


class CompactGuideItemEffectTests(unittest.TestCase):
    def test_compact_effects_keep_requested_values_and_last_duplicate(self) -> None:
        packed = bytearray()
        for row in (
            (41, 5, 8, 6, -17),
            (99, 6, 40, 0, 23),
            (41, 7, 0, -3, 0),
            (78, 8, 6, 2, 30),
        ):
            packed.extend(_EFFECT_CANDIDATE_ROW.pack(*row))
        self.assertEqual(
            _selected_effect_instances(packed, {41, 78, 12345}),
            {
                41: {"effectId": 7, "diceNum": 0, "diceSide": -3, "value": 0},
                78: {"effectId": 8, "diceNum": 6, "diceSide": 2, "value": 30},
            },
        )
        self.assertEqual(_selected_effect_instances(packed, set()), {})
        self.assertEqual(_selected_effect_instances(bytearray(), {41}), {})

    def test_spooled_effects_keep_last_rid_across_batches_with_bounded_ram(self):
        from app.modules.encyclopedia.providers.dofus_item_provider import (
            _selected_effect_instances,
        )

        # 4,097 rows cross the 4,096-row decoder boundary. Force a spill to
        # disk and ensure that the final occurrence wins as with bytearray.
        with tempfile.SpooledTemporaryFile(max_size=1024, mode="w+b") as stream:
            for position in range(4097):
                stream.write(_EFFECT_CANDIDATE_ROW.pack(
                    42 if position in (0, 4096) else position + 100,
                    position, 0, -1, position,
                ))
            self.assertEqual(
                _selected_effect_instances(stream, {42, 105}),
                {
                    42: {"effectId": 4096, "diceNum": 0, "diceSide": -1, "value": 4096},
                    105: {"effectId": 5, "diceNum": 0, "diceSide": -1, "value": 5},
                },
            )
            self.assertEqual(_selected_effect_instances(stream, set()), {})
            self.assertTrue(stream._rolled)

    def test_real_item_worker_uses_spool_and_retains_late_effect_override(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        class EmptyEntries(dict):
            def close(self):
                pass

        def references(path):
            if path.name == "items.json":
                yield {"rid": 77, "data": {"effectId": 300, "value": 2}}
                yield {"rid": 41, "data": {
                    "id": 42001, "typeId": mod.DOFUS_TYPE_ID,
                    "possibleEffects": [{"rid": 77}],
                }}
                yield {"rid": 77, "data": {"effectId": 300, "value": 9}}
            elif path.name == "item_types.json":
                yield {"data": {"id": mod.DOFUS_TYPE_ID}}
            elif path.name == "effects.json":
                yield {"data": {"id": 300}}

        with tempfile.TemporaryDirectory() as directory:
            provider = mod.DofusItemProvider(Path(directory))
            real_spool = tempfile.SpooledTemporaryFile
            with (
                patch.object(mod, "_iter_doduda_refs", side_effect=references),
                patch.object(mod, "SelectedJsonValueMapping",
                             return_value=EmptyEntries()),
                patch.object(provider, "_image_for_icon", return_value=""),
                patch.object(provider, "_effect_label",
                             side_effect=lambda effect, *_: str(effect["value"]) if effect else ""),
                patch.object(mod.tempfile, "SpooledTemporaryFile",
                             wraps=real_spool) as spooled,
            ):
                self.assertEqual(provider._load_in_process(), {})
                self.assertEqual(provider._items[0].effects, ("9",))
                self.assertEqual(spooled.call_count, 1)
                self.assertEqual(spooled.call_args.kwargs["max_size"], 1024 * 1024)

    def test_compact_effects_keep_signed_64bit_source_values(self) -> None:
        packed = _EFFECT_CANDIDATE_ROW.pack(456, 123, -(2**40), 2**40, -1)
        self.assertEqual(
            _selected_effect_instances(packed, {456})[456],
            {
                "effectId": 123,
                "diceNum": -(2**40),
                "diceSide": 2**40,
                "value": -1,
            },
        )


class CompactDofusPayloadTests(unittest.TestCase):
    def test_existing_worker_full_dump_keeps_asdict_serialization(self):
        from app.modules.encyclopedia.models.dofus_item import DofusItem
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        item = DofusItem(
            id=42, original_id=42, name="Dofus", level=200,
            type_id=23, type_name="Dofus", effects=("Bonus",),
        )
        worker = Mock()
        worker._items = [item]
        output = StringIO()
        with (
            patch.object(mod, "DofusItemProvider", return_value=worker),
            redirect_stdout(output),
        ):
            self.assertEqual(mod._dump_compact_default_items(), 0)
        worker._load_in_process.assert_called_once_with()
        self.assertEqual(json.loads(output.getvalue())[0]["id"], 42)
        self.assertEqual(json.loads(output.getvalue())[0]["effects"], ["Bonus"])


    def test_compact_payload_matches_old_json_and_does_not_copy_unused_raw(self):
        from dataclasses import asdict
        from app.modules.encyclopedia.models.dofus_item import DofusItem
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        item = DofusItem(
            id=42, original_id=42, name="Test", level=200,
            type_id=23, type_name="Dofus", effects=("Bonus",),
            raw={"id": 42, "typeId": 23, "level": 200, "unused": {"deep": [1, 2]}},
        )
        expected = asdict(item)
        expected["raw"] = {"id": 42, "typeId": 23, "level": 200}
        result = mod._compact_item_payload(item)
        self.assertEqual(result, expected)
        self.assertEqual(
            json.dumps(result, ensure_ascii=False),
            json.dumps(expected, ensure_ascii=False),
        )
        self.assertEqual(item.raw["unused"], {"deep": [1, 2]})

        class ProhibitDeepCopy:
            def __deepcopy__(self, memo):
                raise AssertionError("Unused raw data must never be copied")

        protected = DofusItem(
            id=7, original_id=7, name="Protected", level=1,
            type_id=1, type_name="Other",
            raw={"id": 7, "unused": ProhibitDeepCopy()},
        )
        self.assertEqual(mod._compact_item_payload(protected)["raw"], {"id": 7})


class CompactGuideItemIndexIntegrityTests(unittest.TestCase):
    def test_items_index_source_replacement_invalidates_same_mtime_cache(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "items.json"
            source.write_text("{}", encoding="utf-8")
            cache = root / "guide_items.json"
            with patch.object(mod, "DATA_DIR", root):
                signature = mod._guide_item_source_signature(root)
                self.assertEqual(len(signature[0]), 5)
                cache.write_text(json.dumps({
                    "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                    "source_signature": signature,
                    "items": {"42": {"id": 42}},
                }), encoding="utf-8")
                self.assertIsNotNone(mod._read_guide_items_index(data_dir=root, path=cache))
                before = source.stat()
                replacement = root / "new.json"
                replacement.write_text("[]", encoding="utf-8")
                os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.assertEqual(replacement.stat().st_size, before.st_size)
                replacement.replace(source)
                self.assertIsNone(mod._read_guide_items_index(data_dir=root, path=cache))

    def test_signature_handles_missing_external_custom_sources(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(mod, "DATA_DIR", root):
                rows = mod._guide_item_source_signature(root)
                self.assertEqual(len(rows), 4)
                self.assertEqual([row[1:] for row in rows], [[-1, -1, -1, -1]] * 4)
                self.assertTrue(all(root.as_posix() in row[0] for row in rows))
                (root / "items.json").write_text("{}", encoding="utf-8")
                refreshed = mod._guide_item_source_signature(root)
                self.assertEqual(refreshed[0][1], 2)
                self.assertEqual(refreshed[1:], rows[1:])

    def test_index_builder_streams_and_preserves_previous_cache_on_failure(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "guide_items.json"
            cache.write_text("previous-cache", encoding="utf-8")
            provider = Mock()
            provider._items = []
            provider._load_in_process.return_value = {}
            with (
                patch.object(mod, "DofusItemProvider", return_value=provider),
                patch.object(mod, "_collect_guide_item_ids", return_value=set()),
                patch.object(mod, "_guide_item_source_signature", return_value=[]),
                redirect_stdout(StringIO()),
            ):
                # Atomic replacement failure cannot destroy the previous
                # generation or leave an abandoned large *.tmp sidecar.
                with patch.object(Path, "replace", side_effect=OSError("locked cache")):
                    with self.assertRaisesRegex(OSError, "locked cache"):
                        mod._build_guide_items_index(cache)
                self.assertEqual(cache.read_text(encoding="utf-8"), "previous-cache")
                self.assertFalse(list(cache.parent.glob(".*.tmp")))
                with patch.object(mod.json, "dump", side_effect=OSError("disk full")):
                    with self.assertRaisesRegex(OSError, "disk full"):
                        mod._build_guide_items_index(cache)
                self.assertEqual(cache.read_text(encoding="utf-8"), "previous-cache")
                self.assertFalse(list(cache.parent.glob(".*.tmp")))
                self.assertEqual(mod._build_guide_items_index(cache), 0)
            self.assertEqual(json.loads(cache.read_text(encoding="utf-8"))["items"], {})
            self.assertFalse(list(cache.parent.glob(".*.tmp")))

    def test_index_builder_serializes_items_one_by_one_in_canonical_shape(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod
        from app.modules.encyclopedia.models.dofus_item import DofusItem

        def item(ident, name):
            return DofusItem(
                id=ident, original_id=ident, name=name, level=200,
                type_id=mod.DOFUS_TYPE_ID, type_name="Dofus",
                effects=("10 Crit",), raw={"id": ident, "ignored": [1] * 10},
            )

        provider = Mock()
        provider._items = [item(20, "Later")]
        provider._load_in_process.return_value = {10: item(10, "Earlier")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "compact.json"
            with (
                patch.object(mod, "DofusItemProvider", return_value=provider),
                patch.object(mod, "_collect_guide_item_ids", return_value={10}),
                patch.object(mod, "_guide_item_source_signature",
                             return_value=[["items.json", 10, 20, 30, 40]]),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(mod._build_guide_items_index(output), 0)
            content = output.read_text(encoding="utf-8")
            payload = json.loads(content)
            self.assertEqual(list(payload), [
                "schema_version", "source_signature", "items",
            ])
            self.assertEqual(list(payload["items"]), ["10", "20"])
            self.assertEqual(payload["items"]["10"]["name"], "Earlier")
            self.assertEqual(payload["items"]["20"]["effects"], ["10 Crit"])
            self.assertEqual(payload["items"]["10"]["raw"], {"id": 10})
            self.assertEqual(payload["source_signature"][0][1:], [10, 20, 30, 40])
            self.assertEqual(content.count('"source_signature"'), 1)
            self.assertEqual(list(output.parent.glob(".*.tmp")), [])

    def test_full_dofus_load_drops_compact_guide_row_graph(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "items.json"
            path.write_text(json.dumps({
                "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                "source_signature": [],
                "items": {"42": {
                    "id": 42, "name": "Dofus fixture",
                    "type_id": mod.DOFUS_TYPE_ID,
                }},
            }), encoding="utf-8")
            provider = mod.DofusItemProvider()
            with (
                patch.object(mod, "GUIDE_ITEMS_INDEX", path),
                patch.object(mod, "_guide_item_source_signature", return_value=[]),
            ):
                self.assertEqual(provider._guide_index_row(42)["id"], 42)
                old_rows = provider._guide_index_rows
                self.assertEqual([item.id for item in provider.load_all()], [42])
                self.assertIsNone(provider._guide_index_rows)
                self.assertIsNone(provider._guide_index_stamp)
                self.assertEqual(provider.get_by_id(42).name, "Dofus fixture")
                self.assertTrue(old_rows)

    def test_invalid_compact_item_raw_and_effects_reuse_source_fallback(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod
        from app.modules.encyclopedia.models.dofus_item import DofusItem

        fallback = DofusItem(
            id=42, original_id=42, name="Source item", level=200,
            type_id=23, type_name="Dofus",
        )
        provider = mod.DofusItemProvider()
        with (
            patch.object(provider, "_guide_index_row") as index,
            patch.object(provider, "_load_one", return_value=fallback) as source,
        ):
            for malformed in (
                {"id": 42, "raw": ["invalid"]},
                {"id": 42, "effects": "not a list"},
                {"id": 42, "effects": [42]},
                {"id": True, "raw": {}},
            ):
                with self.subTest(malformed=malformed):
                    provider._by_id.clear()
                    index.return_value = malformed
                    resolved = provider.get_by_id(42)
                    self.assertIs(resolved, fallback)
            self.assertEqual(source.call_count, 4)

        self.assertIsNone(provider._item_from_compact_row({"id": 42, "raw": ["bad"]}))
        self.assertEqual(
            provider._item_from_compact_row({
                "id": 42, "effects": ["Bonus"], "raw": {"id": 42},
            }).effects,
            ("Bonus",),
        )

    def test_recent_guide_item_cache_evicts_least_recently_used(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "items.json"
            cache.write_text(json.dumps({
                "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                "source_signature": [],
                "items": {
                    str(item_id): {"id": item_id, "name": f"Item {item_id}"}
                    for item_id in range(1, 34)
                },
            }), encoding="utf-8")
            provider = mod.DofusItemProvider()
            with (
                patch.object(mod, "GUIDE_ITEMS_INDEX", cache),
                patch.object(mod, "_guide_item_source_signature", return_value=[]),
                patch.object(provider, "_load_one",
                             side_effect=AssertionError("compact cache expected")),
            ):
                for item_id in range(1, 33):
                    self.assertEqual(provider.get_by_id(item_id).id, item_id)
                first = provider.get_by_id(1)
                provider.get_by_id(33)
                self.assertEqual(len(provider._by_id), 32)
                self.assertIn(1, provider._by_id)
                self.assertNotIn(2, provider._by_id)
                self.assertIs(provider.get_by_id(1), first)

    def test_recent_guide_item_is_not_stale_after_atomic_index_replacement(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "items.json"

            def publish(target, label):
                target.write_text(json.dumps({
                    "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                    "source_signature": [],
                    "items": {"42": {"id": 42, "name": label, "type_id": 6}},
                }), encoding="utf-8")

            publish(cache, "Old")
            provider = mod.DofusItemProvider()
            with (
                patch.object(mod, "GUIDE_ITEMS_INDEX", cache),
                patch.object(mod, "_guide_item_source_signature", return_value=[]),
                patch.object(provider, "_load_one", side_effect=AssertionError("source fallback")),
            ):
                self.assertEqual(provider.get_by_id(42).name, "Old")
                self.assertEqual(provider.get_by_id(42).name, "Old")
                before = cache.stat()
                replacement = root / "replacement.json"
                publish(replacement, "New")
                os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.assertEqual(replacement.stat().st_size, before.st_size)
                replacement.replace(cache)
                self.assertEqual(cache.stat().st_mtime_ns, before.st_mtime_ns)
                self.assertEqual(provider.get_by_id(42).name, "New")
                self.assertEqual(len(provider._by_id), 1)

    def test_provider_refreshes_index_after_preload_or_atomic_replacement(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "items.json"
            provider = mod.DofusItemProvider()
            with (
                patch.object(mod, "GUIDE_ITEMS_INDEX", cache),
                patch.object(mod, "_guide_item_source_signature", return_value=[]),
            ):
                # A failed early lookup is not a permanent negative cache.
                self.assertIsNone(provider._guide_index_row(42))
                def publish(ident, path):
                    path.write_text(json.dumps({
                        "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                        "source_signature": [],
                        "items": {str(ident): {"id": ident}},
                    }), encoding="utf-8")

                publish(42, cache)
                self.assertEqual(provider._guide_index_row(42)["id"], 42)
                previous = cache.stat()
                replacement = root / "replacement.json"
                publish(43, replacement)
                os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                self.assertEqual(replacement.stat().st_size, previous.st_size)
                replacement.replace(cache)
                self.assertIsNone(provider._guide_index_row(42))
                self.assertEqual(provider._guide_index_row(43)["id"], 43)

    def test_valid_items_and_malformed_rows_are_not_silently_dropped(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide_items.json"
            valid = {
                "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                "source_signature": [["items.json", 23, 45]],
                "items": {
                    "42": {"id": 42, "name": "Item"},
                    "99": {"id": 99, "name": "Second"},
                },
            }
            with patch.object(mod, "_guide_item_source_signature",
                              return_value=valid["source_signature"]):
                path.write_text(json.dumps(valid), encoding="utf-8")
                self.assertEqual(
                    set(_read_guide_items_index(path=path)), {42, 99},
                )
                # Preserve all IDs emitted by the original integer-key
                # builder, including zero and signed compatibility IDs.
                signed = {**valid, "items": {"0": {"id": 0}, "-1": {"id": -1}}}
                path.write_text(json.dumps(signed), encoding="utf-8")
                self.assertEqual(set(_read_guide_items_index(path=path)), {0, -1})
                for bad in (
                    {"items": {}},
                    {"items": {"42": {"id": 99}}},
                    {"items": {"42": {"id": True}}},
                    {"items": {"42": "invalid"}},
                    {"items": {"042": {"id": 42}}},
                    {"items": {"false": {"id": 42}}},
                    {"items": {"42": {"id": 42}, "042": {"id": 42}}},
                    {"schema_version": True},
                    {"source_signature": []},
                ):
                    with self.subTest(bad=bad):
                        path.write_text(json.dumps({**valid, **bad}), encoding="utf-8")
                        self.assertIsNone(_read_guide_items_index(path=path))
                path.write_text("{broken", encoding="utf-8")
                self.assertIsNone(_read_guide_items_index(path=path))


if __name__ == "__main__":
    unittest.main()
