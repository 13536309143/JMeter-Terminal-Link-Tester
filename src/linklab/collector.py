"""Independent MQTT subscriber: readiness, validation, persistence and collection latency."""
from __future__ import annotations

import json
import math
import os
import queue
import threading
import time
from collections import Counter
from pathlib import Path

import paho.mqtt.client as mqtt

from .metrics import Distribution


class CollectionState:
    """Single-writer state; exposed separately so corruption tests need no network."""

    def __init__(self, scenario, run_id, devices):
        self.scenario = scenario
        self.run_id = run_id
        self.devices = {d["device_id"]: d for d in devices}
        self.expected = scenario.expected_messages
        self.received = self.valid = self.invalid = self.duplicates = self.out_of_order = 0
        self.injected_drops = self.queue_overflows = self.foreign = 0
        self.seen = set()
        self.last_seq = {}
        self.reasons = Counter()
        self.transport = Distribution()
        self.e2e = Distribution()
        self.worker_error = ""
        self.abort = threading.Event()

    def process(self, payload: bytes, topic: str | None, received_ms: int, retained=False, processed_ms=None):
        self.received += 1
        record = {"received_at_ms": received_ms, "topic": topic, "bytes": len(payload)}
        try:
            if len(payload) > self.scenario.values["collection"]["max_payload_bytes"]:
                raise ValueError("payload_too_large")
            body = json.loads(payload.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non_finite_json")))
            if not isinstance(body, dict):
                raise ValueError("payload_not_object")
            if body.get("run_id") != self.run_id:
                self.foreign += 1
                raise ValueError("wrong_run_id")
            device_id = body.get("device_id")
            if not isinstance(device_id, str) or device_id not in self.devices:
                raise ValueError("unknown_device")
            expected_topic = f'{self.scenario.values["mqtt"]["topic_prefix"]}/{self.run_id}/{self.scenario.values["collection"]["topic_stage"]}/{device_id}'
            if topic is not None and topic != expected_topic:
                raise ValueError("topic_device_mismatch")
            if retained:
                raise ValueError("retained_message")
            seq = body.get("seq")
            if type(seq) is not int or not 1 <= seq <= self.scenario.values["load"]["messages_per_terminal"]:
                raise ValueError("invalid_sequence")
            message_id = f"{self.run_id}:{device_id}:{seq}"
            if body.get("message_id") != message_id or type(body.get("schema_version")) is not int or body["schema_version"] != 1:
                raise ValueError("invalid_message_identity")
            for field in ("device_type", "site"):
                if body.get(field) != self.devices[device_id][field]:
                    raise ValueError(f"invalid_{field}")
            sent_ms = body.get("sent_at_ms")
            if type(sent_ms) is not int or not 0 <= received_ms - sent_ms <= 604800000:
                raise ValueError("invalid_timestamp_or_clock")
            temperature = body.get("temperature_c")
            if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or not -40 <= temperature <= 125:
                raise ValueError("temperature_out_of_range")
            record.update({"device_id": device_id, "seq": seq, "message_id": message_id,
                           "sent_at_ms": sent_ms, "temperature_c": temperature})
            if message_id in self.seen:
                self.duplicates += 1
                record["status"] = "duplicate"
                return record
            every = self.scenario.values["faults"]["drop_every"]
            if every and seq % every == 0:
                self.injected_drops += 1
                record["status"] = "injected_drop"
                return record
            delay = self.scenario.values["faults"]["processing_delay_ms"]
            if delay and self.abort.wait(delay / 1000):
                self.worker_error = "Collector processing cancelled at drain deadline"
                record["status"] = "aborted"
                return record
            processed_ms = int(time.time() * 1000) if processed_ms is None else processed_ms
            self.seen.add(message_id)
            if seq < self.last_seq.get(device_id, 0):
                self.out_of_order += 1
            self.last_seq[device_id] = max(seq, self.last_seq.get(device_id, 0))
            self.valid += 1
            self.transport.add(received_ms - sent_ms)
            self.e2e.add(processed_ms - sent_ms)
            record.update({"status": "valid", "processed_at_ms": processed_ms,
                           "transport_ms": received_ms - sent_ms, "e2e_ms": processed_ms - sent_ms})
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            self.invalid += 1
            reason = str(exc)[:160]
            self.reasons[reason] += 1
            record.update({"status": "invalid", "reason": reason})
        return record

    def summary(self):
        return {"expected": self.expected, "received": self.received, "valid_unique": self.valid,
                "missing": max(0, self.expected - self.valid), "invalid": self.invalid,
                "duplicates": self.duplicates, "out_of_order": self.out_of_order,
                "injected_drops": self.injected_drops, "foreign": self.foreign,
                "queue_overflows": self.queue_overflows, "worker_error": self.worker_error,
                "delivery_rate_pct": self.valid / self.expected * 100,
                "transport": self.transport.summary(), "e2e": self.e2e.summary(),
                "invalid_reasons": dict(self.reasons)}


def credentials(scenario):
    broker = scenario.values["broker"]
    result = []
    for key in ("username_env", "password_env"):
        variable = broker[key]
        if variable and variable not in os.environ:
            raise ValueError(f"Required environment variable is not set: {variable}")
        result.append(os.environ.get(variable, "") if variable else "")
    return tuple(result)


class Collector:
    def __init__(self, scenario, run_id: str, devices: list[dict], output: Path):
        self.scenario, self.run_id, self.output = scenario, run_id, output
        self.state = CollectionState(scenario, run_id, devices)
        self.ready = threading.Event()
        self.error = ""
        self.inbox = queue.Queue(maxsize=10000)
        self.stop_worker = threading.Event()
        self.worker = threading.Thread(target=self._consume, name="linklab-collector", daemon=True)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"lc-{run_id[-16:]}",
                                  protocol=mqtt.MQTTv311, reconnect_on_failure=False)
        username, password = credentials(scenario)
        if username:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            self.error = f"Collector connection rejected: {reason_code}"
            self.ready.set()
            return
        stage = self.scenario.values["collection"]["topic_stage"]
        result, _ = client.subscribe(f'{self.scenario.values["mqtt"]["topic_prefix"]}/{self.run_id}/{stage}/+',
                                     qos=self.scenario.values["mqtt"]["qos"])
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.error = f"Collector subscribe failed: {result}"
            self.ready.set()

    def _on_subscribe(self, _client, _userdata, _mid, reason_codes, _properties):
        if not reason_codes or any(r.is_failure for r in reason_codes):
            self.error = "Collector subscription rejected"
        self.ready.set()

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            self.error = f"Collector disconnected unexpectedly: {reason_code}"

    def _on_message(self, _client, _userdata, message):
        received_ms = int(time.time() * 1000)
        if len(message.payload) > self.scenario.values["collection"]["max_payload_bytes"]:
            self.state.queue_overflows += 1
            return
        try:
            self.inbox.put_nowait((message.payload, message.topic, received_ms, message.retain))
        except queue.Full:
            self.state.queue_overflows += 1

    def _consume(self):
        try:
            with self.output.open("w", encoding="utf-8", buffering=1) as stream:
                while not self.stop_worker.is_set():
                    try:
                        args = self.inbox.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    try:
                        record = self.state.process(*args)
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    finally:
                        self.inbox.task_done()
        except Exception as exc:
            self.state.worker_error = f"{type(exc).__name__}: {exc}"

    def start(self):
        self.worker.start()
        broker = self.scenario.values["broker"]
        timeout = self.scenario.values["mqtt"]["connect_timeout_seconds"]
        self.client.connect_timeout = timeout
        self.client.connect(broker["host"], broker["port"], self.scenario.values["mqtt"]["keepalive_seconds"])
        self.client.loop_start()
        if not self.ready.wait(timeout) or self.error:
            raise RuntimeError(self.error or "Collector SUBACK timed out")

    def close(self, drain=True):
        deadline = time.monotonic() + self.scenario.values["collection"]["drain_seconds"]
        if drain:
            while time.monotonic() < deadline and (self.state.valid < self.state.expected or self.inbox.unfinished_tasks) and not self.state.worker_error:
                time.sleep(0.05)
        self.client.disconnect()
        self.client.loop_stop()
        while drain and self.inbox.unfinished_tasks and time.monotonic() < deadline and not self.state.worker_error:
            time.sleep(0.05)
        self.stop_worker.set()
        self.state.abort.set()
        if self.worker.ident:
            self.worker.join(timeout=2)
            if self.worker.is_alive():
                self.state.worker_error = "Collector processing exceeded drain deadline"
        if self.inbox.unfinished_tasks and not self.state.worker_error:
            self.state.worker_error = "Collector queue did not drain before deadline"
        if self.error and not self.state.worker_error:
            self.state.worker_error = self.error
        return self.state.summary()
