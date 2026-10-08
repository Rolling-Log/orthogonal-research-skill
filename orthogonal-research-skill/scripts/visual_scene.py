#!/usr/bin/env python3
"""Validated, dependency-free scene model shared by SVG and PDF renderers."""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


WIDTH = 1200
BG = "#FFFFFF"
INK = "#2C3E50"
MUTED = "#6B7280"
LIGHT = "#F4F6F7"
BORDER = "#D5DBDB"
DEEP_BLUE = "#1A5276"
GREEN = "#1E8449"
LIGHT_BLUE = "#2E86C1"
PURPLE = "#5B2C6F"
AMBER = "#B9770E"
RED = "#B03A2E"
PALETTE = [DEEP_BLUE, GREEN, LIGHT_BLUE, PURPLE, AMBER, "#117864"]
SVG_FONT = "'Source Han Sans CN','Microsoft YaHei','Noto Sans CJK SC',sans-serif"


class SpecError(ValueError):
    """Raised when a visual specification cannot be rendered safely."""


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    title: str
    description: str
    elements: Tuple[Dict[str, Any], ...]


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError("{} must be a number".format(field))
    result = float(value)
    if not math.isfinite(result):
        raise SpecError("{} must be finite".format(field))
    return result


def _list(spec: Dict[str, Any], key: str) -> List[Any]:
    value = spec.get(key)
    if not isinstance(value, list) or not value:
        raise SpecError("{} must be a non-empty list".format(key))
    return value


def _text(x: float, y: float, value: Any, size: int = 24, fill: str = INK,
          anchor: str = "start", weight: int = 400, max_chars: int = 0,
          rotation: float = 0, role: str = "body",
          count_text: Optional[str] = None) -> Dict[str, Any]:
    raw = str(value)
    lines = [raw]
    if max_chars and len(raw) > max_chars:
        lines = [raw[i:i + max_chars] for i in range(0, len(raw), max_chars)][:3]
    item = {"kind": "text", "x": x, "y": y, "lines": lines, "size": size,
            "fill": fill, "anchor": anchor, "weight": weight,
            "line_height": int(size * 1.25), "rotation": rotation, "role": role}
    if count_text is not None:
        item["count_text"] = count_text
    return item


def _rect(x: float, y: float, width: float, height: float, fill: str,
          stroke: Optional[str] = None, radius: float = 0) -> Dict[str, Any]:
    return {"kind": "rect", "x": x, "y": y, "width": width, "height": height,
            "fill": fill, "stroke": stroke, "radius": radius}


