#!/usr/bin/env python3
"""Build PDF, offline HTML and reusable research data from one study manifest."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

import build_report as report
from check_research import check_research
from report_components import validate_components, components_markdown, export_tables


GENERATOR = "orthogonal-research-delivery-v1"
FORMATS = {"both", "pdf", "html"}


class DeliveryError(ValueError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def invalid(value):
        raise DeliveryError("Non-finite JSON number: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=invalid)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def local_file(value, root):
    if not isinstance(value, str) or not value or "\\" in value:
        raise DeliveryError("Use a non-empty package-relative path with forward slashes")
    raw = urlparse(value)
    if raw.scheme or raw.netloc or raw.query or raw.fragment or Path(value).is_absolute():
        raise DeliveryError("Expected a local package-relative path: " + value)
    path = (root / unquote(value)).resolve()
    if not within(path, root) or not path.is_file():
        raise DeliveryError("Missing file or path outside study: " + value)
    return path


def load_study(path):
    path = Path(path).resolve()
    study = read_json(path)
    if not isinstance(study, dict) or type(study.get("version")) is not int or study["version"] != 1:
        raise DeliveryError("study.json requires version: 1")
    allowed = {"version", "id", "title", "subtitle", "subject_type", "as_of", "report", "sources", "components", "visual_spec", "theme"}
    if set(study) - allowed:
        raise DeliveryError("Unknown study fields: " + ", ".join(sorted(set(study) - allowed)))
    if not isinstance(study.get("id"), str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,79}", study["id"]):
        raise DeliveryError("study.id must be a stable ASCII slug, beginning with a letter")
    for key in ("title", "subject_type", "as_of"):
        if not isinstance(study.get(key), str) or not study[key].strip():
            raise DeliveryError("study requires " + key)
    if len(study["title"]) > 180 or any(ord(c) < 32 for c in study["title"]):
        raise DeliveryError("study.title must be a single line, at most 180 characters")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", study["as_of"]):
            raise ValueError()
        date.fromisoformat(study["as_of"])
    except ValueError:
        raise DeliveryError("study.as_of must be an ISO date")
    if "subtitle" in study and not isinstance(study["subtitle"], str):
        raise DeliveryError("study.subtitle must be text")
    theme = study.get("theme", {})
    if not isinstance(theme, dict) or set(theme) - {"accent", "source"}:
        raise DeliveryError("theme supports only accent and source")
    if theme and (not re.fullmatch(r"#[0-9a-fA-F]{6}", str(theme.get("accent", ""))) or not isinstance(theme.get("source"), str) or not theme["source"].strip()):
        raise DeliveryError("theme requires a six-digit accent and its source/editorial rationale")
    root = path.parent
    paths = {key: local_file(study.get(key, default), root) for key, default in (
        ("report", "report.md"), ("sources", "sources/sources.json"))}
    for key in ("components", "visual_spec"):
        if study.get(key):
            paths[key] = local_file(study[key], root)
    return study, paths, root


def strip_bibliography(text, source_mapping):
    """Replace numbered metadata later, preserving all authored method prose."""
    match = report.BIBLIOGRAPHY_HEADING_RE.search(text)
    if not match:
        return text.rstrip() + "\n\n## 五、信息来源与方法说明\n"
    before, tail = text[:match.end()], text[match.end():]
    kept, active = [], True
    known = {report._clean_url(str(s["url"])) for s in source_mapping.values()}
    for line in tail.splitlines():
        if report.HEADING_RE.match(line):
            active = False
        item = report.BIBLIOGRAPHY_ITEM_RE.match(line)
        urls = {report._clean_url(u) for u in report.URL_RE.findall(line)}
        if active and item and urls and urls <= known:
            continue
        kept.append(line)
    return before + "\n" + "\n".join(kept).strip() + "\n"


def bibliography(order, sources):
    return "\n".join("{}. {}｜{}｜{}｜{}｜发布日期：{}｜访问日期：{}".format(
        i + 1, s["display_name"], s["publisher"], s["title"], s["url"],
        s["published_at"], s["accessed_at"])
        for i, s in enumerate(sources[sid] for sid in order))


def place_components(text, spec, web=False):
    headings = [b.text for b in report.parse_markdown(text) if b.kind == "heading"]
    slots, remaining = {}, []
    for component in spec["components"]:
        target = component.get("after_heading")
        content = ('<div data-component-slot="{}"></div>'.format(component["id"]) if web else
                   components_markdown({"version": 1, "components": [component]}).strip())
        if target:
            if headings.count(target) != 1 or "信息来源与方法说明" in target:
                raise DeliveryError("after_heading must match one non-bibliography heading: " + target)
            slots.setdefault(target, []).append(content)
        else:
            remaining.append(content)
    lines = []
    for line in text.splitlines():
        lines.append(line)
        h = report.HEADING_RE.match(line)
        if h:
            # Parse exactly as the report parser, including optional trailing hashes.
            title = report.parse_markdown(line)[0].text
            if title in slots:
                lines.extend(["", "\n\n".join(slots[title]), ""])
    joined = "\n".join(lines).strip() + "\n"
    if remaining:
        match = report.BIBLIOGRAPHY_HEADING_RE.search(joined)
        at = match.start() if match else len(joined)
        addition = ("\n## 图解与条件对照\n\n" if not web else "\n") + "\n\n".join(remaining) + "\n\n"
        joined = joined[:at] + addition + joined[at:]
    return joined


def image_paths(text):
    result = []
    for block in report.parse_markdown(text):
        if block.kind == "image":
            result.append(block.path)
        elif block.kind == "representative_images":
            result.extend(row[1] for row in block.rows or [])
    return list(dict.fromkeys(result))


def copy_images(text, base, study_root, stage, visual_paths):
    for raw in image_paths(text):
        if raw in visual_paths:
            continue
        source = local_file(raw, base)
        if not within(source, study_root):
            raise DeliveryError("Report image escapes the study")
        if source.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise DeliveryError("Use PNG/JPEG or an SVG generated from visual_spec: " + raw)
        relative = "media/" + digest(source)[:20] + source.suffix.lower()
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        text = text.replace("](" + raw + ")", "](" + relative + ")")
    return text


def body_html(text, numbers, sources):
    """Use the established parser while keeping component insertion slots intact."""
    chunks = re.split(r'(<div data-component-slot="[A-Za-z][A-Za-z0-9_-]*"></div>)', text)
    rendered = []
    for chunk in chunks:
        if chunk.startswith('<div data-component-slot='):
            rendered.append(chunk)
        else:
            rendered.append(report._html_blocks(list(report._report_body_blocks(report.parse_markdown(chunk))), sources, numbers))
    value = "\n".join(rendered)
    inverse = {str(number): sid for sid, number in numbers.items()}
    def link_marker(match):
        return '<sup>' + re.sub(r'\[(\d+)\]', lambda m: '<a href="#source-{}">[{}]</a>'.format(inverse[m[1]], m[1]), match[1]) + '</sup>'
    return re.sub(r'<super[^>]*><font[^>]*>(.*?)</font></super>', link_marker, value)


def safe_publish(stage, output, study_id):
    """Only replace this generator's unchanged prior outputs; retain unrelated files."""
    prior_path = output / "manifest.json"
    previous = {}
    if output.exists():
        if not output.is_dir() or output.is_symlink():
            raise DeliveryError("Output must be a real directory")
        if any(output.iterdir()):
            if not prior_path.is_file():
                raise DeliveryError("Output directory is not a managed delivery; choose a new directory")
            prior = read_json(prior_path)
            if prior.get("generator") != GENERATOR or prior.get("study_id") != study_id:
                raise DeliveryError("Output belongs to another study or generator")
            previous = prior.get("files", {})
            for relative, expected in previous.items():
                p = (output / relative).resolve()
                if not within(p, output):
                    raise DeliveryError("Invalid prior manifest path")
                if p.exists() and (not p.is_file() or digest(p) != expected):
                    raise DeliveryError("Generated output was edited; choose a new output directory: " + relative)
    generated = [p for p in stage.rglob("*") if p.is_file()]
    new_paths = {p.relative_to(stage).as_posix() for p in generated}
    for relative in new_paths:
        candidate = output / relative
        if not within(candidate, output):
            raise DeliveryError("Output symlink escapes delivery")
        if candidate.exists() and relative != "manifest.json" and relative not in previous:
            raise DeliveryError("Refusing to overwrite an unrelated file: " + relative)
    output.mkdir(parents=True, exist_ok=True)
    for p in generated:
        target = output / p.relative_to(stage)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    for relative in set(previous) - new_paths:
        old = output / relative
        if old.is_file() and within(old, output):
            old.unlink()


