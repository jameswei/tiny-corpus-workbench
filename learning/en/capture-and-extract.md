<p class="guide-kicker">Lesson 2</p>

# Capture and extract

Extraction should describe a known source, not whatever happened to be at a
path later. The application opens the source once, captures its bytes, and gives
Docling and MarkItDown the same private snapshot.

## What you will learn

You will learn why the source is captured before extraction, why the project
keeps two extraction views, and why `DoclingDocument` is the document used by
the later stages.

## Start with one stable source

A filename is only a location. The file at that location can be replaced,
renamed, or changed while another process is working. Observation therefore
starts by reading one regular local file and capturing its bytes. The record
stores source identity such as filename, media type, size, and SHA-256.

This does not prove who authored the file or that it is trustworthy. It gives a
more limited but useful result: later stages can refer to the same captured
source instead of silently reading a newer file at the same path.

## Compare views without ranking them

The two extractors produce different useful views:

- Lossless `DoclingDocument` JSON is the canonical working representation.
- Docling Markdown is a readable rendering of that canonical document.
- MarkItDown Markdown is an independent extraction view.

The comparison records measurable differences. A difference is evidence to
inspect. It is not a score and it does not prove that one extractor is better.

~~~text
one captured source
  -> Docling -> canonical DoclingDocument -> readable Markdown
  -> MarkItDown -> independent Markdown
~~~

The canonical `DoclingDocument` matters because diagnosis and controlled
refinement need stable document references. They should not depend on a
best-looking Markdown rendering. Markdown remains useful because a learner can
read it easily. The independent MarkItDown output remains useful because it
shows what another extraction path produced from the same source.

## Ask useful comparison questions

Do not ask “Which extractor won?” Ask questions that the comparison can answer:

- Did both extractors produce a usable result?
- Are their normalized outputs equivalent or different?
- If they differ, what should we inspect before using either result?
- Which view is the canonical input for diagnosis and refinement?

Equivalent output does not prove that both views are complete or correct.
Different output does not prove that either view is wrong. The comparison is a
prompt for inspection, not an automated verdict.

## Understand an Observation record

An Observation preserves source identity, extractor outcomes, artifact hashes,
and comparison data. It does not diagnose a document or change it. You can
verify it later to check that its recorded bytes and relationships still agree.

Verification checks historical integrity. It does not prove authorship,
authenticity, or that a current file at the same path is the historical source.

An Observation contains more detail than a learner needs at first. Read it in
this order:

1. Confirm which source was captured.
2. Check whether each extractor produced a usable result.
3. Identify the canonical `DoclingDocument` handoff.
4. Read the comparison status as evidence, not a quality grade.
5. Open an artifact only when you need to inspect a concrete output.

This order prevents a common mistake: starting with a large JSON file before
you know what question it answers.

## Try it in the Workbench

Use **Add a document** and choose the guided `policy-memo.md` example.
Complete Observe. In the Observe stage, identify the source metadata, the two
extraction views, and the canonical handoff.

The guided memo is designed to show an ordinary clean observation. The important
result is not “passed.” It is that the Workbench has published inspectable
evidence for a specific source.

Then add `whitespace-cleanup.md`. Its observation has the same purpose, but it
will later lead to a diagnosis finding. Notice that Observe itself does not
predict or apply that later change.

::: warning Common mistake
Do not treat equal or different extraction outputs as a correctness verdict.
They only describe what the two extraction paths produced from the same source.
:::

::: tip What to remember
Observation protects the meaning of “this is the document we examined.” It
preserves source identity, keeps extraction outputs separate, and names one
canonical document for later mechanical work. It does not judge or change the
document.
:::

Next: [Inspect and Diagnose](./inspect-and-diagnose.md).
