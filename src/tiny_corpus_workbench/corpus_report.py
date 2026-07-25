"""Deterministic offline HTML rendering for v0.4 corpus runs."""

from __future__ import annotations

from html import escape
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from tiny_corpus_workbench.comparison import NUMERIC_METRICS


STYLES_CSS = """\
:root {
  color-scheme: light dark;
  font-family: system-ui, sans-serif;
  line-height: 1.5;
}
body {
  margin: 0 auto;
  max-width: 76rem;
  padding: 1.5rem;
}
h1, h2, h3 { line-height: 1.2; }
nav ul {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem 1.25rem;
  list-style: none;
  padding: 0;
}
table {
  border-collapse: collapse;
  display: block;
  margin-block: 1rem;
  overflow-x: auto;
  width: 100%;
}
th, td {
  border: 1px solid currentColor;
  padding: .4rem .6rem;
  text-align: left;
  vertical-align: top;
}
th { background: color-mix(in srgb, CanvasText 10%, Canvas); }
code { overflow-wrap: anywhere; }
.status-complete { color: #147d36; font-weight: 700; }
.status-partial { color: #9a6700; font-weight: 700; }
.status-failed { color: #cf222e; font-weight: 700; }
.muted { opacity: .75; }
"""


def _text(value: Any) -> str:
    return escape(str(value), quote=True)


def _anchor(value: str) -> str:
    safe = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value
    )
    return "-".join(part for part in safe.split("-") if part) or "item"


def _url_path(value: str) -> str:
    """Encode a stored safe POSIX path without changing path separators."""

    path = PurePosixPath(value)
    return "/".join(quote(part, safe="") for part in path.parts)


def _link(path: str, label: str) -> str:
    return f'<a href="{_text(_url_path(path))}">{_text(label)}</a>'


def _nested_root(descriptor: dict[str, Any] | None) -> str | None:
    if not descriptor:
        return None
    path = PurePosixPath(descriptor["path"])
    return (PurePosixPath("..") / path.parent).as_posix()


def _member_links(
    member: dict[str, Any],
    comparison: dict[str, Any],
) -> str:
    links: list[str] = []
    observation_root = _nested_root(member["observation"]["manifest"])
    if observation_root is not None:
        links.extend(
            [
                _link(f"{observation_root}/manifest.json", "observation"),
                _link(f"{observation_root}/comparison.json", "comparison"),
            ]
        )
        if comparison["docling"] is not None:
            links.extend(
                [
                    _link(
                        f"{observation_root}/docling/document.json",
                        "Docling JSON",
                    ),
                    _link(
                        f"{observation_root}/docling/document.md",
                        "Docling Markdown",
                    ),
                ]
            )
        if comparison["markitdown"] is not None:
            links.append(
                _link(
                    f"{observation_root}/markitdown/document.md",
                    "MarkItDown",
                )
            )
    diagnosis_root = _nested_root(member["diagnosis"]["manifest"])
    if diagnosis_root is not None:
        links.extend(
            [
                _link(
                    f"{diagnosis_root}/diagnosis-manifest.json",
                    "diagnosis",
                ),
                _link(f"{diagnosis_root}/findings.json", "findings"),
                _link(f"{diagnosis_root}/report.md", "diagnosis report"),
            ]
        )
    return " · ".join(links) if links else '<span class="muted">None</span>'


def _revision_links(revision: dict[str, Any]) -> str:
    refinement = revision["bundle_paths"]["refinement"].rstrip("/")
    return " · ".join(
        [
            _link(
                f"{refinement}/refinement-manifest.json",
                "refinement",
            ),
            _link(f"{refinement}/decision.json", "decision"),
            _link(f"{refinement}/transformation.json", "transformation"),
            _link(f"{refinement}/history.json", "history"),
            _link(
                f"{refinement}/prepared/document.json",
                "prepared document",
            ),
        ]
    )


