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
    Path("docs/plans/v0.5-learning-first-correction-ledger.md"),
    Path("docs/plans/v0.5-pre-release-amendment-ledger.md"),
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
README_REFINEMENT_ROW = (
    "| Draft one refinement proposal | `corpus draft-refinement` |"
)
STALE_README_REFINEMENT_PHRASE = "Draft one decision"
STALE_CURRENT_CLOSEOUT_PHRASE = "Closeout evidence must be established externally"
STALE_LEDGER_CLOSEOUT_PHRASE = "Remaining closeout gates:"
STALE_RELEASE_READINESS_STATUS = "| Release readiness | `not started` |"


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


def _require_table_row(
    path: Path,
    text: str,
    label: str,
    facts: tuple[tuple[str, str], ...],
) -> None:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if cells and cells[0] == label:
            rows.append(line)
    if len(rows) != 1:
        raise PolicyError(
            f"{path.as_posix()}: expected exactly one {label} evidence row"
        )
    row = rows[0]
    for phrase, topic in facts:
        exact_phrase = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(phrase)}(?![A-Za-z0-9_-])",
            flags=re.IGNORECASE,
        )
        if exact_phrase.search(row) is None:
            raise PolicyError(
                f"{path.as_posix()}: {label} row missing associated {topic}"
            )


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
            r"\btag\s+and\s+github\s+release:\s*authorized\b"
            r"|\btag\s+or\s+github\s+release\s+(?:is|are)\s+authorized\b",
            "release authorization claim",
        ),
        (
            r"\bverification-result\s+json\s+schemas?\s+"
            r"(?:are|remain|exist|apply)\b",
            "verification-result schema claim",
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


def _require_readme_refinement_wording(text: str) -> None:
    path = Path("README.md")
    if STALE_README_REFINEMENT_PHRASE.casefold() in text.casefold():
        raise PolicyError(f"{path.as_posix()}: stale refinement draft wording")
    _require(
        path,
        text,
        README_REFINEMENT_ROW,
        "refinement proposal command wording",
    )


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


def _reject_stale_closeout_status(current: str, amendment_ledger: str) -> None:
    if STALE_CURRENT_CLOSEOUT_PHRASE.casefold() in current.casefold():
        raise PolicyError("CURRENT.md: stale closeout evidence status")
    if STALE_LEDGER_CLOSEOUT_PHRASE.casefold() in amendment_ledger.casefold():
        raise PolicyError(
            "docs/plans/v0.5-pre-release-amendment-ledger.md: "
            "stale remaining closeout gates"
        )
    if STALE_RELEASE_READINESS_STATUS.casefold() in amendment_ledger.casefold():
        raise PolicyError(
            "docs/plans/v0.5-pre-release-amendment-ledger.md: "
            "stale release-readiness status"
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

    correction_ledger_path = Path(
        "docs/plans/v0.5-learning-first-correction-ledger.md"
    )
    correction_ledger = documents[correction_ledger_path]
    _require(
        correction_ledger_path,
        correction_ledger,
        "Overall correction status: `complete`",
        "complete correction status",
    )
    _require_table_row(
        correction_ledger_path,
        correction_ledger,
        "PR 9 — Rewrite current documentation and close the correction",
        (
            (
                "`452fcd2d8ca39bbb5b92d20d1a7996588baf8ad5` | `complete` |",
                "complete status",
            ),
            (
                "| `PASS` | `9780d87faf1337e4c8acf28ea2e704b39fcb402e`",
                "independent verdict",
            ),
            (
                "`9780d87faf1337e4c8acf28ea2e704b39fcb402e`",
                "reviewed head",
            ),
            (
                "`8b04885a9471091cdfce17560e395a2d103d2806`",
                "squash merge",
            ),
            ("PR #26", "PR number"),
            ("PR CI run `30376868533` passed", "PR CI"),
            ("CI run `30377410412` passed", "post-main CI"),
            ("Pages run `30377410609` passed", "post-main Pages"),
        ),
    )

    amendment_ledger_path = Path("docs/plans/v0.5-pre-release-amendment-ledger.md")
    amendment_ledger = documents[amendment_ledger_path]
    _reject_stale_closeout_status(current, amendment_ledger)
    for phrase, topic in (
        (
            "Overall implementation and integration status: `complete`",
            "complete amendment status",
        ),
        ("Tag and GitHub Release: `not authorized`", "release authorization limit"),
    ):
        _require(amendment_ledger_path, amendment_ledger, phrase, topic)
    for label, facts in (
        (
            "Establishment PR",
            (
                ("`complete` | PR #27;", "complete status and PR number"),
                (
                    "reviewed head `729bb89d5ad82db09851c5602a985e7b9d4f7d5c`",
                    "reviewed head",
                ),
                (
                    "squash merge `bb4341f6a995a702a89f9bfb6f0873c4671f06f6`",
                    "squash merge",
                ),
                ("PR CI `30452529395` passed", "PR CI"),
                ("post-main CI `30453075126` passed", "post-main CI"),
                ("post-main Pages `30453075891` passed", "post-main Pages"),
            ),
        ),
        (
            "PR A — Transient typed verification results",
            (
                ("`complete` | PR #28;", "complete status and PR number"),
                (
                    "reviewed head `e256fe20897c20399ccbf6a2bb9fad8acfdd43cc`",
                    "reviewed head",
                ),
                (
                    "squash merge `a829991ded2e6203122e428a990f9893e4c0b41d`",
                    "squash merge",
                ),
                ("PR CI `30457725350` passed", "PR CI"),
                ("post-main CI `30460335836` passed", "post-main CI"),
                ("post-main Pages `30460335643` passed", "post-main Pages"),
            ),
        ),
        (
            "PR B — Proposal-only refinement and one persisted authority",
            (
                ("`complete` | PR #29;", "complete status and PR number"),
                (
                    "reviewed head `ebbe06a20917b2a0d8f16433a09b009ec37ff8b6`",
                    "reviewed head",
                ),
                (
                    "squash merge `c03b70ed04dc07f9d5f94e53ca944814ec61f08d`",
                    "squash merge",
                ),
                ("exact-head PR CI `30468716510` passed", "exact-head PR CI"),
                ("post-main CI `30470529695` passed", "post-main CI"),
                ("post-main Pages `30470529661` passed", "post-main Pages"),
            ),
        ),
        (
            "Narrow corrective PR",
            (
                ("`complete` | PR #30;", "complete status and PR number"),
                (
                    "reviewed head `59fc1df7ef26f914bc828df6a6bd3edc8d3298e0`",
                    "reviewed head",
                ),
                (
                    "squash merge `c80842cec401d6110ad60ccac696cebb1028d640`",
                    "squash merge",
                ),
                ("PR CI `30472255094` passed", "PR CI"),
                ("post-main CI `30472763206` passed", "post-main CI"),
                ("post-main Pages `30472763290` passed", "post-main Pages"),
            ),
        ),
        (
            "Combined technical integration review",
            (
                (
                    "`complete` | Fresh independent reviewer returned `PASS`",
                    "complete status and verdict",
                ),
                ("zero findings", "findings"),
                (
                    "exact base `8b04885a9471091cdfce17560e395a2d103d2806`",
                    "base",
                ),
                (
                    "exact candidate `c80842cec401d6110ad60ccac696cebb1028d640`",
                    "candidate",
                ),
                (
                    "All 169 focused unit tests and 8 integration tests passed",
                    "test result",
                ),
                (
                    "policy, assets, site, compile, schema, removal, stale-token, "
                    "diff, and clean checks",
                    "technical checks",
                ),
                (
                    "Hosted CI and Pages were confirmed at the exact head",
                    "hosted exact-head checks",
                ),
                ("No review issue remains unresolved", "review resolution"),
            ),
        ),
        (
            "Closeout",
            (
                ("`complete` | PR #31;", "complete status and PR number"),
                (
                    "reviewed head `5e5a3772a85b44111121ff057f2971db421df1a4`",
                    "reviewed head",
                ),
                (
                    "fresh independent reviewer returned `PASS` with zero findings",
                    "independent verdict",
                ),
                (
                    "exact-head PR CI `30476653488` passed Fast and Full",
                    "exact-head PR CI",
                ),
                (
                    "squash merge `40b2083de70cfe9f7ad2dfa2cea8435b377a5ecc`",
                    "squash merge",
                ),
                (
                    "post-main CI `30477806685` passed Fast and Full at the exact squash",
                    "post-main CI",
                ),
                (
                    "post-main Pages `30477806662` passed build and deploy at the "
                    "exact squash",
                    "post-main Pages",
                ),
                (
                    "owner-approved Pages interpretation recorded that exact-head "
                    "Fast ran `validate_site.py` because Pages jobs are main-only",
                    "pre-merge Pages interpretation",
                ),
            ),
        ),
        (
            "Release readiness",
            (
                ("`external release gate`", "timeless external status"),
                (
                    "The current external release-readiness verdict governs",
                    "current external verdict boundary",
                ),
                (
                    "fresh zero-finding `PASS` for the exact current `main` candidate",
                    "exact-candidate release-readiness review",
                ),
                (
                    "separate owner authorization for that exact SHA",
                    "exact-SHA release authorization",
                ),
            ),
        ),
    ):
        _require_table_row(amendment_ledger_path, amendment_ledger, label, facts)

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
    for phrase, topic in (
        ("four verifier outputs", "verifier output count"),
        ("dependency-free frozen Python dataclasses", "transient typed results"),
        ("deterministic compact JSON on standard output", "verifier stdout"),
        ("no verification-result JSON Schemas", "removed verifier schemas"),
        ("11 retained self-contained JSON Schemas", "retained schema count"),
        ("local `$defs`", "local schema definitions"),
        ("no cross-file reference", "self-contained schemas"),
        ("canonical proposal-only `proposal.json`", "proposal-only draft"),
        ("Inspect this file, but do not edit it", "proposal inspection"),
        ("exactly one of `--approve` or `--reject`", "exclusive decision flags"),
        ("together with the diagnosis and base", "resolution inputs"),
        (
            "manifest decision is the only persisted structured authority",
            "manifest decision authority",
        ),
        ("There is no actor, note, manifest status, or `decision.json`", "removed decision fields"),
        ("approved refinement contains", "approved artifact behavior"),
        ("rejected refinement contains", "rejected artifact behavior"),
        ("report is derived from the manifest decision", "report derivation"),
        ("only fully verified approved revisions", "corpus admission"),
        ("read-only local internal bridge", "Workbench boundary"),
        ("derives its views from admitted records", "Workbench view derivation"),
        ("no migration or cross-version reader", "current-format-only policy"),
        ("hosted API", "hosted API limit"),
        ("v0.5 remains unreleased", "unreleased close"),
    ):
        _require(Path("docs/releases/v0.5.0.md"), release, phrase, topic)
    readme = usage_documents[Path("README.md")]
    _require_readme_refinement_wording(readme)
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
