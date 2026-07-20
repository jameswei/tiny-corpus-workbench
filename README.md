# tiny-corpus-workbench

`tiny-corpus-workbench` is a small, learning-by-doing project for making the
document-preparation lifecycle before RAG inspectable, trustworthy, and
reversible.

> **Project status:** proposal stage. The repository is initialized, but
> implementation does not begin until the project proposal is reviewed and
> accepted.

## Purpose

Documents can lose content, structure, reading order, provenance, or revision
context before a RAG system ever chunks or indexes them. This project explores
how to inspect extraction results, diagnose concrete quality problems, and
apply controlled refinements without hiding or overwriting the original
evidence.

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

This is an independent sibling project. It grew from discussions around the
work that precedes `tiny-rag-lab`, but it is not a `tiny-rag-lab` phase,
dependency, or implementation component. A prepared document may eventually
be consumed by any downstream system; integration is outside the initial
scope.

## Initial direction

- Use [Docling](https://github.com/docling-project/docling) for mature,
  format-aware extraction.
- Use `DoclingDocument` as the canonical working representation and retain its
  lossless JSON artifact.
- Keep source files and raw extraction artifacts immutable.
- Record findings with stable identifiers, affected document-item references,
  and concrete evidence.
- Separate diagnosis from authorization to change a document.
- Make refinements deterministic, explicit, attributable, and reversible.
- Require human confirmation for interpretive changes.

These choices are the agreed starting direction, not yet an implementation
contract. See the [draft project proposal](docs/proposal.md) for the review
gate and remaining design decisions.

## Development

No implementation environment or commands are defined yet. They will be added
after the proposal establishes the first milestone and acceptance criteria.

## License

This repository is licensed under the [MIT License](LICENSE).
