import tempfile
import unittest
from pathlib import Path

from linklab.config import ConfigError, Scenario


class ConfigTests(unittest.TestCase):
    def test_defaults_and_expected_workload(self):
        config = Scenario.from_mapping({})
        self.assertEqual(config.expected_messages, 50)
        self.assertEqual(len(config.devices()), 5)
        self.assertEqual(len({d["device_id"] for d in config.devices()}), 5)

    def test_misspelled_field_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "Unknown field"):
            Scenario.from_mapping({"load": {"terminal": 10}})

    def test_nonfinite_bool_and_fractional_counts_are_rejected(self):
        for value in (True, 0, -1, 2.5, float("nan"), float("inf"), "10"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                Scenario.from_mapping({"load": {"terminals": value}})

    def test_fractional_ramp_is_rejected(self):
        with self.assertRaises(ConfigError):
            Scenario.from_mapping({"load": {"ramp_up_seconds": 0.5}})

    def test_protocol_wildcards_and_incomplete_auth_are_rejected(self):
        for values in ({"broker": {"host": "tcp://localhost"}}, {"mqtt": {"topic_prefix": "unsafe/#"}},
                       {"broker": {"username_env": "MQTT_USER"}}, {"version": True}):
            with self.subTest(values=values), self.assertRaises(ConfigError):
                Scenario.from_mapping(values)

    def test_impossible_timeout_and_payload_are_rejected(self):
        for values in ({"load": {"messages_per_terminal": 10000}},
                       {"data": {"padding_bytes": 2000}, "collection": {"max_payload_bytes": 1024}}):
            with self.assertRaises(ConfigError):
                Scenario.from_mapping(values)

    def test_yaml_duplicate_and_executable_tags_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "scenario.yaml"
            for body in ("name: one\nname: two", "!!python/object/apply:os.system ['echo bad']"):
                file.write_text(body)
                with self.assertRaises(ConfigError):
                    Scenario.load(file)

    def test_csv_relative_path_shortage_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / "devices.csv"
            file.write_text("device_id,device_type,site\na,wearable,dg\nb,home,dg\n")
            config = Scenario.from_mapping({"load": {"terminals": 2}, "data": {"devices_csv": "devices.csv"}}, root / "scenario.yaml")
            self.assertEqual(config.devices()[1]["device_id"], "b")
            file.write_text("device_id,device_type,site\na,wearable,dg\na,home,dg\n")
            with self.assertRaisesRegex(ConfigError, "Duplicate"):
                config.devices()
            file.write_text("device_id,device_type,site\na,wearable,dg\n")
            with self.assertRaisesRegex(ConfigError, "CSV has"):
                config.devices()
