"""Execute one isolated, auditable JMeter experiment and always preserve evidence."""
from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .collector import CollectionState, Collector, credentials
from .metrics import evaluate, read_jtl
from .network_receipts import read_receipts
from .plans import compile_plan
from .reporting import write_report
from .runtime import Runtime, launch, sha256, terminate


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_scenario(scenario, workspace: Path, results_root: Path | None = None):
    runtime = Runtime(workspace)
    runtime.require()
    is_mqtt = scenario.values["protocol"] == "mqtt"
    if is_mqtt:
        credentials(scenario)
    if scenario.values["protocol"] == "http":
        token = scenario.values["http"]["bearer_token_env"]
        if token and not os.environ.get(token):
            raise ValueError(f"Required environment variable is not set: {token}")
    scenario.devices()
    run_id = uuid.uuid4().hex[:16]
    directory = (results_root or workspace / "results/runs") / f'{scenario.values["name"]}-{run_id}'
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    started = timestamp()
    manifest = {"run_id": run_id, "scenario_name": scenario.values["name"], "started_at": started,
                "state": "preparing", "directory": str(directory)}

    def event(stage, detail):
        item = {"time": timestamp(), "stage": stage, "detail": detail}
        with (directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        manifest["state"] = stage
        atomic_json(directory / "run.json", manifest)
        print(f"[{stage}] {detail}", file=sys.stderr, flush=True)

    event("preparing", f"run_id={run_id}")
    plan, devices = compile_plan(scenario, directory, run_id)
    props = directory / "jmeter.properties"
    props.write_text("\n".join([
        "jmeter.save.saveservice.output_format=csv", "jmeter.save.saveservice.print_field_names=true",
        "jmeter.save.saveservice.timestamp_format=ms", "jmeter.save.saveservice.assertion_results_failure_message=true",
        "jmeter.save.saveservice.autoflush=true", "jmeter.save.saveservice.hostname=false",
        "jmeter.reportgenerator.overall_granularity=1000", "jmeterengine.nongui.port=0",
    ]) + "\n", encoding="utf-8")
    args = ["-n", "-t", plan, "-q", props, "-l", directory / "samples.jtl", "-j", directory / "jmeter.log"]
    if scenario.values["execution"]["html_dashboard"]:
        args += ["-e", "-o", directory / "dashboard"]
    command = runtime.command(args)
    atomic_json(directory / "provenance.json", {"python": platform.python_version(), "os": platform.platform(),
                "linklab_version": "1.0.0", "jmeter_home": str(runtime.jmeter_home),
                "plan_sha256": sha256(plan), "scenario_sha256": sha256(directory / "scenario.json"),
                "devices_sha256": sha256(directory / "devices.csv"), "command": command})
    collector = Collector(scenario, run_id, devices, directory / "collected.jsonl") if is_mqtt else None
    process = None
    exit_code = None
    error = ""
    timed_out = cancelled = False
    wall_start = time.monotonic()
    try:
        if collector:
            event("subscribing", "等待独立采集器连接并确认 SUBACK")
            collector.start()
        event("running", f"启动 JMeter，终端数 {len(devices)}，预期消息 {scenario.expected_messages}")
        with (directory / "console.log").open("w", encoding="utf-8") as console:
            process = launch(command, workspace, console)
            sampled = psutil.Process(process.pid)
            sampled.cpu_percent()
            psutil.cpu_percent()
            deadline = time.monotonic() + scenario.values["execution"]["timeout_seconds"]
            with (directory / "resources.csv").open("w", encoding="utf-8", newline="") as resource_file:
                writer = csv.writer(resource_file)
                writer.writerow(["time_utc", "jmeter_cpu_pct", "jmeter_rss_bytes", "host_cpu_pct", "host_memory_pct"])
                while process.poll() is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, scenario.values["execution"]["timeout_seconds"])
                    try:
                        writer.writerow([timestamp(), sampled.cpu_percent(), sampled.memory_info().rss,
                                         psutil.cpu_percent(), psutil.virtual_memory().percent])
                        resource_file.flush()
                    except psutil.NoSuchProcess:
                        break
                    except psutil.Error:
                        # Sandboxed hosts may deny process counters; test execution still has a deadline.
                        exit_code = process.wait(timeout=max(0.01, remaining))
                        break
                    try:
                        process.wait(timeout=min(0.5, remaining))
                    except subprocess.TimeoutExpired:
                        pass
                exit_code = process.wait(timeout=1)
        if exit_code != 0:
            error = f"JMeter exited with status {exit_code}; inspect console.log and jmeter.log"
    except subprocess.TimeoutExpired:
        timed_out = True
        error = "JMeter execution timeout; process tree terminated"
    except KeyboardInterrupt:
        cancelled = True
        error = "Cancelled by operator"
    except (OSError, RuntimeError, ValueError) as exc:
        # Include the exception class; credentials are never included in our messages.
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if process and process.poll() is None:
            terminate(process)
            exit_code = process.returncode
        event("draining", "收尾采集与原始证据落盘")
        collection = collector.close(drain=not cancelled and not timed_out) if collector else read_receipts(scenario, run_id, devices, directory)
    try:
        jtl = read_jtl(directory / "samples.jtl")
    except ValueError as exc:
        error = error or str(exc)
        jtl = read_jtl(directory / "missing.jtl")
    acceptance = evaluate(scenario, jtl, collection, exit_code=exit_code, timed_out=timed_out)
    if (directory / "observer.json").exists():
        observer = json.loads((directory / "observer.json").read_text(encoding="utf-8"))
    else:
        observer = {"received": 0, "ready": False, "terminals_finished": 0}
    extra = [{"name": "订阅探针就绪", "actual": observer["ready"], "operator": "==", "expected": True,
              "passed": observer["ready"] is True},
             {"name": "订阅探针观测消息数", "actual": observer["received"], "operator": ">=",
              "expected": scenario.expected_messages, "passed": observer["received"] >= scenario.expected_messages}] if is_mqtt else []
    if scenario.values["execution"]["html_dashboard"]:
        exists = (directory / "dashboard/index.html").is_file()
        extra.append({"name": "JMeter HTML 仪表盘", "actual": exists, "operator": "==", "expected": True, "passed": exists})
    acceptance["gates"] += extra
    acceptance["passed"] = not error and not cancelled and all(g["passed"] for g in acceptance["gates"])
    status = "cancelled" if cancelled else "timeout" if timed_out else "error" if error else "passed" if acceptance["passed"] else "failed"
    label = {"mqtt": "MQTT Publish", "tcp": "TCP Request", "udp": "UDP Request", "http": "HTTP Request"}[scenario.values["protocol"]]
    publish_count = jtl["labels"].get(label, {}).get("count", 0)
    summary = {"run_id": run_id, "scenario_name": scenario.values["name"], "started_at": started,
               "finished_at": timestamp(), "protocol": scenario.values["protocol"], "status": status, "error": error, "jmeter_exit_code": exit_code,
               "wall_seconds": time.monotonic() - wall_start, "expected_messages": scenario.expected_messages,
               "load": scenario.values["load"], "faults": scenario.values["faults"],
               "mqtt": scenario.values["mqtt"], "collection_stage": scenario.values["collection"]["topic_stage"],
               "jmeter": jtl, "collection": collection, "observer": observer, "acceptance": acceptance,
               "message_throughput_per_second": publish_count / jtl["duration_seconds"] if jtl["duration_seconds"] else None,
               "directory": str(directory)}
    write_report(directory, summary)
    event(status, f"报告: {directory / 'report.html'}")
    return summary
