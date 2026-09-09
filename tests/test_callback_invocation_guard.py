from __future__ import annotations

import unittest

from app.storage import invoke_compatible_callback


class CallbackInvocationGuardTests(unittest.TestCase):
    def test_internal_type_error_is_propagated_after_one_call(self) -> None:
        calls: list[object] = []

        def callback(value) -> None:
            calls.append(value)
            raise TypeError("failure inside callback")

        with self.assertRaisesRegex(TypeError, "failure inside callback"):
            invoke_compatible_callback(callback, "payload")

        self.assertEqual(calls, ["payload"])

    def test_zero_argument_legacy_callback_is_selected_before_call(self) -> None:
        calls: list[str] = []

        def callback() -> str:
            calls.append("called")
            return "ok"

        result = invoke_compatible_callback(callback, "new-argument")

        self.assertEqual(result, "ok")
        self.assertEqual(calls, ["called"])

    def test_incompatible_signature_fails_without_calling_callback(self) -> None:
        calls: list[str] = []

        def callback(required_a, required_b) -> None:
            calls.append(f"{required_a}:{required_b}")

        with self.assertRaises(TypeError):
            invoke_compatible_callback(callback, "only-one")

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
