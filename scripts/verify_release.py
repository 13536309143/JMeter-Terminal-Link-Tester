#!/usr/bin/env python3
"""Verify an extracted runtime using fixtures supplied by the source checkout."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from linklab.config import Scenario
from linklab.demo_broker import DemoBroker
from linklab.network import reference_endpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--evidence", type=Path, default=Path("results/release-verification"))
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    executable = bundle / ("jmeter-link-tester.exe" if os.name == "nt" else "jmeter-link-tester")
    environment = {**os.environ, "JAVA_HOME": "/invalid-system-java", "JMETER_HOME": "/invalid-system-jmeter"}
    environment.pop("PYTHONPATH", None)
    doctor = subprocess.run([str(executable), "doctor"], cwd=bundle, env=environment, text=True, encoding="utf-8", capture_output=True, timeout=60)
    (evidence / "doctor.json").write_text(doctor.stdout, encoding="utf-8")
    if doctor.returncode or not json.loads(doctor.stdout)["passed"]:
        raise RuntimeError(f"Bundled runtime check failed: {doctor.stderr} {doctor.stdout}")
    cases = []
    for protocol in ("mqtt", "tcp", "udp", "http"):
        for negative in ([False, True] if protocol == "http" else [False]):
            values = {"protocol": protocol, "name": f"packaged-{protocol}" + ("-error" if negative else ""),
                      "load": {"terminals": 2, "messages_per_terminal": 3, "ramp_up_seconds": 0, "interval_ms": 25}}
            if negative:
                values["faults"] = {"http_error_every": 2}
            scenario = Scenario.from_mapping(values)
            fixture = DemoBroker() if protocol == "mqtt" else reference_endpoint(scenario)
            with fixture as endpoint:
                section = "broker" if protocol == "mqtt" else "http" if protocol == "http" else "network"
                values[section] = {"host": "127.0.0.1", "port": endpoint.port}
                scenario = Scenario.from_mapping(values)
                file = evidence / f'{values["name"]}.json'
                scenario.write(file)
                result = subprocess.run([str(executable), "run", str(file), "--results", str(evidence / "runs")],
                                        cwd=bundle, env=environment, text=True, encoding="utf-8", capture_output=True, timeout=150)
            (evidence / f'{values["name"]}-stdout.json').write_text(result.stdout, encoding="utf-8")
            (evidence / f'{values["name"]}-stderr.log').write_text(result.stderr, encoding="utf-8")
            summary = json.loads(result.stdout)
            passed = result.returncode == (3 if negative else 0) and summary["acceptance"]["passed"] == (not negative)
            cases.append({"protocol": protocol, "negative": negative, "passed": passed,
                          "valid_messages": summary["collection"]["valid_unique"]})
            if not passed:
                raise RuntimeError(f"Packaged {protocol} verification failed; evidence: {evidence}")
    report = {"passed": all(c["passed"] for c in cases), "cases": cases, "platform": sys.platform}
    (evidence / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
