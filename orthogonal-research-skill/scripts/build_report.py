#!/usr/bin/env python3
"""Build a v1-styled HTML/PDF report with bundled, cross-platform dependencies.

Annotation syntax:
  {{@S014,@S019 | A short methodology or source note}}

The rendered body keeps only compact deep-blue reference numbers in superscript.
Optional methodology or scope notes are placed on a quiet line below the block.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
VENDOR_DIR = SKILL_DIR / "vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

try:
    from reportlab import Version as REPORTLAB_VERSION
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics, pdfutils
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
except Exception as exc:  # pragma: no cover - actionable import boundary
    raise SystemExit("error: bundled ReportLab could not be loaded: {}".format(exc))

from visual_scene import Scene, SpecError, load_visual_specs, scene_from_spec, scene_to_svg


DEEP_BLUE = colors.HexColor("#1A5276")
GREEN = colors.HexColor("#1E8449")
LIGHT_BLUE = colors.HexColor("#2E86C1")
PURPLE = colors.HexColor("#5B2C6F")
RED = colors.HexColor("#B03A2E")
INK = colors.HexColor("#2C3E50")
MUTED = colors.HexColor("#6B7280")
LIGHT_BG = colors.HexColor("#F4F6F7")
BORDER = colors.HexColor("#D5DBDB")
FONT_REGULAR = "SourceHanSansCN-Regular"
FONT_BOLD = "SourceHanSansCN-Bold"
FONT_REGULAR_PATH = SKILL_DIR / "assets" / "fonts" / "SourceHanSansCN-Regular.ttf"
FONT_BOLD_PATH = SKILL_DIR / "assets" / "fonts" / "SourceHanSansCN-Bold.ttf"
DEFAULT_CSS = SKILL_DIR / "assets" / "report.css"

ANNOTATION_RE = re.compile(
    r"\{\{\s*((?:@S\d{3,})(?:\s*,\s*@S\d{3,})*)\s*\|\s*(.+?)\s*\}\}"
)
OLD_MARKER_RE = re.compile(r"\[@S\d{3,}\]")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
IMAGE_RE = re.compile(r'^!\[(.*?)\]\(([^)\s]+)(?:\s+["\'][^"\']*["\'])?\)\s*$')
LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|(\d+)[.)]\s+)(.+)$")
TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
CAPTION_RE = re.compile(r'^<span\s+class=["\']figure-source["\']>(.*?)</span>\s*$', re.I)
BIBLIOGRAPHY_HEADING_RE = re.compile(
    r"^##\s+(?:五[、.]\s*)?信息来源(?:与方法说明)?\s*$", re.M
)
BIBLIOGRAPHY_ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$")
SOURCE_ID_RE = re.compile(r"S\d{3,}")
URL_RE = re.compile(r"https?://[^\s)）>|｜]+")
CJK_COUNT_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]"
)
WORD_COUNT_RE = re.compile(r"[^\W_]+(?:[-'’._][^\W_]+)*", re.UNICODE)
COUNT_URL_RE = re.compile(r"https?://[^\s)）>|｜，。；！？、：‘’“”《》〈〉【】]+")
READING_RATE_SLOW = 300
READING_RATE_FAST = 500


class BuildError(RuntimeError):
    """Raised for an actionable report build failure."""


@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 0
    rows: Optional[List[List[str]]] = None
    ordered: bool = False
    path: str = ""
    alt: str = ""
    note_ids: Optional[List[str]] = None
    note_text: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_fonts() -> None:
    for path in (FONT_REGULAR_PATH, FONT_BOLD_PATH):
        if not path.is_file():
            raise BuildError("bundled font is missing: {}".format(path.name))
    if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_REGULAR_PATH)))
    if FONT_BOLD not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_BOLD_PATH)))
    pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD,
                                  italic=FONT_REGULAR, boldItalic=FONT_BOLD)


def load_sources(path: Optional[Path]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    if path is None:
        return {}, {"coverage": {}, "limitations": []}
    if not path.is_file():
        raise BuildError("sources file not found: {}".format(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError("cannot read sources JSON: {}".format(exc))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise BuildError("sources.json must contain a sources array")
    mapping = {}
    seen_urls = {}
    for index, source in enumerate(payload["sources"]):
        if not isinstance(source, dict):
            raise BuildError("sources[{}] must be an object".format(index))
        source_id = str(source.get("id", ""))
        if not re.fullmatch(r"S\d{3,}", source_id):
            raise BuildError("sources[{}].id must match S001 style".format(index))
        if source_id in mapping:
            raise BuildError("duplicate source id: {}".format(source_id))
        if not str(source.get("display_name", "")).strip():
            raise BuildError("{} requires display_name for explanatory source notes".format(source_id))
        if not str(source.get("url", "")).strip():
            raise BuildError("{} requires url".format(source_id))
        if urlparse(str(source["url"])).scheme not in ("http", "https"):
            raise BuildError("{} url must use http or https".format(source_id))
        for key in ("title", "publisher", "published_at", "accessed_at", "type",
                    "language", "region", "perspective_group"):
            if not str(source.get(key, "")).strip():
                raise BuildError("{} requires {}".format(source_id, key))
        if source.get("tier") not in (1, 2, 3, 4):
            raise BuildError("{} tier must be 1, 2, 3, or 4".format(source_id))
        if not isinstance(source.get("supports"), list):
            raise BuildError("{} supports must be an array".format(source_id))
        normalized_url = str(source["url"]).rstrip("/ ")
        if normalized_url in seen_urls:
            raise BuildError("duplicate source URL in {} and {}".format(
                seen_urls[normalized_url], source_id))
        seen_urls[normalized_url] = source_id
        mapping[source_id] = source
    coverage = payload.get("coverage", {})
    limitations = payload.get("limitations", [])
    if not isinstance(coverage, dict) or not isinstance(limitations, list):
        raise BuildError("sources.json coverage must be an object and limitations an array")
    coverage_keys = ("attempted_languages", "attempted_regions", "attempted_platforms",
                     "successful_source_categories", "successful_domains", "blocked_domains",
                     "network_limitations", "target_perspective_groups")
    for key in coverage_keys:
        if not isinstance(coverage.get(key), list):
            raise BuildError("sources.json coverage.{} must be an array".format(key))
    for index, limitation in enumerate(limitations):
        if not isinstance(limitation, dict) or not all(
                key in limitation for key in ("scope", "cause", "bias", "affected_claims", "confidence")):
            raise BuildError("limitations[{}] is missing disclosure fields".format(index))
        if not all(str(limitation.get(key, "")).strip() for key in ("scope", "cause", "bias")):
            raise BuildError("limitations[{}] disclosure text must not be empty".format(index))
        if (not isinstance(limitation.get("affected_claims"), list)
                or not limitation.get("affected_claims")):
            raise BuildError("limitations[{}].affected_claims must be a non-empty array".format(index))
        if not all(isinstance(value, str) and value.strip()
                   for value in limitation["affected_claims"]):
            raise BuildError("limitations[{}].affected_claims must contain claim IDs".format(index))
        if limitation.get("confidence") not in ("low", "medium", "high"):
            raise BuildError("limitations[{}].confidence must be low, medium, or high".format(index))
    return mapping, payload


def _annotation(block_text: str) -> Tuple[str, List[str], str]:
    ids = []
    notes = []

    def replace(match: re.Match) -> str:
        for raw in match.group(1).split(","):
            source_id = raw.strip().lstrip("@")
            if source_id not in ids:
                ids.append(source_id)
        notes.append(match.group(2).strip())
        return match.group(0)

    body = ANNOTATION_RE.sub(replace, block_text).strip()
    syntax_check = ANNOTATION_RE.sub("", body)
    if "{{@" in syntax_check:
        raise BuildError("invalid source note syntax; use {{@S014,@S019 | note}}")
    return body, ids, "；".join(notes)


def _ordered_add(values: List[str], candidates: Iterable[str]) -> None:
    for value in candidates:
        if value not in values:
            values.append(value)


def _source_ids(value: str) -> List[str]:
    return SOURCE_ID_RE.findall(value or "")


def _visual_reference_map(spec_path: Optional[Path], report_root: Path) -> Dict[Path, List[str]]:
    if spec_path is None:
        return {}
    if not spec_path.is_file():
        raise BuildError("visual spec not found: {}".format(spec_path))
    try:
        visuals = load_visual_specs(spec_path)
    except SpecError as exc:
        raise BuildError("invalid visual specification: {}".format(exc))
    output_dir = report_root / "visuals"
    mapping = {}
    for item in visuals:
        ids = []
        _ordered_add(ids, _source_ids(str(item.get("source", ""))))
        for edge in item.get("edges", []):
            if isinstance(edge, dict):
                _ordered_add(ids, _source_ids(str(edge.get("source", ""))))
        mapping[(output_dir / item["output"]).resolve()] = ids
    return mapping


def _citation_order(blocks: Sequence[Block], report_root: Path,
                    visual_references: Dict[Path, List[str]]) -> List[str]:
    order = []
    for block in blocks:
        _ordered_add(order, block.note_ids or [])
        if block.kind == "image":
            raw = urlparse(block.path)
            if raw.scheme not in ("http", "https", "data"):
                path = (report_root / unquote(raw.path)).resolve()
                _ordered_add(order, visual_references.get(path, []))
            _ordered_add(order, _source_ids(block.alt))
        elif block.kind in ("paragraph", "quote", "heading", "caption", "code"):
            _ordered_add(order, _source_ids(ANNOTATION_RE.sub("", block.text)))
        elif block.kind == "list":
            for item in (block.rows or [[]])[0]:
                _ordered_add(order, _source_ids(item))
        elif block.kind == "table":
            for row in block.rows or []:
                for cell in row:
                    _ordered_add(order, _source_ids(cell))
    return order


def _clean_url(value: str) -> str:
    return value.rstrip(".,;:。；，：、/ ")


def _bibliography_order(source_text: str, sources: Dict[str, Dict[str, Any]]) -> List[str]:
    heading = BIBLIOGRAPHY_HEADING_RE.search(source_text)
    if heading is None:
        raise BuildError("report requires a numbered '信息来源与方法说明' bibliography")
    lines = source_text[heading.end():].splitlines()
    entries = []
    for line in lines:
        if HEADING_RE.match(line):
            break
        item = BIBLIOGRAPHY_ITEM_RE.match(line)
        if not item:
            continue
        urls = [_clean_url(url) for url in URL_RE.findall(item.group(2))]
        if not urls:
            continue
        if len(urls) != 1:
            raise BuildError("each numbered bibliography entry must contain exactly one URL")
        entries.append((int(item.group(1)), item.group(2), urls[0]))
    if not entries:
        raise BuildError("numbered bibliography entries were not found")
    numbers = [number for number, _, _ in entries]
    expected = list(range(1, len(entries) + 1))
    if numbers != expected:
        raise BuildError("bibliography numbers must be consecutive from 1; found {}".format(numbers))

    by_url = {_clean_url(str(source["url"])): source_id for source_id, source in sources.items()}
    order = []
    for number, text_value, url in entries:
        source_id = by_url.get(url)
        if source_id is None:
            raise BuildError("bibliography [{}] URL is absent from sources.json: {}".format(number, url))
        if source_id in order:
            raise BuildError("bibliography repeats source {}".format(source_id))
        source = sources[source_id]
        required_values = (source["display_name"], source["title"], source["publisher"],
                           source["published_at"], source["accessed_at"])
        missing = [str(value) for value in required_values if str(value) not in text_value]
        if missing:
            raise BuildError("bibliography [{}] is missing source metadata: {}".format(
                number, ", ".join(missing)))
        order.append(source_id)
    return order


def _validate_bibliography(citation_order: Sequence[str], bibliography_order: Sequence[str]) -> None:
    citations = list(citation_order)
    bibliography = list(bibliography_order)
    if citations != bibliography:
        missing = [source_id for source_id in citations if source_id not in bibliography]
        unused = [source_id for source_id in bibliography if source_id not in citations]
        if missing:
            raise BuildError("cited sources missing from bibliography: {}".format(", ".join(missing)))
        if unused:
            raise BuildError("bibliography contains unused sources: {}".format(", ".join(unused)))
        raise BuildError("bibliography order must follow first citation order: expected {}; found {}".format(
            citations, bibliography))


def _valid_balance_exception(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    text_keys = ("cause", "bias")
    list_keys = ("attempts", "affected_claims")
    return (all(str(value.get(key, "")).strip() for key in text_keys)
            and all(isinstance(value.get(key), list) and value.get(key)
                    and all(isinstance(item, str) and item.strip() for item in value[key])
                    for key in list_keys)
            and value.get("confidence") in ("low", "medium"))


def _source_balance(cited_ids: Sequence[str], sources: Dict[str, Dict[str, Any]],
                    source_payload: Dict[str, Any]) -> Dict[str, Any]:
    coverage = source_payload.get("coverage", {})
    target_groups = coverage.get("target_perspective_groups", [])
    if (len(target_groups) < 2 or len(target_groups) > 4
            or len(set(target_groups)) != len(target_groups)
            or not all(isinstance(group, str) and group.strip() for group in target_groups)):
        raise BuildError("coverage.target_perspective_groups must contain 2-4 unique groups")

    effective = {}
    duplicates = []
    excluded_tier4 = []
    for source_id in cited_ids:
        source = sources[source_id]
        if source["tier"] == 4:
            excluded_tier4.append(source_id)
            continue
        key = str(source.get("independence_key") or source_id).strip()
        group = str(source["perspective_group"]).strip()
        if key in effective:
            canonical_id = effective[key]
            canonical_group = str(sources[canonical_id]["perspective_group"]).strip()
            if canonical_group != group:
                raise BuildError("sources sharing independence_key must use the original perspective_group: {}".format(key))
            duplicates.append({"source_id": source_id, "counted_as": canonical_id,
                               "independence_key": key})
            continue
        effective[key] = source_id

    counts = {group: 0 for group in target_groups}
    unplanned = []
    for source_id in effective.values():
        group = str(sources[source_id]["perspective_group"]).strip()
        if group not in counts:
            unplanned.append("{}:{}".format(source_id, group))
        else:
            counts[group] += 1
    if unplanned:
        raise BuildError("cited sources use undeclared perspective groups: {}".format(", ".join(unplanned)))
    total = sum(counts.values())
    if total == 0:
        raise BuildError("source balance requires at least one cited independent Tier 1-3 source")
    distribution = [
        {"group": group, "count": counts[group], "share": round(counts[group] / total, 4)}
        for group in target_groups
    ]
    failing = [item for item in distribution if item["share"] < 0.2 or item["share"] > 0.8]
    exception = coverage.get("balance_exception")
    status = "pass"
    if failing:
        if not _valid_balance_exception(exception):
            details = ", ".join("{}={:.1%}".format(item["group"], item["share"])
                                for item in distribution)
            raise BuildError("perspective-group source balance must stay within 20%-80%: {}".format(details))
        matching_limitations = [
            limitation for limitation in source_payload.get("limitations", [])
            if (isinstance(limitation, dict)
                and set(exception["affected_claims"]).issubset(
                    set(limitation.get("affected_claims", [])))
                and limitation.get("confidence") == exception["confidence"]
                and str(limitation.get("bias", "")).strip() == exception["bias"])
        ]
        if not matching_limitations:
            raise BuildError(
                "balance_exception requires a matching limitations entry with the same bias, "
                "confidence, and affected claims"
            )
        status = "exception"
    return {
        "status": status,
        "effective_source_count": total,
        "distribution": distribution,
        "deduplicated_sources": duplicates,
        "excluded_tier4_sources": excluded_tier4,
        "exception": exception if status == "exception" else None,
    }


def _is_table(lines: Sequence[str], index: int) -> bool:
    return index + 1 < len(lines) and "|" in lines[index] and bool(TABLE_RULE_RE.match(lines[index + 1]))


def _starts_block(lines: Sequence[str], index: int) -> bool:
    line = lines[index]
    stripped = line.strip()
    return (not stripped or bool(HEADING_RE.match(line)) or bool(IMAGE_RE.match(stripped))
            or stripped.startswith(">") or stripped.startswith("```") or stripped.startswith("~~~")
            or bool(LIST_RE.match(line)) or _is_table(lines, index)
            or bool(CAPTION_RE.match(stripped)) or stripped in ("---", "***"))


def _cells(line: str) -> List[str]:
    value = line.strip().strip("|")
    return [cell.strip() for cell in value.split("|")]


def parse_markdown(text: str) -> List[Block]:
    if OLD_MARKER_RE.search(text):
        raise BuildError(
            "legacy bracketed @source-ID markers are not supported; "
            "use {{@S001 | explanatory note}} "
            "and let the builder append bibliography numbers"
        )
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    index = 0
    while index < len(lines):
        line, stripped = lines[index], lines[index].strip()
        if not stripped:
            index += 1
            continue
        heading = HEADING_RE.match(line)
        if heading:
            blocks.append(Block("heading", heading.group(2).strip(), len(heading.group(1))))
            index += 1
            continue
        image = IMAGE_RE.match(stripped)
        if image:
            blocks.append(Block("image", path=image.group(2), alt=image.group(1)))
            index += 1
            continue
        caption = CAPTION_RE.match(stripped)
        if caption:
            blocks.append(Block("caption", caption.group(1)))
            index += 1
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            language = stripped[3:].strip()
            index += 1
            content = []
            while index < len(lines) and not lines[index].lstrip().startswith(fence):
                content.append(lines[index])
                index += 1
            if index >= len(lines):
                raise BuildError("unterminated fenced code block")
            index += 1
            blocks.append(Block("code", "\n".join(content), 0))
            blocks[-1].alt = language
            continue
        if stripped.startswith(">"):
            content = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                value = lines[index].strip()[1:].strip()
                if value.startswith("[!") and value.endswith("]"):
                    value = value[2:-1] + "："
                content.append(value)
                index += 1
            body, ids, note = _annotation("\n".join(content))
            blocks.append(Block("quote", body, note_ids=ids, note_text=note))
            continue
        if _is_table(lines, index):
            rows = [_cells(lines[index])]
            index += 2
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                rows.append(_cells(lines[index]))
                index += 1
            width = len(rows[0])
            if width < 2 or any(len(row) != width for row in rows):
                raise BuildError("Markdown table rows must have the same number of cells")
            blocks.append(Block("table", rows=rows))
            continue
        list_match = LIST_RE.match(line)
        if list_match:
            ordered = list_match.group(1) is not None
            items = []
            while index < len(lines):
                match = LIST_RE.match(lines[index])
                if not match or (match.group(1) is not None) != ordered:
                    break
                items.append(match.group(2).strip())
                index += 1
            blocks.append(Block("list", rows=[items], ordered=ordered))
            continue
        if stripped in ("---", "***"):
            blocks.append(Block("rule"))
            index += 1
            continue
        content = [stripped]
        index += 1
        while index < len(lines) and not _starts_block(lines, index):
            content.append(lines[index].strip())
            index += 1
        body, ids, note = _annotation("\n".join(content))
        blocks.append(Block("paragraph", body, note_ids=ids, note_text=note))
    return blocks


def _inline(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    emphasis_colors = {
        "blue": "#1A5276",
        "green": "#1E8449",
        "purple": "#5B2C6F",
        "red": "#B03A2E",
    }
    escaped = re.sub(
        r"\[\[(blue|green|purple|red):(.+?)\]\]",
        lambda match: '<font color="{}"><b>{}</b></font>'.format(
            emphasis_colors[match.group(1)], match.group(2)
        ),
        escaped,
    )
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" color="#1A5276">\1</a>', escaped)
    escaped = escaped.replace("\n", "<br/>")
    return escaped


def _display_source_ids(value: str, reference_numbers: Dict[str, int]) -> str:
    def replace(match: re.Match) -> str:
        source_id = match.group(0)
        if source_id not in reference_numbers:
            raise BuildError("source ID has no bibliography number: {}".format(source_id))
        return "[{}]".format(reference_numbers[source_id])
    return SOURCE_ID_RE.sub(replace, value)


def _inline_display(value: str, reference_numbers: Dict[str, int]) -> str:
    return _inline(_display_source_ids(value, reference_numbers))


def _citation_marker(source_ids: Sequence[str], sources: Dict[str, Dict[str, Any]],
                     reference_numbers: Dict[str, int]) -> str:
    numbers = []
    for source_id in source_ids:
        if source_id not in sources:
            raise BuildError("unresolved source id in source note: {}".format(source_id))
        if source_id not in reference_numbers:
            raise BuildError("source note has no bibliography number: {}".format(source_id))
        numbers.append("[{}]".format(reference_numbers[source_id]))
    return "".join(numbers)


def _inline_with_notes(value: str, sources: Dict[str, Dict[str, Any]],
                       reference_numbers: Dict[str, int]) -> str:
    """Render compact source markers; explanatory text is placed below the block."""
    rendered = []
    cursor = 0
    for match in ANNOTATION_RE.finditer(value):
        rendered.append(_inline_display(value[cursor:match.start()], reference_numbers))
        source_ids = [raw.strip().lstrip("@") for raw in match.group(1).split(",")]
        marker = _citation_marker(source_ids, sources, reference_numbers)
        rendered.append(
            '<super rise="2.5" size="6.8"><font color="#1A5276">{}</font></super>'.format(marker)
        )
        cursor = match.end()
    rendered.append(_inline_display(value[cursor:], reference_numbers))
    return "".join(rendered)


def _explanatory_notes(value: str, sources: Dict[str, Dict[str, Any]],
                       reference_numbers: Dict[str, int]) -> str:
    notes = []
    for match in ANNOTATION_RE.finditer(value):
        note = match.group(2).strip()
        if not note:
            continue
        source_ids = [raw.strip().lstrip("@") for raw in match.group(1).split(",")]
        marker = _citation_marker(source_ids, sources, reference_numbers)
        notes.append("{} {}".format(marker, note))
    return "；".join(notes)


def _styles() -> Dict[str, ParagraphStyle]:
    common = dict(fontName=FONT_REGULAR, textColor=INK, wordWrap="CJK", splitLongWords=True)
    return {
        "body": ParagraphStyle("body", fontSize=10.5, leading=18.4, alignment=TA_JUSTIFY,
                               spaceAfter=7, allowWidows=0, allowOrphans=0, **common),
        "body_left": ParagraphStyle("body_left", fontSize=10.5, leading=18.4, alignment=TA_LEFT,
                                    spaceAfter=4, **common),
        "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=22, leading=30,
                             textColor=DEEP_BLUE, spaceBefore=14, spaceAfter=10, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=17, leading=24,
                             textColor=GREEN, spaceBefore=18, spaceAfter=9, keepWithNext=True),
        "h3": ParagraphStyle("h3", fontName=FONT_BOLD, fontSize=13.5, leading=20,
                             textColor=LIGHT_BLUE, spaceBefore=13, spaceAfter=7, keepWithNext=True),
        "h4": ParagraphStyle("h4", fontName=FONT_BOLD, fontSize=11.5, leading=18,
                             textColor=PURPLE, spaceBefore=10, spaceAfter=6, keepWithNext=True),
        "quote": ParagraphStyle("quote", fontSize=10, leading=17, textColor=INK,
                                alignment=TA_LEFT, leftIndent=3 * mm, rightIndent=2 * mm,
                                fontName=FONT_REGULAR, wordWrap="CJK"),
        "figure_caption": ParagraphStyle("figure_caption", fontSize=8.5, leading=12,
                                         textColor=DEEP_BLUE, alignment=TA_CENTER,
                                         fontName=FONT_BOLD, wordWrap="CJK",
                                         spaceBefore=4, spaceAfter=3),
        "figure_source": ParagraphStyle("figure_source", fontSize=7.2, leading=10.5,
                                        textColor=MUTED, alignment=TA_CENTER,
                                        fontName=FONT_REGULAR, wordWrap="CJK",
                                        spaceBefore=1, spaceAfter=9),
        "source_note": ParagraphStyle("source_note", fontSize=7.5, leading=11.2,
                                      textColor=colors.HexColor("#657786"), alignment=TA_LEFT,
                                      fontName=FONT_REGULAR, wordWrap="CJK",
                                      leftIndent=2 * mm, spaceBefore=1, spaceAfter=7),
        "table": ParagraphStyle("table", fontSize=8.5, leading=13, textColor=INK,
                                fontName=FONT_REGULAR, wordWrap="CJK", alignment=TA_LEFT),
        "table_head": ParagraphStyle("table_head", fontSize=8.5, leading=13,
                                     textColor=colors.white, fontName=FONT_BOLD,
                                     wordWrap="CJK", alignment=TA_LEFT),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=7.5, leading=10,
                               textColor=INK, backColor=LIGHT_BG, leftIndent=4 * mm,
                               rightIndent=4 * mm, spaceBefore=5, spaceAfter=8),
    }


def _hex(value: str) -> colors.Color:
    return colors.HexColor(value)


def _draw_scene(scene: Scene, canvas: Any, scale: float) -> None:
    height = scene.height
    for item in scene.elements:
        kind = item["kind"]
        canvas.saveState()
        canvas.scale(scale, scale)
        if kind == "rect":
            canvas.setFillColor(_hex(item["fill"]))
            if item.get("stroke"):
                canvas.setStrokeColor(_hex(item["stroke"]))
            x, y = item["x"], height - item["y"] - item["height"]
            if item.get("radius"):
                canvas.roundRect(x, y, item["width"], item["height"], item["radius"],
                                 fill=1, stroke=1 if item.get("stroke") else 0)
            else:
                canvas.rect(x, y, item["width"], item["height"],
                            fill=1, stroke=1 if item.get("stroke") else 0)
        elif kind == "line":
            canvas.setStrokeColor(_hex(item["stroke"]))
            canvas.setLineWidth(item["width"])
            canvas.setDash(item.get("dash") or [])
            canvas.line(item["x1"], height - item["y1"], item["x2"], height - item["y2"])
        elif kind == "circle":
            if item.get("fill"):
                canvas.setFillColor(_hex(item["fill"]))
            if item.get("stroke"):
                canvas.setStrokeColor(_hex(item["stroke"]))
                canvas.setLineWidth(item["width"])
            canvas.circle(item["cx"], height - item["cy"], item["radius"],
                          fill=1 if item.get("fill") else 0,
                          stroke=1 if item.get("stroke") else 0)
        elif kind == "text":
            canvas.setFillColor(_hex(item["fill"]))
            font = FONT_BOLD if item.get("weight", 400) >= 600 else FONT_REGULAR
            canvas.setFont(font, item["size"])
            for index, line in enumerate(item["lines"]):
                x = item["x"]
                y = height - (item["y"] + index * item["line_height"])
                width = pdfmetrics.stringWidth(str(line), font, item["size"])
                if item["anchor"] == "middle":
                    x -= width / 2
                elif item["anchor"] == "end":
                    x -= width
                if item.get("rotation"):
                    canvas.saveState()
                    canvas.translate(item["x"], y)
                    canvas.rotate(-item["rotation"])
                    canvas.drawString(0, 0, str(line))
                    canvas.restoreState()
                else:
                    canvas.drawString(x, y, str(line))
        elif kind == "path":
            canvas.setStrokeColor(_hex(item["stroke"]))
            canvas.setLineWidth(item["width"])
            canvas.setDash(item.get("dash") or [])
            path = canvas.beginPath()
            for command in item["commands"]:
                if command[0] == "M":
                    path.moveTo(command[1], height - command[2])
                elif command[0] == "L":
                    path.lineTo(command[1], height - command[2])
                elif command[0] == "C":
                    path.curveTo(command[1], height - command[2], command[3],
                                 height - command[4], command[5], height - command[6])
            if item.get("fill"):
                canvas.setFillColor(_hex(item["fill"]))
            canvas.drawPath(path, fill=1 if item.get("fill") else 0, stroke=1)
        elif kind == "triangle":
            path = canvas.beginPath()
            first = item["points"][0]
            path.moveTo(first[0], height - first[1])
            for x, y in item["points"][1:]:
                path.lineTo(x, height - y)
            path.close()
            canvas.setFillColor(_hex(item["fill"]))
            canvas.drawPath(path, fill=1, stroke=0)
        elif kind == "pie":
            canvas.setFillColor(_hex(item["fill"]))
            x1, y1 = item["cx"] - item["radius"], height - item["cy"] - item["radius"]
            x2, y2 = item["cx"] + item["radius"], height - item["cy"] + item["radius"]
            canvas.wedge(x1, y1, x2, y2, 90 - item["start"],
                         -(item["end"] - item["start"]), fill=1, stroke=0)
        canvas.restoreState()


class SceneFlowable(Flowable):
    def __init__(self, scene: Scene, max_height: float = 375) -> None:
        Flowable.__init__(self)
        self.scene = scene
        self.max_height = max_height
        self.scale = 1.0

    def wrap(self, available_width: float, available_height: float) -> Tuple[float, float]:
        self.scale = min(available_width / self.scene.width,
                         self.max_height / self.scene.height, 1.0)
        self.width, self.height = self.scene.width * self.scale, self.scene.height * self.scale
        return self.width, self.height

    def draw(self) -> None:
        _draw_scene(self.scene, self.canv, self.scale)


class _RawBitmap:
    format = "PNG"
    mode = "RGB"

    def __init__(self, width: int, height: int, data: bytes) -> None:
        self.size = (width, height)
        self._data = data

    def convert(self, mode: str) -> "_RawBitmap":
        if mode != "RGB":
            raise BuildError("internal bitmap conversion only supports RGB")
        return self

    def tobytes(self) -> bytes:
        return self._data


def _paeth(a: int, b: int, c: int) -> int:
    estimate = a + b - c
    pa, pb, pc = abs(estimate - a), abs(estimate - b), abs(estimate - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def decode_png(path: Path) -> _RawBitmap:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BuildError("invalid PNG signature: {}".format(path.name))
    cursor, width, height, bit_depth, color_type, interlace = 8, 0, 0, 0, 0, 0
    compressed, palette = bytearray(), None
    while cursor + 12 <= len(data):
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        chunk_type = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        cursor += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"PLTE":
            palette = [tuple(payload[i:i + 3]) for i in range(0, len(payload), 3)]
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
    if not width or not height or bit_depth != 8 or interlace != 0:
        raise BuildError("PNG must be non-interlaced 8-bit: {}".format(path.name))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise BuildError("unsupported PNG color type {}: {}".format(color_type, path.name))
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise BuildError("cannot decode PNG {}: {}".format(path.name, exc))
    stride = width * channels
    offset, previous, rows = 0, bytearray(stride), []
    for _ in range(height):
        filter_type = raw[offset]
        scan = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        for index in range(stride):
            left = scan[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                scan[index] = (scan[index] + left) & 255
            elif filter_type == 2:
                scan[index] = (scan[index] + above) & 255
            elif filter_type == 3:
                scan[index] = (scan[index] + ((left + above) // 2)) & 255
            elif filter_type == 4:
                scan[index] = (scan[index] + _paeth(left, above, upper_left)) & 255
            elif filter_type != 0:
                raise BuildError("unsupported PNG row filter {}".format(filter_type))
        rows.append(scan)
        previous = scan
    rgb = bytearray()
    for row in rows:
        for x in range(width):
            pixel = row[x * channels:(x + 1) * channels]
            if color_type == 0:
                rgb.extend((pixel[0], pixel[0], pixel[0]))
            elif color_type == 2:
                rgb.extend(pixel)
            elif color_type == 3:
                if palette is None or pixel[0] >= len(palette):
                    raise BuildError("invalid indexed PNG palette: {}".format(path.name))
                rgb.extend(palette[pixel[0]])
            elif color_type in (4, 6):
                base = (pixel[0], pixel[0], pixel[0]) if color_type == 4 else pixel[:3]
                alpha = pixel[-1] / 255.0
                rgb.extend(int(channel * alpha + 255 * (1 - alpha)) for channel in base)
    return _RawBitmap(width, height, bytes(rgb))


class PortableImage(Flowable):
    def __init__(self, path: Path, max_height: float = 355,
                 max_width_ratio: float = 0.78) -> None:
        Flowable.__init__(self)
        self.path, self.max_height, self.max_width_ratio = path, max_height, max_width_ratio
        suffix = path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            with path.open("rb") as handle:
                self.pixel_width, self.pixel_height = pdfutils.readJPEGInfo(handle)[:2]
            self.image = str(path)
        elif suffix == ".png":
            self.image = decode_png(path)
            self.pixel_width, self.pixel_height = self.image.size
        else:
            raise BuildError("unsupported image format {}; convert WebP/AVIF to PNG or JPEG".format(suffix or "(none)"))
        self.scale = 1.0

    def wrap(self, available_width: float, available_height: float) -> Tuple[float, float]:
        self.scale = min((available_width * self.max_width_ratio) / self.pixel_width,
                         self.max_height / self.pixel_height, 1.0)
        self.width, self.height = self.pixel_width * self.scale, self.pixel_height * self.scale
        return self.width, self.height

    def draw(self) -> None:
        self.canv.drawInlineImage(self.image, 0, 0, self.width, self.height,
                                  preserveAspectRatio=True)


def _visual_map(spec_path: Optional[Path], report_root: Path,
                sources: Dict[str, Dict[str, Any]],
                reference_numbers: Dict[str, int]) -> Dict[Path, Scene]:
    if spec_path is None:
        return {}
    if not spec_path.is_file():
        raise BuildError("visual spec not found: {}".format(spec_path))
    try:
        visuals = load_visual_specs(spec_path)
        output_dir = report_root / "visuals"
        output_dir.mkdir(parents=True, exist_ok=True)
    except SpecError as exc:
        raise BuildError("invalid visual specification: {}".format(exc))
    mapping = {}
    for item in visuals:
        referenced = set(re.findall(r"S\d{3,}", str(item.get("source", ""))))
        for edge in item.get("edges", []):
            if isinstance(edge, dict):
                referenced.update(re.findall(r"S\d{3,}", str(edge.get("source", ""))))
        missing = sorted(referenced - set(sources))
        if missing:
            raise BuildError("visual {} references missing sources: {}".format(
                item["output"], ", ".join(missing)))
        display_item = copy.deepcopy(item)
        if referenced and referenced.issubset(reference_numbers):
            display_item["source"] = _display_source_ids(
                str(display_item.get("source", "")), reference_numbers
            )
        scene = scene_from_spec(display_item)
        target = output_dir / item["output"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(scene_to_svg(scene), encoding="utf-8")
        mapping[target.resolve()] = scene
    return mapping


def _local_path(raw: str, base: Path) -> Path:
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https", "data"):
        raise BuildError("remote images must be localized before build: {}".format(raw))
    path = (base / unquote(parsed.path)).resolve()
    root = base.resolve()
    if path != root and root not in path.parents:
        raise BuildError("image path must stay inside the report directory: {}".format(raw))
    if not path.is_file():
        raise BuildError("local image not found: {}".format(path))
    return path


def _paragraph_with_note(block: Block, style: ParagraphStyle,
                         sources: Dict[str, Dict[str, Any]],
                         reference_numbers: Dict[str, int]) -> Flowable:
    return Paragraph(_inline_with_notes(block.text, sources, reference_numbers), style)


def _note_flowable(block: Block, style: ParagraphStyle,
                   sources: Dict[str, Dict[str, Any]],
                   reference_numbers: Dict[str, int]) -> Optional[Flowable]:
    note = _explanatory_notes(block.text, sources, reference_numbers)
    if not note:
        return None
    return Paragraph("说明：{}".format(_inline(note)), style)


def _story(blocks: List[Block], title: str, author: str, sources: Dict[str, Dict[str, Any]],
           visuals: Dict[Path, Scene], report_root: Path, doc_width: float,
           reference_numbers: Dict[str, int], reading_metrics: Dict[str, Any]) -> List[Flowable]:
    styles = _styles()
    story = [Spacer(1, 55 * mm), Paragraph(html.escape(title), ParagraphStyle(
        "cover_title", fontName=FONT_BOLD, fontSize=28, leading=38, textColor=DEEP_BLUE,
        alignment=TA_CENTER, wordWrap="CJK", spaceAfter=9 * mm)),
        Table([[""]], colWidths=[44 * mm], rowHeights=[1.1 * mm],
              style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), DEEP_BLUE),
                                ("ALIGN", (0, 0), (-1, -1), "CENTER")]), hAlign="CENTER"),
        Spacer(1, 8 * mm), Paragraph("横纵分析法深度研究报告", ParagraphStyle(
            "cover_sub", fontName=FONT_REGULAR, fontSize=13, leading=20, textColor=MUTED,
            alignment=TA_CENTER)), Spacer(1, 28 * mm),
        Paragraph("生成日期：{}".format(datetime.now().strftime("%Y-%m-%d %H:%M")), ParagraphStyle(
            "cover_date", fontName=FONT_REGULAR, fontSize=9, leading=16,
            textColor=MUTED, alignment=TA_CENTER)),
        Paragraph("全文字数：{:,} 字".format(reading_metrics["word_count"]), ParagraphStyle(
            "cover_word_count", fontName=FONT_REGULAR, fontSize=9, leading=16,
            textColor=MUTED, alignment=TA_CENTER)),
        Paragraph(_reading_time_label(reading_metrics), ParagraphStyle(
            "cover_reading_time", fontName=FONT_REGULAR, fontSize=9, leading=16,
            textColor=MUTED, alignment=TA_CENTER)),
        Paragraph("按 300 至 500 字/分钟粗估；图表研读与思考另计", ParagraphStyle(
            "cover_reading_basis", fontName=FONT_REGULAR, fontSize=8, leading=14,
            textColor=MUTED, alignment=TA_CENTER)),
        Paragraph("原创作者-数字生命卡兹克", ParagraphStyle(
            "cover_author1", fontName=FONT_REGULAR, fontSize=9, leading=16,
            textColor=MUTED, alignment=TA_CENTER)),
        Paragraph("改进作者-RollingLog滑行日志", ParagraphStyle(
            "cover_author2", fontName=FONT_REGULAR, fontSize=9, leading=16,
            textColor=MUTED, alignment=TA_CENTER)), PageBreak()]

    for block in _report_body_blocks(blocks):
        if block.kind == "heading":
            heading = Paragraph(_inline_display(block.text, reference_numbers),
                                styles["h{}".format(block.level)])
            if block.level == 2:
                holder = Table([[heading]], colWidths=[doc_width], hAlign="LEFT")
                holder.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 3, DEEP_BLUE),
                                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                story.append(holder)
            else:
                story.append(heading)
        elif block.kind == "paragraph":
            story.append(_paragraph_with_note(block, styles["body"], sources, reference_numbers))
            note = _note_flowable(block, styles["source_note"], sources, reference_numbers)
            if note is not None:
                story.append(note)
        elif block.kind == "quote":
            inner = _paragraph_with_note(block, styles["quote"], sources, reference_numbers)
            box = Table([[inner]], colWidths=[doc_width], hAlign="LEFT")
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                                     ("LINEBEFORE", (0, 0), (0, -1), 3, DEEP_BLUE),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                     ("TOPPADDING", (0, 0), (-1, -1), 7),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            story.extend([box, Spacer(1, 6)])
            note = _note_flowable(block, styles["source_note"], sources, reference_numbers)
            if note is not None:
                story.append(note)
        elif block.kind == "list":
            for index, item in enumerate((block.rows or [[]])[0]):
                prefix = "{}. ".format(index + 1) if block.ordered else "• "
                style = ParagraphStyle("list_item", parent=styles["body_left"], leftIndent=6 * mm,
                                       firstLineIndent=-4 * mm, spaceAfter=3)
                story.append(Paragraph(_inline_display(prefix + item, reference_numbers), style))
        elif block.kind == "table":
            rows = block.rows or []
            rendered = []
            for row_index, row in enumerate(rows):
                style = styles["table_head"] if row_index == 0 else styles["table"]
                rendered.append([Paragraph(_inline_display(cell, reference_numbers), style) for cell in row])
            table = Table(rendered, colWidths=[doc_width / len(rows[0])] * len(rows[0]),
                          repeatRows=1, hAlign="LEFT", splitByRow=True)
            commands = [("BACKGROUND", (0, 0), (-1, 0), DEEP_BLUE),
                        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
            for row_index in range(1, len(rows)):
                if row_index % 2 == 0:
                    commands.append(("BACKGROUND", (0, row_index), (-1, row_index), LIGHT_BG))
            table.setStyle(TableStyle(commands))
            story.extend([Spacer(1, 4), table, Spacer(1, 9)])
        elif block.kind == "image":
            path = _local_path(block.path, report_root)
            if path.suffix.lower() == ".svg":
                if path not in visuals:
                    raise BuildError("SVG is not represented in --visual-spec: {}".format(path.name))
                figure = SceneFlowable(visuals[path])
            else:
                figure = PortableImage(path)
            holder = Table([[figure]], colWidths=[doc_width], hAlign="CENTER")
            holder.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            story.append(holder)
            if block.alt:
                story.append(Paragraph(_inline_display(block.alt, reference_numbers),
                                       styles["figure_caption"]))
        elif block.kind == "caption":
            story.append(Paragraph(_inline_display(block.text, reference_numbers),
                                   styles["figure_source"]))
        elif block.kind == "code":
            code = _display_source_ids(block.text, reference_numbers)
            story.append(Paragraph(html.escape(code).replace("\n", "<br/>"), styles["code"]))
        elif block.kind == "rule":
            story.append(Table([[""]], colWidths=[doc_width], rowHeights=[0.4],
                               style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), BORDER)])))
            story.append(Spacer(1, 6))
    return story


def _report_body_blocks(blocks: Sequence[Block]) -> Sequence[Block]:
    """Use the same content boundary as the PDF, excluding cover metadata."""
    start = 1 if blocks and blocks[0].kind == "heading" and blocks[0].level == 1 else 0
    if start < len(blocks) and blocks[start].kind == "quote" and (
            "研究截面" in blocks[start].text or "研究时间" in blocks[start].text):
        start += 1
    return blocks[start:]


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.in_reference = False

    def handle_data(self, data: str) -> None:
        if not self.in_reference:
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "super":
            self.in_reference = True
        if tag == "br":
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "super":
            self.in_reference = False


def _count_visible_text(rendered: str) -> Tuple[int, int]:
    parser = _VisibleText()
    parser.feed(rendered)
    parser.close()
    # Inline styling must not split a word; chunks from distinct cells/blocks
    # are counted separately by the caller. URLs and citation indices are metadata.
    text = "".join(parser.parts)
    text = COUNT_URL_RE.sub(" ", text)
    cjk_count = len(CJK_COUNT_RE.findall(text))
    other_words = len(WORD_COUNT_RE.findall(CJK_COUNT_RE.sub(" ", text)))
    return cjk_count, other_words


def _reading_metrics(blocks: Sequence[Block], visuals: Dict[Path, Scene],
                     report_root: Path, reference_numbers: Dict[str, int],
                     sources: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Count rendered report content, rather than Markdown syntax or raw bytes."""
    chunks: List[str] = []
    for block in _report_body_blocks(blocks):
        if block.kind in ("paragraph", "quote"):
            # Remove only actual source syntax, preserving literal values like [123].
            body = SOURCE_ID_RE.sub("", ANNOTATION_RE.sub("", block.text))
            chunks.append(_inline(body))
            note = _explanatory_notes(block.text, sources, reference_numbers)
            if note:
                chunks.append(_inline("说明：" + block.note_text))
        elif block.kind in ("heading", "caption"):
            chunks.append(_inline(SOURCE_ID_RE.sub("", block.text)))
        elif block.kind in ("list", "table"):
            for row in block.rows or []:
                chunks.extend(_inline(SOURCE_ID_RE.sub("", cell)) for cell in row)
        elif block.kind == "image":
            chunks.append(_inline(SOURCE_ID_RE.sub("", block.alt)))
            scene = visuals.get(_local_path(block.path, report_root))
            if scene is not None:
                for item in scene.elements:
                    if item["kind"] == "text":
                        # A wrapped visual label is one text run.
                        chunks.append(html.escape("".join(str(line) for line in item["lines"])))
        elif block.kind == "code":
            chunks.append(html.escape(SOURCE_ID_RE.sub("", block.text)))
    counts = [_count_visible_text(chunk) for chunk in chunks]
    cjk_count = sum(value[0] for value in counts)
    other_words = sum(value[1] for value in counts)
    count = cjk_count + other_words
    return {
        "word_count": count,
        "cjk_character_count": cjk_count,
        "other_word_count": other_words,
        "estimated_minutes_min": (count + READING_RATE_FAST - 1) // READING_RATE_FAST,
        "estimated_minutes_max": (count + READING_RATE_SLOW - 1) // READING_RATE_SLOW,
        "reading_rate_units_per_minute": {"slow": READING_RATE_SLOW, "fast": READING_RATE_FAST},
        "counting_rule": "汉字各计1；外文单词和数字串各计1；不计标点、空白、URL和引用编号",
        "scope": "正文、标题、表格、图注、段后说明、参考文献及已嵌入矢量图文字；不计封面、页眉页脚及位图内文字",
        "estimate_basis": "面向中文报告的300至500字/分钟粗估假设；图表研读、查证和思考另计，不代表理解或掌握所需时间",
    }


