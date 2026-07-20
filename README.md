# tiny-corpus-workbench

`tiny-corpus-workbench` is a small, learning-by-doing project for making raw
document preparation inspectable, trustworthy, and reversible.

> **Project status:** planning stage. The initial brainstorming direction is
> agreed, but no implementation milestone is active. See
> [`CURRENT.md`](CURRENT.md) for live project state.

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
- Keep source files and raw extraction artifacts immutable.
- Record findings with stable identifiers, affected document-item references,
  and concrete evidence.
- Separate diagnosis from authorization to change a document.
- Make refinements deterministic, explicit, attributable, and reversible.
- Require human confirmation for interpretive changes.

These choices are the agreed starting direction, not an implementation
contract. See the [brainstorming record](docs/proposal.md) for their rationale,
research history, and remaining open questions.

## Development

No implementation environment or commands are defined yet. They will be added
after a separate first-milestone plan is reviewed and accepted.

## License

This repository is licensed under the [MIT License](LICENSE).
