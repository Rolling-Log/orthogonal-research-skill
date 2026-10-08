#!/usr/bin/env python3
"""Finite, standard-library-only report components shared by web and PDF builds.

The JSON contains plain research text and data, never HTML, executable formulas,
or remote assets. Call validate_components before rendering or exporting it.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import re
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable
from urllib.parse import quote


class ComponentError(ValueError):
    """A component contract violation with an actionable field location."""


KINDS = {
    "timeline": "按时间查看事件、类别和转折细节",
    "comparison": "按同一维度比较对象，保留单位和缺失值",
    "process": "逐步解释机制、流程和每步的作用",
    "relationships": "区分事实关系与假设关系，查看节点和连接",
    "scenarios": "比较适用条件、结果与限制不同的情景",
    "evidence": "并列证据、支持边界和独立写明的判断",
    "images": "查看本地图片及坐标标注",
    "glossary": "解释术语、例子和反例",
    "series": "展示有共同口径的柱形或折线数据",
    "calculator": "在明确假设下改变输入，计算有限线性和",
}
_BASE = {"id", "kind", "title", "intro", "source_ids"}
_FIELDS = {
    "timeline": {"events"}, "comparison": {"columns", "rows"},
    "process": {"steps"}, "relationships": {"nodes", "links"},
    "scenarios": {"cases"}, "evidence": {"items", "conclusion"},
    "images": {"items"}, "glossary": {"items"},
    "series": {"mode", "unit", "basis", "x", "series"},
    "calculator": {"inputs", "outputs", "assumptions"},
}
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_SOURCE = re.compile(r"S[0-9]{3,}\Z")
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_ACTIVE_MARKDOWN = re.compile(r"`|\{\{\s*@|\[\[(?:blue|green|purple|red):|\*[^\n]*\*|\[[^\]\n]*\]\([^\n]*\)|\\\|")


def _fail(path: str, message: str) -> None:
    raise ComponentError("{}: {}".format(path, message))


def _object(value: Any, path: str, required: set, optional: set | None = None) -> dict:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    missing = required - set(value)
    if missing:
        _fail(path, "missing fields: " + ", ".join(sorted(missing)))
    extra = set(value) - required - (optional or set())
    if extra:
        _fail(path, "unknown fields: " + ", ".join(sorted(map(str, extra))))
    return value


def _array(value: Any, path: str, maximum: int = 30, empty: bool = False) -> list:
    if not isinstance(value, list) or not (0 if empty else 1) <= len(value) <= maximum:
        _fail(path, "must be an array containing {}..{} items".format(0 if empty else 1, maximum))
    return value


def _text(value: Any, path: str, maximum: int = 20000, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        _fail(path, "must be {}plain text".format("" if not empty else "a string of "))
    if len(value) > maximum:
        _fail(path, "text exceeds {} characters; split it into narrative paragraphs".format(maximum))
    if _CONTROLS.search(value):
        _fail(path, "control characters are not supported")
    if _ACTIVE_MARKDOWN.search(value):
        _fail(path, "use plain text, without Markdown formatting, links, source markers or an escaped pipe")
    return value


def _label(value: Any, path: str, empty: bool = False) -> str:
    return _text(value, path, 300, empty)


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a finite number, not a boolean")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        _fail(path, "number is too large")
    if not math.isfinite(result):
        _fail(path, "must be a finite number")
    return result


def _scalar(value: Any, path: str) -> None:
    if value is None:
        return
    if isinstance(value, str):
        _text(value, path, empty=True)
    else:
        _number(value, path)


def _id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail(path, "must be an ASCII slug starting with a letter (1..64 characters)")
    return value


def _unique(items: list, path: str) -> set:
    seen = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            _fail("{}[{}]".format(path, index), "must be an object")
        key = _id(item.get("id"), "{}[{}].id".format(path, index))
        if key in seen:
            _fail(path, "duplicate id: " + key)
        seen.add(key)
    return seen


def _records(component: dict, key: str, path: str, required: set,
             optional: set | None = None, maximum: int = 30, empty: bool = False) -> list:
    items = _array(component[key], path + "." + key, maximum, empty)
    if "id" in required:
        _unique(items, path + "." + key)
    for i, item in enumerate(items):
        _object(item, "{}.{}[{}]".format(path, key, i), required, optional)
    return items


def _local_image(value: Any, path: str, workspace: Path) -> str:
    if not isinstance(value, str) or not value or _CONTROLS.search(value) or "\n" in value or "\t" in value:
        _fail(path, "must be a local relative image path")
    normalized = value.replace("\\", "/")
    win = PureWindowsPath(value)
    if normalized.startswith("/") or win.drive or win.root or ":" in normalized:
        _fail(path, "absolute paths, URLs and network paths are not allowed")
    if ".." in normalized.split("/"):
        _fail(path, "parent traversal is not allowed")
    target = (workspace / normalized).resolve()
    if workspace not in target.parents:
        _fail(path, "image must stay inside the research package, including through symlinks")
    if target.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        _fail(path, "use PNG or JPEG; SVG visuals belong in the existing visual-spec pipeline")
    if not target.is_file():
        _fail(path, "image file does not exist: " + normalized)
    try:
        with target.open("rb") as handle:
            signature = handle.read(8)
    except OSError as exc:
        _fail(path, "cannot read image: " + str(exc))
    if target.suffix.lower() == ".png" and signature != b"\x89PNG\r\n\x1a\n":
        _fail(path, "PNG extension does not match image signature")
    if target.suffix.lower() in (".jpg", ".jpeg") and not signature.startswith(b"\xff\xd8\xff"):
        _fail(path, "JPEG extension does not match image signature")
    return target.relative_to(workspace).as_posix()


def _finite_sum(values: Iterable[float], path: str) -> float:
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError):
        _fail(path, "calculation overflows; reduce values or coefficients")
    if not math.isfinite(result):
        _fail(path, "calculation is not finite; reduce values or coefficients")
    return result


def evaluate_calculator(component: dict, values: dict | None = None) -> dict:
    """Evaluate a validated calculator; optional overrides must obey its ranges."""
    known = {item["id"]: item for item in component["inputs"]}
    supplied = {} if values is None else values
    if not isinstance(supplied, dict) or set(supplied) - set(known):
        _fail(component["id"], "calculator overrides must name existing inputs")
    current = {}
    for key, item in known.items():
        value = _number(supplied.get(key, item["value"]), component["id"] + "." + key)
        if not item["min"] <= value <= item["max"]:
            _fail(component["id"] + "." + key, "input is outside its declared range")
        current[key] = value
    return {output["id"]: _finite_sum(
        [float(output["base"])] + [current[term["input"]] * term["coefficient"] for term in output["terms"]],
        component["id"] + "." + output["id"])
        for output in component["outputs"]}


def calculator_ranges(component: dict) -> dict:
    """Exact output bounds for the declared independent linear input ranges."""
    inputs = {item["id"]: item for item in component["inputs"]}
    result = {}
    for output in component["outputs"]:
        low, high = [float(output["base"])], [float(output["base"])]
        for term in output["terms"]:
            item = inputs[term["input"]]
            pair = [item[bound] * term["coefficient"] for bound in ("min", "max")]
            if not all(math.isfinite(value) for value in pair):
                _fail(component["id"] + "." + output["id"], "calculation overflows at an input boundary")
            low.append(min(pair))
            high.append(max(pair))
        result[output["id"]] = (_finite_sum(low, component["id"]), _finite_sum(high, component["id"]))
    return result


def validate_components(spec: Any, source_ids: Iterable[str], workspace: str | Path) -> dict:
    """Validate and copy v1 components; do not read URLs or mutate the caller."""
    _object(spec, "components", {"version", "components"})
    if type(spec["version"]) is not int or spec["version"] != 1:
        _fail("version", "only integer version 1 is supported")
    components = _array(spec["components"], "components", empty=True)
    _unique(components, "components")
    if isinstance(source_ids, (str, bytes)):
        _fail("source_ids", "pass the source-ledger IDs, not a string")
    try:
        available = set(source_ids)
    except (TypeError, ValueError):
        _fail("source_ids", "must be an iterable of ledger IDs")
    if not all(isinstance(s, str) and _SOURCE.fullmatch(s) for s in available):
        _fail("source_ids", "ledger IDs must use S001 form")
    root = Path(workspace).resolve()
    if not root.is_dir():
        _fail("workspace", "must be an existing research-package directory")
    normalized = copy.deepcopy(spec)
    for index, c in enumerate(normalized["components"]):
        path = "components[{}]".format(index)
        kind = c.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            _fail(path + ".kind", "must be one of " + ", ".join(KINDS))
        _object(c, path, _BASE | _FIELDS[kind], {"after_heading"})
        _label(c["title"], path + ".title")
        _text(c["intro"], path + ".intro")
        if "after_heading" in c:
            _label(c["after_heading"], path + ".after_heading")
        ids = _array(c["source_ids"], path + ".source_ids", 100)
        for s in ids:
            if not isinstance(s, str) or not _SOURCE.fullmatch(s) or s not in available:
                _fail(path + ".source_ids", "source is absent from ledger or invalid: " + str(s))
        if len(set(ids)) != len(ids):
            _fail(path + ".source_ids", "duplicate source IDs")
        if kind == "timeline":
            for i, item in enumerate(_records(c, "events", path, {"id", "date", "label", "detail"}, {"category"})):
                p = "{}.events[{}]".format(path, i)
                for key in ("date", "label", "category"):
                    if key in item:
                        _label(item[key], p + "." + key)
                _text(item["detail"], p + ".detail")
        elif kind == "comparison":
            columns = _records(c, "columns", path, {"id", "label"}, {"unit"})
            for i, item in enumerate(columns):
                _label(item["label"], path + ".columns[{}].label".format(i))
                if "unit" in item:
                    _label(item["unit"], path + ".columns[{}].unit".format(i), True)
            keys = {item["id"] for item in columns}
            for i, item in enumerate(_records(c, "rows", path, {"id", "label", "values"}, {"detail"})):
                p = "{}.rows[{}]".format(path, i)
                _label(item["label"], p + ".label")
                _object(item["values"], p + ".values", keys)
                for key, value in item["values"].items():
                    _scalar(value, p + ".values." + key)
                if "detail" in item:
                    _text(item["detail"], p + ".detail")
        elif kind == "process":
            for i, item in enumerate(_records(c, "steps", path, {"id", "title", "body"})):
                _label(item["title"], path + ".steps[{}].title".format(i))
                _text(item["body"], path + ".steps[{}].body".format(i))
        elif kind == "relationships":
            nodes = _records(c, "nodes", path, {"id", "label", "detail"})
            for i, item in enumerate(nodes):
                _label(item["label"], path + ".nodes[{}].label".format(i))
                _text(item["detail"], path + ".nodes[{}].detail".format(i))
            node_ids = {item["id"] for item in nodes}
            links = _records(c, "links", path, {"from", "to", "label", "kind"}, empty=True)
            seen_links = set()
            for i, link in enumerate(links):
                p = "{}.links[{}]".format(path, i)
                for key in ("from", "to"):
                    if not isinstance(link[key], str) or link[key] not in node_ids:
                        _fail(p + "." + key, "must name an existing node")
                if link["kind"] not in ("fact", "hypothesis"):
                    _fail(p + ".kind", "must be fact or hypothesis")
                _label(link["label"], p + ".label")
                identity = tuple(link[key] for key in ("from", "to", "label", "kind"))
                if identity in seen_links:
                    _fail(p, "duplicate relationship")
                seen_links.add(identity)
        elif kind == "scenarios":
            for i, case in enumerate(_records(c, "cases", path, {"id", "title", "when", "text", "outcomes", "limitation"})):
                p = "{}.cases[{}]".format(path, i)
                _label(case["title"], p + ".title")
                for key in ("when", "text", "limitation"):
                    _text(case[key], p + "." + key)
                for j, item in enumerate(_records(case, "outcomes", p, {"label", "value"})):
                    _label(item["label"], p + ".outcomes[{}].label".format(j))
                    _scalar(item["value"], p + ".outcomes[{}].value".format(j))
        elif kind == "evidence":
            for i, item in enumerate(_records(c, "items", path, {"id", "title", "statement", "limit", "kind"})):
                p = "{}.items[{}]".format(path, i)
                for key in ("title", "kind"):
                    _label(item[key], p + "." + key)
                for key in ("statement", "limit"):
                    _text(item[key], p + "." + key)
            _text(c["conclusion"], path + ".conclusion")
        elif kind == "images":
            for i, item in enumerate(_records(c, "items", path, {"id", "path", "alt", "caption", "points"})):
                p = "{}.items[{}]".format(path, i)
                item["path"] = _local_image(item["path"], p + ".path", root)
                _label(item["alt"], p + ".alt")
                _text(item["caption"], p + ".caption")
                for j, point in enumerate(_records(item, "points", p, {"x", "y", "title", "body"}, empty=True)):
                    pp = p + ".points[{}]".format(j)
                    for key in ("x", "y"):
                        if not 0 <= _number(point[key], pp + "." + key) <= 100:
                            _fail(pp + "." + key, "must be a percentage from 0 to 100")
                    _label(point["title"], pp + ".title")
                    _text(point["body"], pp + ".body")
        elif kind == "glossary":
            for i, item in enumerate(_records(c, "items", path, {"id", "term", "definition"}, {"example", "counterexample"})):
                p = "{}.items[{}]".format(path, i)
                _label(item["term"], p + ".term")
                for key in ("definition", "example", "counterexample"):
                    if key in item:
                        _text(item[key], p + "." + key)
        elif kind == "series":
            if c["mode"] not in ("bar", "line"):
                _fail(path + ".mode", "must be bar or line")
            _label(c["unit"], path + ".unit", True)
            _text(c["basis"], path + ".basis")
            for i, value in enumerate(_array(c["x"], path + ".x", 120)):
                _label(value, path + ".x[{}]".format(i))
            for i, item in enumerate(_records(c, "series", path, {"id", "label", "values"}, maximum=12)):
                p = "{}.series[{}]".format(path, i)
                _label(item["label"], p + ".label")
                values = _array(item["values"], p + ".values", 120)
                if len(values) != len(c["x"]):
                    _fail(p + ".values", "length must match x; use null for missing data")
                for j, value in enumerate(values):
                    if value is not None:
                        _number(value, p + ".values[{}]".format(j))
        elif kind == "calculator":
            inputs = _records(c, "inputs", path, {"id", "label", "value", "min", "max", "step", "unit"})
            input_ids = {item["id"] for item in inputs}
            for i, item in enumerate(inputs):
                p = "{}.inputs[{}]".format(path, i)
                _label(item["label"], p + ".label")
                _label(item["unit"], p + ".unit", True)
                for key in ("value", "min", "max", "step"):
                    item[key] = _number(item[key], p + "." + key)
                width = item["max"] - item["min"]
                if not math.isfinite(width) or width <= 0:
                    _fail(p, "min must be below max with a finite range")
                if not item["min"] <= item["value"] <= item["max"]:
                    _fail(p + ".value", "must lie between min and max")
                if not 0 < item["step"] <= width:
                    _fail(p + ".step", "must be positive and no larger than max - min")
                remainder = math.fmod(item["value"] - item["min"], item["step"])
                distance = min(remainder, item["step"] - remainder)
                # Respect the HTML number input's step grid without rejecting
                # ordinary decimal values such as 0.3 on a 0.1 grid. Capping
                # the tolerance preserves a meaningful grid for large values.
                tolerance = min(item["step"] * 1e-7, 8 * max(
                    math.ulp(item["value"]), math.ulp(item["min"]), math.ulp(item["step"])))
                if distance > tolerance:
                    _fail(p + ".value", "default value must align with min + an integer multiple of step")
            for i, output in enumerate(_records(c, "outputs", path, {"id", "label", "unit", "base", "terms"})):
                p = "{}.outputs[{}]".format(path, i)
                _label(output["label"], p + ".label")
                _label(output["unit"], p + ".unit", True)
                output["base"] = _number(output["base"], p + ".base")
                seen = set()
                for j, term in enumerate(_records(output, "terms", p, {"input", "coefficient"}, empty=True)):
                    tp = p + ".terms[{}]".format(j)
                    if not isinstance(term["input"], str) or term["input"] not in input_ids:
                        _fail(tp + ".input", "must name an existing input")
                    if term["input"] in seen:
                        _fail(tp, "combine repeated terms for the same input")
                    seen.add(term["input"])
                    term["coefficient"] = _number(term["coefficient"], tp + ".coefficient")
            _text(c["assumptions"], path + ".assumptions")
            evaluate_calculator(c)
            calculator_ranges(c)
    return normalized


def _display(value: Any) -> str:
    if value is None:
        return "缺失（未提供）"
    if isinstance(value, float):
        result = str(value)
        return result[:-2] if result.endswith(".0") else result
    return str(value)


def _md(value: Any) -> str:
    # _text rejects active inline syntax. Existing PDF parser consumes \| and
    # escapes HTML itself, so do not double-escape <, > or ordinary backslashes.
    return _display(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")


def _table(headers: list, rows: Iterable[list]) -> str:
    def cell(value: Any) -> str:
        return _md(value).replace("|", "\\|")

    return "\n".join(["| " + " | ".join(cell(v) for v in headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows])


def _citation(c: dict) -> str:
    return "{{" + ",".join("@" + source for source in c["source_ids"]) + " |}}"


def components_markdown(spec: dict) -> str:
    """Expand all component content for PDF, including every interactive state.

    Image paths are relative to the same package root used during validation.
    The caller inserts this generated section before its bibliography without
    modifying the original research manuscript.
    """
    if not spec["components"]:
        return ""
    result = []
    for c in spec["components"]:
        kind = c["kind"]
        result.extend(["### " + _md(c["title"]), "导读：" + _md(c["intro"]) + _citation(c)])
        if kind == "timeline":
            result.append(_table(["日期", "事件", "类别", "细节"],
                [[v["date"], v["label"], v.get("category", "未分类"), v["detail"]] for v in c["events"]]))
        elif kind == "comparison":
            # A long matrix becomes one object table per row so all dimensions
            # remain readable on A4 rather than compressing thirty columns.
            for row in c["rows"]:
                result.append("#### " + _md(row["label"]))
                result.append(_table(["维度", "值", "单位"], [[col["label"], row["values"][col["id"]], col.get("unit", "")] for col in c["columns"]]))
                if "detail" in row:
                    result.append("说明：" + _md(row["detail"]))
        elif kind == "process":
            for i, step in enumerate(c["steps"], 1):
                result.extend(["#### {}. {}".format(i, _md(step["title"])), "内容：" + _md(step["body"])])
        elif kind == "relationships":
            result.append(_table(["节点", "解释"], [[n["label"], n["detail"]] for n in c["nodes"]]))
            nodes = {n["id"]: n["label"] for n in c["nodes"]}
            if c["links"]:
                result.append(_table(["起点", "终点", "关系", "性质"], [[nodes[v["from"]], nodes[v["to"]], v["label"], "事实" if v["kind"] == "fact" else "假设"] for v in c["links"]]))
            else:
                result.append("关系：未提供连接。")
        elif kind == "scenarios":
            for case in c["cases"]:
                result.extend(["#### " + _md(case["title"]), "适用条件：" + _md(case["when"]),
                               "情景：" + _md(case["text"]), _table(["结果", "值"], [[v["label"], v["value"]] for v in case["outcomes"]]),
                               "限制：" + _md(case["limitation"])])
        elif kind == "evidence":
            for item in c["items"]:
                result.extend(["#### " + _md(item["title"]), "材料类型：" + _md(item["kind"]),
                               "材料支持：" + _md(item["statement"]), "支持边界：" + _md(item["limit"])])
            result.append("研究判断：" + _md(c["conclusion"]))
        elif kind == "images":
            for item in c["items"]:
                # Avoid brackets in image alt syntax; a separate caption keeps
                # the complete original alternative text available to PDF.
                result.extend(["![图片](" + quote(item["path"], safe="/") + ")",
                               "图像说明：" + _md(item["alt"]), "图注：" + _md(item["caption"]) + _citation(c)])
                if item["points"]:
                    result.append(_table(["标注", "位置（左、上百分比）", "说明"], [[p["title"], "{}, {}".format(_display(p["x"]), _display(p["y"])), p["body"]] for p in item["points"]]))
        elif kind == "glossary":
            for item in c["items"]:
                result.extend(["#### " + _md(item["term"]), "定义：" + _md(item["definition"])])
                for key, label in (("example", "例子"), ("counterexample", "反例")):
                    if key in item:
                        result.append(label + "：" + _md(item[key]))
        elif kind == "series":
            result.append("展示方式：{}；单位：{}。口径：{}".format("柱形" if c["mode"] == "bar" else "折线", _md(c["unit"]) or "无", _md(c["basis"])))
            for series in c["series"]:
                result.append("#### " + _md(series["label"]))
                result.append(_table(["横轴", "值", "单位"], [[x, v, c["unit"]] for x, v in zip(c["x"], series["values"])]))
        elif kind == "calculator":
            result.append("假设：" + _md(c["assumptions"]))
            result.append(_table(["输入", "默认", "最小", "最大", "步长", "单位"], [[v[k] for k in ("label", "value", "min", "max", "step", "unit")] for v in c["inputs"]]))
            values, ranges = evaluate_calculator(c), calculator_ranges(c)
            names = {i["id"]: i["label"] for i in c["inputs"]}
            for output in c["outputs"]:
                formula = _display(output["base"]) + "".join(" + ({}) × {}".format(_display(t["coefficient"]), names[t["input"]]) for t in output["terms"])
                result.extend(["#### " + _md(output["label"]), "公式：" + _md(formula),
                               _table(["默认结果", "区间下界", "区间上界", "单位"], [[values[output["id"]], *ranges[output["id"]], output["unit"]]])])
            result.append("区间说明：上下界按各输入在声明区间内独立变化计算；不代表实测结果或预测区间。")
    return "\n\n".join(result) + "\n"


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_tables(spec: dict, directory: str | Path) -> list[str]:
    """Export every component as UTF-8 CSV, with sources and safe spreadsheet text."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    exported = []

    def write(c: dict, suffix: str, headers: list, rows: Iterable[list]) -> None:
        _id(c["id"], "component.id")
        # IDs cannot contain dots. Separate suffixes with a dot so a component
        # named foo-nodes cannot overwrite the nodes table of component foo.
        suffix = "." + suffix.lstrip("-") if suffix else ""
        target = directory / ("component-" + c["id"] + suffix + ".csv")
        if target.is_symlink() or target.resolve().parent != directory:
            _fail(str(target), "export target must stay inside the data directory")
        try:
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["component_id", "component_title", "source_ids"] + headers)
                for row in rows:
                    writer.writerow([_csv_cell(v) for v in [c["id"], c["title"], ";".join(c["source_ids"])] + row])
        except OSError as exc:
            _fail(str(target), "cannot export CSV: " + str(exc))
        exported.append(str(target))

    for c in spec["components"]:
        kind = c["kind"]
        if kind == "timeline":
            keys = ["id", "date", "label", "category", "detail"]
            write(c, "", keys, [[v.get(k, "") for k in keys] for v in c["events"]])
        elif kind == "comparison":
            write(c, "-columns", ["id", "label", "unit"], [[v["id"], v["label"], v.get("unit", "")] for v in c["columns"]])
            write(c, "", ["id", "label"] + [v["id"] for v in c["columns"]] + ["detail"], [[r["id"], r["label"]] + [r["values"][v["id"]] for v in c["columns"]] + [r.get("detail", "")] for r in c["rows"]])
        elif kind == "process":
            write(c, "", ["order", "id", "title", "body"], [[i, v["id"], v["title"], v["body"]] for i, v in enumerate(c["steps"], 1)])
        elif kind == "relationships":
            write(c, "-nodes", ["id", "label", "detail"], [[v[k] for k in ("id", "label", "detail")] for v in c["nodes"]])
            write(c, "-links", ["from", "to", "label", "kind"], [[v[k] for k in ("from", "to", "label", "kind")] for v in c["links"]])
        elif kind == "scenarios":
            write(c, "", ["id", "title", "when", "text", "outcome_label", "outcome_value", "limitation"], [[v["id"], v["title"], v["when"], v["text"], o["label"], o["value"], v["limitation"]] for v in c["cases"] for o in v["outcomes"]])
        elif kind == "evidence":
            write(c, "", ["id", "title", "kind", "statement", "limit", "conclusion"], [[v[k] for k in ("id", "title", "kind", "statement", "limit")] + [c["conclusion"]] for v in c["items"]])
        elif kind == "images":
            write(c, "", ["id", "path", "alt", "caption"], [[v[k] for k in ("id", "path", "alt", "caption")] for v in c["items"]])
            write(c, "-points", ["image_id", "order", "x", "y", "title", "body"], [[v["id"], i] + [p[k] for k in ("x", "y", "title", "body")] for v in c["items"] for i, p in enumerate(v["points"], 1)])
        elif kind == "glossary":
            keys = ["id", "term", "definition", "example", "counterexample"]
            write(c, "", keys, [[v.get(k, "") for k in keys] for v in c["items"]])
        elif kind == "series":
            write(c, "", ["mode", "basis", "series_id", "series_label", "x", "value", "unit"], [[c["mode"], c["basis"], s["id"], s["label"], x, value, c["unit"]] for s in c["series"] for x, value in zip(c["x"], s["values"])])
        elif kind == "calculator":
            keys = ["id", "label", "value", "min", "max", "step", "unit"]
            write(c, "-inputs", keys, [[v[k] for k in keys] for v in c["inputs"]])
            values, ranges = evaluate_calculator(c), calculator_ranges(c)
            write(c, "-outputs", ["id", "label", "unit", "base", "default_result", "minimum", "maximum", "assumptions"], [[v[k] for k in ("id", "label", "unit", "base")] + [values[v["id"]], *ranges[v["id"]], c["assumptions"]] for v in c["outputs"]])
            write(c, "-terms", ["output_id", "input_id", "coefficient"], [[v["id"], t["input"], t["coefficient"]] for v in c["outputs"] for t in v["terms"]])
    return exported


