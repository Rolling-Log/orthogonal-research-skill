#!/usr/bin/env python3
"""Render validated report visual specifications to self-contained SVG files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from visual_scene import SpecError, render_file


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="JSON visual specification")
    parser.add_argument("--output-dir", type=Path, default=Path("visuals"))
    args = parser.parse_args(argv)
    try:
        written = render_file(args.spec, args.output_dir)
    except SpecError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
