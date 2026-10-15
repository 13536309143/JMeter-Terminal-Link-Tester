"""TCP newline/JSON and UDP JSON reference endpoints, plus receipt import."""
from __future__ import annotations

import base64
import json
import socketserver
import threading
import time
from copy import deepcopy
from pathlib import Path

from .collector import CollectionState
from .config import Scenario


def reference_endpoint(scenario, port=0):
    if scenario.values["protocol"] == "http":
        from .http_reference import HTTPReference
        return HTTPReference(scenario, port)
    return ReferenceEndpoint(scenario, port)


from .network_receipts import read_receipts


class _TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    request_queue_size = 256
    daemon_threads = True
    block_on_close = False


class _UDPServer(socketserver.ThreadingUDPServer):
    daemon_threads = True
    block_on_close = False


class ReferenceEndpoint:
    """Loopback-only lab endpoint with deterministic response faults."""

    def __init__(self, scenario, port=0):
        self.scenario = scenario
        self.protocol = scenario.values["protocol"]
        if self.protocol not in ("tcp", "udp"):
            raise ValueError("ReferenceEndpoint requires tcp or udp")
        self.lock = threading.Lock()
        self.pending = {}
        self.port = port
        endpoint = self

        class TCPHandler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(10)
                while True:
                    try:
                        line = self.rfile.readline(endpoint.scenario.values["collection"]["max_payload_bytes"] + 2)
                    except (OSError, ValueError):
                        return
                    if not line:
                        return
                    if not line.endswith(b"\n"):
                        return
                    close_every = endpoint.scenario.values["faults"]["tcp_close_every"]
                    if close_every:
                        try:
                            if json.loads(line)["seq"] % close_every == 0:
                                return
                        except (ValueError, TypeError, KeyError):
                            return
                    def send(payload):
                        frame = payload + b"\n"
                        fragment = endpoint.scenario.values["faults"]["tcp_fragment_bytes"]
                        if fragment:
                            for start in range(0, len(frame), fragment):
                                self.request.sendall(frame[start:start + fragment])
                                time.sleep(0.001)
                        else:
                            self.request.sendall(frame)
                    try:
                        endpoint.respond(line.rstrip(b"\r\n"), send, self.client_address)
                    except OSError:
                        return

        class UDPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                data, sock = self.request
                try:
                    endpoint.respond(data, lambda payload: sock.sendto(payload, self.client_address), self.client_address)
                except OSError:
                    pass

        self.server = (_TCPServer if self.protocol == "tcp" else _UDPServer)(("127.0.0.1", port), TCPHandler if self.protocol == "tcp" else UDPHandler)
        self.port = self.server.server_address[1]
        self.worker = threading.Thread(target=self.server.serve_forever, name=f"linklab-{self.protocol}-lab", daemon=True)

    def respond(self, data, send, address):
        try:
            body = json.loads(data)
            seq = body["seq"]
            if type(seq) is not int:
                return
        except (ValueError, TypeError, KeyError):
            return
        faults = self.scenario.values["faults"]
        if faults["response_drop_every"] and seq % faults["response_drop_every"] == 0:
            return
        if faults["processing_delay_ms"]:
            time.sleep(faults["processing_delay_ms"] / 1000)
        if faults["response_invalid_every"] and seq % faults["response_invalid_every"] == 0:
            send(b"{invalid-response}")
            return
        if faults["response_wrong_id_every"] and seq % faults["response_wrong_id_every"] == 0:
            body["message_id"] = "uncorrelated-response"
            send(json.dumps(body).encode("utf-8"))
            return
        if self.protocol == "udp" and faults["udp_reorder_pairs"]:
            with self.lock:
                if seq % 2:
                    self.pending[address] = data
                    return
                pending = self.pending.pop(address, None)
            send(data)
            if pending is not None:
                time.sleep(0.005)
                send(pending)
            return
        send(data)
        if self.protocol == "udp" and faults["udp_duplicate_every"] and seq % faults["udp_duplicate_every"] == 0:
            send(data)

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)
