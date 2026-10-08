"""Portable, static-first research reader. Standard library only; never fetches URLs.

The caller owns Markdown parsing and component validation. This module renders the
same safe report HTML, embeds local images, and adds progressive enhancements.
"""
from __future__ import annotations

import base64
import colorsys
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlparse


ASSETS = Path(__file__).resolve().parent.parent / "assets"


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def prose(value):
    return "<p>" + esc(value).replace("\n", "<br>") + "</p>" if value else ""


def display(value):
    if value is None:
        return "未提供"
    if isinstance(value, int) and not isinstance(value, bool):
        return format(value, ",")
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _safe_url(value):
    value = str(value or "").strip()
    return value if urlparse(value).scheme.lower() in {"https", "http"} else ""


def _image(path, workspace):
    if path.startswith("data:image/"):
        if not re.match(r"^data:image/(?:png|jpeg|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+$", path):
            raise ValueError("Unsupported embedded image")
        return path
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        raise ValueError("Offline report images must use local workspace paths: " + path)
    root = workspace.resolve()
    target = (root / unquote(parsed.path)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Image is outside the research workspace: " + path) from exc
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml", ".gif": "image/gif", ".webp": "image/webp"}.get(target.suffix.lower())
    if mime is None or not target.is_file():
        raise ValueError("Missing or unsupported report image: " + path)
    payload = target.read_bytes()
    if len(payload) > 25 * 1024 * 1024:
        raise ValueError("Report image exceeds 25 MiB: " + path)
    # SVG is rendered only as an image. Reject external references to keep it offline.
    if mime == "image/svg+xml":
        svg = payload.decode("utf-8-sig")
        if re.search(r"<!ENTITY|<!DOCTYPE|<script\b|<foreignObject\b|\bon\w+\s*=|(?:href|src)\s*=\s*['\"]\s*(?!#|data:)|url\(\s*['\"]?(?!#|data:)", svg, re.I):
            raise ValueError("SVG contains external or active content: " + path)
    return "data:" + mime + ";base64," + base64.b64encode(payload).decode("ascii")


class _Body(HTMLParser):
    """Add static heading anchors and inline images without parsing Markdown."""
    def __init__(self, workspace):
        super().__init__(convert_charrefs=False)
        self.workspace, self.parts, self.headings = workspace, [], []
        self.current = None
        self.counter = 0
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = list(attrs)
        values = dict(attrs)
        if tag == "table":
            self.parts.append('<div class="rw-table-wrap" tabindex="0" role="region" aria-label="报告表格">')
        if tag in {"h1", "h2", "h3", "h4"}:
            self.counter += 1
            identity = values.get("id") or "report-section-" + str(self.counter)
            if identity in self.ids:
                identity += "-" + str(self.counter)
            attrs = [(k, v) for k, v in attrs if k != "id"] + [("id", identity)]
            self.ids.add(identity)
            self.current = [identity, int(tag[1]), []]
        if tag == "img":
            attrs = [(k, _image(v, self.workspace) if k == "src" else v)
                     for k, v in attrs if k not in {"srcset", "loading"}]
            attrs.append(("loading", "lazy"))
        self.parts.append("<" + tag + "".join(" " + k + ("=\"" + esc(v) + "\"" if v is not None else "")
                                              for k, v in attrs) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.parts.append("</" + tag + ">")
        if tag == "table":
            self.parts.append("</div>")
        if self.current and tag == "h" + str(self.current[1]):
            identity, level, chunks = self.current
            self.headings.append({"id": identity, "level": level, "title": "".join(chunks).strip()})
            self.current = None

    def handle_data(self, data):
        self.parts.append(data)
        if self.current:
            self.current[2].append(data)

    def handle_entityref(self, name):
        self.parts.append("&" + name + ";")
        if self.current:
            self.current[2].append(html.unescape("&" + name + ";"))

    def handle_charref(self, name):
        self.parts.append("&#" + name + ";")
        if self.current:
            self.current[2].append(html.unescape("&#" + name + ";"))

    def handle_comment(self, data):
        self.parts.append("<!--" + data + "-->")


def _theme(study):
    theme = study.get("theme") or {}
    palette = {"product": "#0066cc", "technology": "#0066cc", "industry": "#096b79",
               "company": "#64518c", "protocol": "#965108", "policy": "#356b51",
               "person": "#454b55", "event": "#454b55"}
    requested = theme.get("accent", palette.get(study.get("subject_type"), "#0066cc"))
    if not isinstance(requested, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", requested):
        raise ValueError("theme.accent must be a six-digit hex color")
    def rgb(color):
        return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    def lum(color):
        c = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb(color)]
        return sum(a * b for a, b in zip(c, (.2126, .7152, .0722)))
    def hx(values):
        return "#" + "".join("{:02x}".format(round(max(0, min(1, v)) * 255)) for v in values)
    accent = requested.lower()
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb(accent))
    for _ in range(101):
        soft = hx(.94 + .06 * v for v in rgb(accent))
        if (lum(soft) + .05) / (lum(accent) + .05) >= 4.5:
            break
        lightness = max(0, lightness - .01)
        accent = hx(colorsys.hls_to_rgb(hue, lightness, saturation))
    return ":root{--accent:" + accent + ";--accent-soft:" + soft + ";}"


def _citations(component, sources):
    result = []
    for sid in component.get("source_ids", []):
        if sid not in sources:
            raise ValueError("Unknown source ID: " + str(sid))
        source = sources[sid]
        label = source.get("short_name") or source.get("display_name") or source.get("title") or sid
        visible = "[{}]".format(source["number"]) if source.get("number") is not None else str(label)
        result.append('<a href="#source-{}" data-source="{}" title="{}">{}</a>'.format(esc(sid), esc(sid), esc(label), esc(visible)))
    return '<p class="rw-source-links">依据：' + " · ".join(result) + "</p>" if result else ""


def _choose(items, title_key="title", all_option=True):
    return ('<div class="rw-controls rw-js" role="group" aria-label="选择内容">' +
            ('<button type="button" data-select-all aria-pressed="true">全部</button>' if all_option else "") +
            "".join('<button type="button" data-select="{}" aria-pressed="false">{}</button>'.format(
                esc(item["id"]), esc(item[title_key])) for item in items) + "</div>")


def _item(identity, contents, classes="", extra=""):
    return '<article class="rw-item {}" data-item="{}" {}>{}</article>'.format(classes, esc(identity), extra, contents)


def _series_chart(component):
    labels, series = component["x"], component["series"]
    values = [v for s in series for v in s["values"] if v is not None]
    if not values:
        return '<p class="rw-muted">当前序列未提供可绘制数值；缺失值保留在下表。</p>'
    low, high = min(0, min(values)), max(0, max(values))
    if low == high:
        high = low + 1
    width, height, left, top, plot_width, plot_height = 760, 310, 64, 26, 670, 232
    scale = high - low
    # Dividing before multiplying avoids needless overflow with large finite data.
    if not math.isfinite(scale):
        low, high, scale = low / 2, high / 2, (high / 2 - low / 2)
        normalize = lambda v: v / 2
    else:
        normalize = lambda v: v
    sy = lambda v: top + (1 - (normalize(v) - low) / scale) * plot_height
    sx = lambda i: left + (i + .5) / max(1, len(labels)) * plot_width
    zero = sy(0)
    bits = ['<svg class="rw-series-chart" viewBox="0 0 {} {}" role="img" aria-label="{}；完整数值见下表">'.format(width, height, esc(component["title"]))]
    for ratio in (0, .5, 1):
        y = top + ratio * plot_height
        actual = high - ratio * scale
        if normalize(2) != 2:
            actual *= 2
        bits.append('<line x1="64" x2="734" y1="{0:.2f}" y2="{0:.2f}" class="rw-grid-line"/><text x="57" y="{1:.2f}" text-anchor="end">{2}</text>'.format(y, y + 4, esc(format(actual, ".4g"))))
    dashes = ("", "8 4", "2 3", "10 3 2 3")
    for j, series_item in enumerate(series):
        bits.append('<g data-series="{}">'.format(esc(series_item["id"])))
        if component["mode"] == "line":
            segments, current = [], []
            for i, value in enumerate(series_item["values"]):
                if value is None:
                    if current:
                        segments.append(current)
                    current = []
                else:
                    current.append((sx(i), sy(value)))
            if current:
                segments.append(current)
            for segment in segments:
                points = " ".join("{:.2f},{:.2f}".format(x, y) for x, y in segment)
                bits.append('<polyline points="{}" fill="none" stroke="var(--accent)" stroke-width="2.3" stroke-dasharray="{}"/>'.format(points, dashes[j % len(dashes)]))
                for x, y in segment:
                    bits.append('<circle cx="{:.2f}" cy="{:.2f}" r="3.2" fill="var(--accent)"/>'.format(x, y))
        else:
            cell = plot_width / max(1, len(labels))
            bar = cell * .75 / max(1, len(series))
            for i, value in enumerate(series_item["values"]):
                if value is None:
                    continue
                y = sy(value)
                x = left + i * cell + cell * .125 + j * bar
                bits.append('<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="var(--accent)" opacity="{:.2f}"><title>{} · {}：{}</title></rect>'.format(x, min(y, zero), max(.4, bar - 1), max(.3, abs(zero - y)), .35 + .65 * (j + 1) / len(series), esc(series_item["label"]), esc(labels[i]), esc(display(value))))
        bits.append("</g>")
    stride = max(1, math.ceil(len(labels) / 7))
    for i, label in enumerate(labels):
        if i % stride == 0 or i == len(labels) - 1:
            bits.append('<text x="{:.2f}" y="280" text-anchor="middle">{}</text>'.format(sx(i), esc(label[:12])))
    bits.append("</svg>")
    return "".join(bits)


def _render_component(c, sources, workspace):
    kind, identity = c["kind"], c["id"]
    out = ['<section class="rw-widget" id="component-{}" data-kind="{}" data-component="{}" aria-labelledby="component-{}.title">'.format(esc(identity), esc(kind), esc(identity), esc(identity)),
           '<div class="rw-widget-heading"><h3 id="component-{}.title">{}</h3><button class="rw-js rw-save" type="button" data-bookmark="component-{}" aria-pressed="false">收藏</button></div>'.format(esc(identity), esc(c["title"]), esc(identity)), prose(c.get("intro"))]
    if kind == "timeline":
        items = c["events"]
        categories = list(dict.fromkeys(i.get("category", "") for i in items if i.get("category")))
        if categories:
            out.append('<label class="rw-js rw-filter-label">事件类别 <select data-category><option value="">全部</option>' + "".join('<option>{}</option>'.format(esc(v)) for v in categories) + "</select></label>")
        out.append('<ol class="rw-timeline">')
        for item in items:
            out.append('<li data-category-item="{}"><time>{}</time><div><h4>{}</h4>{}{}</div></li>'.format(esc(item.get("category", "")), esc(item["date"]), esc(item["label"]), prose(item["detail"]), '<small class="rw-muted">' + esc(item.get("category", "")) + "</small>"))
        out.append("</ol>")
    elif kind == "comparison":
        out.append('<label class="rw-js rw-filter-label">筛选比较对象 <input type="search" data-filter placeholder="对象名称或关键词"></label><div class="rw-table-wrap" tabindex="0" role="region" aria-label="比较表"><table><thead><tr><th scope="col">对象</th>')
        out.extend('<th scope="col">{} {}</th>'.format(esc(col["label"]), '<small>(' + esc(col["unit"]) + ')</small>' if col.get("unit") else "") for col in c["columns"])
        out.append("</tr></thead><tbody>")
        for row in c["rows"]:
            out.append('<tr data-filter-item><th scope="row">{}{}</th>{}</tr>'.format(esc(row["label"]), prose(row.get("detail")), "".join('<td>{}</td>'.format(esc(display(row["values"].get(col["id"])))) for col in c["columns"])))
        out.append('</tbody></table></div><p class="rw-filter-status rw-js" role="status"></p>')
    elif kind in {"process", "scenarios"}:
        items = c["steps"] if kind == "process" else c["cases"]
        out.append(_choose(items))
        out.append('<div class="rw-items">')
        for i, item in enumerate(items):
            content = '<h4><span class="rw-index">{:02d}</span> {}</h4>'.format(i + 1, esc(item["title"]))
            if kind == "process":
                content += prose(item["body"])
            else:
                content += '<p class="rw-condition"><b>适用条件：</b>{}</p>'.format(esc(item["when"])) + prose(item["text"])
                content += '<dl class="rw-outcomes">' + "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(esc(v["label"]), esc(display(v["value"]))) for v in item["outcomes"]) + "</dl>"
                content += '<p class="rw-limit"><b>边界：</b>{}</p>'.format(esc(item["limitation"]))
            out.append(_item(item["id"], content))
        out.append("</div>")
    elif kind == "relationships":
        nodes = {n["id"]: n for n in c["nodes"]}
        out.append('<label class="rw-js rw-filter-label">查看一个节点的关系 <select data-node><option value="">全部节点</option>' + "".join('<option value="{}">{}</option>'.format(esc(n["id"]), esc(n["label"])) for n in c["nodes"]) + '</select></label><div class="rw-node-list">')
        for n in c["nodes"]:
            out.append('<div class="rw-node" data-node-item="{}"><h4>{}</h4>{}</div>'.format(esc(n["id"]), esc(n["label"]), prose(n["detail"])))
        out.append('</div><p class="rw-muted">实线：事实关系；虚线：待检验关系。</p><ul class="rw-links">')
        for link in c["links"]:
            out.append('<li class="rw-link rw-{}" data-from="{}" data-to="{}"><b>{}</b><span class="rw-link-label">{} → <small>{}</small></span><b>{}</b></li>'.format(esc(link["kind"]), esc(link["from"]), esc(link["to"]), esc(nodes[link["from"]]["label"]), esc(link["label"]), "事实" if link["kind"] == "fact" else "待检验", esc(nodes[link["to"]]["label"])))
        out.append("</ul>")
    elif kind == "evidence":
        out.append('<p class="rw-js rw-muted">勾选用于对照检查材料；下方研究结论保持原文，勾选数量不代表证据强度。</p><div class="rw-items">')
        for item in c["items"]:
            content = '<h4>{}</h4><p class="rw-muted">{}</p>{}<p class="rw-limit"><b>支持边界：</b>{}</p><label class="rw-js rw-check"><input type="checkbox" data-evidence> 加入当前对照</label>'.format(esc(item["title"]), esc(item["kind"]), prose(item["statement"]), esc(item["limit"]))
            out.append(_item(item["id"], content))
        out.append('</div><p class="rw-js rw-evidence-status" role="status">尚未选择材料。</p><div class="rw-conclusion"><h4>研究结论</h4>{}</div>'.format(prose(c["conclusion"])))
    elif kind == "images":
        out.append('<div class="rw-image-list">')
        for item in c["items"]:
            image_id = identity + "." + item["id"]
            out.append('<figure class="rw-image" data-image="{}"><div class="rw-image-stage"><img src="{}" alt="{}">'.format(esc(image_id), _image(item["path"], workspace), esc(item["alt"])))
            for i, point in enumerate(item["points"]):
                out.append('<button type="button" class="rw-hotspot rw-js" data-image-point="{}" style="left:clamp(22px,{}%,calc(100% - 22px));top:clamp(22px,{}%,calc(100% - 22px))" aria-label="观察：{}">{}</button>'.format(i, point["x"], point["y"], esc(point["title"]), i + 1))
            out.append('</div><figcaption>{}</figcaption><button type="button" class="rw-js" data-image-open>放大查看图片</button><ol class="rw-image-points">'.format(esc(item["caption"])))
            for point in item["points"]:
                out.append('<li><b>{}</b>{}</li>'.format(esc(point["title"]), prose(point["body"])))
            out.append("</ol></figure>")
        out.append("</div>")
    elif kind == "glossary":
        out.append('<label class="rw-js rw-filter-label">查找术语 <input type="search" data-filter placeholder="术语、定义或例子"></label><dl class="rw-glossary">')
        for item in c["items"]:
            out.append('<div data-filter-item><dt>{}</dt><dd>{}{}{}</dd></div>'.format(esc(item["term"]), prose(item["definition"]), '<p><b>例子：</b>' + esc(item["example"]) + '</p>' if item.get("example") else "", '<p><b>反例：</b>' + esc(item["counterexample"]) + '</p>' if item.get("counterexample") else ""))
        out.append('</dl><p class="rw-filter-status rw-js" role="status"></p>')
    elif kind == "series":
        out.append('<p class="rw-muted">单位：{} · {}</p><div class="rw-controls rw-js" role="group" aria-label="显示序列">'.format(esc(c["unit"]), esc(c["basis"])))
        for s in c["series"]:
            out.append('<label class="rw-check"><input type="checkbox" data-series-toggle="{}" checked> {}</label>'.format(esc(s["id"]), esc(s["label"])))
        out.append("</div>" + _series_chart(c))
        out.append('<div class="rw-table-wrap" tabindex="0" role="region" aria-label="完整序列数值"><table><thead><tr><th scope="col">时间 / 类别</th>' + "".join('<th scope="col" data-series-col="{}">{}</th>'.format(esc(s["id"]), esc(s["label"])) for s in c["series"]) + "</tr></thead><tbody>")
        for i, label in enumerate(c["x"]):
            out.append('<tr><th scope="row">{}</th>{}</tr>'.format(esc(label), "".join('<td data-series-col="{}">{}</td>'.format(esc(s["id"]), esc(display(s["values"][i]))) for s in c["series"])))
        out.append('</tbody></table></div><p class="rw-muted">缺失值标为“未提供”，折线在缺失处断开。</p>')
    elif kind == "calculator":
        out.append('<div class="rw-calculator"><div class="rw-inputs">')
        values = {i["id"]: i["value"] for i in c["inputs"]}
        for item in c["inputs"]:
            input_id = "calc." + identity + "." + item["id"]
            out.append('<div class="rw-calc-input"><label for="{}">{} <span class="rw-muted">{}</span></label><input id="{}" type="number" data-input="{}" value="{}" min="{}" max="{}" step="{}" disabled><small>范围 {}–{}；每步 {}</small></div>'.format(esc(input_id), esc(item["label"]), esc(item["unit"]), esc(input_id), esc(item["id"]), item["value"], item["min"], item["max"], item["step"], esc(display(item["min"])), esc(display(item["max"])), esc(display(item["step"]))))
        out.append('</div><div class="rw-results" aria-live="polite" aria-atomic="true">')
        for result in c["outputs"]:
            value = math.fsum([result["base"]] + [values[t["input"]] * t["coefficient"] for t in result["terms"]])
            if not math.isfinite(value):
                raise ValueError("Non-finite calculator output: " + result["id"])
            formula = str(result["base"]) + "".join(" + ({} × {})".format(next(i["label"] for i in c["inputs"] if i["id"] == t["input"]), t["coefficient"]) for t in result["terms"])
            out.append('<div><h4>{}</h4><output data-output="{}">{}</output> <span>{}</span><p class="rw-formula">{}</p></div>'.format(esc(result["label"]), esc(result["id"]), esc(display(value)), esc(result["unit"]), esc(formula)))
        out.append('</div></div><p class="rw-calc-status rw-js" role="status"></p><p class="rw-limit"><b>假设与口径：</b>{}</p><p class="rw-static-note">未启用脚本时显示默认条件的计算结果。</p>'.format(esc(c["assumptions"])))
    else:
        raise ValueError("Unsupported interactive component: " + kind)
    out.append(_citations(c, sources) + "</section>")
    return "".join(out)


def _source_list(sources):
    result = ['<section id="research-sources" class="rw-sources"><h2>参考来源</h2><p class="rw-muted">来源元数据完整保留；外部原文链接需要联网。</p><ol>']
    for sid, source in sources.items():
        url = _safe_url(source.get("url"))
        title = source.get("title") or source.get("display_name") or sid
        short_name = source.get("short_name") or source.get("display_name") or ""
        result.append('<li id="source-{}" data-source-record="{}"{}><div class="rw-source-title"><h3>{}</h3><button class="rw-js rw-save" type="button" data-bookmark="source-{}" aria-pressed="false">收藏来源</button></div>'.format(esc(sid), esc(sid), ' value="{}"'.format(int(source["number"])) if source.get("number") is not None else "", esc(title), esc(sid)))
        metadata = [("简称", short_name), ("发布者", source.get("publisher") or source.get("author") or source.get("organization")), ("发布日期", source.get("published_at") or source.get("published_date") or source.get("date") or source.get("published") or "unknown"), ("访问日期", source.get("accessed_at") or source.get("accessed_date") or source.get("accessed") or source.get("access_date") or "unknown")]
        result.append('<dl class="rw-source-meta">' + "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(esc(label), esc(value)) for label, value in metadata if value) + '</dl>')
        if url:
            result.append('<a class="rw-full-url" href="{}" target="_blank" rel="noopener noreferrer">{}</a>'.format(esc(url), esc(url)))
        else:
            result.append('<p class="rw-muted">此来源未提供可打开的 HTTP(S) 地址。</p>')
        for key, label in (("notes", "说明"), ("locator", "定位"), ("language", "语言"), ("region", "地域"), ("source_type", "来源类型")):
            if source.get(key):
                value = source[key] if isinstance(source[key], str) else json.dumps(source[key], ensure_ascii=False)
                result.append('<p class="rw-source-note"><b>{}：</b>{}</p>'.format(label, esc(value)))
        # Preserve remaining source records in a readable disclosure, including evidence metadata.
        used = {"id", "number", "url", "title", "display_name", "short_name", "publisher", "author", "organization", "published_at", "published_date", "date", "published", "accessed_at", "accessed_date", "accessed", "access_date", "notes", "locator", "language", "region", "source_type"}
        extra = {k: v for k, v in source.items() if k not in used and v is not None}
        if extra:
            result.append('<details><summary>更多来源元数据</summary><pre>{}</pre></details>'.format(esc(json.dumps(extra, ensure_ascii=False, indent=2))))
        result.append("</li>")
    result.append("</ol></section>")
    return "".join(result)


def render_page(study: dict, body_html: str, components: dict, sources: dict,
                workspace: Path, pdf_href: str | None = None) -> str:
    """Return one offline HTML file; raise for missing/remote/out-of-root images.

    ``body_html`` must already be safely rendered by the report parser. Component
    strings and source metadata are always escaped here. No content is fetched.
    """
    workspace = Path(workspace)
    parsed = _Body(workspace)
    parsed.feed(body_html)
    parsed.close()
    component_list = components.get("components", [])
    body = "".join(parsed.parts)
    appended = []
    for component in component_list:
        rendered = _render_component(component, sources, workspace)
        marker = '<div data-component-slot="{}"></div>'.format(esc(component["id"]))
        if marker in body:
            if body.count(marker) != 1:
                raise ValueError("Component slot must occur exactly once: " + component["id"])
            body = body.replace(marker, rendered, 1)
        else:
            if component.get("after_heading"):
                raise ValueError("Missing requested component slot: " + component["id"])
            appended.append(rendered)
    component_html = "".join(appended)
    contents = parsed.headings + [{"id": "component-" + c["id"], "title": c["title"], "level": 3} for c in component_list]
    contents.sort(key=lambda entry: body.find('id="{}"'.format(esc(entry["id"]))) if 'id="{}"'.format(esc(entry["id"])) in body else len(body) + next((i for i, c in enumerate(component_list) if entry["id"] == "component-" + c["id"]), 0))
    contents.append({"id": "research-sources", "title": "参考来源", "level": 2})
    toc = "".join('<li class="rw-toc-level-{}"><a href="#{}">{}</a></li>'.format(h["level"], esc(h["id"]), esc(h["title"])) for h in contents if h["title"])
    title = study.get("title") or "横纵研究报告"
    study_id = str(study.get("id") or hashlib.sha256((title + str(study.get("as_of", ""))).encode("utf-8")).hexdigest()[:24])
    payload = {"version": 1, "study": {"id": study_id, "as_of": str(study.get("as_of", "")), "title": title}, "components": component_list,
               "headings": contents, "sources": {sid: {"id": sid, "title": source.get("title") or source.get("display_name") or sid} for sid, source in sources.items()}}
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    css = (ASSETS / "research-web.css").read_text(encoding="utf-8") + "\n" + _theme(study)
    js = (ASSETS / "research-web.js").read_text(encoding="utf-8")
    pdf = ""
    if pdf_href:
        if urlparse(pdf_href).scheme.lower() not in {"", "http", "https"}:
            raise ValueError("Unsupported PDF link")
        pdf = '<a href="{}">下载 PDF</a>'.format(esc(pdf_href))
    component_section = '<section id="research-explorations" class="rw-explorations"><h2>沿着问题探索</h2>' + component_html + '</section>' if component_html else ""
    metrics = study.get("reading_metrics") or {}
    metric_html = ""
    if metrics.get("word_count") is not None:
        metric_html = '<p class="rw-muted">完整研究与图解：{} 字'.format(esc(display(metrics["word_count"])))
        if metrics.get("estimated_minutes_min") is not None and metrics.get("estimated_minutes_max") is not None:
            metric_html += ' · 约 {}–{} 分钟'.format(esc(metrics["estimated_minutes_min"]), esc(metrics["estimated_minutes_max"]))
        metric_html += '</p>'
    theme_source = (study.get("theme") or {}).get("source")
    page_info = ('<details class="rw-page-info"><summary>页面信息</summary><p>强调色依据：{}；显示色可能为保证文字对比度做过调整。</p></details>'.format(esc(theme_source)) if theme_source else "")
    subject_label = {"product": "产品研究", "industry": "行业研究", "company": "公司研究", "technology": "技术研究", "protocol": "协议研究", "policy": "政策研究", "person": "人物研究", "event": "事件研究"}.get(study.get("subject_type"), "专题研究")
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="generator" content="orthogonal-research-skill"><link rel="icon" href="data:,"><title>''' + esc(title) + '''</title><style>''' + css + '''</style></head>
<body><a class="rw-skip" href="#report-body">跳到正文</a><header class="rw-masthead"><a class="rw-brand" href="#top">横纵研究</a><nav aria-label="阅读工具"><a href="#reader-toc">目录</a><a class="rw-js" href="#reader-search">全文搜索</a><a class="rw-js" href="#reader-notebook">笔记与收藏 <span id="rw-bookmark-count">0</span></a>''' + pdf + '''</nav></header>
<div class="rw-progress rw-js" aria-hidden="true"><span></span></div><main id="top"><header class="rw-hero"><p class="rw-eyebrow">''' + esc(subject_label) + ''' · ''' + esc(study.get("as_of", "")) + '''</p><h1>''' + esc(title) + '''</h1>''' + prose(study.get("subtitle")) + '''<p class="rw-muted">完整论证、交互探索与可追溯来源</p>''' + metric_html + '''</header>
<div class="rw-layout"><aside class="rw-sidebar"><details id="reader-toc" class="rw-toc"><summary>阅读目录</summary><nav aria-label="章节目录"><ol>''' + toc + '''</ol></nav></details></aside><div class="rw-reading">
<section id="reader-search" class="rw-js rw-search" aria-labelledby="reader-search-title"><h2 id="reader-search-title">在全文中查找</h2><label for="rw-search-input">关键词</label><div class="rw-search-field"><input type="search" id="rw-search-input" placeholder="搜索正文、探索内容和来源"><button type="button" id="rw-search-clear">清除</button></div><p id="rw-search-status" role="status"></p><ol id="rw-search-results"></ol></section>
<article id="report-body" class="rw-prose">''' + body + '''</article>''' + component_section + _source_list(sources) + '''
<section id="reader-notebook" class="rw-notebook rw-js" aria-labelledby="reader-notebook-title"><h2 id="reader-notebook-title">我的阅读记录</h2><p class="rw-muted">记录按报告分别保存于当前浏览器。重要笔记请导出；清除浏览器数据会移除本地记录。</p><label for="rw-notes">阅读笔记</label><textarea id="rw-notes" rows="7" maxlength="20000" placeholder="记下问题、证据和待核验的想法"></textarea><p id="rw-storage-status" role="status"></p><div class="rw-controls"><button type="button" id="rw-export">导出记录</button><label class="rw-import-label">导入记录<input type="file" id="rw-import" accept="application/json,.json"></label><button type="button" id="rw-recover" hidden>下载旧记录副本</button></div><p id="rw-import-status" role="status"></p><h3>已收藏</h3><ul id="rw-bookmarks"></ul></section>
</div></div></main><footer class="rw-footer"><span>''' + esc(title) + '''</span><a href="#top">回到开头 ↑</a><p>页面和交互可离线使用；外部原文链接需要联网。</p>''' + page_info + '''</footer>
<noscript><p class="rw-noscript">当前未启用 JavaScript。全文、组件全部内容、默认计算结果和来源仍可阅读；搜索与本地笔记需要启用脚本。</p></noscript>
<dialog id="rw-source-dialog" class="rw-dialog" aria-labelledby="rw-source-dialog-title"><div class="rw-dialog-bar"><h2 id="rw-source-dialog-title">来源详情</h2><button type="button" data-close-dialog>关闭</button></div><div id="rw-source-dialog-body"></div></dialog>
<dialog id="rw-image-dialog" class="rw-dialog rw-image-dialog" aria-labelledby="rw-image-dialog-title"><div class="rw-dialog-bar"><h2 id="rw-image-dialog-title">图片检视</h2><button type="button" data-close-dialog>关闭</button></div><div class="rw-controls"><label for="rw-image-zoom">放大</label><input type="range" id="rw-image-zoom" min="1" max="4" step="0.25" value="1"><output id="rw-image-scale">1×</output><button type="button" id="rw-image-reset">还原</button></div><div id="rw-image-viewport" tabindex="0" role="region" aria-label="放大图片，可拖动或用方向键移动"><img id="rw-image-large" alt=""></div><p id="rw-image-description"></p></dialog>
<script id="research-web-data" type="application/json">''' + data_json + '''</script><script>''' + js + '''</script></body></html>'''
