#!/usr/bin/env python3
"""Check research-record structure and auditability, never claim semantic truth.

Legacy records remain renderable by build_report.py. This separate check may expose
their missing relations; passing it still requires independent original-source review.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List

from build_report import BuildError, load_sources


def check_research(path: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    result: Dict[str, Any] = {"schema_status": "fail", "semantic_review": "not_assessed",
                              "errors": errors, "warnings": warnings}
    try:
        sources, payload = load_sources(path)
    except (BuildError, OSError, ValueError) as exc:
        errors.append("source_structure: {}".format(exc))
        return result
    result["method_version"] = str(payload.get("method_version", "legacy"))
    if result["method_version"] != "3":
        warnings.append("legacy_record: not assessed under V3 high-impact requirements")
    elif payload.get("coverage", {}).get("balance_policy") != "diagnostic":
        errors.append("v3_policy: V3 records must explicitly select diagnostic")

    def parsed_date(value: Any, field: str, unknown: bool = False):
        if unknown and value == "unknown":
            warnings.append("unknown_date: " + field)
            return None
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            return date.fromisoformat(value)
        except ValueError:
            errors.append("invalid_date: " + field)
            return None

    cutoff = parsed_date(payload.get("as_of"), "as_of")
    for sid, source in sources.items():
        for field in ("display_name", "title", "publisher", "url", "type", "language", "region", "perspective_group"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append("source_text: {}.{} must be a non-empty string".format(sid, field))
        published = parsed_date(source.get("published_at"), sid + ".published_at", True)
        accessed = parsed_date(source.get("accessed_at"), sid + ".accessed_at")
        if published and accessed and published > accessed:
            errors.append("date_order: " + sid + " published after recorded access")
        if published and cutoff and published > cutoff:
            warnings.append("post_cutoff_source: " + sid + "; distinguish retrospective evidence from knowledge available then")
        key = source.get("independence_key")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            errors.append("source_root: " + sid + " must use a non-empty string")
        if not key:
            warnings.append("unspecified_root: " + sid + "; independence not established")
        if source.get("published_at") == "unknown" and (not isinstance(source.get("notes"), str) or not source["notes"].strip()):
            errors.append("unknown_date_notes: " + sid)

    claims = payload.get("claims", [])
    datasets = payload.get("datasets", [])
    if not isinstance(claims, list) or not isinstance(datasets, list):
        errors.append("records: claims and datasets must be arrays")
        return result
    records: Dict[str, Dict[str, Any]] = {}
    kinds: Dict[str, str] = {}
    for category, rows, prefix in (("claim", claims, "C"), ("dataset", datasets, "D")):
        for index, record in enumerate(rows):
            if not isinstance(record, dict):
                errors.append("record_object: {}[{}]".format(category, index))
                continue
            rid = record.get("id")
            if not isinstance(rid, str) or not re.fullmatch(prefix + r"\d{3,}", rid):
                errors.append("record_id: {}[{}]".format(category, index))
                continue
            if rid in records:
                errors.append("duplicate_record: " + rid)
                continue
            records[rid], kinds[rid] = record, category
    if not claims:
        errors.append("missing_claims: researched reports require key claims, even if unresolved")

    def ids(value: Any, field: str, valid: Dict[str, Any]):
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            errors.append("id_array: " + field)
            return []
        if len(set(value)) != len(value):
            errors.append("duplicate_link: " + field)
        for identifier in value:
            if identifier not in valid:
                errors.append("dangling_link: {} -> {}".format(field, identifier))
        return value

    source_links = {sid: ids(source.get("supports"), sid + ".supports", records)
                    for sid, source in sources.items()}
    record_links = {rid: ids(record.get("source_ids"), rid + ".source_ids", sources)
                    for rid, record in records.items()}
    for sid, links in source_links.items():
        for rid in links:
            if rid in records and sid not in record_links[rid]:
                errors.append("asymmetric_link: {} -> {}".format(sid, rid))
    for rid, links in record_links.items():
        for sid in links:
            if sid in sources and rid not in source_links[sid]:
                errors.append("asymmetric_link: {} -> {}".format(rid, sid))

    root = path.resolve().parent
    if root.name.lower() == "sources":
        root = root.parent
    for rid, record in records.items():
        if kinds[rid] == "dataset":
            for field in ("file", "unit", "definition", "period", "geography"):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    errors.append("dataset_field: {}.{}".format(rid, field))
            if isinstance(record.get("file"), str) and record["file"].strip():
                try:
                    target = (root / record["file"]).resolve()
                    if target != root and root not in target.parents:
                        errors.append("dataset_path: " + rid + " leaves report root")
                    elif not target.is_file():
                        errors.append("dataset_file: " + rid + " does not exist")
                except (OSError, ValueError, RuntimeError):
                    errors.append("dataset_path: " + rid + " cannot resolve or inspect local file")
            continue
        if not isinstance(record.get("claim"), str) or not record["claim"].strip():
            errors.append("claim_text: " + rid)
        if record.get("confidence") not in ("low", "medium", "high"):
            errors.append("confidence_value: " + rid)
        for field in ("event_date", "observed_at"):
            if field in record:
                event = parsed_date(record[field], rid + "." + field)
                if event and cutoff and event > cutoff and record.get("kind") != "hypothesis":
                    errors.append("future_fact: " + rid + "." + field)
        if "impact_reason" in record and (not isinstance(record["impact_reason"], str) or not record["impact_reason"].strip()):
            errors.append("impact_reason: " + rid + " must be a non-empty string when provided")
        high_impact = isinstance(record.get("impact_reason"), str) and bool(record["impact_reason"].strip())
        if not high_impact:
            continue
        kind = record.get("kind")
        if kind not in ("fact", "disputed", "inference", "hypothesis"):
            errors.append("claim_kind: " + rid)
        evidence = record.get("evidence")
        if not isinstance(evidence, list):
            errors.append("evidence_array: " + rid)
            continue
        if not evidence:
            if not isinstance(record.get("support_gap"), str) or not record["support_gap"].strip():
                errors.append("missing_support_gap: " + rid)
            if record.get("status") not in ("unresolved", "provisional", "hypothesis") or record.get("confidence") == "high":
                errors.append("unsupported_verified: " + rid)
        evidence_ids = []
        for index, item in enumerate(evidence):
            label = "{}.evidence[{}]".format(rid, index)
            if not isinstance(item, dict):
                errors.append("evidence_object: " + label)
                continue
            sid = item.get("source_id")
            if not isinstance(sid, str) or sid not in sources:
                errors.append("evidence_source: " + label)
            else:
                evidence_ids.append(sid)
            for field in ("locator", "supported_statement", "support_boundary", "time_basis"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    errors.append("evidence_field: {}.{}".format(label, field))
            roots = item.get("root_keys")
            if (roots is not None or item.get("mixed_source") is True) and (
                    not isinstance(roots, list) or not roots or
                    not all(isinstance(x, str) and x.strip() for x in roots)):
                errors.append("evidence_roots: " + label)
        if set(evidence_ids) != set(record_links[rid]):
            errors.append("evidence_link_coverage: " + rid)
        if kind in ("disputed", "inference", "hypothesis"):
            review = record.get("review")
            if not isinstance(review, dict) or not all(
                    isinstance(review.get(field), str) and review[field].strip()
                    for field in ("alternative", "discriminating_evidence", "change_condition", "revision")):
                errors.append("review_fields: " + rid)

    for index, limitation in enumerate(payload.get("limitations", [])):
        ids(limitation.get("affected_claims"), "limitation[{}].affected_claims".format(index), records)
    if not errors:
        result["schema_status"] = "pass"
    result["claim_count"] = len(claims)
    result["high_impact_count"] = sum(isinstance(x.get("impact_reason"), str) and bool(x["impact_reason"].strip())
                                      for x in claims if isinstance(x, dict))
    result["required_next_step"] = "Independently identify all consequential claims and compare actual sources, scope, alternatives and revisions; schema pass is insufficient"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_research(args.sources)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        try:
            args.output.write_text(encoded, encoding="utf-8")
        except OSError:
            print("cannot save research-check output", file=sys.stderr)
            return 2
    print(encoded)
    return 0 if result["schema_status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
