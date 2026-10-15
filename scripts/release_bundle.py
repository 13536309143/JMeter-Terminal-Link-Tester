#!/usr/bin/env python3
"""Build a self-contained runtime distribution from an explicit allowlist."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.1"
DEV_MODULES = ["linklab.cli", "linklab.demo_broker", "linklab.network", "linklab.http_reference", "linklab.pipeline"]
FORBIDDEN_PARTS = {"tests", "test", "test-plans", "fixtures", "__pycache__", ".git", ".github", "evidence"}


def bootstrap_module():
    spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "scripts/bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-freeze", action="store_true")
    args = parser.parse_args()
    machine = platform.machine().lower()
    label = ("windows-x64" if os.name == "nt" else "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64")
    if sys.platform not in ("darwin", "win32"):
        raise SystemExit("Runtime releases are built on Windows or macOS")
    work = ROOT / "build/release"
    frozen = work / "frozen"
    if not args.skip_freeze:
        command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
                   "--name", "jmeter-link-tester", "--paths", str(ROOT / "src"),
                   "--distpath", str(frozen), "--workpath", str(work / "pyinstaller"),
                   "--specpath", str(work), "--collect-data", "psutil"]
        for module in [*DEV_MODULES, "amqtt", "pytest", "unittest", "doctest", "test", "tkinter"]:
            command += ["--exclude-module", module]
        subprocess.run([*command, str(ROOT / "scripts/frozen_entry.py")], check=True, cwd=ROOT)
    destination = work / label / "jmeter-link-tester"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(frozen / "jmeter-link-tester", destination, symlinks=True)
    bootstrap = bootstrap_module()
    lock = json.loads((ROOT / "deployments/artifacts.lock.json").read_text())
    runtime = destination / "runtime"
    runtime.mkdir()
    local = ROOT / "runtime/jdk"
    expected_java = local / ("Contents/Home/bin/java" if sys.platform == "darwin" else "bin/java.exe")
    if expected_java.is_file():
        shutil.copytree(local.resolve(), runtime / "jdk", symlinks=False)
    else:
        key = f"{platform.system().lower()}-{machine}"
        archive = bootstrap.acquire(lock["jdk"][key], offline=False)
        staging = work / (label + "-java")
        staging.mkdir(parents=True, exist_ok=True)
        bootstrap.unpack(archive, staging)
        children = [p for p in staging.iterdir() if p.is_dir() and not p.name.startswith("__")]
        if len(children) != 1:
            raise RuntimeError("Unexpected Java archive structure")
        shutil.copytree(children[0], runtime / "jdk", symlinks=False)
    java_home = runtime / "jdk" / ("Contents/Home" if sys.platform == "darwin" else "")
    for relative in ("demo", "sample", "man", "include", "jmods"):
        shutil.rmtree(java_home / relative, ignore_errors=True)
    (java_home / "lib/src.zip").unlink(missing_ok=True)
    jmeter = runtime / "apache-jmeter-5.6.3"
    jmeter.mkdir()
    installed = ROOT / "runtime/apache-jmeter-5.6.3"
    def ignore(directory, names):
        return [n for n in names if n.lower() in FORBIDDEN_PARTS or n in ("templates", "examples", "results", "logs")
                or n.endswith((".jmx", ".jtl", ".log", ".bsh")) or n == ".DS_Store"]
    for folder in ("bin", "lib", "licenses"):
        if (installed / folder).exists():
            shutil.copytree(installed / folder, jmeter / folder, ignore=ignore)
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(installed / name, jmeter / name)
    profiles = destination / "profiles"
    profiles.mkdir()
    for protocol in ("mqtt", "tcp", "udp", "http"):
        value = {"version": 1, "name": f"{protocol}-terminals", "protocol": protocol,
                 "load": {"terminals": 5, "messages_per_terminal": 10, "ramp_up_seconds": 1, "interval_ms": 100}}
        if protocol == "mqtt":
            value["broker"] = {"host": "127.0.0.1", "port": 1883}
        elif protocol == "http":
            value["http"] = {"host": "127.0.0.1", "port": 8080, "path": "/telemetry", "method": "POST"}
        else:
            value["network"] = {"host": "127.0.0.1", "port": 9000 if protocol == "tcp" else 9001}
        (profiles / f"{protocol}.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    for source, target in [("docs/runtime-guide.en.md", "README.md"), ("docs/runtime-guide.zh-CN.md", "README.zh-CN.md"),
                           ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")]:
        content = (ROOT / source).read_text(encoding="utf-8").replace("(runtime-guide.zh-CN.md)", "(README.zh-CN.md)").replace("(runtime-guide.en.md)", "(README.md)")
        (destination / target).write_text(content, encoding="utf-8")
    legal = destination / "legal"
    legal.mkdir()
    shutil.copy2(ROOT / "deployments/licenses/Python-LICENSE.txt", legal / "Python-LICENSE.txt")
    for dependency in ("paho-mqtt", "PyYAML", "psutil", "pyinstaller"):
        distribution = importlib.metadata.distribution(dependency)
        for entry in distribution.files or ():
            if "dist-info" in str(entry) and any(word in entry.name.lower() for word in ("license", "copying")):
                location = distribution.locate_file(entry)
                if location.is_file():
                    folder = legal / dependency
                    folder.mkdir(exist_ok=True)
                    shutil.copy2(location, folder / entry.name)
    shutil.copytree(ROOT / "deployments/licenses/paho-mqtt", legal / "paho-mqtt", dirs_exist_ok=True)
    if os.name == "nt":
        (destination / "JMeter-GUI.cmd").write_text('@echo off\r\ncd /d "%~dp0"\r\n"%~dp0jmeter-link-tester.exe" gui\r\n', encoding="ascii")
    else:
        launcher = destination / "JMeter-GUI.command"
        launcher.write_text('#!/usr/bin/env bash\ncd "$(dirname "$0")"\nexec ./jmeter-link-tester gui\n')
        launcher.chmod(0o755)
    for path in destination.rglob("*"):
        if any(part.lower() in FORBIDDEN_PARTS for part in path.relative_to(destination).parts):
            raise RuntimeError(f"Forbidden development content in runtime bundle: {path}")
    for archive in destination.rglob("base_library.zip"):
        with zipfile.ZipFile(archive) as library:
            if any(any(p in FORBIDDEN_PARTS for p in name.split("/")) for name in library.namelist()):
                raise RuntimeError("Development modules found in frozen Python library")
    (destination / "BUILD-INFO.json").write_text(json.dumps({"product": "JMeter Terminal & Link Tester", "version": VERSION,
        "platform": label, "python": platform.python_version(), "jmeter": "5.6.3", "mqtt_plugin": "2.0.2",
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()}, indent=2) + "\n")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    name = f"jmeter-link-tester-{VERSION}-{label}"
    if os.name == "nt":
        archive = Path(shutil.make_archive(str(output / name), "zip", destination.parent, destination.name))
    else:
        archive = output / f"{name}.tar.gz"
        with tarfile.open(archive, "w:gz", compresslevel=6) as contents:
            contents.add(destination, arcname=destination.name)
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{checksum}  {archive.name}\n")
    print(json.dumps({"archive": str(archive), "bundle": str(destination), "sha256": checksum}))


if __name__ == "__main__":
    main()
