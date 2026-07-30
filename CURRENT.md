# Handoff Snapshot

**Last updated:** 2026-07-30

This is an informational handoff, not a required agent workflow or taskboard.
Future work may use whichever sound engineering practices fit the task.

## Status

- Milestone v0.6, Shared Workbench Workspace, was delivered through core PR
  [#37](https://github.com/jameswei/tiny-corpus-workbench/pull/37), merged as
  `74d1c860392c42f91f294d17b6b09263790b3611`, and pre-release public-surface
  PR [#38](https://github.com/jameswei/tiny-corpus-workbench/pull/38), merged
  as exact release target
  `545be3c6520290450971f718094f9ca0838ef925`.
- A final fresh release-readiness review returned `PASS` with zero findings
  for that exact target, and the owner explicitly authorized it. Main CI
  `30541505013` and Pages `30541504973` passed at the same commit.
- [`v0.6.0`](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.6.0)
  was published on 2026-07-30 as the latest, source-only GitHub Release with
  no custom assets. Annotated tag object
  `1595ace0575c8e8aa54ba07e886d6e1b06e467c1` peels to the exact release
  target. Tag CI `30542655933` passed Fast and Full, and the downloaded GitHub
  source archive contained the `0.6.0` package metadata, approved plan, and
  release note.
- The v0.5 learning-first correction is complete and merged. Correction PRs
  [#18](https://github.com/jameswei/tiny-corpus-workbench/pull/18) through
  [#26](https://github.com/jameswei/tiny-corpus-workbench/pull/26) delivered
  PR 0 through PR 9. PR #26 was independently reviewed at
  `9780d87faf1337e4c8acf28ea2e704b39fcb402e`, returned `PASS`, and was
  squash-merged as `8b04885a9471091cdfce17560e395a2d103d2806`.
- The original milestone PRs
  [#13](https://github.com/jameswei/tiny-corpus-workbench/pull/13) and
  [#17](https://github.com/jameswei/tiny-corpus-workbench/pull/17) are merged.
  They represent pre-correction history.
- The approved v0.5 pre-release amendment is also implemented and merged.
  Establishment PR #27, amendment PR A #28, amendment PR B #29, and narrow
  corrective PR #30 are complete. A fresh combined technical integration
  review returned `PASS` with zero findings for the exact range from
  `8b04885a9471091cdfce17560e395a2d103d2806` through candidate
  `c80842cec401d6110ad60ccac696cebb1028d640`.
- The amendment closeout is complete. PR #31 was independently reviewed at
  head `5e5a3772a85b44111121ff057f2971db421df1a4` and returned `PASS` with zero
  findings. Exact-head CI `30476653488` passed Fast and Full. PR #31 was
  squash-merged as `40b2083de70cfe9f7ad2dfa2cea8435b377a5ecc`.
  Post-main CI `30477806685` passed Fast and Full, and post-main Pages
  `30477806662` passed build and deploy at that exact squash.
- Post-closeout status correction PR #32 was independently reviewed at head
  `7877c8e028bd7c73af02f6d6c2aa701ed6481aa8` and returned `PASS` with zero
  findings. PR CI `30479472643` passed Fast and Full, and Copilot completed
  4/4 with zero comments. PR #32 was squash-merged as
  `6ed049bbf889cde6ea1ba63b1d57813bac820214`. Post-main CI `30480029674`
  passed Fast and Full, and post-main Pages `30480029443` passed build and
  deploy at that exact squash.
- A final fresh release-readiness review returned `PASS` with zero findings
  for exact candidate `6ed049bbf889cde6ea1ba63b1d57813bac820214`.
  Before publication, 291 unit tests and 8 model-free/Workbench integration
  tests passed, together with portability, policy, assets, site, schema,
  version, lock, documentation, review-thread, and tag-absence checks. The
  owner then explicitly authorized that exact SHA for v0.5.0 publication.
- Milestone v0.5, Local Visual Workbench, was released on 2026-07-30 as
  [`v0.5.0`](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.5.0).
  The annotated tag ref targets tag object
  `2f5843e9ae492eaef6db4cd863e6299fc458c085`, which peels to exact commit
  `6ed049bbf889cde6ea1ba63b1d57813bac820214`. The published GitHub Release is
  latest, non-draft, non-prerelease, and source-only, with no custom assets.
- Post-release correction PR #33 removed the current-document policy validator,
  its prose and historical-evidence tests, and its CI hook. Documentation and
  evidence are not executable implementation contracts. A fresh independent
  review returned `PASS` with zero findings for head
  `4f6dd65729334b811c29048e19e8cc3b9a2c7dc5`; PR CI `30510663242` passed Fast
  and Full, and Copilot reviewed 4/4 files with zero comments. PR #33 was
  squash-merged as `1a358bdf6ab97dd77d31ac8bf8f17c0f3852c6aa`.
  Post-main CI `30510994588` passed Fast and Full, and post-main Pages
  `30510994584` passed build and deploy at that exact squash.
- The completed correction follows the approved
  [v0.5 learning-first correction plan](docs/plans/v0.5-learning-first-correction.md)
  and its
  [ledger](docs/plans/v0.5-learning-first-correction-ledger.md). The ledger
  records the exact reviewed heads, squash commits, and post-merge hosted
  evidence for completed PR 0 through PR 9.
- The amendment follows the frozen
  [v0.5 pre-release amendment plan](docs/plans/v0.5-pre-release-amendment.md)
  and its
  [ledger](docs/plans/v0.5-pre-release-amendment-ledger.md).
- Milestone v0.1, Extraction Observatory, is released as `v0.1.0` on `main`.
- The released baseline contains source observation and verification, twelve
  deterministic CC0 fixtures, immutable observation artifacts, tests, user
  documentation, learning material, CI, and the project website.
- The local v0.1 baseline passes 80 unit tests, the twelve-fixture registry
  check, and static website validation.
- Milestone v0.2, Evidence-Based Diagnosis, is released as
  [`v0.2.0`](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.2.0)
  on `main`.
- Its accepted implementation contract is
  `docs/plans/v0.2-evidence-based-diagnosis.md`.
- The release contains evidence-based diagnosis and verification, eight fixed
  rules, immutable diagnosis artifacts, deterministic CC0 diagnosis fixtures,
  tests, user documentation, and learning material.
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
- Milestone v0.4, Corpus Inspection and Comparison, is released as
  [`v0.4.0`](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.4.0)
  on `main`.
- Its accepted implementation contract is
  `docs/plans/v0.4-corpus-inspection-comparison.md`.
- The release contains explicit corpus inspection and verification, four
  closed corpus schemas, deterministic aggregation, a static offline report,
  two explicit example corpora, tests, user documentation, learning material,
  and the updated project website.
- Local acceptance passes 203 unit tests and 214 complete tests, including the
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
- Copilot review identified three integrity gaps: claimed extractor
  availability did not require every expected artifact descriptor to match,
  percent-encoded link control characters were not rejected after decoding,
  and corpus verification omitted the shared format checker. Follow-up review
  found the same checker omission in the execution and publication validator
  factories. All corpus runtime validators now use the shared checker. The
  five findings have focused regression coverage. All five review threads are
  resolved.
- A final owner-requested contract audit found additional corpus composition
  gaps before merge. The verifier did not compare the recorded runtime,
  snapshot, nested manifest descriptors, or nested observation and diagnosis
  identities. A duplicate family-format cell could also hide one member, and
  a symbolic-link model directory could become a partial result. The
  implementation now recomputes those identities, records and validates the
  exact model inventory, lists every matrix member, rejects unsafe paths with
  exit `5`, and completes self-verification before the atomic publish rename.
  Focused tamper, concurrent-publication, no-invalid-publication, link-safety,
  and input-drift tests pass.
- Independent final review found that the HTML extractor table showed both raw
  views but omitted the exact deltas already present in `summary.json`. The
  report now shows every numeric Docling-minus-MarkItDown delta and the exact
  normalized-equality state. Focused report coverage and the complete local
  suite pass. Refreshed independent review returned `PASS` with no remaining
  blocker.
- Pull request
  [#11](https://github.com/jameswei/tiny-corpus-workbench/pull/11) delivered
  the milestone as commit `ae7ce99`, which is the target of the annotated
  `v0.4.0` tag.
- Main
  [CI](https://github.com/jameswei/tiny-corpus-workbench/actions/runs/30161871876),
  release-target
  [CI](https://github.com/jameswei/tiny-corpus-workbench/actions/runs/30161978252),
  and the
  [Pages deployment](https://github.com/jameswei/tiny-corpus-workbench/actions/runs/30161871869)
  passed on that commit. The tagged documentation links and live v0.4 website
  were verified on 2026-07-25.
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

No unreleased milestone is active. v0.6, Shared Workbench Workspace, is the
latest completed milestone and `v0.6.0` is the latest source release.

The roadmap now records three bounded, progressive Workbench improvements:
v0.6 Shared Workbench Workspace, v0.7 Web Observation Workflow, and v0.8
Interactive Document Lifecycle. The v0.7 and v0.8 entries remain inactive and
each requires its own reviewed and approved implementation plan before work
begins. Roadmap entries do not activate implementation by themselves. The exact
[v0.6 plan](docs/plans/v0.6-shared-workbench-workspace.md) passed independent
review and received explicit owner approval before implementation began.

The [v0.5 Local Visual Workbench plan](docs/plans/v0.5-local-visual-workbench.md)
and its
[ledger](docs/plans/v0.5-local-visual-workbench-ledger.md) are historical
records of the superseded implementation direction and activity. They do not
govern current implementation.

The v0.6 Workbench remains read-only and loopback-only. It discovers the four
fixed record families under `build/` or a custom workspace and accepts a new
verified snapshot only after startup or manual transactional refresh. The
loopback HTTP server is an internal bridge for the bundled browser interface,
not a public or stable API.

## Latest completed milestone

Milestone v0.6 lets the read-only Local Visual Workbench discover the four
fixed record families under `build/` or a custom workspace. Startup and manual
refresh accept a new immutable in-memory projection only after the complete
candidate passes verification. A failed refresh reports the error and keeps
the last good record details and captured artifact bytes.

Core PR #37 was merged as
`74d1c860392c42f91f294d17b6b09263790b3611`. Public-surface PR #38 was merged
as exact release target `545be3c6520290450971f718094f9ca0838ef925`.
A fresh release-readiness review returned `PASS` with zero findings for that
target, the owner explicitly authorized it, and main CI and Pages passed.
Annotated `v0.6.0` tag object
`1595ace0575c8e8aa54ba07e886d6e1b06e467c1` peels to the same target. The
[GitHub Release](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.6.0)
was published on 2026-07-30 as the latest source-only release with no custom
assets, and tag CI passed Fast and Full.

## Previous completed milestone

Milestone v0.5 adds the bundled Local Visual Workbench for read-only inspection
of explicit verified records. It serves a frozen in-memory projection through
a loopback-only internal bridge and does not discover records, persist session
state, or move workflow execution out of the CLI.

The learning-first correction aligned current records, verification, CLI
ownership, documentation, and the Workbench. The pre-release amendment made
verification results transient typed values and reduced refinement decisions
to one persisted authority.

PR #32 supplied the final status correction and was independently reviewed,
CI-verified, and squash-merged as exact release target
`6ed049bbf889cde6ea1ba63b1d57813bac820214`. A separate final readiness review
returned `PASS` with zero findings for that exact commit, and the owner
explicitly authorized it. The annotated `v0.5.0` tag peels to the same commit,
and the
[GitHub Release](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.5.0)
was published on 2026-07-30 as a source-only release.

## Earlier released milestone

Milestone v0.4 adds explicit, local corpus inspection over the released
observation and diagnosis contracts. It processes members sequentially,
aggregates source-text-free evidence, and publishes deterministic JSON plus a
navigable static HTML report. Explicitly listed applied revisions remain
read-only comparison inputs.

The golden matrix covers three document families in PDF, DOCX, Markdown, and
text. The separate quality corpus covers D002, D003, D004, D005, D007, D009,
and D010. The report includes exact extractor deltas, findings, incomplete
members, and verified revision histories without embedding arbitrary source or
prepared-document text.

Corpus verification checks the complete top-level record, every nested
observation and diagnosis, deterministic report regeneration, exact model
inventory, safe links, and optional live-input advisory states. The mandatory
compatibility spike preserves verification of representative v0.1, v0.2, and
v0.3 artifacts under the exact v0.4 package and lock identity.

Copilot produced five actionable findings across two reviews. All five were
fixed with focused regression coverage and all review threads are resolved.
The final contract audit added runtime, snapshot, inventory, nested identity,
atomic publication, unsafe-path, and matrix-completeness protections. A final
independent review found one missing HTML delta presentation, which was fixed
before refreshed review returned `PASS`.

Pull request
[#11](https://github.com/jameswei/tiny-corpus-workbench/pull/11) delivered the
milestone as `ae7ce99`. The annotated `v0.4.0` tag targets that commit. Main
CI, release-target CI, Pages deployment, tagged documentation, and the live
website all passed final verification. At the v0.4 closeout, no later
milestone was active.

## Release history

Milestone v0.3 adds explicit refinement decisions and immutable prepared
revisions. It includes fixed refiners for whitespace normalization, repeated
boilerplate removal, and deterministic dehyphenation. One approved finding
produces one successor revision. A rejected finding records the decision
without changing the document.

The released contract requires reversible transformation history,
before-and-after hashes, forward and inverse verification, chained revision
support, and backward verification of v0.2 diagnoses. It preserves `orig`,
provenance, stable document references, sources, observations, diagnoses, and
earlier revisions.

Independent milestone review returned `PASS` after the blocking findings were
addressed. Two later Copilot comments identified a paired table-coordinate
integrity gap, which was fixed with schema and replay validation plus
regression coverage. Pull request
[#9](https://github.com/jameswei/tiny-corpus-workbench/pull/9) delivered the
milestone as `25be2dd`. Release-target CI and Pages passed, and `v0.3.0` was
published on 2026-07-25.
