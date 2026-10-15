"""Public CLI. Exit codes: 0 pass, 1 execution, 2 config, 3 gate, 4 timeout, 130 cancel."""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path

from . import __version__
from .config import ConfigError, Scenario
from .demo_broker import DemoBroker
from .plans import compile_plan
from .pipeline import PersistenceBridge
from .network import ReferenceEndpoint, reference_endpoint
from .reporting import compare_results, write_report
from .runner import atomic_json, run_scenario, timestamp
from .runtime import Runtime


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser():
    command = argparse.ArgumentParser(prog="linklab", description="终端模拟与数据采集链路测试 · JMeter + EMQX MQTT plugin")
    command.add_argument("--version", action="version", version=__version__)
    command.add_argument("--workspace", type=Path, default=Path(os.environ.get("LINKLAB_WORKSPACE", Path.cwd())))
    sub = command.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="检查 Java、JMeter 和 MQTT 插件")
    for name in ("validate", "plan", "run"):
        item = sub.add_parser(name, help={"validate": "校验场景与终端 CSV", "plan": "生成可编辑的 JMX", "run": "运行场景并执行验收门禁"}[name])
        item.add_argument("scenario", type=Path)
        if name == "plan":
            item.add_argument("--output", type=Path, required=True)
        if name == "run":
            item.add_argument("--results", type=Path)
    demo = sub.add_parser("demo", help="自动启动回环 MQTT Broker 并完成真实 MQTT 实验")
    demo.add_argument("--scenario", type=Path)
    demo.add_argument("--protocol", choices=["mqtt", "tcp", "udp", "http"])
    demo.add_argument("--results", type=Path)
    persistence = sub.add_parser("pipeline-demo", help="验证 MQTT 上报 → SQLite 提交 → MQTT 回执的完整链路")
    persistence.add_argument("--results", type=Path)
    bridge = sub.add_parser("bridge", help="运行 SQLite 采集参考服务并发送提交后的回执")
    bridge.add_argument("scenario", type=Path)
    bridge.add_argument("--database", type=Path, required=True)
    server = sub.add_parser("serve", help="运行 TCP/UDP 回环参考服务端")
    server.add_argument("scenario", type=Path)
    lab = sub.add_parser("broker", help="运行仅供本地实验的回环 MQTT Broker")
    lab.add_argument("--port", type=int, default=1883)
    gui = sub.add_parser("gui", help="用 JMeter 原生图形界面打开生成的 JMX")
    gui.add_argument("plan", type=Path, nargs="?")
    report = sub.add_parser("report", help="从汇总数据重新生成 HTML/Markdown 报告")
    report.add_argument("run_directory", type=Path)
    compare = sub.add_parser("compare", help="比较两次测试的耗时、完整率与吞吐量")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path)
    runs = sub.add_parser("runs", help="列出保留的运行记录")
    runs.add_argument("--results", type=Path)
    experiments = sub.add_parser("experiments", help="执行正常、并发和故障注入实验矩阵")
    experiments.add_argument("--results", type=Path)
    experiments.add_argument("--protocol", choices=["mqtt", "tcp", "udp", "http", "all"], default="all")
    return command


def result_code(result):
    return {"passed": 0, "failed": 3, "error": 1, "timeout": 4, "cancelled": 130}[result["status"]]


