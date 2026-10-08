#!/usr/bin/env python3
"""End-to-end delivery invariants; generated studies are explicitly fictional."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import build_delivery as delivery
from create_delivery_fixture import create_fixture
from check_research import check_research


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="report-delivery-test-")
        self.root = Path(self.temp.name)
        self.study = self.root / "study"
        create_fixture("product", self.study)
        self.path = self.study / "study.json"

    def tearDown(self):
        self.temp.cleanup()

    def load(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def build(self, **kwargs):
        return delivery.build_delivery(self.path, **kwargs)

    def test_dual_output_and_source_unchanged(self):
        before = delivery.digest(self.study / "report.md")
        result = self.build()
        out = Path(result["directory"])
        self.assertEqual(result["formats"], ["pdf", "html"])
        self.assertTrue((out / "report.pdf").read_bytes().startswith(b"%PDF-"))
        html = (out / "report.html").read_text(encoding="utf-8")
        self.assertIn('href="report.pdf"', html)
        self.assertIn("data:image/png;base64,", html)
        self.assertEqual(before, delivery.digest(self.study / "report.md"))
        manifest = self.load(out / "manifest.json")
        self.assertEqual(manifest["research_review_status"], "not_assessed")
        for relative, expected in manifest["files"].items():
            self.assertEqual(delivery.digest(out / relative), expected)
        self.assertEqual(check_research(out / "sources.json")["schema_status"], "pass")
        for component in self.load(out / "components.json")["components"]:
            self.assertIn(component["title"], (out / "report.md").read_text(encoding="utf-8"))
        self.assertTrue(list((out / "data").glob("component-*.csv")))

    def test_moved_export_rebuilds_from_own_inputs(self):
        original = Path(self.build(formats="html")["directory"])
        moved = self.root / "moved"
        shutil.copytree(original, moved)
        # Prohibit using original inputs by renaming their enclosing directory.
        hidden = self.root / "unavailable"
        self.study.rename(hidden)
        target = self.root / "rebuilt"
        result = delivery.build_delivery(moved / "study.json", target, "html")
        self.assertEqual(result["status"], "built")
        self.assertIn("data:image/png;base64,", (target / "report.html").read_text(encoding="utf-8"))
        self.assertEqual(check_research(target / "sources.json")["schema_status"], "pass")

    def test_pdf_only_then_html_only_removes_owned_stale_artifacts(self):
        out = Path(self.build(formats="pdf")["directory"])
        self.assertFalse((out / "report.html").exists())
        unrelated = out / "my-notes.txt"
        unrelated.write_text("keep", encoding="utf-8")
        self.build(formats="html")
        self.assertFalse((out / "report.pdf").exists())
        self.assertNotIn('href="report.pdf"', (out / "report.html").read_text(encoding="utf-8"))
        self.assertEqual(unrelated.read_text(), "keep")

    def test_protects_edited_exports(self):
        out = Path(self.build(formats="html")["directory"])
        (out / "source.md").write_text("user edit", encoding="utf-8")
        with self.assertRaisesRegex(delivery.DeliveryError, "edited"):
            self.build(formats="html")
        self.assertEqual((out / "source.md").read_text(), "user edit")

    def test_rejects_input_directory_as_output(self):
        with self.assertRaisesRegex(delivery.DeliveryError, "contain"):
            self.build(output=self.study, formats="html")

    def test_check_only_checks_body_citations_without_writing(self):
        text = (self.study / "report.md").read_text(encoding="utf-8")
        (self.study / "report.md").write_text(text.replace("@S001", "@S999"), encoding="utf-8")
        with self.assertRaisesRegex(delivery.DeliveryError, "Unknown|unknown"):
            self.build(check_only=True)
        self.assertFalse((self.study / "delivery").exists())

    def test_unknown_and_ambiguous_heading_rejected(self):
        spec = self.load(self.study / "data/components.json")
        spec["components"][0]["after_heading"] = "Absent heading"
        self.save(self.study / "data/components.json", spec)
        with self.assertRaisesRegex(delivery.DeliveryError, "heading"):
            self.build(check_only=True)

    def test_no_components_is_valid(self):
        self.save(self.study / "data/components.json", {"version": 1, "components": []})
        result = self.build(formats="html")
        self.assertEqual(result["components"], 0)

    def test_legacy_six_visuals_share_the_delivery_pipeline(self):
        examples = self.load(Path(__file__).resolve().parent.parent / "references/sample_visuals.json")
        for visual in examples["visuals"]:
            visual["source"] = "S001"
            for edge in visual.get("edges", []):
                edge["source"] = "S001"
        self.save(self.study / "data/visuals.json", examples)
        study = self.load(self.path)
        study["visual_spec"] = "data/visuals.json"
        self.save(self.path, study)
        text_path = self.study / "report.md"
        text = text_path.read_text(encoding="utf-8")
        images = "\n\n".join("![静态图](visuals/" + v["output"] + ")" for v in examples["visuals"])
        text = text.replace("## 五、信息来源与方法说明", "## 静态图构建验证\n\n" + images + "\n\n## 五、信息来源与方法说明")
        text_path.write_text(text, encoding="utf-8")
        out = Path(self.build()["directory"])
        self.assertEqual(len(list((out / "visuals").glob("*.svg"))), 6)
        self.assertEqual((out / "report.html").read_text(encoding="utf-8").count("data:image/svg+xml;base64,"), 6)

    def test_path_escape_and_cutoff_mismatch(self):
        value = self.load(self.path)
        value["report"] = "../outside.md"
        (self.root / "outside.md").write_text("outside", encoding="utf-8")
        self.save(self.path, value)
        with self.assertRaisesRegex(delivery.DeliveryError, "outside"):
            self.build(check_only=True)
        value["report"] = "report.md"
        value["as_of"] = "2026-10-07"
        self.save(self.path, value)
        with self.assertRaisesRegex(delivery.DeliveryError, "as_of"):
            self.build(check_only=True)


if __name__ == "__main__":
    unittest.main()
