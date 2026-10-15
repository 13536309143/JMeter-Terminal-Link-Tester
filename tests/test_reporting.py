import json
import tempfile
import unittest
from pathlib import Path

from linklab.collector import CollectionState
from linklab.config import Scenario
from linklab.metrics import evaluate, read_jtl
from linklab.reporting import compare_results, write_report


def empty_result(root):
    config = Scenario.from_mapping({})
    jtl = read_jtl(root / "absent")
    collection = CollectionState(config, "a" * 16, config.devices()).summary()
    return {"run_id": "a" * 16, "scenario_name": "example", "started_at": "2026-10-15T00:00:00Z",
            "status": "failed", "protocol": "mqtt", "error": "<script>alert('bad')</script>",
            "expected_messages": 50, "jmeter": jtl, "collection": collection,
            "acceptance": evaluate(config, jtl, collection, exit_code=1),
            "faults": config.values["faults"], "load": config.values["load"]}


class ReportingTests(unittest.TestCase):
    def test_html_escapes_external_error_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_report(root, empty_result(root))
            html = (root / "report.html").read_text()
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertTrue((root / "report.md").is_file())
            self.assertFalse(json.loads((root / "summary.json").read_text())["acceptance"]["passed"])

    def test_comparison_does_not_divide_by_zero_or_hide_protocol_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = empty_result(root)
            baseline["collection"]["delivery_rate_pct"] = 0
            candidate = empty_result(root)
            candidate["protocol"] = "udp"
            candidate["collection"]["delivery_rate_pct"] = 100
            (root / "a.json").write_text(json.dumps(baseline))
            (root / "b.json").write_text(json.dumps(candidate))
            result = compare_results(root / "a.json", root / "b.json")
            self.assertFalse(result["same_protocol"])
            self.assertIsNone(result["metrics"]["delivery_rate_pct"]["change_pct"])
            self.assertEqual(result["metrics"]["delivery_rate_pct"]["delta"], 100)
