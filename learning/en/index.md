---
outline: false
title: Learning Guides
---

<p class="guide-kicker">tiny-corpus-workbench</p>

# Learn document preparation by doing it

<p class="guide-lede">Learn how a raw document becomes an inspectable prepared revision for later corpus use. Read the principle first. Then use the Local Visual Workbench to test the same idea on a real local record.</p>

Document preparation happens before a later system searches, ranks, or
generates from a corpus. Those downstream tasks are useful, but they are not
this project's subject. This course asks an earlier question: **what document
do we have, how did we prepare it, and what evidence explains that work?**

The course stops at a prepared document revision. It does not teach chunking,
embeddings, indexing, retrieval, generation, or RAG evaluation.

## Start with one lifecycle

~~~text
raw source
  -> captured source and extraction views
  -> canonical DoclingDocument
  -> evidence-based diagnosis
  -> explicit human decision
  -> immutable prepared revision
  -> explicit corpus inspection
~~~

The CLI and the Workbench are two interfaces over the same local lifecycle.
The CLI is the complete, precise interface. The Workbench is the practice
table. It helps you see what each stage means before you inspect detailed
records. Neither interface creates a second lifecycle.

## The questions behind the stages

Each stage answers one different question. Keep the questions separate.

| Stage | Question | Main result | It does not do this |
| --- | --- | --- | --- |
| Observe | What did we receive and extract? | A captured source, extraction views, and a canonical document when usable. | Diagnose or change the document. |
| Diagnose | Which fixed conditions match? | Findings with rule-specific evidence. | Decide that a change is allowed. |
| Refine | What supported change is possible, and do we accept it? | A proposal, then one explicit human decision. | Quietly edit a document. |
| Revision | What did an approved decision create? | One immutable successor and its history. | Replace the original document. |
| Inspect a corpus | What patterns exist across declared members? | Aggregate, source-text-free evidence. | Discover files or modify members. |

Two ideas hold the course together:

- **Evidence** says what the application observed or calculated.
- **Authority** says whether a person chose to apply a supported change.

The application can produce useful evidence without changing anything. A
person can reject a proposal without losing that evidence. This distinction is
why the lifecycle remains understandable after several runs.

## Learning path

<div class="learning-map">
  <a href="./prepare-documents.html"><strong>1. Prepare Documents for a Corpus</strong><span>Understand the boundary, outputs, and questions that a preparation workflow must answer.</span></a>
  <a href="./capture-and-extract.html"><strong>2. Capture and Extract</strong><span>Keep the source stable and compare two extraction views without choosing a winner.</span></a>
  <a href="./inspect-and-diagnose.html"><strong>3. Inspect and Diagnose</strong><span>Use fixed rules and evidence to describe a condition without authorizing a change.</span></a>
  <a href="./decide-and-revise.html"><strong>4. Decide and Revise</strong><span>Turn one supported proposal into an explicit approval or rejection.</span></a>
  <a href="./inspect-a-corpus.html"><strong>5. Inspect a Corpus</strong><span>Read aggregate evidence for an explicit collection of sources and revisions.</span></a>
  <a href="./complete-lifecycle.html"><strong>6. Practice the Complete Lifecycle</strong><span>Use the Workbench to connect the ideas in one guided, end-to-end exercise.</span></a>
</div>

## Before you begin

These lessons assume that the repository is already installed in an active
Python virtual environment. Confirm that `corpus --help` works, then begin
with the first lesson. The first four Workbench exercises use project-authored
Markdown fixtures and do not need PDF models.

Use a separate temporary workspace for practice when you want to start again:

~~~bash
LESSON_WORKSPACE="$(mktemp -d)"
corpus workbench --workspace "$LESSON_WORKSPACE" --no-open
~~~

The command prints a local address. Open it in a browser. Press `Ctrl-C` in the
terminal when you finish. The first lesson starts with the ideas you need
before you run any lifecycle action.
