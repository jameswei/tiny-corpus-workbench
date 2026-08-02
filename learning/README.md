# Learn the Document Lifecycle

These five lessons teach one document-preparation lifecycle. The CLI and the
Local Visual Workbench are two interfaces over the same application behavior.
The lessons start with a raw source and end with an immutable prepared
revision. They do not cover chunking, embeddings, retrieval, or generation.

## Set up once

Use CPython 3.12 and run all commands from the repository root.

```bash
uv sync --frozen --python 3.12
source .venv/bin/activate
corpus --help
```

After activation, the lessons use `corpus ...` commands. Start with the
project-authored fixtures before you use private documents.

The main exercises in lessons 1, 2, and 3 are model-free. The guided path in
lesson 5 is also model-free. PDF observation is an optional extension in
lesson 1.

Both committed corpus specifications contain PDF members. A `COMPLETE` run of
either specification needs prefetched Docling models. Download them once while
network access is available:

```bash
uv run docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
```

Corpus execution does not download models. Without the models, a committed
corpus can still publish a valid `PARTIAL` record when other members produce
usable evidence.

## Learning path

| Topic | Lesson | Main result |
| --- | --- | --- |
| 1. Observe | [Observe extraction](observe-extraction.md) | Compare two extraction views and verify their evidence. |
| 2. Diagnose | [Diagnose with evidence](diagnose-with-evidence.md) | Apply fixed rules without changing the document. |
| 3. Decide | [Control a document revision](control-document-revision.md) | Approve or reject one reversible proposal. |
| 4. Compare | [Inspect a corpus](inspect-a-corpus.md) | Aggregate explicit members in a source-text-free report. |
| 5. Complete | [Complete the document lifecycle](complete-document-lifecycle.md) | Use Workbench stages and preparation rounds from observation through revision. |

## Shared terms

- A **raw source** is the document supplied for observation.
- A **record** is an immutable published evidence directory.
- The **canonical document** is lossless `DoclingDocument` JSON.
- A **finding** records a rule result and cites document evidence.
- A **proposal** describes one possible refinement before a decision.
- A **revision** is the immutable prepared document from an approved proposal.
- A **corpus** is an explicit list of sources and optional approved revisions.
- A **workspace snapshot** is one accepted in-memory Workbench view of verified
  records.

## Study method

1. Run each exercise in order.
2. Read the generated evidence before you read the implementation.
3. Use temporary copies for integrity experiments.
4. Answer the knowledge check before you read its answers.

The lessons use concise, plain English. They use ASD-STE100 Simplified
Technical English as a practical style reference, but they do not claim full
conformance.

For precise behavior, use the current guides:

- [Extraction Observatory](../docs/extraction-observatory.md)
- [Evidence-Based Diagnosis](../docs/evidence-based-diagnosis.md)
- [Controlled Revisions](../docs/controlled-revisions.md)
- [Corpus Inspection and Comparison](../docs/corpus-inspection-comparison.md)
- [Local Visual Workbench](../docs/local-visual-workbench.md)
- [Project roadmap](../docs/roadmap.md)
