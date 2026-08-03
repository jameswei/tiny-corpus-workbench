# Workbench UI/UX Verdict

**Status:** Accepted interaction and presentation direction for v0.9.1.

The Local Visual Workbench is a learner's local work surface for corpus
preparation. It presents the same immutable records that the CLI can publish.
It does not replace the CLI, create a public API, or add a hosted service.

## Work surface

The Workbench has four stable areas:

1. The header identifies the Workbench, its source version, the rule
   reference, and the interface language.
2. The sidebar separates Documents from Corpora. It shows the current
   selection clearly and gives each list only the actions that apply to it.
3. The main area focuses on one selected document and, when applicable, one
   preparation round.
4. The Inspector provides Summary, Evidence, and Artifacts for the current
   stage or selected corpus.

The browser selects its initial language from the browser preference. A single
control switches the Workbench-owned interface between English and Simplified
Chinese. The current selection and view stay in place.

## Document lifecycle

Document work follows four learner-question stages. The stage navigator is
always available for the selected document. A learner can inspect an earlier
stage, but historical rounds are read-only.

| Stage | Learner question | Main result |
| --- | --- | --- |
| Observe | What did extraction produce? | Source metadata, two extraction views, and the canonical `DoclingDocument` handoff. |
| Diagnose | What needs attention? | Fixed-rule findings and the evidence for each match. |
| Refine | What change is proposed? | One selected finding, its supported refiner, a temporary proposal, and an explicit decision. |
| Revision | What was preserved? | An immutable prepared revision, its history, applied relationship, and comparison. |

Observe and Diagnose never change the source. Refine creates a proposal before
it records a decision. Approve creates one immutable prepared revision. Reject
records the decision while keeping the base document unchanged.

No findings is a normal diagnosis result. It ends the current round without a
proposal or prepared revision. It is not a general correctness or compliance
verdict.

## Learner guidance and visual hierarchy

The main area uses distinct presentation roles:

- A stage explanation states the stable purpose and boundary of the stage.
- A result notification confirms a completed or not-needed state.
- Local explanations answer a question about a specific finding or decision.
- Available next step identifies the meaningful action that can advance the
  lifecycle.

Cards group one coherent object or concept. They do not fragment one object
into unrelated tiles. A comparison always shows the complete selected change;
visible whitespace and changed text make mechanical edits readable.

The rule reference is derived from the Python rule and refiner registries. The
browser does not maintain a second ruleset.

## Inspector and artifacts

Summary, Evidence, and Artifacts use one shared Inspector layout. Their data
is stage-scoped for documents. Evidence answers the question raised by the
current stage; it is not a general record dump.

Artifact readers format JSON, show Markdown as source, and isolate
project-generated HTML reports. Uploaded original files are not rendered or
served. Browser-visible SHA-256 values are compact monospace values with the
full value available on hover; records retain the full hash.

The Workbench does not generate CLI continuation commands. When useful, it
states that the published record can also be consumed with the CLI and points
the learner to `corpus --help` and the learning materials.

## Corpus inspection

A corpus uses the same shell and Inspector, but it is an aggregate object.
Its main view therefore uses aggregate forms:

- one compact totals strip for members, findings, revisions, and failures;
- a family-by-format coverage matrix with status markers; and
- grouped Inspector evidence for coverage, extraction, findings, and
  revisions.

Corpus creation and execution remain CLI operations. The Workbench only
inspects complete records that are present in its local workspace.

## Deliberate boundaries

The Workbench is a trusted-local, loopback-only interface for one learner. It
does not provide remote access, authentication, multi-user features, public
HTTP contracts, persistent browser drafts, or original-file rendering. Its
scope remains raw document to immutable prepared document revision.

Chunking, embeddings, indexing, retrieval, generation, RAG evaluation, and
downstream integration remain outside this Workbench.

See the [Local Visual Workbench guide](local-visual-workbench.md) for usage
and [v0.9.0 release notes](releases/v0.9.0.md) for the preceding redesign.
