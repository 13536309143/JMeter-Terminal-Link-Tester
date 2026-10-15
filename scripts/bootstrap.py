#!/usr/bin/env python3
"""Install pinned Java/JMeter/plugin artifacts and an isolated Python environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path, algorithm):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def acquire(spec, offline):
    target = ROOT / "downloads" / spec["filename"]
    if target.exists() and digest(target, spec["algorithm"]) == spec["digest"]:
        print(f"Verified cached artifact: {target.name}", flush=True)
        return target
    if offline:
        raise RuntimeError(f"Offline artifact missing or checksum mismatch: {target}")
    temporary = target.with_suffix(target.suffix + ".part")
    context = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if sys.platform == "darwin" else None)
    errors = []
    for url in [spec["url"], *([spec["fallback_url"]] if spec.get("fallback_url") else [])]:
        for attempt in range(3):
            try:
                print(f"Download {target.name} (attempt {attempt + 1})", flush=True)
                request = urllib.request.Request(url, headers={"User-Agent": "LinkLab-bootstrap/1.0"})
                with urllib.request.urlopen(request, timeout=60, context=context) as source, temporary.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if digest(temporary, spec["algorithm"]) != spec["digest"]:
                    raise RuntimeError(f"Checksum mismatch: {target.name}")
                temporary.replace(target)
                return target
            except (OSError, RuntimeError) as exc:
                errors.append(str(exc))
                time.sleep(1)
    raise RuntimeError(f"Could not download {target.name}: {errors[-1]}")


def unpack(archive: Path, destination: Path):
    """Reject archive traversal and devices; vendor links must remain inside the archive root."""
    destination = destination.resolve()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as contents:
            for member in contents.infolist():
                path = (destination / member.filename).resolve()
                if not path.is_relative_to(destination) or "\\" in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError(f"Unsafe ZIP member: {member.filename}")
            contents.extractall(destination)
    else:
        with tarfile.open(archive) as contents:
            for member in contents.getmembers():
                if not (destination / member.name).resolve().is_relative_to(destination) or member.isdev() or member.isfifo():
                    raise RuntimeError(f"Unsafe TAR member: {member.name}")
                if member.issym() or member.islnk():
                    base = destination / Path(member.name).parent if member.issym() else destination
                    if not (base / member.linkname).resolve().is_relative_to(destination):
                        raise RuntimeError(f"Unsafe TAR link: {member.name}")
            # Python 3.11 supports data filters in current patch releases; explicit checks above cover older ones.
            kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            contents.extractall(destination, **kwargs)


def install_artifacts(offline):
    lock = json.loads((ROOT / "deployments/artifacts.lock.json").read_text(encoding="utf-8"))
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    local_java = runtime / "jdk" / ("Contents/Home/bin/java" if sys.platform == "darwin" else "bin/java.exe" if os.name == "nt" else "bin/java")
    if not local_java.is_file() and not os.environ.get("JAVA_HOME"):
        key = f"{platform.system().lower()}-{platform.machine().lower()}"
        if key not in lock["jdk"]:
            raise RuntimeError(f"Automatic JDK installation is not configured for {key}; set JAVA_HOME to JDK 17+")
        archive = acquire(lock["jdk"][key], offline)
        with tempfile.TemporaryDirectory(prefix="linklab-jdk-", dir=runtime) as staging:
            unpack(archive, Path(staging))
            children = [p for p in Path(staging).iterdir() if p.is_dir() and not p.name.startswith("__MACOSX")]
            if len(children) != 1:
                raise RuntimeError("Unexpected JDK archive structure")
            target = runtime / "jdk"
            if target.exists() or target.is_symlink():
                raise RuntimeError(f"Incomplete JDK directory already exists: {target}; rename it and retry")
            children[0].replace(target)
    jmeter = runtime / f'apache-jmeter-{lock["jmeter"]["version"]}'
    if not (jmeter / "bin/ApacheJMeter.jar").is_file():
        archive = acquire(lock["jmeter"], offline)
        with tempfile.TemporaryDirectory(prefix="linklab-jmeter-", dir=runtime) as staging:
            unpack(archive, Path(staging))
            extracted = Path(staging) / jmeter.name
            if not extracted.is_dir() or jmeter.exists():
                raise RuntimeError("Unexpected or incomplete JMeter directory")
            extracted.replace(jmeter)
    target_plugin = jmeter / "lib/ext" / lock["mqtt_plugin"]["filename"]
    if not target_plugin.exists() or digest(target_plugin, "sha256") != lock["mqtt_plugin"]["digest"]:
        plugin = acquire(lock["mqtt_plugin"], offline)
        shutil.copy2(plugin, target_plugin)


def install_python(offline):
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not (environment / "pyvenv.cfg").is_file() or not python.is_file():
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(environment)
    index = ["--no-index", "--find-links", str(ROOT / "downloads/wheels")] if offline else []
    subprocess.run([str(python), "-m", "pip", "install", *index, "-r", str(ROOT / "requirements.lock")], check=True)
    subprocess.run([str(python), "-m", "pip", "install", *index, "--no-deps", "--no-build-isolation", "-e", str(ROOT)], check=True)
    subprocess.run([str(python), "-m", "linklab", "--workspace", str(ROOT), "doctor"], cwd=ROOT, check=True)


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ is required; Python 3.12 is recommended")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Only use downloads and the platform-specific wheelhouse")
    parser.add_argument("--skip-python", action="store_true", help="Install Java/JMeter/plugin only")
    args = parser.parse_args()
    (ROOT / "downloads").mkdir(exist_ok=True)
    try:
        install_artifacts(args.offline)
        if not args.skip_python:
            install_python(args.offline)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Bootstrap failed: {exc}") from exc
    print("Ready. Run linklab.cmd demo (Windows) or ./linklab demo (macOS).")


if __name__ == "__main__":
    main()
