# Handoff Snapshot

**Last updated:** 2026-07-20

This is an informational handoff, not a required agent workflow or taskboard.
Future work may use whichever sound engineering practices fit the task.

## Status

- The repository is initialized locally and on GitHub.
- The initial brainstorming verdict is preserved in `docs/proposal.md`.
- No implementation plan or milestone is active.
- No product source code has been written.

## Document roles

- `AGENTS.md` contains instructions and reading order for coding agents.
- `CURRENT.md` is an informational snapshot for the next working session.
- `README.md` is the evolving public description of the project.
- `docs/proposal.md` preserves the agreed brainstorming verdict, rationale,
  research history, boundaries, and open questions. It is not a live taskboard.

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

Start by reviewing the candidate first milestone and the open questions in
`docs/proposal.md`. A useful next step would be to choose one small coherent
increment and define how to verify it. Relevant questions include:

- the first golden fixture set
- whether MarkItDown comparison is deferred
- the first human-readable inspection format
- revision and transformation serialization
- the pinned `DoclingDocument` compatibility boundary
- finding severities and human-approval states
- exact milestone acceptance criteria

Codex CLI does not need to adopt a preinstalled workflow or phase system. It
should confirm the intended first increment with the project owner before
adding product code or runtime dependencies.
