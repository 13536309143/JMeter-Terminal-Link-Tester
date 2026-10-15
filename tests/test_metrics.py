import tempfile
import unittest
from pathlib import Path

from linklab.config import Scenario
from linklab.metrics import Distribution, evaluate, read_jtl


class MetricsTests(unittest.TestCase):
    def test_nearest_rank_percentile_with_repeated_values(self):
        values = Distribution()
        for number in [1] * 19 + [100]:
            values.add(number)
        self.assertEqual(values.percentile(95), 1)
        self.assertEqual(values.percentile(99), 100)
        self.assertEqual(values.summary()["mean_ms"], 5.95)

    def test_empty_data_is_unknown_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            jtl = read_jtl(Path(temporary) / "absent.jtl")
        self.assertIsNone(jtl["error_rate_pct"])
        result = evaluate(Scenario.from_mapping({}), jtl, {}, exit_code=0)
        self.assertFalse(result["passed"])

    def test_jtl_quoted_error_and_label_separation(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "samples.jtl"
            file.write_text('timeStamp,elapsed,label,success,responseCode,responseMessage,bytes\n1000,20,MQTT Publish,true,200,OK,10\n1020,100,MQTT Publish,false,500,"bad, response",0\n1010,5,MQTT Connect,true,200,OK,5\n')
            result = read_jtl(file)
            self.assertEqual(result["samples"], 3)
            self.assertEqual(result["labels"]["MQTT Publish"]["p95_ms"], 100)
            self.assertEqual(sum(v["samples"] for v in result["series"]), 2)
            self.assertAlmostEqual(result["error_rate_pct"], 100 / 3)
            self.assertIn("MQTT Publish [500]: bad, response", result["errors_by_message"])

    def test_corrupt_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "samples.jtl"
            file.write_text('timeStamp,elapsed,label,success,responseCode\n100,-1,MQTT Publish,true,200\n')
            with self.assertRaisesRegex(ValueError, "row 2"):
                read_jtl(file)