def _reading_time_label(metrics: Dict[str, Any]) -> str:
    low, high = metrics["estimated_minutes_min"], metrics["estimated_minutes_max"]
    interval = str(low) if low == high else "{} 至 {}".format(low, high)
    return "预计阅读时间：约 {} 分钟".format(interval)


def _html_blocks(blocks: List[Block], sources: Dict[str, Dict[str, Any]],
                 reference_numbers: Dict[str, int]) -> str:
    result = []
    for block in blocks:
        if block.kind == "heading":
            result.append("<h{0}>{1}</h{0}>".format(
                block.level, _inline_display(block.text, reference_numbers)))
        elif block.kind in ("paragraph", "quote"):
            body = "<p>{}</p>".format(
                _inline_with_notes(block.text, sources, reference_numbers))
            if block.kind == "quote":
                body = "<blockquote>{}</blockquote>".format(body)
            note = _explanatory_notes(block.text, sources, reference_numbers)
            if note:
                body += '<p class="source-note">说明：{}</p>'.format(_inline(note))
            result.append(body)
        elif block.kind == "list":
            tag = "ol" if block.ordered else "ul"
            items = "".join("<li>{}</li>".format(
                _inline_display(item, reference_numbers)) for item in (block.rows or [[]])[0])
            result.append("<{0}>{1}</{0}>".format(tag, items))
        elif block.kind == "table":
            rows = block.rows or []
            head = "".join("<th>{}</th>".format(
                _inline_display(cell, reference_numbers)) for cell in rows[0])
            body = "".join("<tr>{}</tr>".format("".join(
                "<td>{}</td>".format(_inline_display(cell, reference_numbers))
                for cell in row)) for row in rows[1:])
            result.append("<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>".format(head, body))
        elif block.kind == "image":
            suffix = Path(urlparse(block.path).path).suffix.lower()
            figure_class = "data-visual" if suffix == ".svg" else "illustration"
            result.append('<figure class="{}"><img src="{}" alt="{}"><figcaption>{}</figcaption></figure>'.format(
                figure_class, html.escape(block.path, quote=True), html.escape(block.alt, quote=True),
                _inline_display(block.alt, reference_numbers)))
        elif block.kind == "caption":
            result.append('<p class="figure-source">{}</p>'.format(
                _inline_display(block.text, reference_numbers)))
        elif block.kind == "code":
            result.append("<pre><code>{}</code></pre>".format(
                html.escape(_display_source_ids(block.text, reference_numbers))))
        elif block.kind == "rule":
            result.append("<hr>")
    return "\n".join(result)


