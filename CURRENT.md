# Handoff Snapshot

**Last updated:** 2026-07-21

This is an informational handoff, not a required agent workflow or taskboard.
Future work may use whichever sound engineering practices fit the task.

## Status

- The repository is initialized locally and on GitHub.
- The initial brainstorming verdict is preserved in `docs/proposal.md`.
- The major milestones from v0.0 through v1.0 are recorded in
  `docs/roadmap.md`.
- Milestone v0.1, Extraction Observatory, is active on
  `milestone/v0.1-extraction-observatory`.
- Its accepted implementation and review contract is
  `docs/plans/v0.1-extraction-observatory.md`.
- The initial `tcw observe` implementation, schemas, twelve deterministic CC0
  fixtures, tests, and user guide are present.
- The owner accepted a local-integrity amendment defining observations as
  application-immutable and locally tamper-evident, adding private source
  snapshots, PDF model stability checks, and read-only `tcw verify`.
- The owner further narrowed v0.1 `VERIFIED` to structural validity, artifact
  integrity, and explicitly derivable semantic consistency. Authenticity and
  future fingerprint/anchoring mechanisms remain outside v0.1.
- The accepted amendment is implemented locally: both adapters consume one
  owner-only source snapshot, PDF models are checked before and after
  extraction, persisted comparison bytes are inventoried, and the standalone
  verifier checks published observations plus opt-in provenance advisories.

## Document roles

- `AGENTS.md` contains instructions and reading order for coding agents.
- `CURRENT.md` is an informational snapshot for the next working session.
- `README.md` is the evolving public description of the project.
- `docs/proposal.md` preserves the agreed brainstorming verdict, rationale,
  research history, boundaries, and questions left open at that stage. It is
  not a live taskboard.
- `docs/roadmap.md` records the intended major-version progression. It does
  not activate a milestone or replace a milestone implementation plan.

## Settled boundary

The project starts with raw documents and ends with a trustworthy prepared
document revision. Its initial scope contains:

1. extraction adapters
2. `DoclingDocument` as the canonical working representation
3. evidence-based diagnosis and controlled refinement

Chunking, embeddings, indexing, retrieval, generation, and RAG evaluation are
downstream concerns and remain outside the initial project.

Original sources and raw extraction artifacts remain immutable. Diagnosis does
not authorize mutation, and interpretive refinements require explicit human
confirmation.

## Current milestone

Milestone v0.1 has been implemented according to
`docs/plans/v0.1-extraction-observatory.md`. The mandatory compatibility spike
passed with CPython 3.12 and the exact lock: four formats through both
extractors, four reloadable Docling JSON artifacts, offline PDF conversion from
the prefetched `layout` and `tableformer` files, and no observation-time
network access. The emitted Docling schema identity is `DoclingDocument`
version `1.10.0`.

Implementation and local-integrity amendment verification on 2026-07-21:

- fast unit suite: 68 tests passed
- full suite: 71 tests passed, including the mandatory spike, all twelve
  fixtures through both extractors, same-lock JSON reload, expected table
  counts, anchor preservation, network denial, and byte-identical comparison
  summaries across isolated output roots
- deterministic fixture regeneration and registry verification passed both
  locally and in a separate byte-identical `core.autocrlf=true` checkout
- staged publication inventory checks passed for missing, changed, replaced,
  symlinked, and unexpected content while preserving prior runs
- source snapshot, extractor preflight, PDF model-stability, neutral
  concurrency, and verifier corruption/advisory tests passed
- schema-valid provenance/status/artifact mutations are rejected as broken,
  and equivalent model inventories match across different absolute roots
- RFC 3339 timestamps, durations, sanitized errors, and persisted Docling
  schema identity are structurally and semantically verified; valid changes to
  non-derivable metadata remain explicitly outside authenticity claims
- observation preflight covers CPython 3.12 and every Docling serialization API
  used, while non-PDF model advisories remain `NOT_APPLICABLE` for any supplied
  model path
- the exact three-package runtime mapping is shared by observation and
  verification; changed, missing, and unexpected dependency entries are broken
- malformed decoded manifest/comparison shapes complete as broken reports, and
  staged evidence is schema-valid before publication; empty text is rejected
- CLI import is independent of `jsonschema`; guarded lazy verification/schema
  bootstrap failures use runtime exit 6 without stdout or publication
- schema validation, compile check, `git diff --check`, and the documented
  manual PDF observation plus `tcw verify` checks passed

The accepted v0.1 implementation and final Section 13.8/13.13 clarification are
complete locally. The next action is a fresh milestone review. The CLI binary
remains `tcw`.

No repository-wide agent workflow is automatically activated. The current
milestone is being run through the explicitly requested plan-build-review
workflow and remains subject to its review and publication gates.
