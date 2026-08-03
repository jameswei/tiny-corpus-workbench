<p class="guide-kicker">Lesson 5</p>

# Inspect a corpus

A corpus is an explicit set of local members. It is not a directory scan and it
does not follow URLs, read standard input, discover files, or apply changes.
The specification states which sources and verified approved revisions belong
to the inspection.

## What you will learn

You will learn how corpus inspection changes the question from one document to
patterns across documents, why membership must be explicit, and how to read a
complete or partial result without treating it as a hidden quality grade.

## Move from one document to patterns

Document preparation asks, “What happened to this document?” Corpus inspection
asks, “What can we observe across this declared set of members?” The answer is
an aggregate report, not a replacement for individual document records.

Corpus inspection aggregates source-text-free evidence. Its static report can
group member status, extraction deltas, findings, and listed revision histories
by family, format, rule, or severity. It helps you ask pattern questions:

- Which document formats show a condition?
- Which extractors differ most often?
- Which approved revisions are included?
- Is the inspection complete, partial, or failed?

The report does not copy decision authority from a refinement. It does not embed
arbitrary source passages or recommend a change.

## Why explicit membership matters

An explicit corpus specification names each member and its local source. This
makes the collection inspectable too. A reader can see what was included and
what was not. A later file that appears in the same directory cannot silently
become part of the result.

The same principle applies to revisions. A corpus can list an approved revision
only when its associated refinement, diagnosis, and base evidence verify
together. A rejected refinement is useful evidence about a decision, but it is
not a prepared revision and cannot be included as one.

## Understand complete and partial work

The committed corpus examples contain PDF members. A complete run needs local
Docling models. If those models are missing, usable non-PDF members can still
produce a valid `PARTIAL` corpus record. This means that the report honestly
describes an incomplete declared collection.

An invalid listed revision is different. It stops publication instead of
becoming a partial result, because the requested evidence relationship cannot
be trusted. Learn to distinguish these two cases:

| Result | Meaning |
| --- | --- |
| `COMPLETE` | All declared members reached a usable result. |
| `PARTIAL` | The report records both usable members and member-level failures. |
| Failed publication | The requested inputs or evidence relationships were invalid. |

None of these statuses says whether the corpus is suitable for every downstream
task. They describe what this inspection could establish.

## Try it with the CLI and Workbench

After downloading the local Docling models, inspect the quality corpus:

~~~bash
docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
corpus inspect fixtures/corpus/quality-corpus.json \
  --docling-artifacts .cache/docling/models
~~~

Keep the Workbench open and select **Refresh workspace**. Refresh discovers
records that the CLI published after the Workbench started. It does not run a
new observation, diagnosis, or corpus inspection.

Choose the published corpus in the Corpora list. Read its totals and member
evidence in the central area. Then use the Inspector to view its summary,
evidence, and artifacts. The corpus view does not show a document stage
navigator because it answers questions about several members, not one document
lifecycle.

## What to remember

Corpus inspection makes a declared collection inspectable. It summarizes the
evidence that already exists; it does not discover a collection, change a
member, or replace the evidence for an individual document.

Next: [Practice the Complete Lifecycle](./complete-lifecycle.md).
