# Current Repository Guide

Use this file as a navigation index. It does not record execution history,
review evidence, or publication state.

## Source state

This checkout identifies package version `0.9.2`. The current product
milestones cover:

1. extraction observation;
2. evidence-based diagnosis;
3. controlled revisions;
4. corpus inspection and comparison;
5. the Local Visual Workbench;
6. shared workspace discovery with transactional refresh;
7. guided or uploaded observation from the browser;
8. visible verification, diagnosis, proposal decisions, and immutable
   revision inspection in the browser; and
9. a coherent bilingual Workbench with document-centered navigation,
   preparation rounds, focused evidence, comparisons, and artifact readers; and
10. a bilingual learning docsite that teaches the lifecycle through paired
    principles and Workbench practice.

For published versions and release availability, use
[GitHub Releases](https://github.com/jameswei/tiny-corpus-workbench/releases).

## Current source

The current source contains the v0.9.2 bilingual learning docsite. The CLI
remains the full lifecycle interface. The bundled browser groups immutable
records by document and preparation round. The docsite teaches those concepts
and uses the Workbench as its practice table. For published versions and
availability, use [GitHub Releases](https://github.com/jameswei/tiny-corpus-workbench/releases).

## Settled invariants

- Scope starts with a raw document and ends with a prepared document revision.
- Original sources and raw extraction artifacts remain immutable and
  inspectable.
- Lossless `DoclingDocument` JSON is the canonical extracted representation.
- Diagnosis records findings but does not authorize mutation.
- Interpretive refinements require explicit human confirmation.
- Record-producing commands publish new immutable directories.
- The `corpus` CLI provides every lifecycle and verification command.
- The Workbench can publish observations. Published records stay immutable.
- The Workbench can diagnose actionable documents and resolve supported
  proposals only after an explicit browser decision.
- The Workbench shows Documents and Corpora in one sidebar and uses
  stage-scoped Summary, Evidence, and Artifacts inspection.
- The Workbench localizes its own interface in English and Simplified Chinese.
- Browser-visible hashes are compact, but records and internal identity checks
  keep full SHA-256 values.
- The Workbench is loopback-only. Its HTTP routes are an internal bridge, not
  a public API.
- Distribution is source-only. The project provides no hosted processing
  service.

## Authoritative reading paths

Read these files for the current question:

- [README](README.md): public purpose, setup, interfaces, and project boundary
- [initial proposal](docs/proposal.md): original brainstorming verdict and
  rationale
- [technical documentation](docs/): commands, records, and implementation history
- [learning docsite](learning/): guided bilingual lessons for learners
- [roadmap](docs/roadmap.md): major future direction
- [historical plans](docs/plans/): completed milestone outcomes, rationale, and
  boundaries
- [release notes](docs/releases/): source changes for each version
- code, schemas, fixtures, and tests: current technical behavior
- Git and GitHub: detailed execution, review, and change history

## Inactive directions

Chunking, embeddings, indexing, retrieval, reranking, generation, RAG
evaluation, hosted processing, remote Workbench access, multi-user operation,
and production orchestration remain outside the active project boundary.
