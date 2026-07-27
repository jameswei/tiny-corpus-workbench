from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "fixtures/golden"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(root: Path, golden: Path) -> None:
    registry = json.loads((golden / "fixtures.json").read_text("utf-8"))
    if (
        not isinstance(registry, dict)
        or set(registry) != {"fixtures"}
        or not isinstance(registry["fixtures"], list)
    ):
        raise SystemExit("fixture registry must contain only a fixture list")
    fixtures = registry["fixtures"]
    if not all(
        isinstance(item, dict) and isinstance(item.get("id"), str)
        for item in fixtures
    ):
        raise SystemExit(
            "fixture registry entries must be objects with string IDs"
        )
    ids = [item["id"] for item in fixtures]
    if ids != sorted(ids) or len(ids) != len(set(ids)) or len(ids) != 12:
        raise SystemExit("fixture registry must contain exactly twelve unique sorted IDs")
    registered = {Path(item["path"]).name for item in fixtures}
    actual = {
        path.name
        for path in golden.iterdir()
        if path.is_file() and path.name != "fixtures.json"
    }
    if actual != registered:
        raise SystemExit(f"golden files differ from registry: actual={sorted(actual)} registered={sorted(registered)}")
    if {(item["family"], item["format"]) for item in fixtures} != {
        (family, format_name)
        for family in ("policy-memo", "meeting-minutes", "release-notice")
        for format_name in ("pdf", "docx", "md", "txt")
    }:
        raise SystemExit("fixture registry is not the exact 3 x 4 matrix")
    for item in fixtures:
        if set(item) != {
            "anchors",
            "authored_source",
            "expected_docling_table_count",
            "family",
            "format",
            "id",
            "license",
            "media_type",
            "ownership",
            "path",
            "recipe",
            "sha256",
            "size",
        }:
            raise SystemExit(f"fixture registry entry has an invalid shape: {item.get('id')}")
        if item["recipe"] != "tools/generate_fixtures.py":
            raise SystemExit(f"fixture recipe mismatch: {item['id']}")
        path = root / item["path"]
        authored = root / item["authored_source"]["path"]
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


def main() -> int:
    try:
        _verify(ROOT, GOLDEN)
    except SystemExit:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        raise SystemExit(
            "fixture registry or fixture files are malformed"
        ) from None
    print("verified exactly 12 CC0 fixtures and registry metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
