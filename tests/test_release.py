"""Check the installable release, independently of checkout timestamps."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from install_skill import install
from package_release import package_release, read_version


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="orthogonal-release-")
        self.root = Path(self.temporary.name)
        self.skill = self.root / "source"
        self.skill.mkdir()
        self.write("SKILL.md", "---\nname: orthogonal-research-skill\n---\n")
        self.write("VERSION.txt", "orthogonal-research-skill V9.8.7\nFixture version.\n")
        self.write("LICENSE", "Fixture license\n")
        self.write("scripts/check.py", "print('fixture')\n")
        self.write("references/说明.md", "固定版本的虚构输入\n")

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, text):
        path = self.skill / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_reproducible_zip_manifest_and_checksums(self):
        first = self.root / "first"
        second = self.root / "second"
        manifest = package_release(self.skill, first)
        for path in self.skill.rglob("*"):
            if path.is_file():
                os.utime(path, (1700000000, 1700000000))
        package_release(self.skill, second)
        for name in ("orthogonal-research-skill.zip", "release-manifest.json", "SHA256SUMS.txt"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
        self.assertEqual(manifest["version"], "9.8.7")
        with zipfile.ZipFile(first / manifest["archive"]["name"]) as archive:
            self.assertTrue(all(name.startswith("orthogonal-research-skill/") for name in archive.namelist()))
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            for item in manifest["files"]:
                data = archive.read(item["path"])
                self.assertEqual(len(data), item["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(len(archive.namelist()), manifest["file_count"])
        for line in (first / "SHA256SUMS.txt").read_text().splitlines():
            checksum, filename = line.split("  ")
            self.assertEqual(hashlib.sha256((first / filename).read_bytes()).hexdigest(), checksum)

    def test_caches_and_local_runtime_are_excluded_from_zip_and_install(self):
        for name in ("scripts/__pycache__/cache.pyc", ".env", "assets/runtime/private.txt", "scripts/temporary.log"):
            self.write(name, "not shipped")
        manifest = package_release(self.skill, self.root / "dist")
        self.assertEqual(manifest["file_count"], 5)
        destination = self.root / "installed"
        self.assertEqual(install(self.skill, destination), "9.8.7")
        installed_files = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
        expected = {entry["path"].split("/", 1)[1] for entry in manifest["files"]}
        self.assertEqual(installed_files, expected)
        with self.assertRaises(ValueError):
            install(self.skill, destination)

    def test_old_version_and_local_credentials_cannot_enter_release(self):
        for name in ("old-v1/SKILL.md", "assets/cookies.json", "assets/token.key"):
            with self.subTest(path=name):
                path = self.write(name, "not shipped")
                with self.assertRaises(ValueError):
                    package_release(self.skill, self.root / "dist")
                path.unlink()

    def test_version_and_destination_validation(self):
        with self.assertRaises(ValueError):
            package_release(self.skill, self.root / "dist", "v9.8.6")
        with self.assertRaises(ValueError):
            package_release(self.skill, self.skill / "dist")
        with self.assertRaises(ValueError):
            install(self.skill, self.skill / "installed")
        package_release(self.skill, self.root / "dist", "v9.8.7")
        self.write("VERSION.txt", "unspecified\n")
        with self.assertRaises(ValueError):
            read_version(self.skill)


if __name__ == "__main__":
    unittest.main()
