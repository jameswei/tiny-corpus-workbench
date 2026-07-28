#!/usr/bin/env python3
"""Verify the committed v0.5 corpus specifications without rewriting them."""

from __future__ import annotations

import json
from pathlib import Path

from tiny_corpus_workbench.corpus import load_corpus_spec


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "fixtures/corpus/v0.5"
GOLDEN_SPEC = CORPUS / "golden-matrix.json"
QUALITY_SPEC = CORPUS / "quality-corpus.json"
GOLDEN_REGISTRY = ROOT / "fixtures/golden/fixtures.json"
DIAGNOSIS_REGISTRY = ROOT / "fixtures/diagnosis/fixtures.json"
REFINEMENT_REGISTRY = ROOT / "fixtures/refinement/fixtures.json"
FORMATS = {"pdf", "docx", "md", "txt"}
QUALITY_RULES = {
    "TCW-D002",
    "TCW-D003",
    "TCW-D004",
    "TCW-D005",
    "TCW-D007",
    "TCW-D009",
    "TCW-D010",
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _fail(message: str) -> None:
    raise SystemExit(message)


def _registry_members(registry: dict) -> dict[str, dict]:
    return {item["id"]: item for item in registry["fixtures"]}


def main() -> int:
    before = {
        path: path.read_bytes()
        for path in (GOLDEN_SPEC, QUALITY_SPEC)
    }
    golden = load_corpus_spec(GOLDEN_SPEC).normalized
    quality = load_corpus_spec(QUALITY_SPEC).normalized

    registered_golden = _registry_members(_read(GOLDEN_REGISTRY))
    actual_golden = {item["member_id"]: item for item in golden["members"]}
    if set(actual_golden) != set(registered_golden) or len(actual_golden) != 12:
        _fail("golden corpus must contain exactly the twelve registered fixtures")
    expected_matrix = {
        (family, format_name)
        for family in ("meeting-minutes", "policy-memo", "release-notice")
        for format_name in FORMATS
    }
    if {
        (item["family"], item["format"]) for item in golden["members"]
    } != expected_matrix:
        _fail("golden corpus must contain the exact three-family four-format matrix")
    for member_id, member in actual_golden.items():
        registered = registered_golden[member_id]
        expected_path = (ROOT / registered["path"]).resolve()
        actual_path = (GOLDEN_SPEC.parent / member["source"]).resolve()
        if (
            member["family"] != registered["family"]
            or member["format"] != registered["format"]
            or actual_path != expected_path
        ):
            _fail(f"golden corpus metadata differs: {member_id}")

    diagnosis = _registry_members(_read(DIAGNOSIS_REGISTRY))
    refinement = _registry_members(_read(REFINEMENT_REGISTRY))
    registered_quality = {**diagnosis, **refinement}
    actual_quality = {item["member_id"]: item for item in quality["members"]}
    if set(actual_quality) != set(registered_quality) or len(actual_quality) != 5:
        _fail("quality corpus must contain exactly the five registered quality fixtures")
    covered_rules: set[str] = set()
    for member_id, member in actual_quality.items():
        registered = registered_quality[member_id]
        expected_format = Path(registered["path"]).suffix.lstrip(".")
        expected_path = (ROOT / registered["path"]).resolve()
        actual_path = (QUALITY_SPEC.parent / member["source"]).resolve()
        if (
            member["family"] != member_id
            or member["format"] != expected_format
            or actual_path != expected_path
        ):
            _fail(f"quality corpus metadata differs: {member_id}")
        covered_rules.update(registered["expected_rules"])
    if covered_rules != QUALITY_RULES:
        _fail("quality corpus rule coverage differs from the accepted seven-rule set")

    after = {
        path: path.read_bytes()
        for path in (GOLDEN_SPEC, QUALITY_SPEC)
    }
    if before != after:
        _fail("corpus specification verification rewrote a committed fixture")
    print(
        "verified exact v0.5 golden and quality corpus specifications "
        "with rules D002, D003, D004, D005, D007, D009, and D010"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