def component_example(kind: str) -> dict:
    """Small editable examples for --describe; image.png must be supplied locally."""
    if kind not in KINDS:
        _fail("kind", "unknown component: " + str(kind))
    payloads = {
        "timeline": {"events": [{"id": "event1", "date": "2026", "label": "事件名称", "detail": "事件细节", "category": "类别"}]},
        "comparison": {"columns": [{"id": "metric", "label": "比较维度", "unit": ""}], "rows": [{"id": "object1", "label": "对象", "values": {"metric": None}, "detail": "数据边界"}]},
        "process": {"steps": [{"id": "step1", "title": "步骤名称", "body": "机制与作用"}]},
        "relationships": {"nodes": [{"id": "a", "label": "节点一", "detail": "角色"}, {"id": "b", "label": "节点二", "detail": "角色"}], "links": [{"from": "a", "to": "b", "label": "关系", "kind": "hypothesis"}]},
        "scenarios": {"cases": [{"id": "case1", "title": "情景", "when": "适用条件", "text": "解释", "outcomes": [{"label": "结果", "value": None}], "limitation": "限制"}]},
        "evidence": {"items": [{"id": "item1", "title": "材料", "statement": "支持的事实", "limit": "不能支持的推断", "kind": "观察"}], "conclusion": "由研究者写明的判断"},
        "images": {"items": [{"id": "image1", "path": "assets/image.png", "alt": "图像说明", "caption": "图注及边界", "points": [{"x": 50, "y": 50, "title": "标注", "body": "位置含义"}]}]},
        "glossary": {"items": [{"id": "term1", "term": "术语", "definition": "定义", "example": "例子", "counterexample": "反例"}]},
        "series": {"mode": "line", "unit": "件", "basis": "数据口径与缺失说明", "x": ["2025", "2026"], "series": [{"id": "series1", "label": "序列", "values": [10, None]}]},
        "calculator": {"inputs": [{"id": "quantity", "label": "数量", "value": 10, "min": 0, "max": 20, "step": 1, "unit": "件"}], "outputs": [{"id": "total", "label": "线性结果", "unit": "单位", "base": 5, "terms": [{"input": "quantity", "coefficient": 2}]}], "assumptions": "结果为演示计算；说明线性假设及适用范围"},
    }
    return {"id": kind + "_example", "kind": kind, "title": KINDS[kind], "intro": "解释读者能从本组件核查的问题", "source_ids": ["S001"], **payloads[kind]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="list the ten supported kinds")
    mode.add_argument("--describe", choices=tuple(KINDS), help="print one editable component example")
    mode.add_argument("--validate", type=Path, help="validate a components.json file")
    parser.add_argument("--sources", type=Path, help="source ledger containing a sources array")
    parser.add_argument("--workspace", type=Path, help="research package root for local images")
    args = parser.parse_args(argv)
    try:
        if args.list:
            print("\n".join("{}: {}".format(k, v) for k, v in KINDS.items()))
        elif args.describe:
            print(json.dumps({"version": 1, "components": [component_example(args.describe)]}, ensure_ascii=False, indent=2))
            print("\n文本使用纯文本；source_ids 必须已在来源台账；图片路径相对研究包。null 表示缺失，不自动填零。")
        else:
            if args.sources is None or args.workspace is None:
                parser.error("--validate requires --sources and --workspace")
            spec = json.loads(args.validate.read_text(encoding="utf-8"))
            ledger = json.loads(args.sources.read_text(encoding="utf-8"))
            if not isinstance(ledger, dict) or not isinstance(ledger.get("sources"), list):
                _fail("sources", "ledger must contain a sources array")
            ids = []
            for i, source in enumerate(ledger["sources"]):
                if not isinstance(source, dict) or "id" not in source:
                    _fail("sources[{}]".format(i), "must contain an id")
                ids.append(source["id"])
            checked = validate_components(spec, ids, args.workspace)
            print(json.dumps({"status": "pass", "components": len(checked["components"]), "kinds": sorted({c["kind"] for c in checked["components"]})}, ensure_ascii=False))
    except (ComponentError, OSError, ValueError) as exc:
        parser.exit(1, "error: {}\n".format(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
