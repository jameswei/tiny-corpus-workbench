from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "fixtures/golden"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    registry = json.loads((GOLDEN / "fixtures.json").read_text("utf-8"))
    schema = json.loads((ROOT / "src/tiny_corpus_workbench/schemas/fixture-registry-v0.1.schema.json").read_text("utf-8"))
    Draft202012Validator(schema).validate(registry)
    fixtures = registry["fixtures"]
    ids = [item["id"] for item in fixtures]
    if ids != sorted(ids) or len(ids) != len(set(ids)) or len(ids) != 12:
        raise SystemExit("fixture registry must contain exactly twelve unique sorted IDs")
    registered = {Path(item["path"]).name for item in fixtures}
    actual = {path.name for path in GOLDEN.iterdir() if path.is_file() and path.name != "fixtures.json"}
    if actual != registered:
        raise SystemExit(f"golden files differ from registry: actual={sorted(actual)} registered={sorted(registered)}")
    if {(item["family"], item["format"]) for item in fixtures} != {
        (family, format_name)
        for family in ("policy-memo", "meeting-minutes", "release-notice")
        for format_name in ("pdf", "docx", "md", "txt")
    }:
        raise SystemExit("fixture registry is not the exact 3 x 4 matrix")
    for item in fixtures:
        path = ROOT / item["path"]
        authored = ROOT / item["authored_source"]["path"]
        if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
            raise SystemExit(f"fixture hash or size mismatch: {item['id']}")
        if digest(authored) != item["authored_source"]["sha256"]:
            raise SystemExit(f"authored source hash mismatch: {item['id']}")
        spec = json.loads(authored.read_text("utf-8"))
        for value in item["anchors"].values():
            if value not in path.read_text("utf-8", errors="ignore") and item["format"] in ("md", "txt"):
                raise SystemExit(f"missing visible anchor in {item['id']}: {value}")
        if item["anchors"] != {"document_id": spec["document_id"], "date": spec["date"], "url": spec["url"]}:
            raise SystemExit(f"fixture anchors mismatch: {item['id']}")
    print("verified exactly 12 CC0 fixtures and registry metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
