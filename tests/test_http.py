import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linklab.config import ConfigError, Scenario
from linklab.http_reference import HTTPReference
from linklab.production_cli import main


class HTTPTests(unittest.TestCase):
    def test_json_request_response_and_error_status(self):
        config = Scenario.from_mapping({"protocol": "http", "faults": {"http_error_every": 2}})
        with HTTPReference(config) as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=2)
            for seq in (1, 2):
                body = {"seq": seq, "message_id": "example"}
                client.request("POST", "/telemetry", json.dumps(body), {"Content-Type": "application/json"})
                response = client.getresponse()
                self.assertEqual(response.status, 200 if seq == 1 else 500)
                received = json.loads(response.read())
                if seq == 1:
                    self.assertEqual(received, body)
            client.close()

    def test_configuration_rejects_url_injection_and_invalid_method(self):
        for values in ({"protocol": "http", "http": {"path": "/${__groovy(1)}"}},
                       {"protocol": "http", "http": {"method": "CONNECT"}},
                       {"protocol": "http", "http": {"bearer_token_env": "bad-name"}}):
            with self.assertRaises(ConfigError):
                Scenario.from_mapping(values)

    def test_production_cli_has_no_development_server_or_experiment_commands(self):
        with patch("sys.stderr"), self.assertRaises(SystemExit) as result:
            main(["demo"])
        self.assertEqual(result.exception.code, 2)
