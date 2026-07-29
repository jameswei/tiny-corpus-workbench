#!/usr/bin/env python3
"""Verify semantic policy markers in current project documents."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


POLICY_PATHS = (
    Path("CURRENT.md"),
    Path("docs/roadmap.md"),
    Path("docs/releases/v0.5.0.md"),
)
ACTIVE_USAGE_PATHS = (
    Path("README.md"),
    Path("docs/controlled-revisions.md"),
    Path("docs/corpus-inspection-comparison.md"),
    Path("docs/evidence-based-diagnosis.md"),
    Path("docs/extraction-observatory.md"),
    Path("docs/local-visual-workbench.md"),
    Path("docs/releases/v0.5.0.md"),
    Path("fixtures/README.md"),
    Path("learning/README.md"),
    Path("learning/v0.1-extraction-observatory.md"),
    Path("learning/v0.2-evidence-based-diagnosis.md"),
    Path("learning/v0.3-controlled-revisions.md"),
    Path("learning/v0.4-corpus-inspection-comparison.md"),
    Path("learning/v0.5-local-visual-workbench.md"),
    Path("site/index.html"),
)
HISTORICAL_PATHS = (
    "docs/plans/v0.5-local-visual-workbench.md",
    "docs/plans/v0.5-local-visual-workbench-ledger.md",
)


class PolicyError(ValueError):
    """A current document contradicts the approved policy."""


def _read(root: Path, relative: Path) -> str:
    path = root / relative
    try:
        return path.read_text("utf-8")
    except (OSError, UnicodeError) as error:
        raise PolicyError(f"{relative.as_posix()}: unreadable policy surface") from error


def _require(path: Path, text: str, phrase: str, topic: str) -> None:
    if phrase.casefold() not in text.casefold():
        raise PolicyError(f"{path.as_posix()}: missing {topic} policy")


def _reject_claims(path: Path, text: str) -> None:
    claim_patterns = (
        (
            r"\b(?:one\s+)?unified\s+(?:public\s+)?schema\s+baseline\b"
            r"|\bpublic\s+(?:json\s+)?schema\s+(?:baseline|contract)\b",
            "public schema promise",
        ),
        (
            r"\b(?:stable|public)\s+(?:loopback\s+)?http\s+api\b"
            r"|\bloopback\s+(?:http\s+)?api\s+is\s+(?:stable|public)\b",
            "public loopback API promise",
        ),
        (
            r"\bstatus:\s*released\b|\bv0\.5(?:\.0)?\s+is\s+(?:now\s+)?released\b",
            "released v0.5 claim",
        ),
        (
            r"\b(?:ships?|provides?|publishes?|delivers?|includes?)\s+"
            r"(?:a\s+|prebuilt\s+)*(?:binary|binaries|docker\s+images?|"
            r"packages?\s+on\s+(?:a\s+)?registry|container-registry\s+image)\b",
            "binary or registry deliverable",
        ),
        (
            r"\bstable\s+artifact\s+contracts?\b"
            r"|\bdependency\s+compatibility\s+(?:handling|promise|contract)\b",
            "artifact or dependency compatibility promise",
        ),
    )
    for pattern, topic in claim_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise PolicyError(f"{path.as_posix()}: prohibited {topic}")


def _reject_stale_usage(path: Path, text: str) -> None:
    if re.search(r"\btcw\b|\binspect-corpus\b", text):
        raise PolicyError(f"{path.as_posix()}: stale CLI command")


def _require_historical_links(text: str) -> None:
    for historical_path in HISTORICAL_PATHS:
        link = re.search(
            rf"\[[^\]]+\]\({re.escape(historical_path)}\)",
            text,
            flags=re.IGNORECASE,
        )
        if link is None:
            raise PolicyError(
                f"CURRENT.md: missing historical link for {historical_path}"
            )
        context = text[max(0, link.start() - 120) : link.end() + 240]
        if "historical" not in context.casefold() or re.search(
            r"\b(?:active|current|binding)\s+(?:plan|ledger|contract|record)",
            context,
            flags=re.IGNORECASE,
        ):
            raise PolicyError(
                f"CURRENT.md: misclassified historical path {historical_path}"
            )


def verify(root: Path) -> None:
    documents = {path: _read(root, path) for path in POLICY_PATHS}
    usage_documents = {path: _read(root, path) for path in ACTIVE_USAGE_PATHS}
    for path, text in documents.items():
        _reject_claims(path, text)
    for path, text in usage_documents.items():
        _reject_stale_usage(path, text)

    current = documents[Path("CURRENT.md")]
    current_path = Path("CURRENT.md")
    _require(current_path, current, "v0.5 is unreleased", "release pause")
    _require(current_path, current, "pull/13", "merged PR")
    _require(current_path, current, "pull/17", "merged PR")
    _require(
        current_path,
        current,
        "docs/plans/v0.5-learning-first-correction.md",
        "correction plan link",
    )
    _require(
        current_path,
        current,
        "docs/plans/v0.5-learning-first-correction-ledger.md",
        "correction ledger link",
    )
    _require_historical_links(current)

    roadmap = documents[Path("docs/roadmap.md")]
    _require(
        Path("docs/roadmap.md"),
        roadmap,
        "document-preparation lifecycle",
        "lifecycle",
    )
    _require(
        Path("docs/roadmap.md"),
        roadmap,
        "internal loopback HTTP bridge",
        "internal bridge",
    )

    release = documents[Path("docs/releases/v0.5.0.md")]
    _require(
        Path("docs/releases/v0.5.0.md"),
        release,
        "Unreleased Draft",
        "draft status",
    )
    _require(Path("docs/releases/v0.5.0.md"), release, "source-only", "distribution")
    _require(
        Path("docs/releases/v0.5.0.md"),
        release,
        "not a public or stable API",
        "internal bridge",
    )
    readme = usage_documents[Path("README.md")]
    _require(
        Path("README.md"),
        readme,
        "distributed as source from this repository",
        "source repository distribution",
    )
    _require(
        Path("README.md"),
        readme,
        "prebuilt binaries",
        "prebuilt binary limit",
    )
    _require(Path("README.md"), readme, "does not ship", "delivery limit")

    controlled = usage_documents[Path("docs/controlled-revisions.md")]
    for phrase, topic in (
        ("Inspect `proposal.json`. Do not edit it.", "proposal inspection"),
        ("--approve", "approval flag"),
        ("--reject", "rejection flag"),
        ("only machine-authoritative persisted decision field", "decision authority"),
        ("path: proposal.json", "proposal path"),
        ("role: refinement-proposal", "proposal role"),
        ("media_type: application/json", "proposal media type"),
        ("An approved publication contains", "approved inventory"),
        ("A rejected publication contains", "rejected inventory"),
        ("non-authoritative human rendering", "derived report"),
        ("Only a record with manifest decision `APPROVED`", "corpus eligibility"),
    ):
        _require(Path("docs/controlled-revisions.md"), controlled, phrase, topic)

    corpus = usage_documents[Path("docs/corpus-inspection-comparison.md")]
    _require(
        Path("docs/corpus-inspection-comparison.md"),
        corpus,
        "does not copy the approval decision",
        "corpus decision isolation",
    )

    workbench = usage_documents[Path("docs/local-visual-workbench.md")]
    _require(
        Path("docs/local-visual-workbench.md"),
        workbench,
        "only from `refinement-manifest.json.decision`",
        "workbench decision derivation",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify semantic policy in current project documents."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository tree to inspect (default: current directory)",
    )
    args = parser.parse_args(argv)
    try:
        verify(args.root)
    except PolicyError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
