# Evidence-Based Diagnosis

Milestone v0.2 introduced an observation-only diagnosis contract with eight
rules. Milestone v0.3 accepts one verified observation or one verified applied
revision and runs ten rules. Diagnosis reads only the canonical
`DoclingDocument`. It does not use the MarkItDown comparison to produce
findings.

Diagnosis is local, offline, and read-only. It does not need model files. It
never changes the source, subject, originating observation, or extraction
artifacts.

## Commands

Create a diagnosis:

```bash
uv run --frozen tcw diagnose DOCUMENT_DIRECTORY
```

Choose another publication root:

```bash
uv run --frozen tcw diagnose DOCUMENT_DIRECTORY \
  --output-root build/evidence-based-diagnosis
```

Verify the published diagnosis:

```bash
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY
```

Compare a v0.3 diagnosis with its subject and rerun all rules:

```bash
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject DOCUMENT_DIRECTORY
```

`diagnose` accepts an intact v0.1 observation or an intact applied v0.3
revision. An observation's Docling result must be `SUCCESS` or
`PARTIAL_SUCCESS`. The command runs all ten rules. It has no rule or threshold
options.

For a diagnosis published by v0.2, retain the released observation-only
verification command:

```bash
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY \
  --observation OBSERVATION_DIRECTORY
```

The verifier selects the contract from the diagnosis manifest schema.
Use `--subject` for v0.3. Use `--observation` for the optional v0.2 observation
comparison and rule rerun.

## Published artifacts

The current `diagnose` command publishes the v0.3 contract. Its output path is:

```text
<output-root>/<source-key>/<subject-id>/<diagnosis-run-id>/
  diagnosis-manifest.json
  findings.json
  report.md
```

The publisher writes a private staging directory and uses an exclusive atomic
rename. It does not overwrite an existing run. Staging must contain exactly
the three expected regular files. A directory, symlink, socket, FIFO, device,
or other node aborts publication.
The resolved publication parent must not be the subject or a path inside the
subject. The source key and subject ID must each be one safe
path component. The resolved publication parent must stay inside the resolved
output root. The output root and existing publication path components must be
directories.

`diagnosis-manifest.json` records:

- source, subject, and originating observation identities
- subject manifest and canonical document hashes
- manifest schema version and diagnosis status
- CPython, lock, package, and dependency versions
- the complete fixed ruleset and parameter hash
- finding counts by severity and rule
- immutable descriptors for `findings.json` and `report.md`

`findings.json` is the machine-readable result. `report.md` is a deterministic
human-readable rendering. Repeated diagnosis of the same subject produces
byte-identical findings and reports. Run identifiers and timestamps in the
manifest are intentionally unique.

Each canonical item must declare the `self_ref` implied by its collection and
array position. Child references must resolve through those canonical paths.
Diagnosis rejects inconsistent paths before publication.

The v0.3 diagnosis ID is a full SHA-256 hash over canonical JSON with three
inputs: the subject descriptor, the canonical document SHA-256 as a separate
input, and the complete ruleset. The descriptor includes the subject kind and
ID, canonical document path, size and hash, and originating observation ID.
The subject manifest hash is provenance; it is not an input to the diagnosis
ID.
The v0.2 diagnosis ID instead binds the observation ID, observation manifest
hash, canonical document hash, and complete v0.2 ruleset.
Finding IDs bind the diagnosis, rule, sorted document references, and canonical
evidence.
Each rule has one closed evidence shape and a rule-specific document-reference
shape. Evidence fields from another rule are invalid.

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
| `TCW-D009 NORMALIZABLE_WHITESPACE` | `INFO` | Eligible body text or a body table cell has normalizable line endings or horizontal whitespace. |
| `TCW-D010 POSSIBLE_LINE_END_HYPHENATION` | `WARNING` | Eligible body text or a table cell has one deterministic lowercase line-end hyphenation candidate. |

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
Diagnosis neither modifies content nor approves a repair. See the
[Controlled Revisions guide](controlled-revisions.md) for explicit decisions.

## Verification

`verify-diagnosis` always checks the diagnosis inventory, schemas, hashes,
identities, counts, canonical JSON, fixed rule metadata, exact artifact
descriptor meanings, canonical ordering, and deterministic report.
Diagnosis and verification read active installed distribution metadata. The
installed project and extractor versions must match the source contract.
`uv.lock` must match the committed exact-lock byte identity before publication
or rule rerun.

`artifact_integrity` is one of:

- `VERIFIED`
- `INTEGRITY_MISMATCH`
- `BROKEN`

For v0.3, `--subject` compares the recorded subject with an observation or
applied revision. `subject_state` is one of:

- `MATCH`
- `CHANGED`
- `MISSING`
- `ERROR`

Without `--subject`, it is `NOT_CHECKED`. The match check includes the complete
subject descriptor, subject manifest identity, and source identity.

For v0.2, `--observation` retains the released observation-only comparison.
Its result uses `observation_state` with the same status values. Without
`--observation`, it is `NOT_CHECKED`.

The corresponding rule rerun uses `derivation_state`:

- `MATCH`
- `MISMATCH`
- `ERROR`
- `NOT_CHECKED`

Subject or observation state and derivation state are advisory. An intact
diagnosis still exits zero when its optional external subject is missing or
changed.

## Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Diagnosis completed, or diagnosis integrity verified. |
| `1` | Unexpected internal failure. |
| `2` | Invalid or unsupported input. |
| `4` | Canonical Docling artifact is unavailable. |
| `5` | Integrity change, verification failure, or publication conflict. |
| `6` | Locked runtime, schema, or Docling API is incompatible. |

`diagnose` failures write no stdout. `verify-diagnosis` usage, runtime, and
internal failures also write no stdout. A verifier integrity failure exits `5`
after it writes the compact JSON verification result to stdout. Application
diagnostics are sanitized.

## Integrity limits

Diagnosis snapshots the complete subject inventory before analysis and
checks it again before publication. A changed path, kind, identity, size,
hash, mode, or timestamp aborts publication.

Local hashes provide tamper evidence within the trusted-local model. They are
not signatures and do not prove who created an artifact. Copy a publication
before destructive experiments.
