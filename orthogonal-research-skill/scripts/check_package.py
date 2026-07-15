#!/usr/bin/env python3
"""Validate portability, v1 regression guardrails, assets, and package hygiene."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SKILL_DIR = Path(__file__).resolve().parent.parent
CANONICAL = SKILL_DIR / "SKILL.md"
DEFAULT_ROOT_COPY = SKILL_DIR.parent / "SKILL.md"
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


def validate() -> List[str]:
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
    forbidden_suffixes = {".dll", ".exe", ".pyd", ".pyc"}
    for path in SKILL_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in forbidden_suffixes:
            problems.append("forbidden generated or platform-specific file: {}".format(path.relative_to(SKILL_DIR)))
        if path.is_dir() and path.name == "__pycache__":
            problems.append("extraneous cache directory: {}".format(path.relative_to(SKILL_DIR)))
    for path in SKILL_DIR.parent.rglob(".DS_Store"):
        problems.append("extraneous metadata file: {}".format(path))
    problems.extend(scan_portability())
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    del argv
    problems = validate()
    if problems:
        for problem in problems:
            print("error: {}".format(problem), file=sys.stderr)
        return 2
    print("package-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
