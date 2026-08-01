# Inspect a Corpus

## Purpose

Aggregate evidence for an explicit set of sources and approved revisions.
Inspect the source-text-free summary and static report.

## Terms and boundaries

A specification lists every member. A member names one local source and can
list verified approved revisions. A snapshot binds normalized specification,
source, extractor, diagnosis, model, and revision evidence. The report is a
static offline view of the aggregate.

Corpus inspection is CLI-only. It does not discover a directory, follow a
URL, read standard input, create a refinement, or authorize a change.

## Model requirement

Both committed specifications contain PDF members. Prefetched Docling models
are required for a `COMPLETE` run of either specification. Use the model setup
in the [learning hub](README.md) before the complete exercises.

## Run the golden matrix

```bash
corpus inspect fixtures/corpus/golden-matrix.json \
  --docling-artifacts .cache/docling/models
```

Set `CORPUS_DIRECTORY` from the printed manifest path. Open
`report/index.html` and `summary.json`.

The golden matrix has 12 members: three families in PDF, DOCX, Markdown, and
text. A complete run has exactly nine D009 findings. They occur only in the
three TXT members. It has no D010 or other-rule finding. The repeated spaces
are mechanical evidence, not approval to normalize them.

## Run the quality corpus

```bash
corpus inspect fixtures/corpus/quality-corpus.json \
  --docling-artifacts .cache/docling/models
```

The quality corpus has five members. A complete run covers exactly D002, D003,
D004, D005, D007, D009, and D010.

The report groups source-text-free counts, extractor deltas, findings, and
explicit revision histories. It does not embed arbitrary source passages,
rank extractors, or recommend changes. An approved revision can appear only
when the specification lists its verified refinement, diagnosis, and base
bundle. A rejected refinement is not a revision.

## Publish a missing-model PARTIAL record

Use isolated paths that do not contain the model inventory:

```bash
LAB_ROOT="$(mktemp -d)"
corpus inspect fixtures/corpus/golden-matrix.json \
  --output-root "$LAB_ROOT/corpus-inspection" \
  --docling-artifacts "$LAB_ROOT/missing-models"
```

Expected result: the command exits `3` and publishes a valid `PARTIAL` corpus.
The nine non-PDF members complete. The three PDF members record model
failures. No download starts.

Reset `CORPUS_DIRECTORY` from this command output. Verify the published record
without models:

```bash
corpus verify-corpus CORPUS_DIRECTORY
```

Self-contained `verify-corpus` is model-free after a corpus record exists.
Adding `--spec` requests optional live specification, source, model, and
revision advisories.

## Interpret status

- `COMPLETE` means every member has both extraction views, a usable canonical
  document, a diagnosis, and verified listed revisions.
- `PARTIAL` means some evidence is usable, but one member, extractor, or
  diagnosis is incomplete.
- `FAILED` means no member produced a usable extraction view.

Admission fully verifies every listed revision. An invalid or unverifiable
listed revision stops execution before the corpus record is published. It
does not produce a `PARTIAL` corpus.

Historical artifact integrity and live advisories answer different questions.
A later source, specification, or model change does not rewrite a valid
historical record.

## Knowledge check

1. Why do both committed specifications need models for `COMPLETE`?
2. Why can missing models still produce `PARTIAL`?
3. Does the report copy approval authority?
4. What can self-contained verification check without live inputs?

## Answers

1. Each specification includes at least one PDF member.
2. Non-PDF members can still produce usable evidence.
3. No. Authority remains in each refinement manifest decision.
4. It checks the historical schemas, identities, hashes, nested records, summary, and report.

Next: [Complete the document lifecycle](complete-document-lifecycle.md).
