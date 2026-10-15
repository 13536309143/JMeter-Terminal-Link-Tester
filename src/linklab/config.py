"""Strict, versioned scenario loading. Configuration is data, never executable code."""
from __future__ import annotations

import csv
import json
import math
import re
from itertools import islice
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


DEFAULTS = {
    "version": 1, "name": "terminal-baseline", "description": "", "protocol": "mqtt",
    "broker": {"host": "127.0.0.1", "port": 1883,
               "username_env": "", "password_env": ""},
    "load": {"terminals": 5, "messages_per_terminal": 10,
             "ramp_up_seconds": 1, "interval_ms": 100},
    "network": {"host": "127.0.0.1", "port": 9000, "connect_timeout_ms": 3000,
                "response_timeout_ms": 1000},
    "http": {"host": "127.0.0.1", "port": 8080, "path": "/telemetry", "method": "POST",
             "connect_timeout_ms": 3000, "response_timeout_ms": 1000, "expected_status": 200,
             "bearer_token_env": ""},
    "mqtt": {"qos": 1, "keepalive_seconds": 60, "connect_timeout_seconds": 5,
             "topic_prefix": "linklab/dongguan"},
    "data": {"devices_csv": "", "seed": 2025, "padding_bytes": 0},
    "collection": {"drain_seconds": 3, "max_payload_bytes": 65536, "topic_stage": "up"},
    "faults": {"invalid_every": 0, "drop_every": 0, "processing_delay_ms": 0,
               "response_drop_every": 0, "response_invalid_every": 0, "response_wrong_id_every": 0,
               "udp_duplicate_every": 0, "udp_reorder_pairs": False, "tcp_fragment_bytes": 0, "tcp_close_every": 0,
               "http_error_every": 0},
    "thresholds": {"max_error_rate_pct": 0, "min_delivery_rate_pct": 100,
                   "max_request_p95_ms": 3000, "max_e2e_p95_ms": 3000,
                   "max_duplicates": 0, "max_out_of_order": 0},
    "execution": {"timeout_seconds": 120, "html_dashboard": True},
}


class UniqueSafeLoader(yaml.SafeLoader):
    """Reject duplicate keys rather than silently changing a load setting."""


