# Current Project State

**Last updated:** 2026-07-20

## Status

- The repository is initialized locally and on GitHub.
- The initial brainstorming verdict is preserved in `docs/proposal.md`.
- No implementation plan or milestone is active.
- No product source code has been written.

## Document roles

- `AGENTS.md` contains instructions and reading order for coding agents.
- `CURRENT.md` is the source of truth for live state and the next action.
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

## Next session

Continue with planning, not implementation. Turn the candidate first milestone
into a decision-complete plan by resolving the open questions recorded in
`docs/proposal.md`, especially:

- the first golden fixture set
- whether MarkItDown comparison is deferred
- the first human-readable inspection format
- revision and transformation serialization
- the pinned `DoclingDocument` compatibility boundary
- finding severities and human-approval states
- exact milestone acceptance criteria

Do not create an implementation skeleton or add runtime dependencies until the
project owner reviews that plan and `CURRENT.md` is updated to activate it.