def _line(x1: float, y1: float, x2: float, y2: float, stroke: str,
          width: float = 1, dash: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    return {"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "stroke": stroke, "width": width, "dash": list(dash or [])}


def _circle(cx: float, cy: float, radius: float, fill: Optional[str],
            stroke: Optional[str] = None, width: float = 1) -> Dict[str, Any]:
    return {"kind": "circle", "cx": cx, "cy": cy, "radius": radius,
            "fill": fill, "stroke": stroke, "width": width}


def _path(commands: Sequence[Sequence[Any]], stroke: str, width: float = 1,
          fill: Optional[str] = None, dash: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    return {"kind": "path", "commands": [list(c) for c in commands], "stroke": stroke,
            "width": width, "fill": fill, "dash": list(dash or [])}


def _pie(cx: float, cy: float, radius: float, start: float, end: float,
         fill: str) -> Dict[str, Any]:
    return {"kind": "pie", "cx": cx, "cy": cy, "radius": radius,
            "start": start, "end": end, "fill": fill}


def _header(spec: Dict[str, Any], height: int) -> List[Dict[str, Any]]:
    title = str(spec.get("title", "Untitled visual"))
    subtitle = str(spec.get("subtitle", ""))
    elements = [_rect(0, 0, WIDTH, height, BG), _text(72, 72, title, 36, DEEP_BLUE, weight=700)]
    if subtitle:
        elements.append(_text(72, 108, subtitle, 20, MUTED))
    elements.append(_line(72, 132, 1128, 132, BORDER))
    return elements


def _scene(spec: Dict[str, Any], height: int, elements: Iterable[Dict[str, Any]],
           description: str = "") -> Scene:
    items = list(elements)
    source = str(spec.get("source", ""))
    # A bounded footer preserves the existing chart area and font sizes. Longer
    # provenance belongs in the accompanying caption rather than tiny type.
    if len(source) > 165:
        raise SpecError("visual source is too long; keep source IDs and time here and move details into the figure-source caption")
    count_source = str(spec.get("source_count_text", re.sub(
        r"(?<![A-Za-z0-9_])S\d{3,}(?![A-Za-z0-9_])", "", source)))
    source_lines = (len("来源：" + source) + 57) // 58
    if spec.get("type") == "bar" and len(spec.get("labels", [])) >= 6 and source_lines > 2:
        raise SpecError("bar source needs more than two lines; move detailed provenance into the figure-source caption")
    footer_y = (height - 118 if spec.get("type") == "knowledge_graph"
                else height - 22 - (source_lines - 1) * 22)
    items.append(_text(72, footer_y, "来源：" + source, 18, MUTED,
                       max_chars=58, count_text="来源：" + count_source))
    return Scene(WIDTH, height, str(spec.get("title", "Untitled visual")),
                 description or str(spec.get("subtitle", "")), tuple(items))


def _bar(spec: Dict[str, Any]) -> Scene:
    labels, raw = _list(spec, "labels"), _list(spec, "values")
    if len(labels) != len(raw) or len(labels) > 15:
        raise SpecError("bar requires matching labels/values and at most 15 categories")
    values = [_number(v, "values[{}]".format(i)) for i, v in enumerate(raw)]
    if any(v < 0 for v in values):
        raise SpecError("bar values must be non-negative")
    maximum = max(values) or 1
    unit = str(spec.get("unit", ""))
    height = max(560, 210 + len(labels) * 58)
    items = _header(spec, height)
    left, right, top = 320, 1080, 174
    for index, (label, value) in enumerate(zip(labels, values)):
        y = top + index * 58
        items.extend([_text(left - 24, y + 27, label, 20, anchor="end"),
                      _rect(left, y, right - left, 32, LIGHT, radius=8)])
        width = (right - left) * value / maximum
        items.append(_rect(left, y, width, 32, DEEP_BLUE, radius=8))
        items.append(_text(min(left + width + 12, 1110), y + 24,
                           "{:g}{}".format(value, unit), 18, weight=700))
    return _scene(spec, height, items)


def _line_chart(spec: Dict[str, Any]) -> Scene:
    labels, series = _list(spec, "labels"), _list(spec, "series")
    if not 2 <= len(labels) <= 24 or len(series) > 4:
        raise SpecError("line requires 2-24 labels and at most 4 series")
    parsed = []
    for index, item in enumerate(series):
        if not isinstance(item, dict) or not isinstance(item.get("values"), list):
            raise SpecError("series[{}] must be an object with values".format(index))
        values = item["values"]
        if len(values) != len(labels):
            raise SpecError("series[{}].values length must equal labels".format(index))
        parsed.append((str(item.get("name", "Series {}".format(index + 1))),
                       [_number(v, "series value") for v in values]))
    all_values = [value for _, values in parsed for value in values]
    low, high = min(0.0, min(all_values)), max(all_values)
    if high == low:
        high = low + 1
    height = 700
    items = _header(spec, height)
    x0, x1, y0, y1 = 120, 1080, 190, 560
    for index in range(5):
        y = y1 - (y1 - y0) * index / 4
        value = low + (high - low) * index / 4
        items.extend([_line(x0, y, x1, y, BORDER),
                      _text(x0 - 16, y + 6, "{:g}".format(value), 16, MUTED, "end")])
    for index, label in enumerate(labels):
        x = x0 + (x1 - x0) * index / (len(labels) - 1)
        if index in (0, len(labels) - 1) or len(labels) <= 10 or index % 2 == 0:
            items.append(_text(x, y1 + 34, label, 15, MUTED, "middle"))
    for series_index, (name, values) in enumerate(parsed):
        color = PALETTE[series_index]
        points = []
        for index, value in enumerate(values):
            x = x0 + (x1 - x0) * index / (len(labels) - 1)
            y = y1 - (value - low) / (high - low) * (y1 - y0)
            points.append((x, y))
        commands = [("M", points[0][0], points[0][1])] + [("L", x, y) for x, y in points[1:]]
        items.append(_path(commands, color, 5))
        for x, y in points:
            items.append(_circle(x, y, 6, BG, color, 4))
        lx, ly = 770 + (series_index % 2) * 180, 160 + (series_index // 2) * 30
        items.extend([_line(lx, ly, lx + 28, ly, color, 5),
                      _text(lx + 38, ly + 6, name, 16, MUTED)])
    return _scene(spec, height, items)


def _donut(spec: Dict[str, Any]) -> Scene:
    labels, raw = _list(spec, "labels"), _list(spec, "values")
    if len(labels) != len(raw) or not 2 <= len(labels) <= 6:
        raise SpecError("donut requires 2-6 labels with matching values")
    values = [_number(v, "donut value") for v in raw]
    if any(v < 0 for v in values) or sum(values) <= 0:
        raise SpecError("donut values must be non-negative and sum above zero")
    total, height = sum(values), 650
    items = _header(spec, height)
    cx, cy, radius, start = 390, 360, 175, 0.0
    for index, value in enumerate(values):
        end = start + 360 * value / total
        items.append(_pie(cx, cy, radius, start, end, PALETTE[index]))
        start = end
    items.extend([_circle(cx, cy, 103, BG),
                  _text(cx, cy - 6, "{:g}".format(total), 42, INK, "middle", 700),
                  _text(cx, cy + 30, spec.get("unit", "合计"), 18, MUTED, "middle")])
    for index, (label, value) in enumerate(zip(labels, values)):
        y = 236 + index * 58
        items.extend([_circle(720, y, 8, PALETTE[index]), _text(744, y + 7, label, 20),
                      _text(1080, y + 7, "{:.1f}%".format(value / total * 100),
                            20, INK, "end", 700)])
    return _scene(spec, height, items)


def _timeline(spec: Dict[str, Any]) -> Scene:
    events = _list(spec, "events")
    if not 2 <= len(events) <= 10:
        raise SpecError("timeline requires 2-10 events")
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not event.get("date") or not event.get("label"):
            raise SpecError("events[{}] requires date and label".format(index))
    height = 720
    items = _header(spec, height)
    x0, x1, axis_y = 110, 1090, 350
    items.append(_line(x0, axis_y, x1, axis_y, INK, 3))
    for index, event in enumerate(events):
        x = x0 + (x1 - x0) * index / (len(events) - 1)
        above = index % 2 == 0
        box_y = 182 if above else 414
        line_end = box_y + 106 if above else box_y
        box_x = max(22, min(x - 92, WIDTH - 206))
        items.extend([_line(x, axis_y, x, line_end, BORDER, 2),
                      _circle(x, axis_y, 9, DEEP_BLUE, BG, 4),
                      _rect(box_x, box_y, 184, 106, LIGHT, BORDER, 14),
                      _text(x, box_y + 31, event["date"], 17, DEEP_BLUE, "middle", 700),
                      _text(x, box_y + 62, event["label"], 17, INK, "middle", 400, 10)])
    return _scene(spec, height, items, "Key turning points")


def _matrix(spec: Dict[str, Any]) -> Scene:
    points = _list(spec, "points")
    if len(points) > 20:
        raise SpecError("matrix supports at most 20 points")
    height = 720
    items = _header(spec, height)
    x0, x1, y0, y1 = 160, 1080, 180, 580
    items.extend([_rect(x0, y0, x1 - x0, y1 - y0, LIGHT),
                  _line((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, BORDER, 1, [8, 8]),
                  _line(x0, (y0 + y1) / 2, x1, (y0 + y1) / 2, BORDER, 1, [8, 8]),
                  _text((x0 + x1) / 2, y1 + 48, spec.get("x_label", "X"), 19, MUTED, "middle"),
                  _text(x0 - 58, (y0 + y1) / 2, spec.get("y_label", "Y"), 19,
                        MUTED, "middle", rotation=-90)])
    colors = {}
    for index, point in enumerate(points):
        if not isinstance(point, dict) or "label" not in point:
            raise SpecError("points[{}] requires label, x and y".format(index))
        px, py = _number(point.get("x"), "point.x"), _number(point.get("y"), "point.y")
        if not 0 <= px <= 1 or not 0 <= py <= 1:
            raise SpecError("matrix x and y must be between 0 and 1")
        group = str(point.get("group", "default"))
        if group not in colors:
            colors[group] = PALETTE[len(colors) % len(PALETTE)]
        x, y = x0 + px * (x1 - x0), y1 - py * (y1 - y0)
        items.extend([_circle(x, y, 13, colors[group], BG, 4),
                      _text(x + 18, y - 10, point["label"], 17, INK, weight=700)])
    return _scene(spec, height, items)


@dataclass(frozen=True)
class _Node:
    node_id: str
    x: float
    y: float
    width: float
    height: float
    label: str
    group: str


def _knowledge_graph(spec: Dict[str, Any]) -> Scene:
    raw_nodes, edges = _list(spec, "nodes"), _list(spec, "edges")
    if not 3 <= len(raw_nodes) <= 18:
        raise SpecError("knowledge_graph requires 3-18 nodes")
    ids, levels = set(), {}
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict) or not node.get("id") or not node.get("label"):
            raise SpecError("nodes[{}] requires id and label".format(index))
        node_id = str(node["id"])
        if node_id in ids:
            raise SpecError("duplicate node id: {}".format(node_id))
        ids.add(node_id)
        level = int(_number(node.get("level", 1), "node.level"))
        if not 0 <= level <= 4:
            raise SpecError("node level must be between 0 and 4")
        levels.setdefault(level, []).append(node)
    if len(levels.get(0, [])) != 1:
        raise SpecError("knowledge_graph requires exactly one level-0 center node")
    height = 300 + max(levels) * 190 + 170
    items = _header(spec, height)
    boxes = {}
    styles = {"core": (DEEP_BLUE, BG), "product": (LIGHT_BLUE, BG),
              "person": ("#EAF3FF", INK), "organization": ("#F1F1F3", INK),
              "technology": ("#E8F7F0", INK), "market": ("#FFF4E5", INK),
              "default": (LIGHT, INK)}
    for level in sorted(levels):
        row = levels[level]
        gap, y = 1040 / len(row), 190 + level * 190
        for index, node in enumerate(row):
            center = 80 + gap * (index + 0.5)
            label = str(node["label"])
            width = min(220, max(150, 92 + len(label) * 10))
            boxes[str(node["id"])] = _Node(str(node["id"]), center - width / 2,
                                                y, width, 86, label,
                                                str(node.get("group", "default")))
    edge_labels = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise SpecError("edges[{}] must be an object".format(index))
        start_id, end_id = str(edge.get("from", "")), str(edge.get("to", ""))
        if start_id not in boxes or end_id not in boxes:
            raise SpecError("edges[{}] references an unknown node".format(index))
        if not str(edge.get("source", "")).strip():
            raise SpecError("edges[{}].source is required".format(index))
        kind = str(edge.get("kind", "fact"))
        if kind not in ("fact", "hypothesis"):
            raise SpecError("edge kind must be fact or hypothesis")
        start, end = boxes[start_id], boxes[end_id]
        sx, sy = start.x + start.width / 2, start.y + start.height
        ex, ey = end.x + end.width / 2, end.y
        if ey <= sy:
            sy, ey = start.y + start.height / 2, end.y + end.height / 2
        middle = (sy + ey) / 2
        color = RED if kind == "hypothesis" else MUTED
        items.append(_path([("M", sx, sy), ("C", sx, middle, ex, middle, ex, ey)],
                           color, 2.2, dash=[10, 8] if kind == "hypothesis" else None))
        items.append({"kind": "triangle", "points": [(ex, ey), (ex - 7, ey - 12),
                                                        (ex + 7, ey - 12)], "fill": color})
        label, source = str(edge.get("label", "")), str(edge["source"])
        # Each relation carries its own evidence marker, including unlabeled
        # relations. Reference identity, rather than a numeric regex, controls
        # exclusion from the report's visible-text count.
        if len(label) > 6 or len(source) > 40:
            raise SpecError("edge label/source is too long; use a short verb and source IDs, or split the graph")
        lx, ly = (sx + ex) / 2, middle - 7
        label_width = len(label) * 20
        source_width = len(source) * 11
        width = max(40, label_width + source_width + 14)
        left = lx - width / 2
        edge_labels.append(_rect(left - 5, ly - 21, width + 10, 29, BG, radius=8))
        if label:
            edge_labels.append(_text(left, ly, label, 20, color))
        edge_labels.append(_text(left + label_width + (8 if label else 0), ly - 3,
                                 source, 20, color, role="reference"))
    # Paint labels after every relation path, so a later crossing edge cannot
    # draw through an earlier relationship's source marker.
    items.extend(edge_labels)
    for box in boxes.values():
        fill, foreground = styles.get(box.group, styles["default"])
        items.extend([_rect(box.x, box.y, box.width, box.height, fill, BORDER, 18),
                      _text(box.x + box.width / 2, box.y + 39, box.label, 19,
                            foreground, "middle", 700, 12)])
    items.extend([_line(770, height - 62, 812, height - 62, MUTED, 2),
                  _text(822, height - 56, "事实关系", 15, MUTED),
                  _line(930, height - 62, 972, height - 62, RED, 2, [8, 6]),
                  _text(982, height - 56, "假设关系", 15, MUTED)])
    return _scene(spec, height, items)


RENDERERS = {"bar": _bar, "line": _line_chart, "donut": _donut,
             "timeline": _timeline, "matrix": _matrix,
             "knowledge_graph": _knowledge_graph}


def scene_from_spec(spec: Dict[str, Any]) -> Scene:
    if not isinstance(spec, dict):
        raise SpecError("visual must be an object")
    if not str(spec.get("title", "")).strip():
        raise SpecError("visual title is required")
    if not str(spec.get("source", "")).strip():
        raise SpecError("visual source is required")
    renderer = RENDERERS.get(str(spec.get("type")))
    if renderer is None:
        raise SpecError("visual type must be one of: {}".format(", ".join(RENDERERS)))
    return renderer(spec)


def load_visual_specs(path: Path) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpecError("cannot read visual JSON: {}".format(exc))
    visuals = payload.get("visuals") if isinstance(payload, dict) else None
    if not isinstance(visuals, list) or not visuals:
        raise SpecError("top-level visuals must be a non-empty list")
    for index, item in enumerate(visuals):
        if not isinstance(item, dict):
            raise SpecError("visuals[{}] must be an object".format(index))
        output = item.get("output")
        if not isinstance(output, str) or not output.lower().endswith(".svg"):
            raise SpecError("visuals[{}].output must be a relative SVG path".format(index))
        output_path = Path(output)
        if output_path.is_absolute() or ".." in output_path.parts:
            raise SpecError("visual output must stay inside the output directory")
        scene_from_spec(item)
    return visuals


def _svg_attrs(item: Dict[str, Any]) -> str:
    dash = item.get("dash") or []
    return ' stroke-dasharray="{}"'.format(" ".join(str(v) for v in dash)) if dash else ""


def _polar(cx: float, cy: float, radius: float, degrees: float) -> Tuple[float, float]:
    radians = math.radians(degrees)
    return cx + radius * math.sin(radians), cy - radius * math.cos(radians)


def scene_to_svg(scene: Scene) -> str:
    output = ['<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" '
              'viewBox="0 0 {} {}" role="img" aria-labelledby="title desc">'.format(
                  scene.width, scene.height, scene.width, scene.height),
              '<title id="title">{}</title><desc id="desc">{}</desc>'.format(
                  html.escape(scene.title), html.escape(scene.description))]
    for item in scene.elements:
        kind = item["kind"]
        if kind == "rect":
            stroke_attr = ' stroke="{}"'.format(item["stroke"]) if item.get("stroke") else ""
            output.append('<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
                          'rx="{radius:.1f}" fill="{fill}"{stroke_attr}/>'.format(stroke_attr=stroke_attr, **item))
        elif kind == "line":
            output.append('<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          'stroke="{stroke}" stroke-width="{width}"{}/>'.format(_svg_attrs(item), **item))
        elif kind == "circle":
            fill = item.get("fill") or "none"
            stroke_attr = ' stroke="{}" stroke-width="{}"'.format(item["stroke"], item["width"]) if item.get("stroke") else ""
            output.append('<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{fill_value}"{stroke_attr}/>'.format(fill_value=fill, stroke_attr=stroke_attr, **item))
        elif kind == "text":
            transform = ''
            if item.get("rotation"):
                transform = ' transform="rotate({rotation} {x:.1f} {y:.1f})"'.format(**item)
            content = []
            for index, line in enumerate(item["lines"]):
                dy = 0 if index == 0 else item["line_height"]
                content.append('<tspan x="{:.1f}" dy="{}">{}</tspan>'.format(
                    item["x"], dy, html.escape(str(line))))
            output.append('<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" '
                          'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}"{transform}>{body}</text>'.format(
                              font=SVG_FONT, transform=transform, body="".join(content), **item))
        elif kind == "path":
            commands = []
            for command in item["commands"]:
                commands.append(command[0] + " " + " ".join("{:.1f}".format(float(v)) for v in command[1:]))
            output.append('<path d="{}" fill="{}" stroke="{}" stroke-width="{}"{} stroke-linecap="round" stroke-linejoin="round"/>'.format(
                " ".join(commands), item.get("fill") or "none", item["stroke"], item["width"], _svg_attrs(item)))
        elif kind == "triangle":
            points = " ".join("{:.1f},{:.1f}".format(x, y) for x, y in item["points"])
            output.append('<polygon points="{}" fill="{}"/>'.format(points, item["fill"]))
        elif kind == "pie":
            sx, sy = _polar(item["cx"], item["cy"], item["radius"], item["start"])
            ex, ey = _polar(item["cx"], item["cy"], item["radius"], item["end"])
            large = 1 if item["end"] - item["start"] > 180 else 0
            path = "M {cx:.1f} {cy:.1f} L {sx:.1f} {sy:.1f} A {radius:.1f} {radius:.1f} 0 {large} 1 {ex:.1f} {ey:.1f} Z".format(
                sx=sx, sy=sy, ex=ex, ey=ey, large=large, **item)
            output.append('<path d="{}" fill="{}"/>'.format(path, item["fill"]))
    output.append("</svg>")
    return "".join(output)


def safe_output(base: Path, name: Any) -> Path:
    if not isinstance(name, str) or not name.lower().endswith(".svg"):
        raise SpecError("output must be a relative SVG path")
    candidate, root = (base / name).resolve(), base.resolve()
    if candidate == root or root not in candidate.parents:
        raise SpecError("output must stay inside output directory")
    return candidate


def render_file(spec_path: Path, output_dir: Path) -> List[Path]:
    written = []
    for item in load_visual_specs(spec_path):
        target = safe_output(output_dir, item["output"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(scene_to_svg(scene_from_spec(item)), encoding="utf-8")
        written.append(target)
    return written
