# Project Roadmap

This roadmap describes the major learning and product milestones for
`tiny-corpus-workbench`. It records the intended progression, not an active
implementation plan. Each milestone still needs a focused, approved plan
before product code is written.

The workbench starts with raw documents and ends with a trustworthy prepared
document revision. RAG is a typical downstream consumer of prepared documents,
but chunking, indexing, retrieval, generation, and related integration remain
outside this roadmap through v1.0.

Each milestone keeps the lifecycle inspectable with current, project-owned
record shapes. These internal shapes can change as the learning tool improves.
Git tags preserve earlier implementations; the current project does not
promise cross-version readers or migrations.

The v0.6 through v0.9 sequence deliberately splits the next Workbench
direction into bounded, independently useful increments. It is not one large
Webapp implementation milestone.

The current learning curriculum follows lifecycle topics rather than one
lesson for each product milestone.

## Milestone overview

| Version | Milestone | Primary outcome |
| --- | --- | --- |
| v0.0 | Planning Baseline | Establish the purpose, boundaries, decisions, and roadmap. |
| v0.1 | Extraction Observatory | Make extraction outputs comparable and inspectable. |
| v0.2 | Evidence-Based Diagnosis | Detect document-quality problems with concrete evidence. |
| v0.3 | Controlled Revisions | Apply approved, reversible refinements without losing history. |
| v0.4 | Corpus Inspection and Comparison | Inspect patterns across a small mixed-format corpus. |
| v0.5 | Local Visual Workbench | Explore artifacts and revisions through a local web interface. |
| v0.6 | Shared Workbench Workspace | Keep CLI-produced records available to one independently running, refreshable Workbench. |
| v0.7 | Web Observation Workflow | Observe one guided or uploaded document through the browser. |
| v0.8 | Interactive Document Lifecycle | Diagnose and explicitly resolve one document refinement through the browser. |
| v0.9 | Workbench UI/UX Redesign | Present the document lifecycle through a focused, bilingual learning interface. |
| v1.0 | Coherent Workbench | Present the complete learning workflow through clear local interfaces. |

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

Add an interactive local view over the document-preparation lifecycle.

Deliverables:

- application services shared with the CLI
- an internal loopback HTTP bridge for the bundled interface
- a local browser interface for sources, extraction artifacts, findings,
  decisions, transformations, revisions, and comparisons

Exit condition: a user can inspect the end-to-end preparation history through
the browser without exposing the service beyond the local machine.

## v0.6 — Shared Workbench Workspace

Replace the startup-only record list with one explicit local workspace shared
by the CLI and Workbench.

Deliverables:

- a small workspace layout for inputs and current record families
- Workbench startup without requiring an existing record
- bounded discovery of complete records inside that workspace
- manual refresh of the current record catalog
- atomic replacement of the current in-memory projection
- clear empty, loading, invalid-record, and refresh-failure states

Exit condition: a user can keep the Workbench running, publish a record with
the CLI, refresh the browser, and inspect the new record without restarting the
server or resupplying record paths.

This increment does not add browser uploads, workflow execution, filesystem
watching, Docker delivery, or a public API.

## v0.7 — Web Observation Workflow

Make observation the first document-preparation operation available through
the browser.

Deliverables:

- one guided project fixture and one local document-upload path
- a lightweight in-memory job model with queued, running, completed, and
  failed states
- stage-level observation feedback without invented percentage progress
- direct reuse of the same observation application service as the CLI
- automatic publication into and refresh of the shared workspace
- clear handling of unsupported inputs, extraction failures, and missing PDF
  models

Exit condition: a learner can select the guided Markdown example or upload one
supported document, run observation, and inspect the two extraction views and
canonical evidence without using the CLI. The CLI remains an equivalent
interface over the same observation application behavior.

This increment does not add diagnosis, refinement, corpus execution,
persistent jobs, Docker delivery, or a public API.

## v0.8 — Interactive Document Lifecycle

Complete the single-document preparation lifecycle through the browser while
preserving explicit human authority.

Deliverables:

- observation verification and evidence-based diagnosis
- finding views that distinguish detected conditions from available refiners
- proposal creation for the supported deterministic refiners
- readable before-and-after proposal evidence without manual JSON editing
- mutually exclusive approve and reject actions
- immutable refinement publication, verification, revision history, and
  reversibility views
- CLI and Workbench interoperability over the same published workspace records

Exit condition: a learner can use the guided whitespace example to observe,
verify, diagnose, inspect the D009 evidence, create a proposal, explicitly
approve or reject it, and inspect the resulting verification and revision
history. Diagnosis never authorizes mutation, rejection creates no revision,
and approval never overwrites earlier evidence.

This increment remains single-document focused. It does not add browser-driven
corpus execution, automatic repair, persistent jobs, Docker delivery, hosted
services, authentication, or a public API.

## v0.9 — Workbench UI/UX Redesign

Redesign and polish the functional v0.8.1 Workbench without consuming the
v1.0 outcome.

Deliverables:

- one stable shell with Documents and Corpora navigation
- learner-question stages and numbered preparation rounds
- stage-scoped Summary, Evidence, and Artifacts inspection
- guidance that separates findings, proposals, and explicit decisions
- shared readable comparisons and full-width artifact readers
- compact visible hashes with full values available on demand
- English and Simplified Chinese Workbench UI
- a canonical rule reference derived from the rule and refiner registries
- clear refresh, failure, reload, and restart behavior

Exit condition: a learner can follow Observe, Diagnose, Refine, and Revision
without navigating a flat record dashboard. The interface keeps evidence
available, preserves explicit human authority, and remains local and
source-only.

This milestone changes the bundled human interface. It does not add new rules,
refiners, persisted schemas, migrations, CLI behavior, browser corpus
execution, hosted processing, or a public API.

## v1.0 — Coherent Workbench

Complete the local workbench as a coherent, documented learning tool.

Deliverables:

- a clear CLI for the complete document lifecycle
- a bundled local browser interface over the same application behavior
- understandable current record roles and integrity checks
- predictable errors for invalid current inputs
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