def build_delivery(study_path, output=None, formats="both", check_only=False):
    if formats not in FORMATS:
        raise DeliveryError("format must be both, pdf, or html")
    study, paths, root = load_study(study_path)
    sources, payload = report.load_sources(paths["sources"])
    if payload.get("as_of") != study["as_of"]:
        raise DeliveryError("study.as_of and source ledger as_of must agree")
    research_check = check_research(paths["sources"])
    if research_check["schema_status"] != "pass":
        raise DeliveryError("Source ledger checks failed: " + "; ".join(research_check["errors"]))
    spec = read_json(paths["components"]) if "components" in paths else {"version": 1, "components": []}
    spec = validate_components(spec, set(sources), root)
    source_text = paths["report"].read_text(encoding="utf-8-sig")
    original_hash = digest(paths["report"])
    prose = strip_bibliography(source_text, sources)
    # Resolve placement before producing files.
    preview = place_components(prose, spec)
    preview_vrefs = report._visual_reference_map(paths.get("visual_spec"), paths["report"].parent)
    preview_order = report._citation_order(report.parse_markdown(preview), paths["report"].parent, preview_vrefs)
    if not preview_order or set(preview_order) - set(sources):
        raise DeliveryError("Report requires valid cited sources; unknown IDs: " + ", ".join(sorted(set(preview_order) - set(sources))))
    report._source_balance(preview_order, sources, payload)
    for raw in image_paths(prose):
        expected = (paths["report"].parent / unquote(raw)).resolve()
        if expected not in preview_vrefs:
            local_file(raw, paths["report"].parent)
    if check_only:
        return {"status": "validated", "study_id": study["id"], "component_count": len(spec["components"]),
                "research_review_status": "not_assessed"}
    output = Path(output).resolve() if output else root / "delivery"
    if output == root or any(within(p, output) for p in paths.values()):
        raise DeliveryError("Output must not contain the study inputs")
    work = root / "build"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="delivery-stage-", dir=work) as temp:
        stage = Path(temp)
        staged_spec = copy.deepcopy(spec)
        visual_spec = None
        visual_paths = set()
        if "visual_spec" in paths:
            visual_payload = read_json(paths["visual_spec"])
            visual_spec = stage / "data/visuals.json"
            write_json(visual_spec, visual_payload)
            visual_paths = {"visuals/" + item["output"] for item in report.load_visual_specs(visual_spec)}
        prose = copy_images(prose, paths["report"].parent, root, stage, visual_paths)
        for component in staged_spec["components"]:
            if component["kind"] == "images":
                for item in component["items"]:
                    source = local_file(item["path"], root)
                    relative = "media/" + digest(source)[:20] + source.suffix.lower()
                    (stage / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, stage / relative)
                    item["path"] = relative
        (stage / "source.md").write_text(prose, encoding="utf-8")
        compiled = place_components(prose, staged_spec)
        vrefs = report._visual_reference_map(visual_spec, stage)
        order = report._citation_order(report.parse_markdown(compiled), stage, vrefs)
        if not order:
            raise DeliveryError("A complete research delivery needs cited sources")
        unknown = set(order) - set(sources)
        if unknown:
            raise DeliveryError("Unknown sources: " + ", ".join(sorted(unknown)))
        heading = report.BIBLIOGRAPHY_HEADING_RE.search(compiled)
        compiled = compiled[:heading.end()] + "\n\n" + bibliography(order, sources) + "\n" + compiled[heading.end():]
        (stage / "report.md").write_text(compiled, encoding="utf-8")
        staged_payload = copy.deepcopy(payload)
        for dataset in staged_payload.get("datasets", []):
            dataset_source = local_file(dataset["file"], root)
            if dataset_source == paths.get("components"):
                dataset["file"] = "components.json"
            else:
                relative = "data/raw/" + digest(dataset_source)[:20] + dataset_source.suffix.lower()
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dataset_source, target)
                dataset["file"] = relative
        write_json(stage / "sources.json", staged_payload)
        write_json(stage / "components.json", staged_spec)
        blocks = report.parse_markdown(prose)
        write_json(stage / "report.json", {
            "version": 1, "study_id": study["id"], "as_of": study["as_of"],
            "title": study["title"], "purpose": "Shared input for alternate document/presentation renderers; not an automatically authored slide deck",
            "blocks": [{"id": "block-{}".format(i + 1), "kind": b.kind,
                        "text": b.text, "level": b.level, "rows": b.rows,
                        "path": b.path, "alt": b.alt, "ordered": b.ordered,
                        "source_ids": report._citation_order([b], stage, vrefs)}
                       for i, b in enumerate(blocks)],
            "components": "components.json", "sources": "sources.json",
        })
        exported_study = {**study, "report": "source.md", "sources": "sources.json", "components": "components.json"}
        if visual_spec:
            exported_study["visual_spec"] = "data/visuals.json"
        write_json(stage / "study.json", exported_study)
        (stage / "build").mkdir()
        write_json(stage / "build/research-check.json", research_check)
        build = report.build_report(stage / "report.md", stage / "report.pdf", study["title"], "",
            stage / "sources.json", visual_spec, report.DEFAULT_CSS, stage / "build/print-preview.html",
            "zh-CN", formats == "html", stage / "build/report.build.json")
        # Citation order is identical in both forms, including component-only sources.
        ordered_sources = {sid: {**sources[sid], "number": build["reference_numbers"][sid]} for sid in order}
        if formats != "pdf":
            from report_web import render_page
            web_body = body_html(place_components(prose, staged_spec, web=True), build["reference_numbers"], sources)
            page = render_page({**study, "reading_metrics": build["reading_metrics"]}, web_body,
                staged_spec, ordered_sources, stage, "report.pdf" if formats == "both" else None)
            (stage / "report.html").write_text(page, encoding="utf-8")
        (stage / "data").mkdir(exist_ok=True)
        export_tables(staged_spec, stage / "data")
        with (stage / "data/sources.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            columns = ["id", "display_name", "title", "publisher", "url", "published_at", "accessed_at", "type"]
            writer.writerow(columns)
            for sid in order:
                cells = [str(sources[sid].get(k, "")) for k in columns]
                writer.writerow(["'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for v in cells])
        if digest(paths["report"]) != original_hash:
            raise DeliveryError("Source report changed while building; retry against a consistent revision")
        manifest = {"generator": GENERATOR, "study_id": study["id"], "as_of": study["as_of"],
            "formats": ["pdf", "html"] if formats == "both" else [formats],
            "original_report_sha256": original_hash, "original_prose_rewritten": False,
            "component_kinds": sorted({c["kind"] for c in staged_spec["components"]}),
            "source_ids": order, "reading_metrics": build["reading_metrics"],
            "render_status": "success", "research_review_status": "not_assessed",
            "visual_review_status": "not_assessed", "network_calls": 0, "model_calls": 0,
            "files": {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob("*")) if p.is_file()}}
        write_json(stage / "manifest.json", manifest)
        safe_publish(stage, output, study["id"])
    return {"status": "built", "directory": str(output), "formats": manifest["formats"],
            "components": len(spec["components"]), "research_review_status": "not_assessed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=sorted(FORMATS), default="both")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(build_delivery(args.study, args.output, args.format, args.check_only), ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, report.BuildError) as exc:
        print("delivery error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
