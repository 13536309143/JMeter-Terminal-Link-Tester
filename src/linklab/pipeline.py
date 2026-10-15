"""Reference collection service: commit SQLite before publishing a correlated receipt."""
from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt

from .collector import credentials


class PersistenceBridge:
    def __init__(self, scenario, database: Path):
        self.scenario = scenario
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.stage = scenario.values["collection"]["topic_stage"]
        if self.stage == "up":
            raise ValueError("Persistence bridge requires collection.topic_stage other than 'up', e.g. persisted")
        self.prefix = scenario.values["mqtt"]["topic_prefix"]
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.inbox = queue.Queue(maxsize=10000)
        self.error = ""
        self.rejected = 0
        self.worker = threading.Thread(target=self._consume, name="linklab-persistence", daemon=True)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"lb-{uuid.uuid4().hex[:16]}",
                                  protocol=mqtt.MQTTv311, reconnect_on_failure=False)
        username, password = credentials(scenario)
        if username:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message

    def _on_connect(self, client, _userdata, _flags, reason, _properties):
        if reason.is_failure:
            self.error = f"Persistence bridge connection rejected: {reason}"
            self.ready.set()
            return
        client.subscribe(f"{self.prefix}/+/up/+", qos=self.scenario.values["mqtt"]["qos"])

    def _on_subscribe(self, _client, _userdata, _mid, reasons, _properties):
        if not reasons or any(r.is_failure for r in reasons):
            self.error = "Persistence bridge subscription rejected"
        self.ready.set()

    def _on_message(self, _client, _userdata, message):
        if len(message.payload) > self.scenario.values["collection"]["max_payload_bytes"]:
            self.rejected += 1
            return
        try:
            self.inbox.put_nowait((message.topic, message.payload))
        except queue.Full:
            self.error = "Persistence bridge queue overflow"

    def _consume(self):
        try:
            with sqlite3.connect(self.database) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("""CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, device_id TEXT NOT NULL,
                    seq INTEGER NOT NULL, persisted_at_ms INTEGER NOT NULL, payload TEXT NOT NULL)""")
                connection.execute("CREATE INDEX IF NOT EXISTS ix_messages_run ON messages(run_id)")
                while not self.stopping.is_set() or not self.inbox.empty():
                    try:
                        topic, payload = self.inbox.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    try:
                        body = json.loads(payload)
                        suffix = topic[len(self.prefix) + 1:].split("/")
                        if not isinstance(body, dict) or len(suffix) != 3:
                            raise ValueError("invalid payload/topic")
                        run_id, _, device_id = suffix
                        seq = body.get("seq")
                        expected = f"{run_id}:{device_id}:{seq}"
                        if (body.get("run_id") != run_id or body.get("device_id") != device_id or
                                type(seq) is not int or seq < 1 or body.get("message_id") != expected):
                            raise ValueError("invalid message identity")
                        with connection:
                            connection.execute("INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?)",
                                               (expected, run_id, device_id, seq, int(time.time() * 1000), payload.decode("utf-8")))
                        # The receipt is emitted only after the transaction context commits.
                        receipt = self.client.publish(f"{self.prefix}/{run_id}/{self.stage}/{device_id}", payload, qos=1, retain=False)
                        receipt.wait_for_publish(timeout=5)
                        if not receipt.is_published():
                            raise RuntimeError("Persistence receipt PUBACK timeout")
                    except (ValueError, UnicodeError, TypeError):
                        self.rejected += 1
                    finally:
                        self.inbox.task_done()
        except Exception as exc:
            self.error = f"Persistence bridge worker failed: {type(exc).__name__}: {exc}"

    def __enter__(self):
        self.worker.start()
        broker = self.scenario.values["broker"]
        timeout = self.scenario.values["mqtt"]["connect_timeout_seconds"]
        try:
            self.client.connect_timeout = timeout
            self.client.connect(broker["host"], broker["port"], 60)
            self.client.loop_start()
            if not self.ready.wait(timeout) or self.error:
                raise RuntimeError(self.error or "Persistence bridge SUBACK timed out")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_args):
        self.stopping.set()
        self.worker.join(timeout=7)
        self.client.disconnect()
        self.client.loop_stop()
        if self.worker.is_alive():
            self.error = self.error or "Persistence bridge shutdown exceeded deadline"
