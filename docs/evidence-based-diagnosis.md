# Evidence-Based Diagnosis

Milestone v0.2 adds deterministic diagnosis over one verified extraction
observation. Diagnosis reads only the canonical `DoclingDocument`. It does not
use the MarkItDown comparison to produce findings.

Diagnosis is local, offline, and read-only. It does not need model files. It
never changes the source, observation, or extraction artifacts.

## Commands

Create a diagnosis:

```bash
uv run --frozen tcw diagnose OBSERVATION_DIRECTORY
```

Choose another publication root:

```bash
uv run --frozen tcw diagnose OBSERVATION_DIRECTORY \
  --output-root build/evidence-based-diagnosis
```

Verify the published diagnosis:

```bash
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY
```

Compare it with its observation and rerun all rules:

```bash
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY \
  --observation OBSERVATION_DIRECTORY
```

`diagnose` accepts an intact v0.1 observation. The Docling result must be
`SUCCESS` or `PARTIAL_SUCCESS`, and canonical JSON must be available. The
command runs all eight rules. v0.2 has no rule or threshold options.

## Published artifacts

The output path is:

```text
<output-root>/<source-key>/<observation-run-id>/<diagnosis-run-id>/
  diagnosis-manifest.json
  findings.json
  report.md
```

The publisher writes a private staging directory and uses an exclusive atomic
rename. It does not overwrite an existing run.

`diagnosis-manifest.json` records:

- source and observation identities
- observation manifest and canonical document hashes
- Docling schema identity
- CPython, lock, package, and dependency versions
- the complete fixed ruleset and parameter hash
- finding counts by severity and rule
- immutable descriptors for `findings.json` and `report.md`

`findings.json` is the machine-readable result. `report.md` is a deterministic
human-readable rendering. Repeated diagnosis of the same observation produces
byte-identical findings and reports. Run identifiers and timestamps in the
manifest are intentionally unique.

The diagnosis ID is a full SHA-256 hash over the observation identity, the
observation manifest hash, the canonical document hash, and the ruleset.
Finding IDs bind the diagnosis, rule, sorted document references, and canonical
evidence.

## Rules

Text normalization uses Unicode NFC, normalized line endings, collapsed
Unicode whitespace, and removed outer whitespace. It preserves case.

| Rule | Severity | Fixed condition |
| --- | --- | --- |
| `TCW-D001 EMPTY_DOCUMENT` | `ERROR` | Body has no non-whitespace text-item or table-cell content. |
| `TCW-D002 SUSPICIOUSLY_SHORT_DOCUMENT` | `INFO` | Body has 1–199 non-whitespace characters. D001 suppresses this rule. |
| `TCW-D003 REPLACEMENT_CHARACTER` | `ERROR` | U+FFFD occurs in a text item or table cell. |
| `TCW-D004 DUPLICATE_TEXT_BLOCK` | `WARNING` | The same case-sensitive normalized body text or paragraph of at least 80 characters occurs twice. |
| `TCW-D005 HEADING_LEVEL_JUMP` | `WARNING` | The first body heading is deeper than level 1, or a later heading increases by more than one level. |
| `TCW-D006 ORPHAN_CAPTION` | `WARNING` | A caption has no valid incoming table or picture link, or a declared caption link is invalid. |
| `TCW-D007 REPEATED_PAGE_MARGIN_TEXT` | `WARNING` | PDF body text of 3–200 characters repeats in the same outer 10% band on at least three pages. |
| `TCW-D008 MISSING_PDF_PROVENANCE` | `WARNING` | A PDF text, table, or picture item has no provenance entry. |

D007 converts boxes to a top-left origin and groups top and bottom occurrences
separately. Furniture content is excluded. D006 does not report a table or
picture only because it has no caption.

Evidence contains stable references, counts, hashes, offsets, coordinates,
page numbers, or relationship kinds. It does not copy arbitrary source
passages.

## Status and severity

The manifest status is:

- `FINDINGS` when at least one rule produces a finding
- `NO_FINDINGS` when no fixed rule produces a finding

`NO_FINDINGS` is not proof that the document is correct. The rules detect only
their defined mechanical conditions.

Severity communicates the condition type. It does not authorize a change.
Diagnosis neither modifies content nor approves a repair. Controlled revisions
begin in a later milestone.

## Verification

`verify-diagnosis` always checks the diagnosis inventory, schemas, hashes,
identities, counts, canonical ordering, and deterministic report.

`artifact_integrity` is one of:

- `VERIFIED`
- `INTEGRITY_MISMATCH`
- `BROKEN`

When `--observation` is present, `observation_state` is one of:

- `MATCH`
- `CHANGED`
- `MISSING`
- `ERROR`

Without that option it is `NOT_CHECKED`.

Rule rerun state is:

- `MATCH`
- `MISMATCH`
- `ERROR`
- `NOT_CHECKED`

Observation and derivation states are advisory. An intact diagnosis still
exits zero when its optional observation is missing or changed.

## Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Diagnosis completed, or diagnosis integrity verified. |
| `1` | Unexpected internal failure. |
| `2` | Invalid or unsupported input. |
| `4` | Canonical Docling artifact is unavailable. |
| `5` | Integrity change, verification failure, or publication conflict. |
| `6` | Locked runtime, schema, or Docling API is incompatible. |

Failures write no stdout. Application diagnostics are sanitized.

## Integrity limits

Diagnosis snapshots the complete observation inventory before analysis and
checks it again before publication. A changed path, kind, identity, size,
hash, mode, or timestamp aborts publication.

Local hashes provide tamper evidence within the trusted-local model. They are
not signatures and do not prove who created an artifact. Copy a publication
before destructive experiments.