def build_html(blocks: List[Block], css: str, title: str, author: str,
               sources: Dict[str, Dict[str, Any]], lang: str,
               reference_numbers: Dict[str, int], reading_metrics: Dict[str, Any]) -> str:
    return """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="orthogonal-research-skill"><title>{title}</title><style>{css}</style></head>
<body><section class="cover"><h1>{title}</h1><div class="cover-rule"></div><p>横纵分析法深度研究报告</p>
<p class="cover-meta">生成日期：{day}</p><p class="cover-stat">全文字数：{word_count:,} 字</p>
<p class="cover-stat">{reading_time}</p><p class="cover-stat">按 300 至 500 字/分钟粗估；图表研读与思考另计</p>
<p class="cover-meta">原创作者-数字生命卡兹克</p><p class="cover-meta">改进作者-RollingLog滑行日志</p></section><main class="report">{body}</main></body></html>""".format(
        lang=html.escape(lang, quote=True), title=html.escape(title), css=css,
        day=datetime.now().strftime("%Y-%m-%d %H:%M"),
        word_count=reading_metrics["word_count"], reading_time=html.escape(_reading_time_label(reading_metrics)),
        body=_html_blocks(blocks, sources, reference_numbers))


def _header_footer(canvas: Any, doc: Any, title: str) -> None:
    canvas.saveState()
    canvas.setFont(FONT_REGULAR, 7.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, A4[1] - 14 * mm,
                      "{} | 横纵分析法深度研究报告".format(title))
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, A4[1] - 16 * mm, A4[0] - 20 * mm, A4[1] - 16 * mm)
    canvas.setFont(FONT_REGULAR, 8)
    canvas.drawCentredString(A4[0] / 2, 11 * mm, "第 {} 页".format(max(1, doc.page - 1)))
    canvas.restoreState()