def _comparison_cells(comparison: dict[str, Any]) -> str:
    def cells(view: dict[str, Any] | None) -> str:
        if view is None:
            return "".join("<td>—</td>" for _ in NUMERIC_METRICS)
        return "".join(
            f"<td>{int(view[name])}</td>" for name in NUMERIC_METRICS
        )

    return (
        cells(comparison["docling"])
        + cells(comparison["markitdown"])
    )


def render_report(
    *,
    title: str,
    summary: dict[str, Any],
    members: list[dict[str, Any]],
    revisions: list[dict[str, Any]],
) -> bytes:
    """Render one source-text-free, script-free, deterministic HTML report."""

    formats = ("pdf", "docx", "md", "txt")
    families = sorted({member["family"] for member in members})
    member_lookup = {
        (member["family"], member["format"]): member for member in members
    }
    status_class = f"status-{summary['status'].lower()}"
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{_text(title)} — Corpus inspection</title>",
        '<link rel="stylesheet" href="styles.css">',
        "</head>",
        "<body>",
        "<header>",
        f"<h1>{_text(title)}</h1>",
        (
            f'<p>Corpus <code>{_text(summary["corpus_id"])}</code> · '
            f'Snapshot <code>{_text(summary["snapshot_id"])}</code></p>'
        ),
        (
            f'<p class="{status_class}">Completion status: '
            f'{_text(summary["status"])}</p>'
        ),
        "</header>",
        '<nav aria-label="Report sections"><ul>',
        '<li><a href="#overview">Overview</a></li>',
        '<li><a href="#matrix">Corpus matrix</a></li>',
        '<li><a href="#extractors">Extractor comparisons</a></li>',
        '<li><a href="#findings">Findings</a></li>',
        '<li><a href="#revisions">Revisions</a></li>',
        '<li><a href="#integrity">Incomplete and integrity</a></li>',
        "</ul></nav>",
        '<main id="overview">',
        "<h2>Overview</h2>",
        "<table><thead><tr><th>Members</th><th>Complete</th>"
        "<th>Partial</th><th>Failed</th><th>Findings</th>"
        "<th>Revisions</th></tr></thead><tbody><tr>",
        (
            f'<td>{summary["totals"]["member_count"]}</td>'
            f'<td>{summary["totals"]["complete"]}</td>'
            f'<td>{summary["totals"]["partial"]}</td>'
            f'<td>{summary["totals"]["failed"]}</td>'
            f'<td>{summary["totals"]["finding_count"]}</td>'
            f'<td>{summary["totals"]["revision_count"]}</td>'
        ),
        "</tr></tbody></table>",
        '<section id="matrix">',
        "<h2>Family × format corpus matrix</h2>",
        "<table><thead><tr><th>Family</th>",
        *(f"<th>{_text(format_name.upper())}</th>" for format_name in formats),
        "</tr></thead><tbody>",
    ]
    for family in families:
        lines.append(f"<tr><th>{_text(family)}</th>")
        for format_name in formats:
            member = member_lookup.get((family, format_name))
            if member is None:
                lines.append("<td>—</td>")
            else:
                lines.append(
                    f'<td><a href="#member-{_anchor(member["member_id"])}">'
                    f'{_text(member["member_id"])}</a><br>'
                    f'{_text(member["status"])}</td>'
                )
        lines.append("</tr>")
    lines.extend(
        [
            "</tbody></table>",
            "</section>",
            '<section id="extractors">',
            "<h2>Extractor comparisons</h2>",
            "<table><thead>",
            "<tr><th rowspan=\"2\">Member</th><th rowspan=\"2\">Status</th>"
            f'<th colspan="{len(NUMERIC_METRICS)}">Docling</th>'
            f'<th colspan="{len(NUMERIC_METRICS)}">MarkItDown</th>'
            '<th rowspan="2">Evidence</th></tr>',
            "<tr>"
            + "".join(
                f"<th>{_text(name.replace('_', ' '))}</th>"
                for name in NUMERIC_METRICS * 2
            )
            + "</tr></thead><tbody>",
        ]
    )
    comparisons = {
        item["member_id"]: item for item in summary["comparisons"]
    }
    for member in members:
        comparison = comparisons[member["member_id"]]
        lines.extend(
            [
                f'<tr id="member-{_anchor(member["member_id"])}">',
                f"<th>{_text(member['member_id'])}</th>",
                f"<td>{_text(comparison['status'])}</td>",
                _comparison_cells(comparison),
                f"<td>{_member_links(member, comparison)}</td>",
                "</tr>",
            ]
        )
    lines.extend(
        [
            "</tbody></table>",
            "</section>",
            '<section id="findings">',
            "<h2>Findings by rule and severity</h2>",
            "<table><thead><tr><th>Rule</th><th>Severity</th>"
            "<th>Family</th><th>Format</th><th>Findings</th>"
            "<th>Affected members</th></tr></thead><tbody>",
        ]
    )
    if summary["findings"]:
        for finding in summary["findings"]:
            lines.append(
                "<tr>"
                f"<td>{_text(finding['rule_id'])}</td>"
                f"<td>{_text(finding['severity'])}</td>"
                f"<td>{_text(finding['family'])}</td>"
                f"<td>{_text(finding['format'])}</td>"
                f"<td>{finding['finding_count']}</td>"
                f"<td>{finding['affected_member_count']}</td>"
                "</tr>"
            )
    else:
        lines.append('<tr><td colspan="6">No findings.</td></tr>')
    lines.extend(
        [
            "</tbody></table>",
            "</section>",
            '<section id="revisions">',
            "<h2>Revision and transformation history</h2>",
            "<table><thead><tr><th>Member</th><th>Finding</th>"
            "<th>Refiner</th><th>Chain length</th><th>Affected references</th>"
            "<th>Before hash</th><th>After hash</th><th>Evidence</th>"
            "</tr></thead><tbody>",
        ]
    )
    revision_summary = {
        item["revision_id"]: item for item in summary["revisions"]
    }
    if revisions:
        for revision in revisions:
            item = revision_summary[revision["revision_id"]]
            lines.append(
                "<tr>"
                f"<td>{_text(revision['member_id'])}</td>"
                f"<td>{_text(revision['finding_rule'])}</td>"
                f"<td>{_text(revision['refiner']['refiner_id'])}</td>"
                f"<td>{revision['chain_length']}</td>"
                f"<td>{revision['affected_reference_count']}</td>"
                f"<td><code>{_text(item['before_document_sha256'])}</code></td>"
                f"<td><code>{_text(item['after_document_sha256'])}</code></td>"
                f"<td>{_revision_links(revision)}</td>"
                "</tr>"
            )
    else:
        lines.append('<tr><td colspan="8">No revisions were listed.</td></tr>')
    lines.extend(
        [
            "</tbody></table>",
            "</section>",
            '<section id="integrity">',
            "<h2>Incomplete members and integrity</h2>",
            "<table><thead><tr><th>Member</th><th>Status</th>"
            "<th>Error code</th><th>Message</th></tr></thead><tbody>",
        ]
    )
    incomplete = [member for member in members if member["status"] != "COMPLETE"]
    if incomplete:
        for member in incomplete:
            error = member["error"] or {"code": "NONE", "message": "No error"}
            lines.append(
                "<tr>"
                f"<td>{_text(member['member_id'])}</td>"
                f"<td>{_text(member['status'])}</td>"
                f"<td>{_text(error['code'])}</td>"
                f"<td>{_text(error['message'])}</td>"
                "</tr>"
            )
    else:
        lines.append('<tr><td colspan="4">Every member is complete.</td></tr>')
    lines.extend(
        [
            "</tbody></table>",
            (
                "<p>Artifact hashes and nested verification records protect "
                "this local report from ordinary corruption. They are not "
                "signatures or trusted timestamps.</p>"
            ),
            (
                "<p>Revision links refer to explicitly supplied local records. "
                "Moving those records can break the links.</p>"
            ),
            "</section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_stylesheet() -> bytes:
    """Return the fixed local stylesheet bytes."""

    return STYLES_CSS.encode("utf-8")
