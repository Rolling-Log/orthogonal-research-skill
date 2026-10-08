#!/usr/bin/env python3
"""Validate this skill package and, when requested, an explicit SKILL.md copy."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SKILL_DIR = Path(__file__).resolve().parent.parent
CANONICAL = SKILL_DIR / "SKILL.md"
EXPECTED_ASSETS = {
    "assets/fonts/SourceHanSansCN-Regular.ttf": "dd4ae04ab7d33f43202750cf755b2ba47a2122ba41412954e562da459337bbf6",
    "assets/fonts/SourceHanSansCN-Bold.ttf": "2dcaecc0dcba896fdc48e32617633123d91fa80c7eb9f7ae7c836da70e45ce88",
    "assets/fonts/OFL-1.1.txt": "dbaa78e2fdeef95b4f94cfb86bc53cb07b2abb4bb104cf361dde00724243dc35",
    "assets/sample/jpeg_fixture.jpg": "6e0b7c5fb9e3557fe17c5cec52fa14d45f48e25fc4d155ebebfcb2fab7c2096f",
}
REQUIRED = [
    "SKILL.md", "agents/openai.yaml", "assets/report.css",
    "assets/licenses/DEPENDENCIES.json", "assets/licenses/REPORTLAB-LICENSE.txt",
    "references/research-protocol.md", "references/report-spec.md",
    "references/visual-system.md", "references/adversarial-review.md",
    "references/v1-regression-matrix.md", "references/examples.md",
    "scripts/build_report.py", "scripts/init_workspace.py",
    "scripts/render_visuals.py", "scripts/visual_scene.py",
    "scripts/check_research.py",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def authored_files() -> List[Path]:
    files = []
    for path in SKILL_DIR.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(SKILL_DIR)
        if relative.parts[0] in ("vendor",) or "fonts" in relative.parts or "licenses" in relative.parts:
            continue
        if path.name == Path(__file__).name or path.suffix.lower() not in (".md", ".py", ".css", ".yaml", ".yml", ".json"):
            continue
        files.append(path)
    return files


def scan_portability() -> List[str]:
    problems = []
    forbidden: Dict[str, str] = {
        "automatic index token": "[" + "TO" + "C" + "]",
        "index stylesheet selector": "." + "to" + "c",
        "legacy PDF backend": "Weasy" + "Print",
        "macOS package-manager command": "br" + "ew ",
        "Linux package-manager command": "apt" + "-get",
        "Windows Unix-compat layer": "MS" + "YS2",
    }
    old_marker = re.compile(r"\[" + r"@S\d{3,}" + r"\]")
    absolute_path = re.compile(r"(?<!https:)(?<!http:)(?<!file:)/(?:Users|home|mnt|tmp)/")
    index_heading = re.compile(r"^#{1,6}\s+目" + r"录\s*$", re.M)
    shell_continuation = re.compile(r"\\\s*$", re.M)
    for path in authored_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(SKILL_DIR)
        for name, token in forbidden.items():
            if token.lower() in text.lower():
                problems.append("{} contains {}".format(relative, name))
        if old_marker.search(text):
            problems.append("{} contains legacy [@S001] marker syntax".format(relative))
        if absolute_path.search(text):
            problems.append("{} contains a host-specific absolute path".format(relative))
        if index_heading.search(text):
            problems.append("{} contains a report index heading".format(relative))
        if shell_continuation.search(text):
            problems.append("{} contains a shell-only line continuation".format(relative))
    return problems


def validate(root_copy: Optional[Path] = None) -> List[str]:
    problems = []
    for relative in REQUIRED:
        if not (SKILL_DIR / relative).is_file():
            problems.append("missing required file: {}".format(relative))
    if not CANONICAL.is_file():
        return problems
    text = CANONICAL.read_text(encoding="utf-8")
    if len(text.splitlines()) >= 500:
        problems.append("SKILL.md must stay below 500 lines")
    if not re.match(r"^---\nname: orthogonal-research-skill\ndescription: .+?\n---\n", text, re.S):
        problems.append("SKILL.md frontmatter is invalid")
    for relative, expected in EXPECTED_ASSETS.items():
        path = SKILL_DIR / relative
        if not path.is_file():
            problems.append("missing bundled asset: {}".format(relative))
        elif sha256(path) != expected:
            problems.append("asset hash mismatch: {}".format(relative))
    for path in SKILL_DIR.rglob(".DS_Store"):
        problems.append("extraneous metadata file: {}".format(path))
    if root_copy is not None and (not root_copy.is_file() or root_copy.read_bytes() != CANONICAL.read_bytes()):
        problems.append("root SKILL.md is not synchronized with canonical SKILL.md")
    problems.extend(scan_portability())
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="overwrite root copy from canonical")
    parser.add_argument("--root-copy", type=Path, help="explicit SKILL.md copy to compare or sync")
    args = parser.parse_args(argv)
    if args.sync:
        if args.root_copy is None:
            parser.error("--sync requires an explicit --root-copy target")
        try:
            args.root_copy.write_bytes(CANONICAL.read_bytes())
        except OSError as exc:
            parser.error("cannot sync the explicit copy: {}".format(exc))
    problems = validate(args.root_copy)
    if problems:
        for problem in problems:
            print("error: {}".format(problem), file=sys.stderr)
        return 2
    print("package-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
