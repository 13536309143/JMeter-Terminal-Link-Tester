#!/usr/bin/env python3
"""Build a portable source delivery, excluding runtimes, credentials and raw customer documents."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRECTORIES = ["src/linklab", "scripts", "scenarios", "data", "docs", "deployments", "tests", ".github", "source", "test-plans", "config"]
FILES = ["README.md", "README.zh-CN.md", "jmeter-link-tester", "jmeter-link-tester.cmd", "jmeter", "start-jmeter.command", "pyproject.toml", "requirements.lock", ".gitignore", "linklab", "linklab.cmd", "THIRD_PARTY_NOTICES.md"]


def main():
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    package = destination / "jmeter-link-tester-1.0.0-source.zip"
    paths = [ROOT / name for name in FILES]
    for name in DIRECTORIES:
        paths.extend(p for p in (ROOT / name).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.name != ".DS_Store")
    checksums = {}
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            if not path.is_file():
                raise FileNotFoundError(path)
            relative = path.relative_to(ROOT).as_posix()
            contents = path.read_bytes()
            archive.writestr("jmeter-link-tester/" + relative, contents)
            checksums[relative] = hashlib.sha256(contents).hexdigest()
        archive.writestr("jmeter-link-tester/SHA256SUMS.json", json.dumps(checksums, indent=2))
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix(".zip.sha256").write_text(f"{checksum}  {package.name}\n")
    print(package)
    print(checksum)


if __name__ == "__main__":
    main()
