# Project Roadmap

This roadmap describes the major learning and product milestones for
`tiny-corpus-workbench`. It records the intended progression, not an active
implementation plan. Each milestone still needs a focused, approved plan
before product code is written.

The workbench starts with raw documents and ends with a trustworthy prepared
document revision. RAG is a typical downstream consumer of prepared documents,
but chunking, indexing, retrieval, generation, and related integration remain
outside this roadmap through v1.0.

## Milestone overview

| Version | Milestone | Primary outcome |
| --- | --- | --- |
| v0.0 | Planning Baseline | Establish the purpose, boundaries, decisions, and roadmap. |
| v0.1 | Extraction Observatory | Make extraction outputs comparable and inspectable. |
| v0.2 | Evidence-Based Diagnosis | Detect document-quality problems with concrete evidence. |
| v0.3 | Controlled Revisions | Apply approved, reversible refinements without losing history. |
| v0.4 | Corpus Inspection and Comparison | Inspect patterns across a small mixed-format corpus. |
| v0.5 | Local Visual Workbench | Explore artifacts and revisions through a local web interface. |
| v1.0 | Stable Workbench | Stabilize the workbench's local contracts and documentation. |

## v0.0 — Planning Baseline

Establish the project before implementation begins.

Deliverables:

- public project description and lifecycle boundary
- preserved brainstorming proposal and decision history
- agent-facing project guidance and current handoff snapshot
- versioned roadmap from the planning baseline through v1.0

Exit condition: the project direction is documented and no product milestone
is treated as active without a separate approved plan.

## v0.1 — Extraction Observatory

Build a local CLI for observing how two extraction paths represent the same
source documents.

Deliverables:

- Docling and MarkItDown extraction paths
- twelve project-owned or permissively licensed golden fixtures: three
  document families, each represented as PDF, DOCX, Markdown, and plain text
- source identity, media type, and content hash
- project-owned preparation manifest
- lossless `DoclingDocument` JSON
- Markdown serialized from `DoclingDocument`
- Markdown produced by MarkItDown
- deterministic comparison summary for the two extraction views

Exit condition: every fixture can be processed locally through a documented
CLI command, and its source identity and extraction artifacts can be inspected
without consulting hidden service state.

## v0.2 — Evidence-Based Diagnosis

Diagnose concrete quality problems without authorizing document changes.

Deliverables:

- eight deterministic diagnostic rules
- a stable `Finding` contract with identifiers, severity, evidence, affected
  document-item references, and rule provenance
- machine-readable findings stored with the preparation artifacts
- a human-readable Markdown inspection report

Exit condition: known problems in the golden fixtures produce repeatable,
evidence-backed findings, and clean cases avoid documented false positives.

## v0.3 — Controlled Revisions

Turn approved findings into new prepared revisions while preserving every
earlier artifact.

Deliverables:

- immutable source, raw extraction, and prepared-revision snapshots
- append-only transformation history with before-and-after hashes
- explicit requested, approved, rejected, and applied states
- reversible whitespace normalization
- reversible repeated-boilerplate removal
- reversible deterministic dehyphenation or hard-line-break repair

Exit condition: each applied refinement produces a new revision and can be
traced to its finding, decision, operation, and prior content.

## v0.4 — Corpus Inspection and Comparison

Move from inspecting one document at a time to understanding patterns across
the complete golden corpus.

Deliverables:

- corpus-level execution across the full fixture matrix
- summaries grouped by format, document family, extractor, rule, and severity
- comparison of findings and revisions across related fixtures
- static, offline HTML reports that link back to inspectable local artifacts

Exit condition: one local run produces a navigable corpus report without
requiring a long-running service.

## v0.5 — Local Visual Workbench

Add an interactive local view while retaining the same underlying preparation
and audit contracts.

Deliverables:

- framework-neutral application services shared with the CLI
- a loopback-only HTTP API
- a local browser interface for sources, extraction artifacts, findings,
  decisions, transformations, revisions, and comparisons

Exit condition: a user can inspect the end-to-end preparation history through
the browser without exposing the service beyond the local machine.

## v1.0 — Stable Workbench

Stabilize the local workbench as a coherent, documented learning tool.

Deliverables:

- stable CLI commands and exit behavior
- stable loopback HTTP API and artifact contracts
- explicit schema and dependency compatibility handling
- predictable errors for unsupported or incompatible inputs
- end-to-end documentation and continuous integration

Exit condition: the documented workflows and contracts are covered by tests,
work from a clean checkout, and do not depend on unrecorded local state.

## Deferred until after v1.0

The following are intentionally outside the roadmap through v1.0:

- OCR-heavy workflows
- chart and image understanding
- spreadsheet and presentation support
- DocLang
- public benchmark corpora
- PII-specific workflows
- hosted services
- a public Python API
- chunking, embeddings, indexing, retrieval, reranking, generation, RAG
  evaluation, and other RAG integration
