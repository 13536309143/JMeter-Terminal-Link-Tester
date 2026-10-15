"""Production command surface. Development servers and experiment suites are separate."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from . import __version__
from .config import ConfigError, Scenario
from .plans import compile_plan
from .reporting import compare_results, write_report
from .runner import atomic_json, run_scenario
from .runtime import Runtime


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(os.environ.get("LINKLAB_WORKSPACE", Path.cwd()))
    if getattr(sys, "frozen", False):
        os.environ["JAVA_HOME"] = str(root / "runtime/jdk" / ("Contents/Home" if sys.platform == "darwin" else ""))
        os.environ["JMETER_HOME"] = str(root / "runtime/apache-jmeter-5.6.3")
    parser = argparse.ArgumentParser(prog="jmeter-link-tester", description="JMeter Terminal & Link Tester — MQTT / TCP / UDP / HTTP")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", type=Path, default=root)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="Check bundled Java, JMeter and MQTT plugin")
    for action in ("validate", "plan", "run"):
        sub = commands.add_parser(action)
        sub.add_argument("scenario", type=Path)
        if action == "plan":
            sub.add_argument("--output", type=Path, required=True)
        if action == "run":
            sub.add_argument("--results", type=Path)
    gui = commands.add_parser("gui", help="Open the native JMeter GUI")
    gui.add_argument("plan", type=Path, nargs="?")
    report = commands.add_parser("report")
    report.add_argument("run_directory", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path)
    history = commands.add_parser("runs")
    history.add_argument("--results", type=Path)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    workspace = args.workspace.resolve()
    emit = lambda value: print(json.dumps(value, ensure_ascii=False, indent=2))
    try:
        if args.command == "doctor":
            checks = Runtime(workspace).check()
            passed = all(c["ok"] for c in checks)
            emit({"passed": passed, "checks": checks})
            return 0 if passed else 1
        if args.command in ("validate", "plan", "run"):
            scenario = Scenario.load(args.scenario)
            devices = scenario.devices()
            if args.command == "validate":
                emit({"valid": True, "protocol": scenario.values["protocol"], "devices": len(devices),
                      "expected_messages": scenario.expected_messages})
            elif args.command == "plan":
                plan, _ = compile_plan(scenario, args.output.resolve(), uuid.uuid4().hex[:16])
                emit({"plan": str(plan)})
            else:
                result = run_scenario(scenario, workspace, args.results)
                emit(result)
                return {"passed": 0, "failed": 3, "error": 1, "timeout": 4, "cancelled": 130}[result["status"]]
        elif args.command == "gui":
            runtime = Runtime(workspace)
            runtime.require()
            (workspace / "logs").mkdir(exist_ok=True)
            params = ["-j", workspace / "logs/jmeter-gui.log"]
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
            emit([json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*/run.json"), key=lambda p:p.stat().st_mtime, reverse=True)])
    except KeyboardInterrupt:
        return 130
    except (ConfigError, OSError, ValueError, RuntimeError) as exc:
        emit({"error": str(exc), "type": type(exc).__name__})
        return 2 if isinstance(exc, (ConfigError, ValueError)) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
