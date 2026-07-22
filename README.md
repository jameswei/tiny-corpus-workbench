# tiny-corpus-workbench

`tiny-corpus-workbench` is a small, learning-by-doing project for making raw
document preparation inspectable, trustworthy, and reversible.

> **Project status:** v0.1 Extraction Observatory is implemented. It provides
> a local CLI for inspecting Docling and MarkItDown views of one document at a
> time. See the [user guide](docs/extraction-observatory.md) and
> [`CURRENT.md`](CURRENT.md) for the current contracts and verification state.

## Purpose

Documents can lose content, structure, reading order, provenance, or revision
context before downstream systems process them. This project explores how to
inspect extraction results, diagnose concrete quality problems, and apply
controlled refinements without hiding or overwriting the original evidence.

RAG is one common downstream use: extraction and preparation errors can
propagate into chunking, indexing, retrieval, and generated answers.

The intended lifecycle is:

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

## Project boundary

The initial project covers three layers:

1. extraction adapters
2. a canonical working representation
3. diagnosis and controlled refinement

It explicitly excludes chunking, embeddings, indexing, retrieval, reranking,
generation, and RAG evaluation.

The workbench ends at a prepared document revision. Consumption by downstream
systems and integration with them are outside the initial scope.

## Initial direction

- Use [Docling](https://github.com/docling-project/docling) for mature,
  format-aware extraction.
- Use `DoclingDocument` as the canonical working representation and retain its
  lossless JSON artifact.
- Keep source files unchanged and published raw extraction artifacts
  application-immutable.
- Record findings with stable identifiers, affected document-item references,
  and concrete evidence.
- Separate diagnosis from authorization to change a document.
- Make refinements deterministic, explicit, attributable, and reversible.
- Require human confirmation for interpretive changes.

The v0.1 implementation intentionally stops after extraction observation. It
does not diagnose quality, choose a better extractor, or modify documents.
See the [brainstorming record](docs/proposal.md) for the original rationale and
the [project roadmap](docs/roadmap.md) for later planned milestones.

## Development

The acceptance runtime is CPython 3.12 with dependencies locked by `uv.lock`.

```bash
uv sync --frozen --python 3.12
uv run --frozen docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
uv run --frozen tcw observe fixtures/golden/policy-memo.pdf
```

Model download is an explicit setup step. Observation itself is local and
offline: OCR, plugins, remote services, and LLM clients are disabled, and a
missing PDF model inventory causes a recorded failure instead of a download.
Each observation uses one private source snapshot for both extractors and is
locally tamper-evident under the trusted-local limits documented in the user
guide. Published runs can be checked read-only with `tcw verify`.

The repository includes exactly twelve deterministic CC0 fixtures generated
from three project-authored document families. The full setup, artifact,
rerun, compatibility, failure-code, and verification contracts are documented
in the [Extraction Observatory guide](docs/extraction-observatory.md).

## Learn v0.1

The [v0.1 learning module](docs/learning/v0.1-extraction-observatory.md) turns
the completed milestone into a guided lab. It covers the extraction mental
model, artifact inspection, descriptive comparison, safe tamper experiments,
freshness advisories, and the limits of `VERIFIED`. Start from the
[learning-material index](docs/learning/README.md) when following future
milestones.

## License

This repository is licensed under the [MIT License](LICENSE).
