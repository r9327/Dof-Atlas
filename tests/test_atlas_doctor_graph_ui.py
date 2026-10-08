from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.doctor_graph_ui import compact_graph, render_html


class DoctorGraphUiTests(unittest.TestCase):
    def test_interactive_view_has_real_navigation_and_filters(self):
        graph = {"nodes": [
            {"id": "a", "label": "guide", "source_file": "app/modules/encyclopedia/view.py", "community": 5},
            {"id": "b", "label": "db", "source_file": "app/core/db.py", "community": 5},
        ], "links": [{"source": "a", "target": "b", "relation": "imports"}],
                 "built_at_commit": "a" * 40}
        audit = {"orphan_nodes": [{"file": "app/core/db.py"}]}
        data = compact_graph(graph, audit)
        html = render_html(data)
        self.assertIn('id="search"', html)
        self.assertIn('id="domain"', html)
        self.assertIn("canvas.addEventListener('wheel'", html)
        self.assertIn("Doctor Atlas × Graphify", html)
        self.assertEqual(len(data["edges"]), 1)
        self.assertTrue(data["nodes"][1]["reasons"])
        self.assertFalse(data["truncated"])

    def test_labels_cannot_escape_json_script(self):
        graph = {"nodes": [{"id": 1, "label": "</script><img src=x onerror=alert(1)>",
                            "source_file": "app/x.py"}], "links": []}
        html = render_html(compact_graph(graph, {}))
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c", html)


if __name__ == "__main__":
    unittest.main()