def experiments(workspace, results, selected="all"):
    concurrent = {"terminals": 50, "messages_per_terminal": 20, "ramp_up_seconds": 1}
    small = {"terminals": 2, "messages_per_terminal": 6, "ramp_up_seconds": 0, "interval_ms": 10}
    cases = [("mqtt", "mqtt-baseline", {}, True, None),
             ("mqtt", "mqtt-concurrent-50", {"load": concurrent}, True, ("peak_active_terminals", 50)),
             ("mqtt", "mqtt-invalid-payload", {"faults": {"invalid_every": 3}}, False, ("invalid", 15)),
             ("mqtt", "mqtt-collection-drop", {"faults": {"drop_every": 4}}, False, ("injected_drops", 10)),
             ("mqtt", "mqtt-processing-delay", {"load": {"terminals": 2, "messages_per_terminal": 5},
                                                "faults": {"processing_delay_ms": 80},
                                                "thresholds": {"max_e2e_p95_ms": 40}}, False, ("e2e_p95_ms", 41))]
    for protocol in ("tcp", "udp", "http"):
        cases += [(protocol, f"{protocol}-baseline", {}, True, None),
                  (protocol, f"{protocol}-concurrent-50", {"load": concurrent}, True, ("peak_active_terminals", 50)),
                  (protocol, f"{protocol}-invalid-response", {"load": small, "faults": {"response_invalid_every": 2}}, False, ("invalid", 6)),
                  (protocol, f"{protocol}-wrong-message-id", {"load": small, "network": {"response_timeout_ms": 150},
                                                            "faults": {"response_wrong_id_every": 2}}, False, ("invalid", 6)),
                  (protocol, f"{protocol}-response-loss", {"load": small, "network": {"response_timeout_ms": 150},
                                                          "faults": {"response_drop_every": 2}}, False, ("missing", 6)),
                  (protocol, f"{protocol}-processing-delay", {"load": small, "faults": {"processing_delay_ms": 100},
                                                             "thresholds": {"max_e2e_p95_ms": 40}}, False, ("e2e_p95_ms", 41))]
    cases += [("tcp", "tcp-fragmented", {"load": small, "faults": {"tcp_fragment_bytes": 7}}, True, None),
              ("tcp", "tcp-abrupt-close", {"load": small, "faults": {"tcp_close_every": 2}}, False, ("missing", 6)),
              ("udp", "udp-duplicates", {"load": small, "faults": {"udp_duplicate_every": 2}}, False, ("duplicates", 6)),
              ("udp", "udp-reordered", {"load": small, "network": {"response_timeout_ms": 150},
                                         "faults": {"udp_reorder_pairs": True}}, False, ("out_of_order", 2)),
              ("udp", "udp-large-payload", {"load": small, "data": {"padding_bytes": 4096}}, True, None)]
    for method in ("GET", "PUT", "PATCH", "DELETE"):
        cases.append(("http", f"http-{method.lower()}", {"load": small, "http": {"method": method}}, True, None))
    cases.append(("http", "http-error-status", {"load": small, "faults": {"http_error_every": 2}}, False, ("invalid", 6)))
    entries = []
    for protocol, name, overrides, expected, signal in cases:
        if selected != "all" and protocol != selected:
            continue
        values = {"protocol": protocol, "name": name, **deepcopy(overrides)}
        scenario = Scenario.from_mapping(values)
        fixture = DemoBroker() if protocol == "mqtt" else reference_endpoint(scenario)
        with fixture as endpoint:
            section = "broker" if protocol == "mqtt" else "http" if protocol == "http" else "network"
            values.setdefault(section, {}).update({"host": "127.0.0.1", "port": endpoint.port})
            scenario = Scenario.from_mapping(values)
            result = run_scenario(scenario, workspace, results)
        observed = result["acceptance"]["passed"]
        signals = {**result["collection"], "peak_active_terminals": result["jmeter"].get("peak_active_terminals"),
                   "e2e_p95_ms": result["collection"]["e2e"]["p95_ms"]}
        signal_ok = signal is None or (signals.get(signal[0]) is not None and signals[signal[0]] >= signal[1])
        matched = observed == expected and result["status"] in ("passed", "failed") and signal_ok
        entries.append({"case": name, "protocol": protocol, "expected_acceptance": expected, "actual_acceptance": observed,
                        "matched": matched, "signal": signal, "signal_verified": signal_ok,
                        "run_id": result["run_id"], "directory": result["directory"],
                        "delivery_rate_pct": result["collection"]["delivery_rate_pct"],
                        "peak_active_terminals": result["jmeter"].get("peak_active_terminals"),
                        "e2e_p95_ms": result["collection"]["e2e"]["p95_ms"]})
    report = {"time": timestamp(), "passed": all(e["matched"] for e in entries), "cases": entries}
    output = results or workspace / "results/runs"
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "experiments.json", report)
    return report


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    workspace = args.workspace.resolve()
    logging.basicConfig(level=logging.ERROR, format="%(name)s: %(message)s")
    try:
        if args.command == "doctor":
            checks = Runtime(workspace).check()
            emit({"passed": all(c["ok"] for c in checks), "checks": checks})
            return 0 if all(c["ok"] for c in checks) else 1
        if args.command in ("validate", "plan", "run"):
            scenario = Scenario.load(args.scenario)
            devices = scenario.devices()
            if args.command == "validate":
                emit({"valid": True, "scenario": scenario.values, "devices": len(devices),
                      "expected_messages": scenario.expected_messages})
            elif args.command == "plan":
                plan, _ = compile_plan(scenario, args.output.resolve(), uuid.uuid4().hex[:16])
                emit({"plan": str(plan), "note": "Use run for independent collection and acceptance; GUI is for editing/debugging."})
            else:
                result = run_scenario(scenario, workspace, args.results)
                emit(result)
                return result_code(result)
        elif args.command == "demo":
            original = Scenario.load(args.scenario) if args.scenario else Scenario.from_mapping({"name": f"local-{args.protocol or 'mqtt'}-demo"})
            values = deepcopy(original.values)
            if args.protocol:
                values["protocol"] = args.protocol
            if values["protocol"] == "mqtt":
                with DemoBroker() as broker:
                    values["broker"] = {"host": "127.0.0.1", "port": broker.port, "username_env": "", "password_env": ""}
                    scenario = Scenario.from_mapping(values, original.origin)
                    result = run_scenario(scenario, workspace, args.results)
            else:
                scenario = Scenario.from_mapping(values, original.origin)
                with reference_endpoint(scenario) as endpoint:
                    section = "http" if values["protocol"] == "http" else "network"
                    values[section].update({"host": "127.0.0.1", "port": endpoint.port})
                    scenario = Scenario.from_mapping(values, original.origin)
                    result = run_scenario(scenario, workspace, args.results)
            emit(result)
            return result_code(result)
        elif args.command == "broker":
            if not 1 <= args.port <= 65535:
                raise ConfigError("port must be in [1, 65535]")
            with DemoBroker(args.port) as broker:
                print(f"Lab broker: 127.0.0.1:{broker.port}; Ctrl+C to stop", flush=True)
                while True:
                    time.sleep(1)
        elif args.command == "pipeline-demo":
            destination = args.results or workspace / "results/runs"
            database = destination / "persistence" / uuid.uuid4().hex[:16] / "collector.sqlite3"
            with DemoBroker() as broker:
                scenario = Scenario.from_mapping({"name": "persistence-chain", "broker": {"port": broker.port},
                                                  "collection": {"topic_stage": "persisted"}})
                with PersistenceBridge(scenario, database) as bridge:
                    result = run_scenario(scenario, workspace, destination)
                if bridge.error:
                    result["acceptance"]["passed"] = False
                    result["status"] = "error"
                    result["error"] = bridge.error
                result["persistence_database"] = str(database.resolve())
                write_report(Path(result["directory"]), result)
            emit(result)
            return result_code(result)
        elif args.command == "bridge":
            scenario = Scenario.load(args.scenario)
            with PersistenceBridge(scenario, args.database) as bridge:
                print(f"Persistence bridge: {bridge.database}; Ctrl+C to stop", flush=True)
                while not bridge.error:
                    time.sleep(0.5)
                raise RuntimeError(bridge.error)
        elif args.command == "serve":
            scenario = Scenario.load(args.scenario)
            section = "http" if scenario.values["protocol"] == "http" else "network"
            with reference_endpoint(scenario, scenario.values[section]["port"]) as endpoint:
                print(f"Lab {endpoint.protocol.upper()} endpoint: 127.0.0.1:{endpoint.port}; Ctrl+C to stop", flush=True)
                while True:
                    time.sleep(1)
        elif args.command == "gui":
            runtime = Runtime(workspace)
            runtime.require()
            (workspace / "logs").mkdir(exist_ok=True)
            params = ["-j", workspace / "logs/linklab-gui.log"]
            if args.plan:
                params += ["-t", args.plan.resolve()]
            return subprocess.call(runtime.command(params, gui=True), cwd=workspace)
        elif args.command == "report":
            result = json.loads((args.run_directory / "summary.json").read_text(encoding="utf-8"))
            write_report(args.run_directory, result)
            emit({"report": str((args.run_directory / "report.html").resolve())})
        elif args.command == "compare":
            result = compare_results(args.baseline, args.candidate)
            if args.output:
                atomic_json(args.output, result)
            emit(result)
        elif args.command == "runs":
            root = args.results or workspace / "results/runs"
            entries = []
            for file in sorted(root.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    entries.append(json.loads(file.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    pass
            emit(entries)
        elif args.command == "experiments":
            result = experiments(workspace, args.results, args.protocol)
            emit(result)
            return 0 if result["passed"] else 3
    except KeyboardInterrupt:
        return 130
    except (ConfigError, OSError, ValueError, RuntimeError) as exc:
        emit({"error": str(exc), "type": type(exc).__name__})
        return 2 if isinstance(exc, (ConfigError, ValueError)) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
