# Observe Extraction

## Purpose

Observe how two extractors represent the same captured source. Preserve the
evidence before you diagnose or refine anything.

## Objectives

After this lesson, you can:

- distinguish a raw source, private snapshot, extraction view, canonical
  document, and observation record;
- compare Docling and MarkItDown without ranking them;
- verify a published observation independently;
- separate integrity, freshness, and authenticity questions.

## Mental model

```text
raw source -> private snapshot -> Docling view -----+
                              -> MarkItDown view ---+-> observation record
```

The application opens the source once and gives both extractors the same
private bytes. The lossless Docling JSON is canonical. Docling Markdown and
MarkItDown Markdown are readable extraction views. Their differences are
descriptive evidence, not quality scores.

## Observe Markdown

Run a model-free observation:

```bash
corpus observe fixtures/golden/policy-memo.md
```

The command prints one JSON object. Set `OBSERVATION_DIRECTORY` to the parent
directory of its `manifest` path.

```bash
corpus verify OBSERVATION_DIRECTORY
```

Inspect these files:

```text
manifest.json
comparison.json
docling/document.json
docling/document.md
markitdown/document.md
```

The manifest records source identity, extractor results, configuration, and
artifact hashes. `comparison.json` records deterministic counts and deltas.
A delta is Docling minus MarkItDown. A nonzero delta identifies a difference
to inspect. It does not identify the better output.

An untouched record must verify with artifact status `VERIFIED`. This status
means that recorded bytes and relationships agree. It does not prove who made
the record or whether an external party should trust it.

## Use the Workbench as another entry

Start the Workbench with `corpus workbench --no-open`. In the browser, select
**Observe policy memo** for a guided input. You can also upload one `.docx`,
`.md`, `.pdf`, or `.txt` file up to 32 MiB.

Both paths call the same observation service as the CLI. The browser shows
uploaded-source metadata, but it does not display or serve the uploaded
original.

## Optional PDF extension

PDF observation needs a local model inventory. After the download described
in the [learning hub](README.md), run:

```bash
corpus observe fixtures/golden/policy-memo.pdf \
  --docling-artifacts .cache/docling/models
```

Observation stays offline. The application checks the sorted local model
inventory before and after extraction. It does not download a missing model.
A missing inventory produces recorded failure evidence.

## Safe integrity experiment

Copy a record before you change it:

```bash
LAB_ROOT="$(mktemp -d)"
cp -R OBSERVATION_DIRECTORY "$LAB_ROOT/"
LAB_OBSERVATION="$LAB_ROOT/$(basename OBSERVATION_DIRECTORY)"
printf '\nlearner edit\n' >> "$LAB_OBSERVATION/markitdown/document.md"
corpus verify "$LAB_OBSERVATION"
```

Expected result: verification exits `5` and reports an integrity problem. It
does not repair the copied record.

Optional `--source` and `--docling-artifacts` checks answer freshness
questions about current inputs. A changed source advisory can coexist with a
historical artifact status of `VERIFIED`. Freshness is not integrity.

## Knowledge check

1. Why do both extractors use one private snapshot?
2. Why is a comparison delta not a quality score?
3. What does `VERIFIED` not prove?
4. Why can current-source state change without changing record integrity?

## Answers

1. The snapshot prevents the extractors from reading different source bytes.
2. A delta describes a measurable difference but does not establish correctness.
3. It does not prove authorship, authenticity, or a trusted timestamp.
4. The record preserves historical bytes; the advisory checks a current input.

Next: [Diagnose with evidence](diagnose-with-evidence.md).
