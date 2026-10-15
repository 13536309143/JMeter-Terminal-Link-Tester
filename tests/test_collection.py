import json
import time
import unittest

from linklab.collector import CollectionState
from linklab.config import Scenario


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.config = Scenario.from_mapping({"load": {"terminals": 1, "messages_per_terminal": 3}})
        self.state = CollectionState(self.config, "a" * 16, self.config.devices())
        self.topic = "linklab/dongguan/" + "a" * 16 + "/up/dg-00001"

    def message(self, seq=1, **overrides):
        body = {"schema_version": 1, "run_id": "a" * 16, "device_id": "dg-00001", "device_type": "home",
                "site": "dongguan", "seq": seq, "message_id": f'{"a" * 16}:dg-00001:{seq}',
                "sent_at_ms": int(time.time() * 1000) - 20, "temperature_c": 25.5}
        body.update(overrides)
        return json.dumps(body).encode()

    def process(self, payload, topic=None, retained=False):
        return self.state.process(payload, topic or self.topic, int(time.time() * 1000), retained)

    def test_duplicate_does_not_increase_delivery_rate(self):
        self.process(self.message())
        self.process(self.message())
        summary = self.state.summary()
        self.assertEqual(summary["valid_unique"], 1)
        self.assertEqual(summary["duplicates"], 1)
        self.assertAlmostEqual(summary["delivery_rate_pct"], 100 / 3)

    def test_out_of_order_and_missing_are_reported(self):
        self.process(self.message(2))
        self.process(self.message(1))
        self.assertEqual(self.state.summary()["out_of_order"], 1)
        self.assertEqual(self.state.summary()["missing"], 1)

    def test_bad_payloads_never_count_as_valid(self):
        payloads = [b"not-json", b"[]", self.message(temperature_c="bad"), self.message(schema_version=True),
                    self.message(seq=True), self.message(seq=4), self.message(run_id="other"),
                    self.message(sent_at_ms=int(time.time() * 1000) + 10000), self.message(device_id=["bad"]),
                    self.message(message_id="forged"), self.message(temperature_c=float("nan"))]
        for payload in payloads:
            self.assertEqual(self.process(payload)["status"], "invalid")
        self.assertEqual(self.state.valid, 0)
        self.assertEqual(self.state.invalid, len(payloads))

    def test_topic_mismatch_and_retained_messages_are_invalid(self):
        self.assertEqual(self.process(self.message(), self.topic + "extra")["status"], "invalid")
        self.assertEqual(self.process(self.message(), retained=True)["status"], "invalid")

    def test_injected_drop_is_explicit(self):
        config = Scenario.from_mapping({"load": {"terminals": 1, "messages_per_terminal": 3}, "faults": {"drop_every": 2}})
        self.state = CollectionState(config, "a" * 16, config.devices())
        self.assertEqual(self.process(self.message(2))["status"], "injected_drop")
        self.assertEqual(self.state.summary()["injected_drops"], 1)
        self.assertEqual(self.state.valid, 0)

    def test_transport_and_processing_distributions_have_values(self):
        self.process(self.message())
        self.assertGreaterEqual(self.state.summary()["transport"]["p95_ms"], 20)
        self.assertGreaterEqual(self.state.summary()["e2e"]["p95_ms"], 20)
