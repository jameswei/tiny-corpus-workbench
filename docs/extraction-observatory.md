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
Empty Markdown and text files are also rejected because the manifest requires a
positive source size. There is no directory or batch command.

Before capture, `tcw` checks CPython 3.12, the exact locked package versions,
and every adapter API used for conversion and serialization. It then opens the
non-symlink source once and copies it into an owner-only private snapshot. The
descriptor metadata must remain stable throughout that copy. Both extractors
consume the same validated snapshot, which is removed before publication. A
later change to the original source cannot mix extractor inputs and does not
invalidate the completed observation.

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

For PDF input, the complete sorted model inventory is checked before extraction
and again immediately before final staged verification. An added, removed,
replaced, changed, unreadable, or newly symlinked model file aborts publication.
Non-PDF observations do not inventory the model directory.

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
results, artifact hashes, stable errors, and `application_immutable` markers.
The fixed runtime dependency mapping is `docling==2.113.0`,
`docling-core==2.87.1`, and `markitdown==0.1.6`; verification rejects a changed,
missing, or additional entry.
`docling/document.json` is the unmodified output of Docling's
`save_as_json()`.

`comparison.json` normalizes line endings, Unicode, trailing horizontal space,
and surrounding blank lines. It then reports hashes, registered-anchor
presence, and exact counts for bytes, characters, lines, headings, list items,
pipe-table rows, and visible URLs. Deltas are always Docling minus MarkItDown.
There is no fuzzy score, semantic-equivalence claim, ranking, or quality label.

Both adapters are attempted independently. A validated partial or failed
attempt is still published with `INCOMPLETE` or `NOT_AVAILABLE` comparison
evidence. A source mutation during snapshot capture or another integrity
failure discards staging and publishes nothing. Immediately before publication,
the persisted manifest and comparison must satisfy their bundled schemas, and
every staged regular file and directory must match the complete captured
inventory. Invalid schemas or missing, changed, symlinked, replaced, or
unexpected content abort the run.

## Verify a published observation

Verification is self-contained by default and does not import either extractor:

```bash
uv run --frozen tcw verify OBSERVATION_DIRECTORY
```

The command writes exactly one compact JSON report to stdout. `VERIFIED` means
the supported schemas, expected paths, regular-file kinds, recorded sizes and
hashes, observation identity, statuses, and internal references agree. Ordinary
artifact corruption reports `INTEGRITY_MISMATCH`; an uninterpretable manifest,
identity, or reference reports `BROKEN`. Both failure states exit `5` and leave
the observation unchanged. Decoded JSON with a null, scalar, array, or malformed
nested shape also completes as `BROKEN`; it is never treated as an absent value
or an internal verifier failure.

Structural checks include RFC 3339 timestamp syntax, nonnegative integral
durations, and single-line sanitized errors. For a usable Docling result, the
manifest schema name and version must match the identity inside the intact
`docling/document.json`, and its exact-lock compatibility statement must be
exact. A failed Docling result records no document schema identity: its name,
version, and compatibility fields are `null`.

Current provenance checks are opt-in and advisory:

```bash
uv run --frozen tcw verify OBSERVATION_DIRECTORY --source SOURCE
uv run --frozen tcw verify OBSERVATION_DIRECTORY \
  --docling-artifacts .cache/docling/models
```

The source state is `MATCH`, `CHANGED`, `MISSING`, or `ERROR`. The PDF model
state uses the same states; a non-PDF observation is `NOT_APPLICABLE` whenever
a model path is supplied, even if that path is missing or invalid. Without an
option the corresponding state is `NOT_CHECKED`. These advisories never
change historical artifact integrity or the verifier exit code. Model matching
uses the canonical relative-path, size, and hash inventory, so an equivalent
model inventory may be checked from a different absolute directory.

## Reruns and compatibility

Every invocation creates a new UTC/randomized run ID. Published directories
are never reused, overwritten, repaired, or modified by the application. A
rerun preserves all earlier evidence. Rebuilding means running `tcw observe`
again to create a new observation; `tcw verify` never repairs or quarantines a
run.

Docling JSON compatibility is promised only for the exact `uv.lock`
environment that created an artifact. Dependency or model changes create new
observations; they do not migrate old ones. For a run, inspect the source, run
directory, committed lockfile, and recorded local model inventory together.

“Application-immutable” describes `tcw` behavior, not filesystem enforcement.
The local hashes and verifier make runs tamper-evident for ordinary corruption
and uncoordinated changes. v0.1 trusts the local user, operating system, Python
process, and filesystem. It does not provide signatures, attribution, trusted
timestamps, ACL enforcement, or detection of a coordinated rewrite of a
manifest and all referenced artifacts. Deliberate same-user mutation timed
after final staged verification is also outside this trusted-local model.

`VERIFIED` is limited to structural validity, persisted artifact integrity, and
the semantic relationships enumerated above. It does not authenticate a
non-derivable metadata value. For example, replacing one valid `created_at`
timestamp with another valid RFC 3339 timestamp cannot be distinguished from
the original local record and is not a v0.1 verification failure.

## Observe exit codes

| Code | Meaning |
| --- | --- |
| `0` | Both extractors completed successfully. |
| `1` | Unexpected top-level internal failure. |
| `2` | Usage, validation, or unsupported-media error. |
| `3` | One extractor failed or Docling reported partial success. |
| `4` | Neither extractor produced a usable view. |
| `5` | Source mutation, publication conflict, or artifact-integrity failure. |
| `6` | Locked runtime, dependency, or required model artifacts unavailable or incompatible. |

`tcw verify` uses `0` for `VERIFIED`, `2` for an invalid observation-directory
argument, `5` for `INTEGRITY_MISMATCH` or `BROKEN`, `6` when its bundled schema
runtime is unavailable or incompatible, and `1` for an unexpected verifier
failure. Advisory source and model states do not affect those codes.

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
