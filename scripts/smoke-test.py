#!/usr/bin/env python3
"""Run an offline JMeter installation check against a temporary loopback server."""
import csv
import json
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        request = urlsplit(self.path)
        device = parse_qs(request.query).get("device_id", [""])[0]
        valid = request.path == "/health" and device.startswith("dg-device-")
        body = json.dumps({"status": "ok" if valid else "error", "device_id": device}).encode()
        self.send_response(200 if valid else 400)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S-%f")
    output = ROOT / "results" / f"smoke-{stamp}"
    output.mkdir(parents=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    command = [str(ROOT / "jmeter"), "-n", "-t", str(ROOT / "test-plans/local-smoke.jmx"),
               "-l", str(output / "samples.jtl"), "-j", str(output / "jmeter.log"),
               "-Jthreads=2", "-Jloops=5", "-Jrampup=1",
               f"-Jsmoke_port={server.server_port}",
               f"-Jdevice_csv={ROOT / 'test-plans/devices.csv'}",
               "-e", "-o", str(output / "report")]
    print(f"Local server: 127.0.0.1:{server.server_port}", flush=True)
    print(f"Results: {output}", flush=True)
    try:
        with (output / "console.log").open("w") as console:
            result = subprocess.run(command, cwd=ROOT, stdout=console,
                                    stderr=subprocess.STDOUT, timeout=120)
        print((output / "console.log").read_text())
        if result.returncode:
            raise RuntimeError(f"JMeter exited with status {result.returncode}; see {output}")
        with (output / "samples.jtl").open(newline="") as samples:
            rows = list(csv.DictReader(samples))
        failed = [row for row in rows if row["success"].lower() != "true"]
        if len(rows) != 10 or failed:
            raise RuntimeError(f"Expected 10 successful samples; got {len(rows)}, failures={failed}")
        stats = json.loads((output / "report/statistics.json").read_text())
        total = stats["Total"]
        if not (output / "report/index.html").is_file():
            raise RuntimeError("HTML report was not generated")
        summary = {"passed": True, "samples": len(rows), "errors": len(failed),
                   "error_rate_percent": total["errorPct"],
                   "mean_response_ms": total["meanResTime"],
                   "throughput_per_second": total["throughput"],
                   "report": str(output / "report/index.html")}
        (output / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
        latest = ROOT / "results/latest-smoke"
        if latest.is_symlink():
            latest.unlink()
        if not latest.exists():
            latest.symlink_to(output.name, target_is_directory=True)
        print(json.dumps(summary, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
