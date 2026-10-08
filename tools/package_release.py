"""Build the current installable skill and deterministic release metadata."""
import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "orthogonal-research-skill"
ROOT_FILES = {"SKILL.md", "VERSION.txt", "LICENSE"}
ROOT_DIRECTORIES = {"agents", "assets", "references", "scripts", "vendor"}
OMIT_DIRECTORIES = {"__pycache__", "node_modules", "venv", "runtime", "build", "dist"}
OMIT_SUFFIXES = {".pyc", ".pyo", ".pyd", ".exe", ".dll", ".log", ".tmp", ".bak"}
PRIVATE_NAMES = {"cookies", "cookies.txt", "cookies.json", "credentials.json",
                 "auth.json", "storage-state.json", "storage_state.json", "retrieval.json"}
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_version(skill):
    text = (skill / "VERSION.txt").read_text(encoding="utf-8-sig")
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    match = re.fullmatch(r"orthogonal-research-skill [vV](\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)", first_line)
    if not match:
        raise ValueError("VERSION.txt must begin with 'orthogonal-research-skill V<semver>'")
    return match.group(1)


def release_files(skill):
    """Share exactly one clean file set between ZIP packaging and installers."""
    skill = skill.resolve()
    if not (skill / "SKILL.md").is_file():
        raise ValueError("Skill source not found: {}".format(skill))
    for path in sorted(skill.rglob("*"), key=lambda item: item.relative_to(skill).as_posix()):
        relative = path.relative_to(skill)
        parts = relative.parts
        if any(part.startswith(".") or part in OMIT_DIRECTORIES for part in parts):
            continue
        if path.is_symlink():
            raise ValueError("Release cannot contain symlinks: {}".format(relative))
        if not path.is_file():
            continue
        if path.suffix.lower() in OMIT_SUFFIXES or path.name == "Thumbs.db":
            continue
        if parts[0] not in ROOT_DIRECTORIES and relative.as_posix() not in ROOT_FILES:
            raise ValueError("Unexpected skill-root file: {}".format(relative))
        if path.name.lower() in PRIVATE_NAMES or path.suffix.lower() in {".pem", ".key", ".sqlite", ".db"}:
            raise ValueError("Local configuration is not a release asset: {}".format(relative))
        yield path, relative.as_posix()


def package_release(skill, output, expect_version=None):
    skill = skill.resolve()
    output = output.resolve()
    version = read_version(skill)
    if expect_version and expect_version.lstrip("vV") != version:
        raise ValueError("Expected version {} but VERSION.txt contains {}".format(expect_version, version))
    if output == skill or skill in output.parents:
        raise ValueError("Release output must be outside the installable skill")
    entries = list(release_files(skill))
    names = {relative for _, relative in entries}
    if not ROOT_FILES.issubset(names):
        raise ValueError("Release requires SKILL.md, VERSION.txt and LICENSE")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (SKILL_NAME + ".zip")
    files = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path, relative in entries:
            content = path.read_bytes()
            archive_path = SKILL_NAME + "/" + relative
            info = zipfile.ZipInfo(archive_path, date_time=ZIP_DATE)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            files.append({"path": archive_path, "bytes": len(content),
                          "sha256": hashlib.sha256(content).hexdigest()})
    digest = sha256(archive)
    manifest = {"schema_version": 1, "name": SKILL_NAME, "version": version,
                "archive": {"name": archive.name, "bytes": archive.stat().st_size, "sha256": digest},
                "file_count": len(files), "files": files}
    manifest_path = output / "release-manifest.json"
    manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    (output / "SHA256SUMS.txt").write_bytes((digest + "  " + archive.name + "\n" +
                                            sha256(manifest_path) + "  " + manifest_path.name + "\n").encode("ascii"))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--expect-version", help="Check a release tag against VERSION.txt")
    args = parser.parse_args()
    try:
        manifest = package_release(ROOT / SKILL_NAME, args.output_dir, args.expect_version)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(str(args.output_dir.resolve() / manifest["archive"]["name"]))
    print("v{}; {} files; {} bytes; sha256 {}".format(manifest["version"], manifest["file_count"],
                                                    manifest["archive"]["bytes"], manifest["archive"]["sha256"]))


if __name__ == "__main__":
    main()