def build_report(input_path: Path, output_path: Path, title: str, author: str,
                 sources_path: Optional[Path], visual_spec: Optional[Path],
                 css_path: Path, html_output: Optional[Path], lang: str,
                 html_only: bool = False, log_output: Optional[Path] = None) -> Dict[str, Any]:
    if not input_path.is_file():
        raise BuildError("input Markdown not found: {}".format(input_path))
    source_text = input_path.read_text(encoding="utf-8")
    blocks = parse_markdown(source_text)
    if not blocks:
        raise BuildError("input Markdown is empty")
    if title == "横纵分析报告" and blocks[0].kind == "heading":
        title = blocks[0].text
    sources, source_payload = load_sources(sources_path)
    report_root = input_path.parent.resolve()
    visual_references = _visual_reference_map(visual_spec, report_root)
    citation_order = _citation_order(blocks, report_root, visual_references)
    unresolved = [source_id for source_id in citation_order if source_id not in sources]
    if unresolved:
        raise BuildError("unresolved source ids: {}".format(", ".join(unresolved)))
    bibliography_order = []
    reference_numbers = {}
    source_balance = {"status": "not-applicable", "distribution": [],
                      "deduplicated_sources": [], "excluded_tier4_sources": []}
    if citation_order:
        bibliography_order = _bibliography_order(source_text, sources)
        _validate_bibliography(citation_order, bibliography_order)
        reference_numbers = {source_id: index + 1
                             for index, source_id in enumerate(citation_order)}
        source_balance = _source_balance(citation_order, sources, source_payload)
    coverage = source_payload.get("coverage", {})
    disclosure_needed = bool(coverage.get("blocked_domains") or coverage.get("network_limitations")
                             or source_payload.get("limitations")
                             or source_balance.get("status") == "exception")
    if disclosure_needed and not ("执行摘要" in source_text and "研究范围与限制" in source_text):
        raise BuildError("search limitations require both an executive summary and a research limitations section")
    visuals = _visual_map(visual_spec, report_root, sources, reference_numbers)
    reading_metrics = _reading_metrics(blocks, visuals, report_root, reference_numbers, sources)
    html_path = html_output or output_path.with_suffix(".html")
    html_error = None
    try:
        css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
        html_text = build_html(blocks, css, title, author, sources, lang, reference_numbers, reading_metrics)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_text, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        html_error = str(exc)
        if html_only:
            raise BuildError("HTML debug output failed: {}".format(exc))
    register_fonts()
    if not html_only:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=20 * mm,
                                rightMargin=20 * mm, topMargin=25 * mm, bottomMargin=20 * mm,
                                title=title, author=author, subject="横纵分析法深度研究报告",
                                pageCompression=1, allowSplitting=1)
        story = _story(blocks, title, author, sources, visuals, report_root, doc.width,
                       reference_numbers, reading_metrics)
        doc.build(story, onFirstPage=lambda canvas, current: None,
                  onLaterPages=lambda canvas, current: _header_footer(canvas, current, title))
    log_path = log_output or output_path.with_suffix(".build.json")
    record = {
        "status": "html-only" if html_only else "success",
        "backend": "ReportLab {} bundled pure Python subset".format(REPORTLAB_VERSION),
        "python": "{}.{}.{}".format(*sys.version_info[:3]),
        "input": input_path.name,
        "output": None if html_only else output_path.name,
        "html": html_path.name if html_path.is_file() else None,
        "html_error": html_error,
        "reading_metrics": reading_metrics,
        "citation_source_ids": citation_order,
        "bibliography_source_ids": bibliography_order,
        "reference_numbers": reference_numbers,
        "visual_count": len(visuals),
        "bitmap_image_count": sum(
            1 for block in blocks
            if block.kind == "image" and Path(urlparse(block.path).path).suffix.lower() != ".svg"
        ),
        "source_count": len(sources),
        "tier1_source_count": sum(1 for source in sources.values() if source.get("tier") == 1),
        "overseas_source_count": sum(1 for source in sources.values()
                                     if str(source.get("region", "")).upper() not in ("", "CN")
                                     or str(source.get("language", "")).lower() not in ("", "zh", "zh-cn")),
        "coverage": source_payload.get("coverage", {}),
        "limitations": source_payload.get("limitations", []),
        "source_balance": source_balance,
        "font_sha256": {FONT_REGULAR_PATH.name: _sha256(FONT_REGULAR_PATH),
                        FONT_BOLD_PATH.name: _sha256(FONT_BOLD_PATH)},
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _png_fixture(path: Path) -> None:
    width, height = 32, 20
    rows = b"".join(b"\x00" + bytes([42, 86, 118]) * width for _ in range(height))
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    path.write_bytes(data)


def self_test() -> None:
    count_sources = {"S001": {"id": "S001"}}
    count_report = "# 封面标题\n\n> 研究截面：2026-10-02\n\n## 正文\n\n研究 **USB4** & SSD，速度 40。{{@S001 | 口径一致。}}"
    count_metrics = _reading_metrics(parse_markdown(count_report), {}, Path.cwd(), {"S001": 1}, count_sources)
    if count_metrics["word_count"] != 15 or count_metrics["cjk_character_count"] != 12:
        raise BuildError("visible content counting failed: citation notes must be counted once")
    plain_report = "# 另一个封面\n\n## 正文\n\n研究 USB4 & SSD，速度 40。{{@S001 | 口径一致。}}"
    plain_metrics = _reading_metrics(parse_markdown(plain_report), {}, Path.cwd(), {"S001": 1}, count_sources)
    if count_metrics != plain_metrics:
        raise BuildError("cover metadata or inline formatting changed reading metrics")
    extra_metrics = _reading_metrics(parse_markdown(count_report + "\n\n新增事实。"), {}, Path.cwd(),
                                     {"S001": 1}, count_sources)
    if extra_metrics["word_count"] != 19:
        raise BuildError("reading metrics did not update after a content edit")
    if _count_visible_text("<b>USB</b>4<br/>SSD &amp; 40Gbps https://example.com/long/path <super>[1]</super>") != (0, 3):
        raise BuildError("mixed text, line break, URL, or reference counting failed")
    if _count_visible_text("官网：https://example.com。请核查条款。") != (7, 0):
        raise BuildError("URL counting consumed adjacent Chinese content")
    if _count_visible_text("型号 [123] 与 [456]。") != (3, 2):
        raise BuildError("literal bracketed values were mistaken for source references")
    for count, expected in ((1, (1, 1)), (300, (1, 1)), (500, (1, 2)), (501, (2, 2)), (1500, (3, 5))):
        metrics = _reading_metrics([Block("paragraph", "字" * count)], {}, Path.cwd(), {}, {})
        if (metrics["estimated_minutes_min"], metrics["estimated_minutes_max"]) != expected:
            raise BuildError("reading time rounding failed at {} characters".format(count))
    with tempfile.TemporaryDirectory(prefix="orthogonal-research-skill-") as temp:
        root = Path(temp) / "含 空格"
        root.mkdir()
        (root / "data").mkdir()
        (root / "images").mkdir()
        _png_fixture(root / "images" / "sample.png")
        (root / "images" / "sample.jpg").write_bytes(
            (SKILL_DIR / "assets" / "sample" / "jpeg_fixture.jpg").read_bytes()
        )
        visuals = {"visuals": [
            {"type": "timeline", "output": "timeline.svg", "title": "转折点", "source": "S001", "events": [{"date": "2020", "label": "启动"}, {"date": "2024", "label": "转型"}]},
            {"type": "bar", "output": "bar.svg", "title": "份额", "source": "S001", "labels": ["A", "B"], "values": [60, 40], "unit": "%"},
            {"type": "line", "output": "line.svg", "title": "增长", "source": "S001", "labels": ["2023", "2024"], "series": [{"name": "A", "values": [1, 2]}]},
            {"type": "donut", "output": "donut.svg", "title": "构成", "source": "S001", "labels": ["A", "B"], "values": [6, 4]},
            {"type": "matrix", "output": "matrix.svg", "title": "定位", "source": "S001", "x_label": "开放", "y_label": "集成", "points": [{"label": "A", "x": 0.7, "y": 0.8}]},
            {"type": "knowledge_graph", "output": "graph.svg", "title": "生态", "source": "S001", "nodes": [{"id": "x", "label": "对象", "group": "core", "level": 0}, {"id": "p", "label": "产品", "group": "product", "level": 1}, {"id": "c", "label": "渠道", "group": "organization", "level": 2}], "edges": [{"from": "x", "to": "p", "label": "推出", "source": "S001", "kind": "fact"}, {"from": "p", "to": "c", "label": "触达", "source": "S001", "kind": "hypothesis"}]}
        ]}
        (root / "data" / "visuals.json").write_text(json.dumps(visuals, ensure_ascii=False), encoding="utf-8")
        sources = {
            "as_of": date.today().isoformat(),
            "coverage": {
                "attempted_languages": ["zh-CN", "en"],
                "attempted_regions": ["中国", "美国"],
                "attempted_platforms": ["官网", "GitHub"],
                "successful_source_categories": ["official"],
                "successful_domains": ["example.com"],
                "blocked_domains": [],
                "network_limitations": [],
                "target_perspective_groups": ["中文/中国大陆", "英文/北美"],
                "balance_exception": None,
            },
            "limitations": [],
            "sources": [
                {"id": "S001", "display_name": "示例中文公告", "title": "示例中文公告",
                 "url": "https://example.com/zh", "publisher": "示例中国机构",
                 "published_at": "2025-01-01", "accessed_at": date.today().isoformat(),
                 "language": "zh-CN", "region": "CN", "perspective_group": "中文/中国大陆",
                 "tier": 1, "type": "official", "supports": ["C001"]},
                {"id": "S002", "display_name": "Example US Notice", "title": "Example US Notice",
                 "url": "https://example.com/en", "publisher": "Example US Institution",
                 "published_at": "2025-02-01", "accessed_at": date.today().isoformat(),
                 "language": "en", "region": "US", "perspective_group": "英文/北美",
                 "tier": 1, "type": "official", "supports": ["C001"]},
            ],
        }
        (root / "sources.json").write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
        images = "\n\n".join("![图｜{}](visuals/{})".format(name, name) for name in ("timeline.svg", "bar.svg", "line.svg", "donut.svg", "matrix.svg", "graph.svg"))
        table_rows = "\n".join("| 对象 {:02d} | 定位说明 | 用于验证跨页表格 |".format(i) for i in range(1, 56))
        report = "# 跨平台自检报告：一份包含中文 English 和超长标题的横纵分析渲染验证\n\n> 研究截面：{}｜范围：全球\n\n## 一、一句话定义\n\n正文包含中文、English 与长标题；**加粗信息**与[[blue:关键判断]]、[[green:正向信号]]、[[purple:方法概念]]、[[red:风险警告]]可以受控强调。{{{{@S001,@S002 | 两种文化语言语境共同支持该句。}}}}\n\n> 这是用于验证“3pt 深蓝竖线 + 浅灰背景”的引用块。{{{{@S001 | 引用块也支持句末蓝色小字。}}}}\n\n{}\n\n![图 1｜PNG 图片图注](images/sample.png)\n\n<span class=\"figure-source\">来源：本地自检素材</span>\n\n![图 2｜JPEG 图片图注](images/sample.jpg)\n\n## 二、表格\n\n| 对象 | 定位 | 代价 |\n|---|---|---|\n{}\n\n## 五、信息来源与方法说明\n\n1. 示例中文公告｜示例中国机构｜示例中文公告｜https://example.com/zh｜发布日期：2025-01-01｜访问日期：{}\n2. Example US Notice｜Example US Institution｜Example US Notice｜https://example.com/en｜发布日期：2025-02-01｜访问日期：{}\n".format(date.today().isoformat(), images, table_rows, date.today().isoformat(), date.today().isoformat())
        (root / "report.md").write_text(report, encoding="utf-8")
        build_report(root / "report.md", root / "self-test.pdf", "横纵分析报告",
                     "metadata-only-author", root / "sources.json", root / "data" / "visuals.json",
                     DEFAULT_CSS, None, "zh-CN")
        if not (root / "self-test.pdf").is_file() or (root / "self-test.pdf").stat().st_size < 5000:
            raise BuildError("self-test PDF was not created correctly")
        html_debug = (root / "self-test.html").read_text(encoding="utf-8")
        build_log = json.loads((root / "self-test.build.json").read_text(encoding="utf-8"))
        log_metrics = build_log["reading_metrics"]
        if "全文字数：{:,} 字".format(log_metrics["word_count"]) not in html_debug or _reading_time_label(log_metrics) not in html_debug:
            raise BuildError("cover metrics and build log disagree")
        if "作者：" in html_debug or "metadata-only-author" in html_debug:
            raise BuildError("cover author must never be visible")
        if "<super" not in html_debug or "source-note" not in html_debug or "figure-source" not in html_debug:
            raise BuildError("compact source marker, explanatory note, or figure caption hierarchy is missing")
        if "[1][2]" not in html_debug or "S001" in html_debug or "S002" in html_debug:
            raise BuildError("hybrid citation numbers were not rendered or internal IDs leaked")
        if "border-left: 3pt solid var(--deep-blue)" not in html_debug:
            raise BuildError("v1 quote block styling is missing")
        if "padding-left: 3mm" not in html_debug:
            raise BuildError("main chapter heading marker is missing")
        if 'figure class="illustration"' not in html_debug or 'figure class="data-visual"' not in html_debug:
            raise BuildError("illustration and data-visual sizing classes are missing")
        bitmap = PortableImage(root / "images" / "sample.png")
        bitmap_width, _ = bitmap.wrap(20, 100)
        if bitmap_width > 20 * 0.78 + 0.01:
            raise BuildError("bitmap illustration width cap is missing")
        if PureWindowsPath(r"C:\研究 报告\output.pdf").suffix.lower() != ".pdf":
            raise BuildError("Windows path simulation failed")
        pass_balance = _source_balance(["S001", "S002"],
                                       {item["id"]: item for item in sources["sources"]}, sources)
        if pass_balance["status"] != "pass" or any(
                item["share"] != 0.5 for item in pass_balance["distribution"]):
            raise BuildError("50/50 perspective balance test failed")

        def balance_fixture(a_count: int, b_count: int, groups: Optional[List[str]] = None
                            ) -> Tuple[List[str], Dict[str, Dict[str, Any]], Dict[str, Any]]:
            group_names = groups or ["组 A", "组 B"]
            counts = [a_count, b_count] if len(group_names) == 2 else [1, 2, 2]
            ids, mapping = [], {}
            serial = 1
            for group, count in zip(group_names, counts):
                for _ in range(count):
                    source_id = "T{:03d}".format(serial)
                    serial += 1
                    ids.append(source_id)
                    mapping[source_id] = {"tier": 1, "perspective_group": group}
            payload = {"coverage": {"target_perspective_groups": group_names,
                                     "balance_exception": None}, "limitations": []}
            return ids, mapping, payload

        ids_20, mapping_20, payload_20 = balance_fixture(1, 4)
        distribution_20 = _source_balance(ids_20, mapping_20, payload_20)["distribution"]
        if [item["share"] for item in distribution_20] != [0.2, 0.8]:
            raise BuildError("20/80 boundary balance test failed")
        ids_three, mapping_three, payload_three = balance_fixture(
            1, 2, ["组 A", "组 B", "组 C"])
        if _source_balance(ids_three, mapping_three, payload_three)["status"] != "pass":
            raise BuildError("three-group balance test failed")
        ids_fail, mapping_fail, payload_fail = balance_fixture(19, 81)
        try:
            _source_balance(ids_fail, mapping_fail, payload_fail)
        except BuildError:
            pass
        else:
            raise BuildError("19/81 imbalance was not rejected")
        payload_fail["coverage"]["balance_exception"] = {
            "cause": "目标语境公开资料稀缺", "attempts": ["补充当地语言检索"],
            "bias": "结论可能偏向资料较多的一侧", "affected_claims": ["C001"],
            "confidence": "low",
        }
        payload_fail["limitations"] = [{
            "scope": "来源平衡", "cause": "目标语境公开资料稀缺",
            "bias": "结论可能偏向资料较多的一侧", "affected_claims": ["C001"],
            "confidence": "low",
        }]
        if _source_balance(ids_fail, mapping_fail, payload_fail)["status"] != "exception":
            raise BuildError("valid balance exception test failed")
        dedupe_sources = {
            "D001": {"tier": 1, "perspective_group": "组 A", "independence_key": "wire-1"},
            "D002": {"tier": 2, "perspective_group": "组 A", "independence_key": "wire-1"},
            "D003": {"tier": 1, "perspective_group": "组 B"},
            "D004": {"tier": 4, "perspective_group": "组 B"},
        }
        dedupe_payload = {"coverage": {"target_perspective_groups": ["组 A", "组 B"],
                                       "balance_exception": None}, "limitations": []}
        dedupe = _source_balance(list(dedupe_sources), dedupe_sources, dedupe_payload)
        if (dedupe["status"] != "pass" or len(dedupe["deduplicated_sources"]) != 1
                or dedupe["excluded_tier4_sources"] != ["D004"]):
            raise BuildError("deduplication or Tier 4 exclusion test failed")

        duplicate_rescue = {
            **{"A{:03d}".format(index): {"tier": 1, "perspective_group": "组 A"}
               for index in range(1, 6)},
            **{"B{:03d}".format(index): {"tier": 2, "perspective_group": "组 B",
                                         "independence_key": "same-wire"}
               for index in range(1, 5)},
        }
        try:
            _source_balance(list(duplicate_rescue), duplicate_rescue, dedupe_payload)
        except BuildError:
            pass
        else:
            raise BuildError("duplicate derivatives incorrectly rescued source balance")
        tier4_rescue = {
            **{"A{:03d}".format(index): {"tier": 1, "perspective_group": "组 A"}
               for index in range(1, 5)},
            "B001": {"tier": 4, "perspective_group": "组 B"},
        }
        try:
            _source_balance(list(tier4_rescue), tier4_rescue, dedupe_payload)
        except BuildError:
            pass
        else:
            raise BuildError("Tier 4 source incorrectly rescued source balance")

        source_mapping = {item["id"]: item for item in sources["sources"]}
        bibliography_text = (
            "## 五、信息来源与方法说明\n\n"
            "1. 示例中文公告｜示例中国机构｜示例中文公告｜https://example.com/zh｜"
            "发布日期：2025-01-01｜访问日期：{}\n"
            "2. Example US Notice｜Example US Institution｜Example US Notice｜"
            "https://example.com/en｜发布日期：2025-02-01｜访问日期：{}\n"
        ).format(date.today().isoformat(), date.today().isoformat())
        if _bibliography_order(bibliography_text, source_mapping) != ["S001", "S002"]:
            raise BuildError("numbered bibliography mapping test failed")
        for bad_bibliography in (
                bibliography_text.replace("2. Example", "1. Example"),
                bibliography_text.replace("https://example.com/en", "https://wrong.example/en"),
                "## 五、信息来源与方法说明\n\n没有编号来源。"):
            try:
                _bibliography_order(bad_bibliography, source_mapping)
            except BuildError:
                pass
            else:
                raise BuildError("invalid bibliography was not rejected")
        try:
            _validate_bibliography(["S001", "S002"], ["S002", "S001"])
        except BuildError:
            pass
        else:
            raise BuildError("bibliography order mismatch was not rejected")
        try:
            _validate_bibliography(["S001"], ["S001", "S002"])
        except BuildError:
            pass
        else:
            raise BuildError("unused bibliography source was not rejected")
        try:
            parse_markdown("# Bad\n\n旧式标记 [" + "@S001" + "]")
        except BuildError:
            pass
        else:
            raise BuildError("legacy numeric marker was not rejected")
        (root / "bad.md").write_text("# Bad\n\n无法解析。{{@S999 | 缺失来源}}", encoding="utf-8")
        try:
            build_report(root / "bad.md", root / "bad.pdf", "Bad", "",
                         root / "sources.json", None, DEFAULT_CSS, None, "zh-CN")
        except BuildError as exc:
            if "S999" not in str(exc):
                raise
        else:
            raise BuildError("missing source id was not rejected")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", help="input Markdown")
    parser.add_argument("output", type=Path, nargs="?", help="output PDF")
    parser.add_argument("--title", default="横纵分析报告")
    parser.add_argument("--author", default="", help="optional PDF metadata only; never shown on the cover")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--visual-spec", type=Path)
    parser.add_argument("--css", type=Path, default=DEFAULT_CSS, help="HTML debug stylesheet")
    parser.add_argument("--lang", default="zh-CN")
    parser.add_argument("--html-output", type=Path)
    parser.add_argument("--html-only", action="store_true")
    parser.add_argument("--log-output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            self_test()
            print("self-test: PASS")
            return 0
        if args.input is None or args.output is None:
            parser.error("input and output are required unless --self-test is used")
        record = build_report(args.input, args.output, args.title, args.author, args.sources,
                              args.visual_spec, args.css, args.html_output, args.lang,
                              args.html_only, args.log_output)
        print(json.dumps({"pdf": record["output"], "html": record["html"],
                          "status": record["status"]}, ensure_ascii=False))
        return 0
    except (BuildError, OSError, UnicodeError, SpecError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
