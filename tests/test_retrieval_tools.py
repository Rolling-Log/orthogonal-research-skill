"""Behavioral checks for the optional launcher; no external network required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "orthogonal-research-skill/scripts/retrieval_tools.py"
spec = importlib.util.spec_from_file_location("retrieval_tools", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LauncherTests(unittest.TestCase):
    def test_missing_config_and_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(module.read_config(Path(temp) / "absent.json"), {"commands": {}})
            result = module.resolve("gh", {"commands": {"gh": [str(Path(temp) / "absent.exe")]}})
            self.assertEqual(result["status"], "missing")

    def test_reject_malformed_config(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            for data in [{"commands": {"gh": "shell string"}}, {"commands": {"unknown": ["python"]}},
                         {"commands": {}, "network_env": {"PATH": "/replace/system/path"}}]:
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    module.read_config(path)

    def test_spaces_unicode_and_literal_arguments(self):
        with tempfile.TemporaryDirectory(prefix="retrieval 中文 space ") as temp:
            root = Path(temp)
            fake = root / "echo args.py"
            fake.write_text("import sys,json; print(json.dumps(sys.argv[1:],ensure_ascii=False))", encoding="utf-8")
            cfg = root / "config.json"
            cfg.write_text(json.dumps({"commands": {"gh": [sys.executable, str(fake)]}}), encoding="utf-8")
            args = ["two words", "中文", "$(must_not_execute);&literal", 'a"b']
            result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(cfg), "run", "gh", "--"] + args,
                                    capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), args)

    def test_timeout_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "config.json"
            cfg.write_text(json.dumps({"commands": {"gh": [sys.executable, "-c", "import time; time.sleep(2)"]}}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(cfg), "--timeout", ".15", "run", "gh"],
                                    capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 124)


if __name__ == "__main__":
    unittest.main()
