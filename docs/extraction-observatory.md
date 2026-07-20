# Extraction Observatory

The v0.1 Extraction Observatory runs Docling and MarkItDown independently over
one local PDF, DOCX, Markdown, or UTF-8 text file. It publishes both views and a
descriptive comparison. It does not score extraction quality, diagnose a
problem, recommend a repair, or change the source.

## Setup

Use CPython 3.12 and the committed lockfile:

```bash
uv sync --frozen --python 3.12
```

PDF observation requires Docling's layout and table-structure models. Prefetch
them once while network access is intentionally available:

```bash
uv run --frozen docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
```

The models are local runtime data and are ignored by Git. Every PDF manifest
inventories each regular model file by relative path, size, and SHA-256 and
records a canonical inventory hash. Symlinks are rejected.

## Observe one source

```bash
uv run --frozen tcw observe fixtures/golden/policy-memo.pdf
```

Optional locations are explicit:

```bash
uv run --frozen tcw observe SOURCE \
  --output-root build/extraction-observatory \
  --docling-artifacts .cache/docling/models
```

`SOURCE` must be one regular local file ending in `.pdf`, `.docx`, `.md`, or
`.txt`. Directories, stdin, URLs, FIFOs, extension/content mismatches, invalid
OOXML, non-UTF-8 text, and NUL-containing text are rejected before extraction.
There is no directory or batch command.

Each valid attempt prints one compact JSON line to stdout identifying the
published manifest, run ID, and overall status. Diagnostics use stderr.

## Offline and fixed behavior

Observation forces Hugging Face and Transformers offline controls. Docling is
fixed to CPU, OCR disabled, table structure enabled, remote services disabled,
external plugins disabled, and the explicit local artifact path. MarkItDown
uses `convert_local()`, plugins disabled, no LLM client, and explicit
extension/media-type/UTF-8 hints for Markdown and text.

Missing PDF models fail with evidence; observation never downloads them.
Born-digital documents are the v0.1 target. Scans and OCR-heavy workflows are
outside this milestone.

## Published observation

The default location is:

```text
build/extraction-observatory/<source-key>/<run-id>/
  manifest.json
  comparison.json
  docling/document.json
  docling/document.md
  markitdown/document.md
```

`manifest.json` records source identity and hash, the exact dependency and
lockfile environment, fixed configurations, model inventory, extractor
results, artifact hashes, stable errors, and immutability markers.
`docling/document.json` is the unmodified output of Docling's
`save_as_json()`.

`comparison.json` normalizes line endings, Unicode, trailing horizontal space,
and surrounding blank lines. It then reports hashes, registered-anchor
presence, and exact counts for bytes, characters, lines, headings, list items,
pipe-table rows, and visible URLs. Deltas are always Docling minus MarkItDown.
There is no fuzzy score, semantic-equivalence claim, ranking, or quality label.

Both adapters are attempted independently. A validated partial or failed
attempt is still published with `INCOMPLETE` or `NOT_AVAILABLE` comparison
evidence. A source mutation or integrity failure discards staging and publishes
nothing.

## Reruns and compatibility

Every invocation creates a new UTC/randomized run ID. Published directories
are never reused, overwritten, repaired, or modified by the application. A
rerun preserves all earlier evidence.

Docling JSON compatibility is promised only for the exact `uv.lock`
environment that created an artifact. Dependency or model changes create new
observations; they do not migrate old ones. For a run, inspect the source, run
directory, committed lockfile, and recorded local model inventory together.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Both extractors completed successfully. |
| `1` | Unexpected top-level internal failure. |
| `2` | Usage, validation, or unsupported-media error. |
| `3` | One extractor failed or Docling reported partial success. |
| `4` | Neither extractor produced a usable view. |
| `5` | Source mutation, publication conflict, or artifact-integrity failure. |
| `6` | Locked runtime, dependency, or required model artifacts unavailable or incompatible. |

## Fixtures and verification

The `fixtures/authored/` JSON files are authoritative. They generate exactly
twelve CC0 files: three fictional families in PDF, DOCX, Markdown, and text.
Normal tests do not rewrite committed fixtures.

Fast checks:

```bash
uv sync --frozen --python 3.12
uv run --frozen --group test python -m unittest discover -s tests/unit -v
uv run --frozen --group test python -m compileall -q src tests tools
uv run --frozen --group fixtures python tools/generate_fixtures.py --check
uv run --frozen --group fixtures python tools/verify_fixtures.py
git diff --check
```

The checkout-portability regression creates a separate temporary checkout with
`core.autocrlf=true`, compares every fixture byte with its committed Git blob,
and repeats both fixture checks there:

```bash
uv run --frozen --group fixtures python tools/verify_checkout_portability.py
```

Full checks after model prefetch:

```bash
TCW_DOCLING_ARTIFACTS=.cache/docling/models \
  uv run --frozen --group test python -m unittest discover -s tests -v
```
