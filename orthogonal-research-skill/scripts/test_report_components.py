#!/usr/bin/env python3
"""Run with python scripts/test_report_components.py (no third-party test runner)."""
from __future__ import annotations

import base64
import copy
import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from report_components import (
    KINDS, ComponentError, calculator_ranges, component_example,
    components_markdown, evaluate_calculator, export_tables, validate_components,
)


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+ioAAAAASUVORK5CYII=")


class ComponentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "image.png").write_bytes(PNG)
        self.spec = {"version": 1, "components": [component_example(k) for k in KINDS]}

    def tearDown(self):
        self.temp.cleanup()

    def checked(self, spec=None):
        return validate_components(self.spec if spec is None else spec, ["S001", "S002"], self.root)

    def component(self, kind):
        return next(c for c in self.spec["components"] if c["kind"] == kind)

    def test_all_kinds_and_input_immutability(self):
        original = copy.deepcopy(self.spec)
        checked = self.checked()
        self.assertEqual(self.spec, original)
        self.assertEqual({c["kind"] for c in checked["components"]}, set(KINDS))
        self.assertIsNot(checked["components"][0], self.spec["components"][0])
        checked["components"][0]["title"] = "changed"
        self.assertNotEqual(checked["components"][0]["title"], self.spec["components"][0]["title"])

    def test_empty_components_need_no_sources(self):
        checked = validate_components({"version": 1, "components": []}, [], self.root)
        self.assertEqual(components_markdown(checked), "")
        self.assertEqual(export_tables(checked, self.root / "empty"), [])

    def test_all_states_expand_and_all_sources_are_cited(self):
        scenario = self.component("scenarios")
        second = copy.deepcopy(scenario["cases"][0])
        second.update(id="second", title="第二情景", when="SECOND_CONDITION", text="SECOND_DETAIL", limitation="SECOND_LIMIT")
        scenario["cases"].append(second)
        for c in self.spec["components"]:
            c["source_ids"] = ["S001", "S002"]
        md = components_markdown(self.checked())
        for token in ("SECOND_CONDITION", "SECOND_DETAIL", "SECOND_LIMIT", "不能支持的推断", "由研究者写明的判断", "反例", "缺失（未提供）", "位置含义", "区间下界", "区间上界", "{{@S001,@S002 |}}"):
            self.assertIn(token, md)
        self.assertFalse(md.startswith("## "))
        self.assertEqual(md.count("### " + scenario["title"]), 1)

    def test_static_markdown_uses_existing_parser(self):
        from build_report import parse_markdown
        comparison = self.component("comparison")
        comparison["rows"][0]["values"]["metric"] = "A|B <tag> C:\\work"
        self.component("process")["steps"][0]["body"] = "Line one\nLine two <tag> C:\\work"
        md = components_markdown(self.checked())
        blocks = parse_markdown(md)
        self.assertTrue(any(b.kind == "table" and any("A|B <tag> C:\\work" in row for row in b.rows) for b in blocks))
        self.assertTrue(any("Line one Line two <tag> C:\\work" in b.text for b in blocks))
        self.assertFalse(any(b.kind == "code" for b in blocks))

    def test_optional_anchor_and_single_component(self):
        c = self.component("process")
        c["after_heading"] = "四、横纵交汇洞察"
        checked = self.checked({"version": 1, "components": [c]})
        self.assertEqual(checked["components"][0]["after_heading"], c["after_heading"])
        self.assertTrue(components_markdown(checked).startswith("### "))

    def test_source_validation(self):
        for value in ([], ["S999"], ["S001", "S001"], ["@S001"], [True], [None]):
            with self.subTest(value=value):
                spec = copy.deepcopy(self.spec)
                spec["components"][0]["source_ids"] = value
                with self.assertRaisesRegex(ComponentError, "source_ids"):
                    self.checked(spec)

    def test_duplicate_and_bad_ids(self):
        self.spec["components"].append(copy.deepcopy(self.spec["components"][0]))
        with self.assertRaisesRegex(ComponentError, "duplicate id"):
            self.checked()
        self.spec["components"].pop()
        event = self.component("timeline")["events"][0]
        self.component("timeline")["events"].append(copy.deepcopy(event))
        with self.assertRaisesRegex(ComponentError, "duplicate id"):
            self.checked()
        self.component("timeline")["events"].pop()
        event["id"] = "../outside"
        with self.assertRaisesRegex(ComponentError, "ASCII slug"):
            self.checked()

    def test_strict_shapes(self):
        bad = [None, [], {"version": True, "components": []}, {"version": 2, "components": []}, {"version": 1, "components": [], "extra": 0}]
        for spec in bad:
            with self.subTest(spec=spec), self.assertRaises(ComponentError):
                validate_components(spec, ["S001"], self.root)
        for kind in KINDS:
            with self.subTest(kind=kind):
                spec = {"version": 1, "components": [component_example(kind)]}
                spec["components"][0]["unexpected"] = True
                with self.assertRaisesRegex(ComponentError, "unknown fields"):
                    self.checked(spec)

    def test_missing_kind_specific_fields(self):
        fields = {"timeline": "events", "comparison": "columns", "process": "steps", "relationships": "nodes", "scenarios": "cases", "evidence": "conclusion", "images": "items", "glossary": "items", "series": "basis", "calculator": "assumptions"}
        for kind, field in fields.items():
            spec = {"version": 1, "components": [component_example(kind)]}
            del spec["components"][0][field]
            with self.subTest(kind=kind), self.assertRaisesRegex(ComponentError, "missing fields"):
                self.checked(spec)

    def test_plain_text_and_safe_literals(self):
        c = self.component("process")
        c["intro"] = "<script>alert(1)</script> 中文 English C:\\research A|B"
        self.checked()
        for value in ("bad\x00text", "**bold**", "`code`", "{{@S001 |}}", "[[red:notice]]", "[link](https://example.com)", "a\\|b"):
            with self.subTest(value=value):
                c["intro"] = value
                with self.assertRaises(ComponentError):
                    self.checked()

    def test_numbers_and_array_bounds(self):
        for value in (True, float("nan"), float("inf"), -float("inf"), 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                spec = copy.deepcopy(self.spec)
                series = next(c for c in spec["components"] if c["kind"] == "series")
                series["series"][0]["values"][0] = value
                with self.assertRaises(ComponentError):
                    self.checked(spec)
        timeline = self.component("timeline")
        timeline["events"] = [{**timeline["events"][0], "id": "event" + str(i)} for i in range(31)]
        with self.assertRaisesRegex(ComponentError, "0..30|1..30"):
            self.checked()

    def test_series_length_and_capacity(self):
        c = self.component("series")
        c["x"] = [str(i) for i in range(120)]
        c["series"] = [{"id": "series" + str(i), "label": "系列", "values": [None if j == 3 else j for j in range(120)]} for i in range(12)]
        self.checked()
        c["series"].append({"id": "overflow", "label": "超出", "values": [0] * 120})
        with self.assertRaisesRegex(ComponentError, "1..12"):
            self.checked()
        c["series"].pop()
        c["series"][0]["values"].pop()
        with self.assertRaisesRegex(ComponentError, "length must match"):
            self.checked()

    def test_comparison_requires_exact_column_keys(self):
        values = self.component("comparison")["rows"][0]["values"]
        values["extra"] = 1
        with self.assertRaisesRegex(ComponentError, "unknown fields"):
            self.checked()
        del values["extra"]
        del values["metric"]
        with self.assertRaisesRegex(ComponentError, "missing fields"):
            self.checked()

    def test_relationships_reference_existing_nodes(self):
        link = self.component("relationships")["links"][0]
        link["to"] = "missing"
        with self.assertRaisesRegex(ComponentError, "existing node"):
            self.checked()
        link["to"] = "b"
        link["kind"] = "causal-proof"
        with self.assertRaisesRegex(ComponentError, "fact or hypothesis"):
            self.checked()

    def test_image_path_boundaries_and_signature(self):
        image = self.component("images")["items"][0]
        for path in ("https://example.com/a.png", "//server/a.png", "\\\\server\\a.png", "C:\\outside.png", "../outside.png", "/outside.png", "assets/a.svg", "assets/missing.png"):
            with self.subTest(path=path):
                image["path"] = path
                with self.assertRaises(ComponentError):
                    self.checked()
        image["path"] = "assets/bad.png"
        (self.root / image["path"]).write_text("<svg/>", encoding="utf-8")
        with self.assertRaisesRegex(ComponentError, "signature"):
            self.checked()
        image["path"] = "assets\\image.png"
        checked = self.checked()
        self.assertEqual(next(c for c in checked["components"] if c["kind"] == "images")["items"][0]["path"], "assets/image.png")

    def test_image_path_encoding_and_points(self):
        image = self.component("images")["items"][0]
        (self.root / "assets" / "a (图)#%.png").write_bytes(PNG)
        image["path"] = "assets/a (图)#%.png"
        md = components_markdown(self.checked())
        self.assertIn("a%20%28", md)
        self.assertIn("%23%25.png", md)
        image["points"][0]["x"] = 101
        with self.assertRaisesRegex(ComponentError, "0 to 100"):
            self.checked()

    def test_symlink_escape_if_supported(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "image.png"
            target.write_bytes(PNG)
            link = self.root / "assets" / "link.png"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable for this account")
            self.component("images")["items"][0]["path"] = "assets/link.png"
            with self.assertRaisesRegex(ComponentError, "inside the research package"):
                self.checked()

    def test_calculator_defaults_and_exact_extrema(self):
        c = self.component("calculator")
        c["inputs"].append({"id": "offset", "label": "偏移", "value": 3, "min": 1, "max": 5, "step": 1, "unit": ""})
        c["outputs"][0]["terms"].append({"input": "offset", "coefficient": -3})
        c = next(v for v in self.checked()["components"] if v["kind"] == "calculator")
        self.assertEqual(evaluate_calculator(c), {"total": 16})
        self.assertEqual(calculator_ranges(c), {"total": (-10, 42)})
        self.assertEqual(evaluate_calculator(c, {"quantity": 20, "offset": 1}), {"total": 42})
        for values in ({"bad": 1}, {"quantity": 21}, {"quantity": math.inf}, {"quantity": True}):
            with self.subTest(values=values), self.assertRaises(ComponentError):
                evaluate_calculator(c, values)

    def test_calculator_range_errors(self):
        mutations = [("min", 20), ("value", 21), ("step", 0), ("step", 21), ("max", float("inf"))]
        for key, value in mutations:
            spec = {"version": 1, "components": [component_example("calculator")]}
            spec["components"][0]["inputs"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ComponentError):
                self.checked(spec)

    def test_calculator_default_step_grid_and_decimal_roundoff(self):
        c = component_example("calculator")
        item = c["inputs"][0]
        item.update(value=1, min=0, max=10, step=2)
        with self.assertRaisesRegex(ComponentError, "align"):
            self.checked({"version": 1, "components": [c]})
        for value, minimum, maximum, step in ((0.3, 0, 1, 0.1), (0.3, 0.1, 1, 0.2), (1e-9, 0, 1e-8, 1e-9)):
            with self.subTest(value=value, step=step):
                item.update(value=value, min=minimum, max=maximum, step=step)
                self.checked({"version": 1, "components": [c]})

    def test_static_numbers_keep_small_and_large_values(self):
        c = component_example("series")
        c["x"] = ["small", "large"]
        c["series"][0]["values"] = [1e-9, 10000000000000002.0]
        md = components_markdown(self.checked({"version": 1, "components": [c]}))
        self.assertIn("| small | 1e-09 |", md)
        self.assertIn("| large | 1.0000000000000002e+16 |", md)

    def test_calculator_cancellation_retains_small_residual(self):
        c = component_example("calculator")
        c["inputs"] = [dict(id="small", label="small", value=1, min=0, max=2, step=1, unit=""),
                       dict(id="large", label="large", value=1e16, min=1e16-2, max=1e16+2, step=2, unit="")]
        c["outputs"] = [dict(id="result", label="result", unit="", base=1e16,
                             terms=[dict(input="small", coefficient=1), dict(input="large", coefficient=-1)])]
        checked = self.checked({"version": 1, "components": [c]})["components"][0]
        self.assertEqual(evaluate_calculator(checked), {"result": 1})
        self.assertEqual(calculator_ranges(checked), {"result": (-2, 4)})

    def test_calculator_overflow_even_when_default_is_finite(self):
        c = self.component("calculator")
        c["inputs"][0].update(value=0, min=0, max=1e308, step=1)
        c["outputs"][0]["terms"][0]["coefficient"] = 2
        with self.assertRaisesRegex(ComponentError, "boundary"):
            self.checked()
        c["outputs"][0]["terms"][0]["coefficient"] = 1
        c["outputs"][0]["base"] = 1e308
        with self.assertRaisesRegex(ComponentError, "overflows"):
            self.checked()

    def test_calculator_invalid_reference_and_duplicate_term(self):
        terms = self.component("calculator")["outputs"][0]["terms"]
        terms[0]["input"] = "missing"
        with self.assertRaisesRegex(ComponentError, "existing input"):
            self.checked()
        terms[0]["input"] = "quantity"
        terms.append(copy.deepcopy(terms[0]))
        with self.assertRaisesRegex(ComponentError, "repeated terms"):
            self.checked()

    def test_exports_cover_all_kinds_and_preserve_missing_zero_sources(self):
        self.component("comparison")["rows"].append({"id": "zero", "label": "=1+2", "values": {"metric": 0}})
        files = export_tables(self.checked(), self.root / "tables")
        self.assertEqual(len(files), 15)
        self.assertEqual(len(set(files)), len(files))
        exported_ids = set()
        for path in files:
            with Path(path).open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                exported_ids.add(row["component_id"])
                self.assertEqual(row["source_ids"], "S001")
        self.assertEqual(exported_ids, {c["id"] for c in self.spec["components"]})
        with (self.root / "tables" / "component-comparison_example.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["metric"], "")
        self.assertEqual(rows[1]["metric"], "0")
        self.assertEqual(rows[1]["label"], "'=1+2")

    def test_export_names_do_not_collide(self):
        a = component_example("relationships")
        a["id"] = "example"
        b = component_example("process")
        b["id"] = "example-nodes"
        checked = self.checked({"version": 1, "components": [a, b]})
        files = export_tables(checked, self.root / "tables")
        self.assertEqual(len(files), len(set(files)))
        self.assertTrue(all(Path(f).is_file() for f in files))

    def test_cli_discovery_and_validation(self):
        script = Path(__file__).with_name("report_components.py")
        run = subprocess.run([sys.executable, str(script), "--list"], capture_output=True, check=True)
        self.assertIn(b"calculator", run.stdout)
        run = subprocess.run([sys.executable, str(script), "--describe", "process"], capture_output=True, check=True)
        self.assertIn(b'"steps"', run.stdout)
        (self.root / "components.json").write_text(json.dumps(self.spec), encoding="utf-8")
        (self.root / "sources.json").write_text(json.dumps({"sources": [{"id": "S001"}]}), encoding="utf-8")
        run = subprocess.run([sys.executable, str(script), "--validate", str(self.root / "components.json"), "--sources", str(self.root / "sources.json"), "--workspace", str(self.root)], capture_output=True, check=True)
        self.assertEqual(json.loads(run.stdout)["status"], "pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
