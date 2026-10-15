"""Streaming JTL statistics and explicit acceptance gates."""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


class Distribution:
    def __init__(self):
        self.buckets = Counter()
        self.count = 0
        self.total = 0

    def add(self, value):
        value = max(0, int(round(value)))
        self.buckets[value] += 1
        self.count += 1
        self.total += value

    def percentile(self, percentile):
        if not self.count:
            return None
        target = max(1, math.ceil(self.count * percentile / 100))
        current = 0
        for value, count in sorted(self.buckets.items()):
            current += count
            if current >= target:
                return value
        raise AssertionError("Invalid distribution")

    def summary(self):
        return {"count": self.count, "mean_ms": self.total / self.count if self.count else None,
                "min_ms": min(self.buckets) if self.count else None,
                "max_ms": max(self.buckets) if self.count else None,
                "p50_ms": self.percentile(50), "p95_ms": self.percentile(95),
                "p99_ms": self.percentile(99)}


def read_jtl(path: Path):
    groups = defaultdict(lambda: {"latency": Distribution(), "errors": 0, "bytes": 0})
    errors = Counter()
    series = defaultdict(lambda: {"samples": 0, "errors": 0})
    first = None
    last = None
    peak_active = None
    if not path.exists():
        return {"samples": 0, "errors": 0, "error_rate_pct": None, "duration_seconds": 0,
                "throughput_per_second": None, "labels": {}, "errors_by_message": {}, "series": []}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"timeStamp", "elapsed", "label", "success", "responseCode"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("JTL does not contain required CSV columns")
        for number, row in enumerate(reader, 2):
            try:
                timestamp, elapsed = int(row["timeStamp"]), int(row["elapsed"])
                if timestamp < 0 or elapsed < 0 or row["success"].lower() not in ("true", "false"):
                    raise ValueError("Invalid timestamp, elapsed or success")
                failed = row["success"].lower() != "true"
                group = groups[row["label"]]
                group["latency"].add(elapsed)
                group["errors"] += int(failed)
                group["bytes"] += int(row.get("bytes") or 0)
                first = timestamp if first is None else min(first, timestamp)
                last = timestamp + elapsed if last is None else max(last, timestamp + elapsed)
                if row["label"] in ("MQTT Publish", "TCP Request", "UDP Request", "HTTP Request"):
                    if row.get("grpThreads"):
                        peak_active = max(peak_active or 0, int(row["grpThreads"]))
                    series[timestamp // 1000]["samples"] += 1
                    series[timestamp // 1000]["errors"] += int(failed)
                if failed:
                    message = row.get("failureMessage") or row.get("responseMessage") or "Unknown error"
                    errors[f'{row["label"]} [{row["responseCode"]}]: {message}'] += 1
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Invalid JTL row {number}: {exc}") from exc
    labels = {label: {**group["latency"].summary(), "errors": group["errors"],
                      "error_rate_pct": group["errors"] / group["latency"].count * 100,
                      "received_bytes": group["bytes"]} for label, group in groups.items()}
    samples = sum(g["count"] for g in labels.values())
    failures = sum(g["errors"] for g in labels.values())
    duration = (last - first) / 1000 if first is not None else 0
    return {"samples": samples, "errors": failures,
            "error_rate_pct": failures / samples * 100 if samples else None,
            "duration_seconds": duration,
            "peak_active_terminals": peak_active,
            "throughput_per_second": samples / duration if duration > 0 else None,
            "labels": labels, "errors_by_message": dict(errors.most_common(30)),
            "series": [{"timestamp_seconds": k, **v} for k, v in sorted(series.items())]}


def evaluate(scenario, jtl, collection, *, exit_code, timed_out=False):
    v = scenario.values
    gates = []

    def add(name, actual, operator, expected):
        ok = actual is not None and {"<=": lambda: actual <= expected,
                                     ">=": lambda: actual >= expected,
                                     "==": lambda: actual == expected}[operator]()
        gates.append({"name": name, "actual": actual, "operator": operator,
                      "expected": expected, "passed": bool(ok)})

    add("JMeter 正常退出", exit_code, "==", 0)
    add("未触发执行超时", timed_out, "==", False)
    protocol = v["protocol"]
    if protocol == "mqtt":
        add("连接采样数", jtl["labels"].get("MQTT Connect", {}).get("count", 0), "==", v["load"]["terminals"])
        add("断开采样数", jtl["labels"].get("MQTT Disconnect", {}).get("count", 0), "==", v["load"]["terminals"])
    label = {"mqtt": "MQTT Publish", "tcp": "TCP Request", "udp": "UDP Request", "http": "HTTP Request"}[protocol]
    publish = jtl["labels"].get(label, {})
    add("业务采样数", publish.get("count", 0), "==", scenario.expected_messages)
    add("采样错误率 %", jtl["error_rate_pct"], "<=", v["thresholds"]["max_error_rate_pct"])
    add("业务请求 P95 ms", publish.get("p95_ms"), "<=", v["thresholds"]["max_request_p95_ms"])
    add("有效消息完整率 %", collection.get("delivery_rate_pct"), ">=", v["thresholds"]["min_delivery_rate_pct"])
    add("采集处理 P95 ms", collection.get("e2e", {}).get("p95_ms"), "<=", v["thresholds"]["max_e2e_p95_ms"])
    add("非法消息", collection.get("invalid", 0), "==", 0)
    add("重复消息", collection.get("duplicates", 0), "<=", v["thresholds"]["max_duplicates"])
    add("乱序消息", collection.get("out_of_order", 0), "<=", v["thresholds"]["max_out_of_order"])
    add("采集队列溢出", collection.get("queue_overflows", 0), "==", 0)
    add("采集线程健康", collection.get("worker_error"), "==", "")
    return {"passed": all(g["passed"] for g in gates), "gates": gates}
