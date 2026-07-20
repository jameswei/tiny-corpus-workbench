# Agent Entry Point

Read these files before proposing or making changes:

1. `CURRENT.md` for live project state and the next planning decision
2. `README.md` for the evolving public project description
3. `docs/proposal.md` for the agreed brainstorming verdict and history

`docs/proposal.md` is a historical decision record, not a live taskboard or
implementation contract. Do not rewrite it to track routine progress.

No implementation milestone is currently active. Do not begin product
implementation until `CURRENT.md` names an explicitly accepted plan with a
narrow milestone and acceptance criteria.

Preserve these boundaries unless the user explicitly reviews and changes them:

- Scope starts with raw documents and ends with a prepared document revision
  produced through extraction, canonical representation, diagnosis, and
  controlled refinement.
- Chunking, embeddings, indexing, retrieval, generation, and RAG evaluation
  are outside the initial project.
- Original sources and raw extraction artifacts remain immutable and
  inspectable.
- Diagnosis does not by itself authorize mutation.
- Interpretive refinements require explicit human confirmation.

Prefer readable, teachable mechanics over broad framework integration or
production-grade completeness. Record new planning decisions in the active
planning document named by `CURRENT.md`, and update `README.md` when the public
project state changes.