def _mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in mapping:
            raise ConfigError(f"Duplicate or non-string key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _merge(base: dict, values: dict, location="scenario") -> dict:
    if not isinstance(values, dict):
        raise ConfigError(f"{location} must be a mapping")
    unknown = values.keys() - base.keys()
    if unknown:
        raise ConfigError(f"Unknown field in {location}: {', '.join(sorted(unknown))}")
    result = deepcopy(base)
    for key, value in values.items():
        result[key] = _merge(base[key], value, f"{location}.{key}") if isinstance(base[key], dict) else value
    return result


def _number(value: Any, location: str, low: float, high: float, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{location} must be a finite number")
    if integer and not isinstance(value, int):
        raise ConfigError(f"{location} must be an integer")
    if not low <= value <= high:
        raise ConfigError(f"{location} must be in [{low}, {high}]")


@dataclass(frozen=True)
class Scenario:
    values: dict
    origin: Path | None = None

    @classmethod
    def from_mapping(cls, values: dict, origin: Path | None = None):
        # Accept snapshots produced by the initial MQTT-only implementation.
        if isinstance(values, dict) and isinstance(values.get("thresholds"), dict) and "max_publish_p95_ms" in values["thresholds"]:
            values = deepcopy(values)
            if "max_request_p95_ms" in values["thresholds"]:
                raise ConfigError("Use only max_request_p95_ms, not both P95 threshold names")
            values["thresholds"]["max_request_p95_ms"] = values["thresholds"].pop("max_publish_p95_ms")
        v = _merge(DEFAULTS, values)
        if type(v["version"]) is not int or v["version"] != 1:
            raise ConfigError("Only scenario version 1 is supported")
        if not isinstance(v["name"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", v["name"]):
            raise ConfigError("name must contain 1–64 ASCII letters, digits, _ or -")
        if not isinstance(v["description"], str):
            raise ConfigError("description must be a string")
        if v["protocol"] not in ("mqtt", "tcp", "udp", "http"):
            raise ConfigError("protocol must be mqtt, tcp, udp or http")
        if not isinstance(v["network"]["host"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", v["network"]["host"]):
            raise ConfigError("network.host must be a hostname or IP without protocol/path")
        broker = v["broker"]
        if not isinstance(broker["host"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", broker["host"]):
            raise ConfigError("broker.host must be a hostname or IP without protocol/path")
        _number(broker["port"], "broker.port", 1, 65535, True)
        for key in ("username_env", "password_env"):
            if not isinstance(broker[key], str) or (broker[key] and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", broker[key])):
                raise ConfigError(f"broker.{key} must be an environment variable name")
        if bool(broker["username_env"]) != bool(broker["password_env"]):
            raise ConfigError("username_env and password_env must be configured together")
        bounds = {
            "load.terminals": (1, 10000, True), "load.messages_per_terminal": (1, 1000000, True),
            "load.ramp_up_seconds": (0, 86400, True), "load.interval_ms": (0, 3600000, True),
            "mqtt.qos": (0, 2, True), "mqtt.keepalive_seconds": (5, 65535, True),
            "mqtt.connect_timeout_seconds": (1, 120, True), "data.seed": (0, 2147483647, True),
            "data.padding_bytes": (0, 32768, True), "collection.drain_seconds": (0.1, 300, False),
            "collection.max_payload_bytes": (256, 1048576, True),
            "faults.invalid_every": (0, 1000000, True), "faults.drop_every": (0, 1000000, True),
            "faults.processing_delay_ms": (0, 10000, True),
            "thresholds.max_error_rate_pct": (0, 100, False),
            "thresholds.min_delivery_rate_pct": (0, 100, False),
            "thresholds.max_request_p95_ms": (0, 3600000, False),
            "thresholds.max_e2e_p95_ms": (0, 3600000, False),
            "thresholds.max_duplicates": (0, 100000000, True),
            "thresholds.max_out_of_order": (0, 100000000, True),
            "execution.timeout_seconds": (5, 604800, True),
            "network.port": (1, 65535, True), "network.connect_timeout_ms": (1, 120000, True),
            "network.response_timeout_ms": (10, 120000, True),
            "faults.response_drop_every": (0, 1000000, True),
            "faults.response_invalid_every": (0, 1000000, True),
            "faults.response_wrong_id_every": (0, 1000000, True),
            "faults.tcp_close_every": (0, 1000000, True),
            "http.port": (1, 65535, True), "http.connect_timeout_ms": (1, 120000, True),
            "http.response_timeout_ms": (10, 120000, True), "http.expected_status": (100, 599, True),
            "faults.http_error_every": (0, 1000000, True),
            "faults.udp_duplicate_every": (0, 1000000, True),
            "faults.tcp_fragment_bytes": (0, 65536, True),
        }
        for path, (low, high, integer) in bounds.items():
            section, key = path.split(".")
            _number(v[section][key], path, low, high, integer)
        if type(v["faults"]["udp_reorder_pairs"]) is not bool:
            raise ConfigError("faults.udp_reorder_pairs must be true or false")
        if not isinstance(v["http"]["host"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", v["http"]["host"]):
            raise ConfigError("http.host must be a hostname or IP without protocol/path")
        if not isinstance(v["http"]["path"], str) or not re.fullmatch(r"/[A-Za-z0-9_./%~-]*", v["http"]["path"]):
            raise ConfigError("http.path must be an absolute URL path without a query or fragment")
        if v["http"]["method"] not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise ConfigError("http.method must be GET, POST, PUT, PATCH or DELETE")
        auth_env = v["http"]["bearer_token_env"]
        if not isinstance(auth_env, str) or (auth_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", auth_env)):
            raise ConfigError("http.bearer_token_env must be an environment variable name")
        if v["protocol"] != "mqtt" and (v["faults"]["drop_every"] or v["collection"]["topic_stage"] != "up"):
            raise ConfigError("drop_every and collection.topic_stage apply only to MQTT")
        if v["protocol"] != "udp" and (v["faults"]["udp_duplicate_every"] or v["faults"]["udp_reorder_pairs"]):
            raise ConfigError("UDP response fault options require protocol udp")
        if v["protocol"] != "tcp" and (v["faults"]["tcp_fragment_bytes"] or v["faults"]["tcp_close_every"]):
            raise ConfigError("TCP fault options require protocol tcp")
        if v["protocol"] != "http" and v["faults"]["http_error_every"]:
            raise ConfigError("http_error_every requires protocol http")
        if v["protocol"] == "mqtt" and any(v["faults"][key] for key in ("response_drop_every", "response_invalid_every", "response_wrong_id_every")):
            raise ConfigError("Response fault options apply only to TCP/UDP lab endpoints")
        prefix = v["mqtt"]["topic_prefix"]
        if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z0-9_/-]{1,100}", prefix) or prefix.endswith("/"):
            raise ConfigError("mqtt.topic_prefix must be a non-wildcard ASCII topic prefix without trailing /")
        if not isinstance(v["collection"]["topic_stage"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", v["collection"]["topic_stage"]):
            raise ConfigError("collection.topic_stage must be a 1–32 character ASCII topic segment")
        if not isinstance(v["data"]["devices_csv"], str):
            raise ConfigError("data.devices_csv must be a path string")
        if type(v["execution"]["html_dashboard"]) is not bool:
            raise ConfigError("execution.html_dashboard must be true or false")
        estimated = v["load"]["ramp_up_seconds"] + v["load"]["messages_per_terminal"] * v["load"]["interval_ms"] / 1000
        if estimated + v["mqtt"]["connect_timeout_seconds"] + 3 >= v["execution"]["timeout_seconds"]:
            raise ConfigError("execution.timeout_seconds is too short for the configured ramp-up and message schedule")
        if v["data"]["padding_bytes"] + 1024 > v["collection"]["max_payload_bytes"]:
            raise ConfigError("max_payload_bytes is too small for padding_bytes plus message metadata")
        if v["load"]["terminals"] * v["load"]["messages_per_terminal"] > 1000000:
            raise ConfigError("A local run supports at most 1,000,000 expected messages; split larger experiments into runs")
        return cls(v, origin)

    @classmethod
    def load(cls, path: str | Path):
        path = Path(path).resolve()
        if path.stat().st_size > 1024 * 1024:
            raise ConfigError("Scenario file must be smaller than 1 MiB")
        try:
            values = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueSafeLoader)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML/JSON: {exc}") from exc
        return cls.from_mapping(values, path)

    @property
    def expected_messages(self):
        return self.values["load"]["terminals"] * self.values["load"]["messages_per_terminal"]

    def devices(self) -> list[dict]:
        count = self.values["load"]["terminals"]
        source = self.values["data"]["devices_csv"]
        if not source:
            return [{"device_id": f"dg-{i:05d}", "device_type": ["wearable", "home", "industrial"][i % 3],
                     "site": "dongguan"} for i in range(1, count + 1)]
        path = Path(source)
        if not path.is_absolute():
            path = (self.origin.parent if self.origin else Path.cwd()) / path
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or len(reader.fieldnames) != 3 or set(reader.fieldnames) != {"device_id", "device_type", "site"}:
                raise ConfigError("devices CSV must have exactly device_id,device_type,site headers")
            rows = list(islice(reader, count))
        if len(rows) < count:
            raise ConfigError(f"CSV has {len(rows)} devices, but {count} terminals were requested")
        selected = rows[:count]
        seen = set()
        for row in selected:
            for key, value in row.items():
                if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", value):
                    raise ConfigError(f"Invalid CSV {key}: {value!r}")
            if row["device_id"] in seen:
                raise ConfigError(f"Duplicate device_id: {row['device_id']}")
            seen.add(row["device_id"])
        return selected

    def write(self, path: Path):
        path.write_text(json.dumps(self.values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
