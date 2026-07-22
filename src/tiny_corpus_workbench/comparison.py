from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


NUMERIC_METRICS = (
    "bytes",
    "characters",
    "non_whitespace_characters",
    "lines",
    "non_empty_lines",
    "atx_headings",
    "unordered_list_items",
    "ordered_list_items",
    "pipe_table_rows",
    "visible_urls",
)


def normalize_markdown(value: bytes | str) -> str:
    text = value.decode("utf-8", errors="strict") if isinstance(value, bytes) else value
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


def _metrics(text: str, anchors: dict[str, str], artifact_hash: str) -> dict[str, Any]:
    encoded = text.encode("utf-8")
    lines = text[:-1].split("\n") if text else []
    return {
        "artifact_sha256": artifact_hash,
        "normalized_sha256": hashlib.sha256(encoded).hexdigest(),
        "anchors": {key: value in text for key, value in anchors.items()},
        "bytes": len(encoded),
        "characters": len(text),
        "non_whitespace_characters": sum(not char.isspace() for char in text),
        "lines": len(lines),
        "non_empty_lines": sum(bool(line) for line in lines),
        "atx_headings": sum(bool(re.match(r"^#{1,6}(?:\s|$)", line)) for line in lines),
        "unordered_list_items": sum(bool(re.match(r"^\s*[-+*]\s+", line)) for line in lines),
        "ordered_list_items": sum(bool(re.match(r"^\s*\d+[.)]\s+", line)) for line in lines),
        "pipe_table_rows": sum(line.count("|") >= 2 for line in lines),
        "visible_urls": len(re.findall(r"https?://[^\s)>\]]+", text)),
    }


def make_comparison(
    observation_id: str,
    source: dict[str, Any],
    anchors: dict[str, str],
    docling: tuple[bytes, str] | None,
    markitdown: tuple[bytes, str] | None,
) -> dict[str, Any]:
    views: dict[str, Any] = {"docling": None, "markitdown": None}
    normalized: dict[str, str] = {}
    for name, view in (("docling", docling), ("markitdown", markitdown)):
        if view is not None:
            raw, artifact_hash = view
            normalized[name] = normalize_markdown(raw)
            views[name] = _metrics(normalized[name], anchors, artifact_hash)
    if len(normalized) == 2:
        status = "COMPLETE"
        deltas = {
            metric: views["docling"][metric] - views["markitdown"][metric]
            for metric in NUMERIC_METRICS
        }
        deltas["normalized_equal"] = normalized["docling"] == normalized["markitdown"]
    elif normalized:
        status = "INCOMPLETE"
        deltas = None
    else:
        status = "NOT_AVAILABLE"
        deltas = None
    return {
        "schema_version": "tcw.comparison-summary/v0.1",
        "observation_id": observation_id,
        "normalization_algorithm": "tcw-markdown-normalize-v1",
        "source": {
            "sha256": source["sha256"],
            "media_type": source["media_type"],
            "fixture_id": source.get("fixture_id"),
        },
        "anchors": anchors,
        "status": status,
        "views": views,
        "deltas": deltas,
    }
