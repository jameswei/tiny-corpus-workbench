# Agent Entry Point

Before proposing or making changes, read:

1. `README.md` for the evolving public project description
2. `docs/proposal.md` for the agreed brainstorming verdict and history
3. `CURRENT.md` for the latest handoff snapshot, when relevant

`docs/proposal.md` is a historical decision record, not a live taskboard or
implementation contract. Do not rewrite it to track routine progress.

No repository-specific agent framework or phase workflow is required. Use
sound engineering practices appropriate to the task: inspect the current
state, keep changes focused, verify relevant behavior, and update documentation
when public behavior or project direction changes.

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
production-grade completeness. Confirm scope with the project owner before a
change would materially broaden the project or create a public contract.

When you create or update files in `learning/`, use concise, plain, and
accurate English. Use ASD-STE100 Simplified Technical English as a practical
style reference. Prefer active voice, short sentences, one topic per paragraph,
and one instruction per step. Do not claim full ASD-STE100 conformance unless
the text passes all applicable writing rules and controlled-dictionary checks.
