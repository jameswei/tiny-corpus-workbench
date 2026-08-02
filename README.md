# tiny-corpus-workbench

`tiny-corpus-workbench` is a small, hands-on project for learning how to
prepare documents without losing their source, extraction evidence, or change
history.

It follows one document lifecycle:

```text
raw source
    -> two extraction views
    -> canonical DoclingDocument
    -> evidence-based diagnosis
    -> explicit refinement decision
    -> immutable prepared revision
```

The project makes each step inspectable. It preserves raw evidence, separates
findings from authority, and records reversible changes. The Local Visual
Workbench guides one document through learner-question stages and preparation
rounds without JSON editing. Corpus reports help you inspect the same evidence
at a larger scale.

Visit the [project website](https://lifeplayer.space/tiny-corpus-workbench/) for
a concise overview.

## What makes it useful for learning

- **One source, two extraction views.** Docling and MarkItDown process the same
  captured source bytes. Their outputs remain separate for comparison.
- **One canonical working document.** Lossless `DoclingDocument` JSON is the
  canonical representation. Its Markdown rendering is a derived document view.
- **Findings with evidence.** Ten fixed rules identify mechanical conditions
  and cite affected document items. A finding does not approve a change.
- **Human-controlled revisions.** One explicit decision can reject a proposal
  or publish one immutable successor revision.
- **Reversible transformations.** Applied refinements record exact edits,
  before-and-after hashes, lineage, forward derivation, and reversal evidence.
- **Inspection at two scales.** A static offline report compares an explicit
  corpus. The bundled local Workbench can provide a richer interactive view of
  explicit records.
- **Independent verification.** Read-only commands check generated records
  without repairing or overwriting them.

## Current interfaces

The `corpus` CLI provides every lifecycle command and verification command:

| Lifecycle task | Command |
| --- | --- |
| Observe one source | `corpus observe` |
| Verify an observation | `corpus verify` |
| Diagnose a document | `corpus diagnose` |
| Verify a diagnosis | `corpus verify-diagnosis` |
| Draft one refinement proposal | `corpus draft-refinement` |
| Resolve one decision | `corpus resolve-refinement` |
| Verify a refinement | `corpus verify-refinement` |
| Inspect an explicit corpus | `corpus inspect` |
| Verify a corpus | `corpus verify-corpus` |
| Open a shared local workspace | `corpus workbench` |

The Local Visual Workbench is the bundled browser interface. Its Documents and
Corpora sidebar, lifecycle stages, and stage-scoped Summary, Evidence, and
Artifacts inspector keep one learning task in focus. It can observe a guided
example or one uploaded `.docx`, `.md`, `.pdf`, or `.txt` file. It explains
findings, previews supported proposals, records an explicit decision, and
shows immutable revision history and readable comparisons. Artifact readers,
a canonical rule reference, and English or Simplified Chinese UI keep audit
detail available without turning the main surface into a record dashboard.

The CLI remains the full interface for every lifecycle and verification
command. It can use the same published workspace records when that is useful;
the browser does not generate continuation commands.

The Workbench binds only to `127.0.0.1` and trusts the local user and local
processes. A process-local action token helps the bundled interface reject
ordinary cross-origin form submissions; it is not authentication. Internal
loopback routes and draft locations are current implementation details, not
public compatibility contracts. The project provides no hosted processing
service.

## Released milestones

| Version | Milestone |
| --- | --- |
| [v0.1.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.1.0) | Extraction Observatory |
| [v0.2.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.2.0) | Evidence-Based Diagnosis |
| [v0.3.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.3.0) | Controlled Revisions |
| [v0.4.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.4.0) | Corpus Inspection and Comparison |
| [v0.5.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.5.0) | Local Visual Workbench |
| [v0.6.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.6.0) | Shared Workbench Workspace |
| [v0.7.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.7.0) | Web Observation Workflow |
| [v0.8.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.8.0) | Interactive Document Lifecycle |

This checkout identifies version `0.9.0`. It contains the v0.9 Workbench UI/UX
redesign. The table above lists published milestones only. Use
[GitHub Releases](https://github.com/jameswei/tiny-corpus-workbench/releases)
for current publication availability.

## One-time setup

The project requires CPython 3.12 and
[uv](https://docs.astral.sh/uv/). Clone this source repository, then create the
locked environment:

```bash
uv sync --frozen --python 3.12
```

Activate the environment to use the CLI directly:

```bash
source .venv/bin/activate
corpus --help
```

PDF extraction also needs local Docling models. Download them once while
network access is available:

```bash
uv run docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
```

The examples below use Markdown and do not need those model files. If you do
not activate `.venv`, prefix a usage command with `uv run`, such as
`uv run corpus observe SOURCE`.

## Short end-to-end example

Run these commands from the repository root after setup:

```bash
corpus observe fixtures/refinement/whitespace-cleanup.md
```

The command prints a compact JSON result. Set `OBSERVATION_DIRECTORY` to the
parent directory of its `manifest` path, then continue:

```bash
corpus verify OBSERVATION_DIRECTORY
corpus diagnose OBSERVATION_DIRECTORY
```

Set `DIAGNOSIS_DIRECTORY` to the parent directory of the diagnosis `manifest`
path. Choose one supported `FINDING_ID`, then draft a canonical proposal:

```bash
corpus verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject OBSERVATION_DIRECTORY
corpus draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID \
  --base OBSERVATION_DIRECTORY \
  --output proposal.json
```

Inspect `proposal.json`, but do not edit it. Supply the human decision with
exactly one resolution flag:

```bash
corpus resolve-refinement proposal.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY \
  --approve
corpus verify-refinement REFINEMENT_DIRECTORY \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY
```

To inspect the default `build/` workspace without changing records:

```bash
corpus workbench --no-open
```

Open the printed local address. Stop the server with `Ctrl-C`.

In the browser, use **Add a document**, then select
`whitespace-cleanup.md` for the complete model-free preparation path. Follow
Observe, Diagnosis, Refine, and Revision. Inspect D009 and R001, create the
proposal, choose **Approve** or **Reject**, and select **Record decision**.
The Workbench shows readable proposed and applied comparisons. It does not
require proposal JSON editing.

You can also observe one supported local document up to 32 MiB. The browser
shows source metadata but does not display or serve the uploaded original.

## Records and their roles

Record-producing commands publish a new directory and do not overwrite a
previous publication. `draft-refinement` writes the requested proposal file.
Verify commands read records and report results. `workbench` discovers the four
record families under `build/` by default and serves an accepted in-memory
snapshot without publishing a record.

| Record | Main files | Role |
| --- | --- | --- |
| Observation | `manifest.json`, `comparison.json`, and extractor artifacts only when that extractor produced them | Preserves source identity, extractor results, canonical content when available, and descriptive differences. |
| Diagnosis | `diagnosis-manifest.json`, `findings.json`, `report.md` | Records deterministic findings and human-readable evidence without changing the document. |
| Refinement | `refinement-manifest.json`, `proposal.json`, `report.md`, and, when approved, transformation, history, and prepared-document files | Records the manifest decision and either no revision or one reversible successor. |
| Corpus | `corpus-manifest.json`, `corpus-spec.json`, `summary.json`, a static report, and contained member evidence | Aggregates source-text-free counts, findings, extractor deltas, and listed revision histories. |

The lossless Docling JSON is the canonical content. Derived Markdown helps
people inspect that content. The static corpus report renders aggregate
source-text-free evidence as HTML. Bundled HTML provides the Workbench
interface. Local hashes and verification detect ordinary corruption under the
trusted-local model; they do not establish authorship, authenticity, or a
trusted timestamp.

## Corpus inspection

An explicit corpus specification lists every local member. The CLI does not
discover directories, follow URLs, read stdin, or apply refinements:

```bash
corpus inspect fixtures/corpus/golden-matrix.json
corpus verify-corpus CORPUS_DIRECTORY \
  --spec fixtures/corpus/golden-matrix.json
```

The generated `report/index.html` works offline and contains no JavaScript or
remote resources. It shows status, extractor deltas, findings, and listed
revision histories without embedding arbitrary source passages.

## Authority and integrity limits

Diagnosis publishes a separate immutable record. It does not repair a document
or authorize a change. `NO_FINDINGS` means only that none of the ten fixed
rules matched.

`refinement-manifest.json.decision` is the only persisted structured decision
authority. `--approve` creates one prepared revision. `--reject` records a
rejection and creates no prepared document. Proposal state `REQUESTED` and
transformation state `APPLIED` are lifecycle facts, not decision authority.
Diagnose each approved revision before drafting its successor.

Original sources and raw extraction artifacts remain unchanged. Observation
and refinement run locally. OCR, plugins, remote extraction services, and LLM
clients are disabled. Missing PDF models produce recorded failure evidence;
the workflow does not download them during observation.

## Project boundary and learning path

The project starts with a raw document and ends with a prepared document
revision. Chunking, embeddings, indexing, retrieval, reranking, generation,
RAG evaluation, and downstream integrations are outside this boundary.

Start with the project-authored CC0 fixtures before using private documents.
The [learning hub](learning/README.md) provides lessons for the complete
lifecycle:

1. [observe extraction](learning/observe-extraction.md)
2. [diagnose with evidence](learning/diagnose-with-evidence.md)
3. [control a document revision](learning/control-document-revision.md)
4. [inspect an explicit corpus](learning/inspect-a-corpus.md)
5. [complete the document lifecycle](learning/complete-document-lifecycle.md)

Use the deeper guides for exact behavior:

- [Extraction Observatory](docs/extraction-observatory.md)
- [Evidence-Based Diagnosis](docs/evidence-based-diagnosis.md)
- [Controlled Revisions](docs/controlled-revisions.md)
- [Corpus Inspection and Comparison](docs/corpus-inspection-comparison.md)
- [Local Visual Workbench](docs/local-visual-workbench.md)

The historical [project proposal](docs/proposal.md) records the original
brainstorming direction. The consolidated
[v0.5 outcome and rationale](docs/plans/v0.5-local-visual-workbench.md)
records the final Local Visual Workbench design.

## Distribution and license

The project is distributed as source from this repository. It does not ship
prebuilt binaries, a Docker image, or registry packages.

The repository is licensed under the [MIT License](LICENSE). The separate
[CC0 declaration](fixtures/LICENSE-CC0-1.0.txt) applies to
`fixtures/authored/`, `fixtures/golden/`, and `fixtures/diagnosis/`.
