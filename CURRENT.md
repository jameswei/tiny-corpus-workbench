# Handoff Snapshot

**Last updated:** 2026-07-25

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
- Milestone v0.3, Controlled Revisions, is released as
  [`v0.3.0`](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.3.0)
  on `main`.
- Its accepted implementation contract is
  `docs/plans/v0.3-controlled-revisions.md`.
- The release contains v0.3 diagnosis subjects, D009 and D010, explicit
  refinement decisions, three fixed refiners, reversible prepared revisions,
  chained history, schemas, fixtures, tests, and required public and learning
  material.
- Local acceptance passes 157 unit tests and 163 complete tests, including the
  real offline extractor matrix. Fixture generation, registries, the static
  site, compilation, checkout portability, and diff hygiene also pass.
- The documented whitespace workflow passes `observe → diagnose → draft →
  resolve → verify` with derivation and reversibility both `MATCH`.
- Independent milestone review returned `PASS` on 2026-07-24 after all
  blocking implementation and documentation findings were addressed.
- Two subsequent Copilot review comments identified a single paired
  table-coordinate
  integrity gap. The schema and replay guard now reject incomplete
  coordinates, with regression coverage.
- Pull request
  [#9](https://github.com/jameswei/tiny-corpus-workbench/pull/9) delivered the
  milestone as commit `25be2dd`, which is the target of the annotated
  `v0.3.0` tag.
- Release-target
  [CI](https://github.com/jameswei/tiny-corpus-workbench/actions/runs/30142921755)
  passed `Fast validation` and `Full extraction`. The
  [Pages deployment](https://github.com/jameswei/tiny-corpus-workbench/actions/runs/30099689758)
  passed on the same commit, and the live v0.3 site was verified on
  2026-07-25.
- Milestone v0.4, Corpus Inspection and Comparison, is active by explicit
  owner approval. Its accepted implementation contract is
  `docs/plans/v0.4-corpus-inspection-comparison.md`.
- Work continues on `milestone/v0.4-corpus-inspection-comparison`, which
  started from clean `main` at `4e7e6a0`.
- The implementation, schemas, fixtures, tests, user guide, learning lesson,
  CI changes, and website update are complete locally. This does not claim
  that v0.4 is reviewed, merged, or released.
- Local acceptance passes 193 unit tests and 204 complete tests, including the
  real offline extractor and corpus matrices. Fixture generation, registries,
  the static site, compilation, clean-checkout portability, and diff hygiene
  also pass.
- The golden corpus completes all 12 members with both extractor views and
  diagnoses. It reports exactly nine D009 findings in the three TXT members
  and no other finding.
- The quality corpus completes all five members and covers exactly D002, D003,
  D004, D005, D007, D009, and D010. Explicit D009 revision comparison,
  two-step revision history, and missing-model partial publication also pass.
- Self-contained corpus verification returns `VERIFIED`. With the original
  golden specification, all source, model, and specification advisory states
  return `MATCH`.
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

Milestone v0.4 adds one local, offline command that processes an explicit small
corpus through the released observation and diagnosis contracts. It aggregates
source-text-free evidence and publishes a static navigable report. Explicitly
listed existing applied revisions can be compared as read-only inputs.

The milestone does not draft, approve, reject, or apply refinements. It adds no
directory discovery, network input, service, database, interactive user
interface, public Python API, RAG processing, or production orchestration.

The mandatory compatibility spike passes without changing third-party
dependency pins or v0.3 artifact meaning. Representative v0.3 diagnosis,
applied revision, rejected decision, and chained revision records created
under the released runtime verify under v0.4. A new v0.4 successor revision
also verifies, and v0.1 observations and v0.2 diagnoses remain verifiable.

Implementation is ready for hosted checks and independent review. Milestone
completion still requires reviewer `PASS`, resolved actionable automated
feedback, explicit owner approval, merge, publication of `v0.4.0`,
release-target CI and Pages verification, and the docs-only release closeout.
No later milestone is active.

## Latest completed milestone

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

The released implementation includes explicit decisions, the three fixed
refiners, immutable successor revisions or rejection records, chained history,
closed schemas, deterministic fixtures, tests, a user guide, and a learning
lesson. Local acceptance passes 157 unit tests and 163 complete tests,
including the real offline extractor matrix.

Independent milestone review returned `PASS` on 2026-07-24. Two subsequent
Copilot review comments identified a single paired table-coordinate integrity
gap, which was fixed with schema and replay validation plus regression
coverage. Pull request
[#9](https://github.com/jameswei/tiny-corpus-workbench/pull/9) delivered the
milestone. The release-target CI and website deployment passed, and `v0.3.0`
was published on 2026-07-25.

Milestone v0.4 is now active under its separate owner-approved contract. v0.3
remains the latest completed and released milestone.

## Previous released milestone

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
