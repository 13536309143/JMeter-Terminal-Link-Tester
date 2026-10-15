"""Loopback HTTP reference endpoint used only by development experiments."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class HTTPReference:
    def __init__(self, scenario, port=0):
        self.scenario = scenario
        self.protocol = "http"
        self.stopping = threading.Event()
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def respond(self):
                settings = endpoint.scenario.values["http"]
                request = urlsplit(self.path)
                if request.path != settings["path"]:
                    self.reply(404, b'{"error":"path_not_found"}')
                    return
                try:
                    if self.command == "GET":
                        payload = parse_qs(request.query)["payload"][0].encode("utf-8")
                    else:
                        length = int(self.headers.get("Content-Length", 0))
                        if not 0 < length <= endpoint.scenario.values["collection"]["max_payload_bytes"]:
                            self.reply(413, b'{"error":"payload_size"}')
                            self.close_connection = True
                            return
                        payload = self.rfile.read(length)
                    body = json.loads(payload)
                    seq = body["seq"]
                    if type(seq) is not int:
                        raise ValueError("sequence")
                except (ValueError, TypeError, KeyError, UnicodeError):
                    self.reply(400, b'{"error":"invalid_request"}')
                    return
                faults = endpoint.scenario.values["faults"]
                if faults["response_drop_every"] and seq % faults["response_drop_every"] == 0:
                    endpoint.stopping.wait(settings["response_timeout_ms"] / 1000 + 0.25)
                    self.close_connection = True
                    return
                if faults["processing_delay_ms"]:
                    endpoint.stopping.wait(faults["processing_delay_ms"] / 1000)
                if faults["http_error_every"] and seq % faults["http_error_every"] == 0:
                    self.reply(500, b'{"error":"injected_http_error"}')
                elif faults["response_invalid_every"] and seq % faults["response_invalid_every"] == 0:
                    self.reply(settings["expected_status"], b"{invalid-response}")
                elif faults["response_wrong_id_every"] and seq % faults["response_wrong_id_every"] == 0:
                    body["message_id"] = "uncorrelated-response"
                    self.reply(settings["expected_status"], json.dumps(body).encode())
                else:
                    self.reply(settings["expected_status"], payload)

            def reply(self, status, payload):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=UTF-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    self.wfile.flush()
                except OSError:
                    pass

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = respond

            def log_message(self, *_args):
                pass

        class Server(ThreadingHTTPServer):
            request_queue_size = 256
            daemon_threads = True
            block_on_close = False

        self.server = Server(("127.0.0.1", port), Handler)
        self.port = self.server.server_address[1]
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True, name="http-reference")

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *_args):
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)
