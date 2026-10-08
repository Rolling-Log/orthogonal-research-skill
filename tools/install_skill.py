"""Install the checkout's current skill using the release file set."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

from package_release import ROOT, SKILL_NAME, read_version, release_files, sha256


def install(source, destination):
    source = source.resolve()
    destination = destination.absolute()
    version = read_version(source)
    entries = list(release_files(source))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists: {}. Rename it before installing.".format(destination))
    if destination == source or source in destination.resolve().parents:
        raise ValueError("Installation destination must be outside the skill source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".orthogonal-install-", dir=str(destination.parent)) as staging:
        staged_skill = Path(staging) / SKILL_NAME
        staged_skill.mkdir()
        for path, relative in entries:
            target = staged_skill / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(path), str(target))
            if sha256(path) != sha256(target):
                raise ValueError("Copy verification failed: {}".format(relative))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Installation destination was created by another process")
        staged_skill.rename(destination)
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    codex_directory = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("destination", nargs="?", type=Path, default=codex_directory / "skills" / SKILL_NAME)
    args = parser.parse_args()
    try:
        version = install(ROOT / SKILL_NAME, args.destination)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Installed {} v{} to:".format(SKILL_NAME, version))
    print(str(args.destination.absolute()))


if __name__ == "__main__":
    main()
