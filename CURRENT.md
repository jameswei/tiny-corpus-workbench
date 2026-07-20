# Handoff Snapshot

**Last updated:** 2026-07-20

This is an informational handoff, not a required agent workflow or taskboard.
Future work may use whichever sound engineering practices fit the task.

## Status

- The repository is initialized locally and on GitHub.
- The initial brainstorming verdict is preserved in `docs/proposal.md`.
- The major milestones from v0.0 through v1.0 are recorded in
  `docs/roadmap.md`.
- No implementation plan or milestone is active.
- No product source code has been written.

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

## Recommended next session

Prepare a decision-complete plan for v0.1, Extraction Observatory, before
adding product code or runtime dependencies. The roadmap fixes the milestone's
direction; its implementation plan still needs to define:

- the identities and licensing records for the twelve golden fixtures
- exact CLI commands, exit behavior, and artifact directory layout
- the preparation manifest and comparison-summary schemas
- the pinned `DoclingDocument` compatibility boundary
- expected outputs and acceptance checks for every fixture

No agent workflow is automatically activated by this repository. Confirm the
v0.1 plan with the project owner before implementation begins.
