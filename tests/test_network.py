import base64
import json
import socket
import tempfile
import unittest
from pathlib import Path

from linklab.config import ConfigError, Scenario
from linklab.network import ReferenceEndpoint, read_receipts


class NetworkTests(unittest.TestCase):
    def test_tcp_fragmentation_preserves_one_json_frame(self):
        config = Scenario.from_mapping({"protocol": "tcp", "faults": {"tcp_fragment_bytes": 2}})
        with ReferenceEndpoint(config) as server, socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
            payload = b'{"seq":1,"message_id":"test"}'
            client.sendall(payload + b"\n")
            stream = client.makefile("rb")
            self.assertEqual(stream.readline(), payload + b"\n")
            stream.close()

    def test_udp_duplicate_datagrams_are_actually_emitted(self):
        config = Scenario.from_mapping({"protocol": "udp", "faults": {"udp_duplicate_every": 2}})
        with ReferenceEndpoint(config) as server, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            client.connect(("127.0.0.1", server.port))
            client.send(b'{"seq":2}')
            self.assertEqual(client.recv(100), b'{"seq":2}')
            self.assertEqual(client.recv(100), b'{"seq":2}')

    def test_udp_pair_reordering_is_visible_on_wire(self):
        config = Scenario.from_mapping({"protocol": "udp", "faults": {"udp_reorder_pairs": True}})
        with ReferenceEndpoint(config) as server, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(0.1)
            client.connect(("127.0.0.1", server.port))
            client.send(b'{"seq":1}')
            with self.assertRaises(socket.timeout):
                client.recv(100)
            client.send(b'{"seq":2}')
            client.settimeout(2)
            self.assertEqual(json.loads(client.recv(100))["seq"], 2)
            self.assertEqual(json.loads(client.recv(100))["seq"], 1)

    def test_corrupted_receipt_file_cannot_pass(self):
        config = Scenario.from_mapping({"protocol": "udp"})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "network-replies-0.jsonl").write_text('{"payload_b64":"@@@","received_at_ms":1}\n')
            result = read_receipts(config, "a" * 16, config.devices(), output)
            self.assertTrue(result["worker_error"])
            self.assertEqual(result["delivery_rate_pct"], 0)

    def test_protocol_specific_faults_are_not_silently_ignored(self):
        for values in ({"protocol": "mqtt", "faults": {"response_drop_every": 1}},
                       {"protocol": "tcp", "faults": {"udp_reorder_pairs": True}},
                       {"protocol": "udp", "faults": {"tcp_fragment_bytes": 1}}):
            with self.assertRaises(ConfigError):
                Scenario.from_mapping(values)
