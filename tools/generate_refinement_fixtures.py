#!/usr/bin/env python3
"""Check the deterministic project-authored v0.3 refinement fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/refinement/v0.3"
REGISTRY = FIXTURES / "fixtures.json"


def descriptor(path: Path, fixture_id: str, rules: list[str]) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "id": fixture_id,
        "path": path.relative_to(ROOT).as_posix(),
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "license": "CC0-1.0",
        "expected_rules": rules,
    }


def expected() -> dict[str, object]:
    return {
        "schema_version": "tcw.refinement-fixture-registry/v0.3",
        "generator": "tools/generate_refinement_fixtures.py",
        "fixtures": [
            descriptor(
                FIXTURES / "line-end-hyphenation.md",
                "line-end-hyphenation",
                ["TCW-D010"],
            ),
            descriptor(
                FIXTURES / "whitespace-cleanup.md",
                "whitespace-cleanup",
                ["TCW-D009"],
            ),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rendered = (
        json.dumps(expected(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    if arguments.check:
        if not REGISTRY.is_file() or REGISTRY.read_bytes() != rendered:
            print("v0.3 refinement fixture registry differs")
            return 1
        return 0
    REGISTRY.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
