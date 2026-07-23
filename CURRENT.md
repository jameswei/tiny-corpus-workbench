# Handoff Snapshot

**Last updated:** 2026-07-23

This is an informational handoff, not a required agent workflow or taskboard.
Future work may use whichever sound engineering practices fit the task.

## Status

- Milestone v0.1, Extraction Observatory, is released as `v0.1.0` on `main`.
- The released baseline contains `tcw observe`, `tcw verify`, twelve
  deterministic CC0 fixtures, immutable observation artifacts, tests, user
  documentation, learning material, CI, and the project website.
- The local v0.1 baseline passes 80 unit tests, the twelve-fixture registry
  check, and static website validation.
- The owner accepted milestone v0.2, Evidence-Based Diagnosis, on 2026-07-23.
- Its implementation contract is
  `docs/plans/v0.2-evidence-based-diagnosis.md`.
- Milestone v0.2 is active on
  `milestone/v0.2-evidence-based-diagnosis`.
- The v0.2 plan is being executed through the explicitly requested
  plan-build-review workflow. A fresh milestone reviewer returned `PASS` on
  2026-07-23 after all accepted findings were resolved. Publication now
  requires owner approval and the pending push and pull-request checks.
- The project website remains a separate static publication surface at
  `https://lifeplayer.space/tiny-corpus-workbench/`.

## Document roles

- `AGENTS.md` contains instructions and reading order for coding agents.
- `CURRENT.md` is an informational snapshot for the next working session.
- `README.md` is the evolving public description of the project.
- `docs/proposal.md` preserves the agreed brainstorming verdict, rationale,
  research history, boundaries, and questions left open at that stage. It is
  not a live taskboard.
- `docs/roadmap.md` records the intended major-version progression. It does
  not activate a milestone or replace a milestone implementation plan.
- `learning/` contains learner-facing milestone lessons. These explain
  and exercise the contracts but do not replace the user guide or accepted
  implementation plan.

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

Milestone v0.2 adds deterministic, read-only diagnosis over the canonical
`DoclingDocument` from an intact v0.1 observation. It will publish a separate
application-immutable diagnosis with eight fixed evidence-backed rules,
stable findings, a deterministic report, and independent verification.

The accepted plan keeps MarkItDown descriptive, preserves every v0.1 public
contract and golden fixture, adds no refinement capability, and keeps
chunking, embeddings, retrieval, generation, and RAG evaluation out of scope.

The accepted v0.2 implementation is present on the milestone branch. It
includes the two diagnosis commands, eight fixed rules, three public schemas,
separate diagnostic fixtures, tests, a user guide, and a learning lesson.
Builder verification covers the released v0.1 behavior, all twelve unchanged
golden fixtures, and the new diagnosis corpus. Local acceptance passes 130
tests, deterministic fixture checks, static site validation, and clean-checkout
portability verification.

An independent milestone reviewer returned `PASS` on 2026-07-23 after all
accepted findings were resolved. The branch has not been pushed, and no pull
request, hosted CI run, merge, tag, or release has occurred. Publication now
awaits owner approval followed by the normal push and pull-request checks.
