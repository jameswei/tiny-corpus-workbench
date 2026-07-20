# Project Proposal: `tiny-corpus-workbench`

**Status:** Agreed brainstorming record; not an implementation contract
**Role:** Initial decision, rationale, and research history
**Project type:** Independent, learning-by-doing project
**Last updated:** 2026-07-20

## Purpose

Build a small, inspectable workbench that teaches what happens between a raw
business document and a trustworthy prepared-document revision.

The project should make it possible to answer:

- What did the extractor produce?
- Which concrete quality problems were found, and what evidence supports them?
- Which changes are safe to automate?
- What changed between the extracted and prepared revisions?
- Can every change be traced to its source, finding, and decision?

It is not intended to become a production ingestion platform.

## Lifecycle boundary

This project covers document preparation from a raw source through a prepared
revision:

```text
raw document
    -> extraction
    -> canonical working representation
    -> diagnosis and controlled refinement
    -> prepared document revision
```

Prepared revisions may be consumed by other systems. Downstream processing and
integration are outside the initial milestone.

## Agreed boundary

The initial project covers:

1. extraction adapters
2. `DoclingDocument` as the canonical working representation
3. evidence-based diagnosis and controlled refinement

The initial project does not cover:

- chunking, embeddings, indexing, retrieval, reranking, or generation
- RAG evaluation
- enterprise connectors or access-control synchronization
- web crawling or email ingestion
- general-purpose batch orchestration
- production-scale distributed processing
- scanned-document OCR as a first requirement
- silent LLM cleanup

## Agreed ownership model

Docling owns extracted document content and structure. This project owns the
preparation and audit envelope around it:

- source identity, media type, and checksum
- extractor, model, schema, and configuration versions
- extraction status
- diagnostic findings and evidence
- requested, approved, rejected, and applied refinements
- before-and-after hashes
- transformation history
- human confirmation for interpretive changes

The source file and raw extraction artifact remain immutable. Every refinement
produces a new prepared revision rather than overwriting prior evidence.

## Candidate first milestone

The first implementation milestone should remain local and service-free. Its
candidate scope is:

- PDF and DOCX extraction through Docling
- Markdown and plain-text inputs represented as `DoclingDocument`
- lossless Docling JSON artifacts
- a project-owned preparation and audit record
- six to eight deterministic diagnosis rules
- approximately three reversible refiners
- JSON output plus one human-readable inspection format
- a small project-owned golden mixed-format fixture set

This section is a candidate, not an accepted commitment. The review must
narrow it further if it cannot be taught and verified as one coherent slice.

## Candidate diagnoses and refinements

Candidate deterministic findings include empty output, suspiciously little
text, encoding damage, repeated headers or footers, heading-level jumps,
orphaned captions, duplicate blocks, conflicting revisions, and missing
provenance where it is expected.

Candidate safe refiners include whitespace normalization, repeated-boilerplate
removal, and deterministic dehyphenation or hard-line-break repair.

Reading-order changes, table reconstruction, semantic block merging or
splitting, revision selection, and LLM-produced rewrites require explicit
confirmation.

## Remaining open questions

The initial brainstorming intentionally left these questions for later
planning:

1. Which project-owned or permissively licensed documents form the first
   golden fixture set?
2. Is MarkItDown comparison part of the first milestone or deferred?
3. Is the first human-readable inspection experience Markdown, generated HTML,
   or a local browser view?
4. How are prepared revisions and transformation operations serialized?
5. Which `DoclingDocument` version is pinned, and what compatibility promise is
   made?
6. Which finding severities and human-approval states are essential?
7. What are the exact first-milestone acceptance criteria?

## Suggested next step

A separate implementation plan should:

- resolve the open questions above
- define the initial artifacts and their ownership
- identify the exact diagnosis rules and refiners in scope
- define verification fixtures and expected outcomes
- state a narrow implementation milestone and acceptance criteria

That future plan should be reviewed and explicitly activated in `CURRENT.md`.
This document should remain the historical record of the initial brainstorming
verdict rather than becoming a live taskboard.
