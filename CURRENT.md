# Handoff Snapshot

**Last updated:** 2026-07-24

This is an informational handoff, not a required agent workflow or taskboard.
Future work may use whichever sound engineering practices fit the task.

## Status

- Milestone v0.1, Extraction Observatory, is released as `v0.1.0` on `main`.
- The released baseline contains `tcw observe`, `tcw verify`, twelve
  deterministic CC0 fixtures, immutable observation artifacts, tests, user
  documentation, learning material, CI, and the project website.
- The local v0.1 baseline passes 80 unit tests, the twelve-fixture registry
  check, and static website validation.
- Milestone v0.2, Evidence-Based Diagnosis, is released as
  [`v0.2.0`](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.2.0)
  on `main`.
- Its accepted implementation contract is
  `docs/plans/v0.2-evidence-based-diagnosis.md`.
- The release contains `tcw diagnose`, `tcw verify-diagnosis`, eight fixed
  evidence-backed rules, immutable diagnosis artifacts, independent
  verification, deterministic CC0 diagnosis fixtures, tests, user
  documentation, and learning material.
- Final hosted `Fast validation`, `Full extraction`, and website deployment
  passed on the `v0.2.0` release target.
- Milestone v0.3, Controlled Revisions, is active by owner approval.
- Its accepted implementation contract is
  `docs/plans/v0.3-controlled-revisions.md`.
- The v0.3 implementation is complete locally on
  `milestone/v0.3-controlled-revisions`.
- The branch contains v0.3 diagnosis subjects, D009 and D010, explicit
  refinement decisions, three fixed refiners, reversible prepared revisions,
  chained history, schemas, fixtures, tests, and required public and learning
  updates.
- v0.3 is not released. The README released-milestone table intentionally
  stops at v0.2.
- Local acceptance passes 149 unit tests and 154 complete tests, including the
  real offline extractor matrix. Fixture generation, registries, the static
  site, compilation, checkout portability, and diff hygiene also pass.
- The documented whitespace workflow passes `observe → diagnose → draft →
  resolve → verify` with derivation and reversibility both `MATCH`.
- Independent milestone review, hosted pull-request checks, and owner
  publication approval remain required before release.
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

## Active milestone

Milestone v0.3 adds explicit refinement decisions and immutable prepared
revisions. It introduces fixed refiners for whitespace normalization, repeated
boilerplate removal, and deterministic dehyphenation. One approved finding
produces one successor revision. A rejected finding produces an immutable
decision record without changing the document.

The accepted plan requires reversible transformation history, before-and-after
hashes, forward and inverse verification, chained revision support, and
backward verification of v0.2 diagnoses. It preserves `orig`, provenance,
stable document references, sources, observations, diagnoses, and earlier
revisions.

The milestone also requires coordinated updates to `README.md`, the static
landing page, the user guide, and the learning hub and lesson. These public and
learning changes are part of milestone acceptance, not optional release
polish.

The implementation follows `docs/plans/v0.3-controlled-revisions.md`. The next
step is independent milestone review. Release claims remain withheld until
review, hosted checks, publication approval, and post-release verification.

## Latest completed milestone

Milestone v0.2 adds deterministic, read-only diagnosis over the canonical
`DoclingDocument` from an intact v0.1 observation. It publishes a separate
application-immutable diagnosis with eight fixed evidence-backed rules,
stable findings, a deterministic report, and independent verification.

The accepted plan keeps MarkItDown descriptive, preserves every v0.1 public
contract and golden fixture, adds no refinement capability, and keeps
chunking, embeddings, retrieval, generation, and RAG evaluation out of scope.

The released implementation includes the two diagnosis commands, eight fixed
rules, three public schemas, separate diagnostic fixtures, tests, a user
guide, and a learning lesson. Verification covers the released v0.1 behavior,
all twelve unchanged golden fixtures, and the diagnosis corpus. Local
acceptance passes 131 tests, deterministic fixture checks, static site
validation, and clean-checkout portability verification.

An independent milestone reviewer returned `PASS` on 2026-07-23. Two later
automated-review findings were fixed with regression coverage before merge.
Pull request
[#5](https://github.com/jameswei/tiny-corpus-workbench/pull/5) delivered the
milestone. Pull request
[#6](https://github.com/jameswei/tiny-corpus-workbench/pull/6) corrected the
README project links before release. The final release-target CI and website
deployment passed, and `v0.2.0` was published on 2026-07-23.
