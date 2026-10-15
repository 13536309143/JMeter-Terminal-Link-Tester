"""Cross-platform Java invocation, process lifecycle and installation checks."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import zipfile
from pathlib import Path

JMETER_VERSION = "5.6.3"
PLUGIN_NAME = "mqtt-xmeter-2.0.2-jar-with-dependencies.jar"
PLUGIN_SHA256 = "979bc63e8a026996561d6f7f255bc32aa83d298d7d0a7f51a820361dd5afb0cd"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Runtime:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.jmeter_home = Path(os.environ.get("JMETER_HOME") or self.workspace / "runtime" / f"apache-jmeter-{JMETER_VERSION}").resolve()
        java_home = os.environ.get("JAVA_HOME")
        candidates = [Path(java_home) / "bin" if java_home else Path("/nonexistent"),
                      self.workspace / "runtime/jdk/Contents/Home/bin", self.workspace / "runtime/jdk/bin"]
        executable = "java.exe" if os.name == "nt" else "java"
        self.java = next((str(p / executable) for p in candidates if (p / executable).is_file()), shutil.which("java") or "java")

    def check(self):
        checks = []
        try:
            result = subprocess.run([self.java, "-version"], capture_output=True, text=True, timeout=15)
            text = result.stderr + result.stdout
            match = re.search(r'version "(\d+)', text)
            ok = result.returncode == 0 and match is not None and int(match.group(1)) >= 17
            checks.append({"name": "JDK 17+", "ok": ok, "detail": text.strip().splitlines()[0] if text.strip() else "No output"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append({"name": "JDK 17+", "ok": False, "detail": str(exc)})
        jar = self.jmeter_home / "bin/ApacheJMeter.jar"
        version_ok = False
        if jar.is_file():
            try:
                with zipfile.ZipFile(jar) as archive:
                    manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8")
                version_ok = bool(re.search(rf"^Implementation-Version: {re.escape(JMETER_VERSION)}\s*$", manifest, re.MULTILINE))
            except (OSError, KeyError, zipfile.BadZipFile):
                pass
        checks.append({"name": f"JMeter {JMETER_VERSION}", "ok": version_ok, "detail": str(jar)})
        plugin = self.jmeter_home / "lib/ext" / PLUGIN_NAME
        valid_plugin = False
        if plugin.is_file():
            try:
                with zipfile.ZipFile(plugin) as archive:
                    valid_plugin = "net/xmeter/samplers/SubSampler.class" in archive.namelist() and sha256(plugin) == PLUGIN_SHA256
            except (OSError, zipfile.BadZipFile):
                pass
        checks.append({"name": "EMQX MQTT plugin 2.0.2", "ok": valid_plugin, "detail": str(plugin)})
        return checks

    def require(self):
        failures = [f'{c["name"]}: {c["detail"]}' for c in self.check() if not c["ok"]]
        if failures:
            raise RuntimeError("Environment check failed:\n" + "\n".join(failures) + "\nRun scripts/bootstrap.py first.")

    def command(self, arguments, *, gui=False):
        options = ["-Xms256m", f'-Xmx{os.environ.get("LINKLAB_HEAP", "1g")}',
                   f'-Duser.language={"zh" if gui else "en"}', f'-Duser.country={"CN" if gui else "US"}', "-Dfile.encoding=UTF-8",
                   "--add-opens=java.base/java.lang=ALL-UNNAMED",
                   "--add-opens=java.base/java.util=ALL-UNNAMED"]
        if not gui:
            options.append("-Djava.awt.headless=true")
        return [self.java, *options, "-jar", str(self.jmeter_home / "bin/ApacheJMeter.jar"),
                "-d", str(self.jmeter_home), *map(str, arguments)]


def launch(command, cwd, output):
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=output, stderr=subprocess.STDOUT, **kwargs)


def terminate(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=15, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    process.wait(timeout=10)
