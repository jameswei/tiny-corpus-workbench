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

## Active milestone

Implement v0.1 according to `docs/plans/v0.1-extraction-observatory.md`. The
first implementation gate is the mandatory dependency and extractor
compatibility spike defined there. If it fails, stop rather than weakening the
accepted two-extractor or offline-observation contract.

No repository-wide agent workflow is automatically activated. The current
milestone is being run through the explicitly requested plan-build-review
workflow and remains subject to its review and publication gates.
