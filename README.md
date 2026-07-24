# tiny-corpus-workbench

`tiny-corpus-workbench` is a small, hands-on project for learning how to
prepare documents without losing sight of their source or extraction evidence.

Visit the [project website](https://lifeplayer.space/tiny-corpus-workbench/)
for a concise overview of the workbench.

## Released milestones

| Version | Milestone |
| --- | --- |
| [v0.1.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.1.0) | Extraction Observatory |
| [v0.2.0](https://github.com/jameswei/tiny-corpus-workbench/releases/tag/v0.2.0) | Evidence-Based Diagnosis |

## Why this project

Documents can lose content, structure, reading order, provenance, or revision
context before another system uses them. This workbench makes that preparation
step visible. It lets you inspect extraction results, diagnose concrete quality
problems, and preserve the evidence needed for later human-controlled changes.

RAG is one possible downstream use. Extraction and preparation errors can
propagate into chunking, indexing, retrieval, and generated answers.

## Workflow

The project follows this document lifecycle:

```text
raw business documents
        |
        v
format-aware extraction
        |
        v
DoclingDocument
        |
        v
diagnosis + explicit refinement
        |
        v
prepared document revision
```

The current milestone implementation covers source capture, extraction
observation, evidence-based diagnosis, explicit refinement decisions, and
immutable prepared revisions. The v0.3 release has not been published.

## What you can do today

- **Observe extraction.** `tcw observe` runs Docling and MarkItDown against the
  same captured source snapshot. It preserves both outputs instead of choosing
  a winner.
- **Verify an observation.** `tcw verify` checks the published structure,
  artifact hashes, and recorded document relationships without changing the
  record.
- **Diagnose the canonical document.** `tcw diagnose` evaluates ten fixed,
  deterministic rules against the canonical `DoclingDocument` JSON.
- **Verify a diagnosis.** `tcw verify-diagnosis` checks diagnosis artifacts and
  can compare them with the original observation and a fresh rule evaluation.
- **Draft one refinement.** `tcw draft-refinement` binds one supported finding
  to its fixed refiner and writes a pending decision file.
- **Resolve the decision.** `tcw resolve-refinement` records a rejection or
  publishes one approved successor revision.
- **Verify the revision.** `tcw verify-refinement` checks artifacts, lineage,
  forward derivation, and exact reversal.

Diagnosis publishes a separate immutable record. It does not repair a document
or authorize a change. `NO_FINDINGS` means that none of the ten rules
matched; it is not proof that the document is correct.

Each draft targets one finding. Edit only `decision.state`,
`decision.decided_by`, and the optional `decision.note`. An `APPROVED` decision
creates one prepared revision. A `REJECTED` decision records the decision and
creates no prepared document. Diagnose each approved revision before you draft
its successor.

Verification detects changes under the project's trusted-local model. It does
not establish authorship or authenticity.

## Project boundary

The workbench covers three layers:

1. extraction adapters
2. a canonical working representation
3. diagnosis and controlled refinement

It starts with a raw document and ends with a prepared document revision. It
does not include chunking, embeddings, indexing, retrieval, reranking,
generation, or RAG evaluation. Integration with downstream systems is also
outside the project boundary.

## Design principles

- [Docling](https://github.com/docling-project/docling) provides format-aware
  extraction.
- `DoclingDocument` is the canonical working representation, and its lossless
  JSON is retained.
- Source files and published raw extraction artifacts remain unchanged.
- Findings include stable identifiers, affected document-item references, and
  concrete evidence.
- Diagnosis never grants authority to change a document.
- Refinements are designed to be deterministic, explicit, attributable, and
  reversible.
- Interpretive changes require human confirmation.

## Run locally

The workbench requires CPython 3.12 and
[uv](https://docs.astral.sh/uv/). `uv.lock` pins the dependencies.

```bash
uv sync --frozen --python 3.12
uv run --frozen docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
uv run --frozen tcw observe fixtures/golden/policy-memo.pdf
uv run --frozen tcw verify OBSERVATION_DIRECTORY
uv run --frozen tcw diagnose OBSERVATION_DIRECTORY
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject OBSERVATION_DIRECTORY
uv run --frozen tcw draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID --base OBSERVATION_DIRECTORY \
  --output decision.json
# Edit only decision.state, decision.decided_by, and decision.note.
uv run --frozen tcw resolve-refinement decision.json \
  --diagnosis DIAGNOSIS_DIRECTORY --base OBSERVATION_DIRECTORY
uv run --frozen tcw verify-refinement REFINEMENT_DIRECTORY \
  --diagnosis DIAGNOSIS_DIRECTORY --base OBSERVATION_DIRECTORY
```

Each command prints a compact JSON result. Replace `OBSERVATION_DIRECTORY` with
the directory containing the `manifest` path printed by `tcw observe`. Replace
`DIAGNOSIS_DIRECTORY` with the directory containing the `manifest` path printed
by `tcw diagnose`.

The PDF example requires the local Docling models downloaded in the second
step. Observation then runs locally and offline. OCR, plugins, remote services,
and LLM clients are disabled. If the required PDF models are missing, the run
records a failure instead of downloading them.

Diagnosis needs no models or network access. Published observations and
diagnoses are not overwritten by the CLI. Refinement also runs offline. It
changes prepared `text`, never `orig`, and preserves provenance and stable
document references. Each applied transformation stores its before-and-after
hashes and reversible edit data. Local hashes provide tamper evidence under
the trusted-local model; they do not prove authorship or authenticity.

See the [Controlled Revisions guide](docs/controlled-revisions.md) for the
supported findings, artifact layout, chaining rules, verification states, and
integrity limits.

## Learning

The [learning hub](learning/README.md) provides guided, hands-on lessons for
each completed milestone. It includes a suggested learning path, estimated
study times, safe experiments, and links to related references.

Start with the project-authored CC0 fixtures before using private documents.
The learning hub links to detailed guides when a lesson needs them.

## License

This repository is licensed under the [MIT License](LICENSE).
The separate [CC0 declaration](fixtures/LICENSE-CC0-1.0.txt) applies to
`fixtures/authored/`, `fixtures/golden/`, and `fixtures/diagnosis/`.
