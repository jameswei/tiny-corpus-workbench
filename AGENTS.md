# Agent Entry Point

Read these files before proposing or making changes:

1. `README.md`
2. `docs/proposal.md`

The project is currently in proposal stage. Do not begin product
implementation until `docs/proposal.md` is marked accepted and defines a
narrow first milestone with acceptance criteria.

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
production-grade completeness. Record design decisions in the proposal before
turning them into code or public contracts.
