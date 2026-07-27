from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _registry_path() -> Path:
    """Return the optional source-checkout golden fixture registry."""

    return Path(__file__).resolve().parents[2] / "fixtures/golden/fixtures.json"


def _fixtures() -> tuple[Path, list[dict[str, Any]]]:
    registry_path = _registry_path()
    try:
        registry = json.loads(registry_path.read_text("utf-8"))
        fixtures = registry.get("fixtures")
        if not isinstance(fixtures, list):
            return registry_path, []
        return registry_path, [
            fixture for fixture in fixtures if isinstance(fixture, dict)
        ]
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return registry_path, []


def fixture_id_for_path(path: Path) -> str | None:
    registry_path, fixtures = _fixtures()
    repository_root = registry_path.parents[2]
    try:
        resolved = path.resolve()
        for fixture in fixtures:
            relative_path = fixture.get("path")
            fixture_id = fixture.get("id")
            if (
                isinstance(relative_path, str)
                and isinstance(fixture_id, str)
                and (repository_root / relative_path).resolve() == resolved
            ):
                return fixture_id
    except (OSError, ValueError):
        return None
    return None


def fixture_anchors(fixture_id: str | None) -> dict[str, str]:
    if fixture_id is None:
        return {}
    _, fixtures = _fixtures()
    for fixture in fixtures:
        if fixture.get("id") != fixture_id:
            continue
        anchors = fixture.get("anchors")
        if not isinstance(anchors, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in anchors.items()
        ):
            return {}
        return dict(anchors)
    return {}
