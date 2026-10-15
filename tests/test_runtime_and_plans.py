import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from linklab.config import Scenario
from linklab.plans import compile_plan
from linklab.reporting import compare_results, write_report
from linklab.runtime import Runtime, launch, terminate

ROOT = Path(__file__).resolve().parent.parent


class RuntimeTests(unittest.TestCase):
    def test_generated_jmx_uses_native_samplers_and_environment_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Scenario.from_mapping({"broker": {"username_env": "LL_USER", "password_env": "LL_PASS"}})
            plan, devices = compile_plan(config, Path(temporary), "a" * 16)
            root = ET.parse(plan).getroot()
            self.assertTrue(root.findall(".//net.xmeter.samplers.SubSampler"))
            self.assertTrue(root.findall(".//net.xmeter.samplers.PubSampler"))
            self.assertIn("System.getenv('LL_PASS')", plan.read_text(encoding="utf-8"))
            self.assertEqual(len(devices), 5)
            self.assertTrue((Path(temporary) / "scenario.json").exists())

    def test_process_termination_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary, open(Path(temporary) / "out", "w") as output:
            process = launch([sys.executable, "-c", "import time; time.sleep(60)"], temporary, output)
            terminate(process)
            self.assertIsNotNone(process.poll())

    def test_archive_traversal_is_rejected(self):
        spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "scripts/bootstrap.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "unsafe.tar.gz"
            with tarfile.open(archive, "w:gz") as contents:
                member = tarfile.TarInfo("../outside")
                member.size = 4
                contents.addfile(member, io.BytesIO(b"nope"))
            with self.assertRaisesRegex(RuntimeError, "Unsafe TAR"):
                module.unpack(archive, root / "destination")
            self.assertFalse((root / "outside").exists())

    def test_bootstrap_lock_matches_runtime_plugin_pin(self):
        from linklab.runtime import PLUGIN_SHA256
        lock = json.loads((ROOT / "deployments/artifacts.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["mqtt_plugin"]["digest"], PLUGIN_SHA256)
