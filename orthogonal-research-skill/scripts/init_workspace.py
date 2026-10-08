#!/usr/bin/env python3
"""Create a self-contained research workspace in the current project or explicit path."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class WorkspaceError(RuntimeError):
    """Raised when a report workspace cannot be created safely."""


WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *("COM{}".format(index) for index in range(1, 10)),
    *("LPT{}".format(index) for index in range(1, 10)),
}

def safe_subject(value: str) -> str:
    """Return a macOS/Windows-safe, readable folder-name component."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(". ")
    if not cleaned:
        cleaned = "研究对象"
    if cleaned.upper() in WINDOWS_RESERVED:
        cleaned = "_{}".format(cleaned)
    return cleaned[:80].rstrip(". ") or "研究对象"


def _windows_known_desktop() -> Optional[Path]:
    """Resolve FOLDERID_Desktop using only the Python standard library."""
    if sys.platform != "win32":
        return None

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    raw = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
    data = raw.bytes_le
    guid = GUID(
        int.from_bytes(data[0:4], "little"),
        int.from_bytes(data[4:6], "little"),
        int.from_bytes(data[6:8], "little"),
        (ctypes.c_ubyte * 8)(*data[8:16]),
    )
    pointer = ctypes.c_wchar_p()
    try:
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(pointer)
        )
        if result == 0 and pointer.value:
            return Path(pointer.value)
    except (AttributeError, OSError):
        return None
    finally:
        if pointer.value:
            try:
                ctypes.windll.ole32.CoTaskMemFree(pointer)
            except (AttributeError, OSError):
                pass
    return None


def desktop_path() -> Path:
    """Resolve the current user's real Desktop without third-party packages."""
    if sys.platform == "win32":
        known = _windows_known_desktop()
        if known is not None:
            return known
        profile = os.environ.get("USERPROFILE")
        if profile:
            return Path(profile) / "Desktop"
    return Path.home() / "Desktop"


def _unique_path(candidate: Path, timestamp: str) -> Path:
    if not candidate.exists():
        return candidate
    suffix = timestamp
    numbered = candidate.with_name("{}-{}".format(candidate.name, suffix))
    counter = 2
    while numbered.exists():
        numbered = candidate.with_name("{}-{}-{}".format(candidate.name, suffix, counter))
        counter += 1
    return numbered


def create_workspace(subject: str, destination: Optional[Path] = None,
                     desktop: Optional[Path] = None, timestamp: Optional[str] = None) -> Path:
    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "{}_横纵分析报告_{}".format(safe_subject(subject), stamp)
    if destination is None:
        base = (desktop or Path.cwd()).expanduser()
        if not base.is_dir():
            raise WorkspaceError("Base directory is unavailable: {}".format(base))
        root = _unique_path(base / name, stamp)
    else:
        requested = destination.expanduser()
        root = _unique_path(requested, stamp) if requested.exists() else requested

    try:
        root.mkdir(parents=True, exist_ok=False)
        for relative in ("sources", "data", "visuals", "images", "build", "build/qa"):
            (root / relative).mkdir()
        (root / "report.md").write_text(
            "# {}横纵分析报告\n\n> 研究截面：待填写｜范围：待填写｜对象类型：待填写\n".format(subject),
            encoding="utf-8",
        )
        sources = {
            "method_version": "3",
            "as_of": "",
            "coverage": {
                "balance_policy": "diagnostic",
                "attempted_languages": [],
                "attempted_regions": [],
                "attempted_platforms": [],
                "successful_source_categories": [],
                "successful_domains": [],
                "blocked_domains": [],
                "network_limitations": [],
                "target_perspective_groups": [],
                "balance_exception": None,
            },
            "limitations": [],
            "sources": [],
            "claims": [],
            "datasets": [],
        }
        (root / "sources" / "sources.json").write_text(
            json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "sources" / "research-log.json").write_text(
            json.dumps({"brief": {"subject": subject, "type": "", "purpose": "",
                                   "context_basis": "", "questions": [], "reading_budget": None},
                        "rounds": [], "important_unknowns": [], "revisions": [],
                        "stop_reason": ""}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "study.json").write_text(json.dumps({
            "version": 1, "id": "study-" + uuid.uuid4().hex[:16],
            "title": subject + "横纵分析报告", "subject_type": "other",
            "as_of": datetime.now().date().isoformat(), "report": "report.md",
            "sources": "sources/sources.json", "components": "data/components.json",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "data" / "components.json").write_text(
            '{"version": 1, "components": []}\n', encoding="utf-8")
    except OSError as exc:
        raise WorkspaceError("cannot create report workspace at {}: {}".format(root, exc))
    return root.resolve()


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="hv-workspace-") as temp:
        desktop = Path(temp) / "Desktop 空格"
        desktop.mkdir()
        first = create_workspace("勃肯鞋:全球/研究", desktop=desktop,
                                 timestamp="20260713-120000")
        second = create_workspace("勃肯鞋:全球/研究", desktop=desktop,
                                  timestamp="20260713-120000")
        explicit = create_workspace("显式目录", destination=Path(temp) / "用户 指定",
                                    timestamp="20260713-120001")
        if first == second or not second.name.endswith("-20260713-120000"):
            raise WorkspaceError("collision handling failed")
        for root in (first, second, explicit):
            required = (
                "report.md", "sources/sources.json", "sources/research-log.json",
                "data", "visuals", "images", "build/qa", "study.json", "data/components.json",
            )
            if any(not (root / relative).exists() for relative in required):
                raise WorkspaceError("workspace structure is incomplete: {}".format(root))
        if safe_subject("CON") != "_CON" or "/" in safe_subject("A/B"):
            raise WorkspaceError("cross-platform subject sanitization failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", help="research subject used in the package name")
    parser.add_argument("--destination", type=Path,
                        help="explicit package directory; overrides the current-directory default")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print("workspace-self-test: PASS")
            return 0
        if not args.subject:
            parser.error("--subject is required unless --self-test is used")
        root = create_workspace(args.subject, args.destination)
        report_name = "{}_横纵分析报告.pdf".format(safe_subject(args.subject))
        print(json.dumps({
            "workspace": str(root),
            "report_markdown": str(root / "report.md"),
            "expected_pdf": str(root / "delivery" / "report.pdf"),
            "expected_html": str(root / "delivery" / "report.html"),
            "study_manifest": str(root / "study.json"),
        }, ensure_ascii=False))
        return 0
    except (WorkspaceError, OSError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
