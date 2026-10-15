import os
import tempfile
import unittest
from pathlib import Path

from linklab.config import Scenario
from linklab.demo_broker import DemoBroker
from linklab.runner import run_scenario
from linklab.network import ReferenceEndpoint, reference_endpoint


@unittest.skipUnless(os.environ.get("LINKLAB_INTEGRATION") == "1", "Set LINKLAB_INTEGRATION=1 after bootstrap")
class IntegrationTests(unittest.TestCase):
    def test_qos_zero_and_two_end_to_end(self):
        workspace = Path(__file__).resolve().parent.parent
        destination = workspace / "results/integration"
        with DemoBroker() as broker:
            for qos in (0, 2):
                config = Scenario.from_mapping({"name": f"integration-qos-{qos}", "broker": {"port": broker.port},
                                               "load": {"terminals": 2, "messages_per_terminal": 3}, "mqtt": {"qos": qos}})
                result = run_scenario(config, workspace, destination)
                self.assertTrue(result["acceptance"]["passed"], result)
                self.assertEqual(result["collection"]["valid_unique"], 6)

    def test_tcp_udp_and_http_end_to_end(self):
        workspace = Path(__file__).resolve().parent.parent
        for protocol in ("tcp", "udp", "http"):
            values = {"name": f"integration-{protocol}", "protocol": protocol,
                      "load": {"terminals": 2, "messages_per_terminal": 3, "ramp_up_seconds": 0}}
            config = Scenario.from_mapping(values)
            with reference_endpoint(config) as endpoint:
                values["http" if protocol == "http" else "network"] = {"port": endpoint.port}
                result = run_scenario(Scenario.from_mapping(values), workspace, workspace / "results/integration")
            self.assertTrue(result["acceptance"]["passed"], result)
            self.assertEqual(result["collection"]["valid_unique"], 6)


if __name__ == "__main__":
    unittest.main()
