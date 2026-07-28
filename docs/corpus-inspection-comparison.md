# Corpus Inspection and Comparison

Milestone v0.4 processes one explicit small corpus through the released
observation and diagnosis contracts. It aggregates evidence and publishes one
static local report.

Corpus inspection is read-only with respect to existing evidence. It never
drafts, approves, rejects, or applies a refinement.

## Commands

Inspect a committed example corpus:

```bash
uv run --frozen tcw inspect-corpus \
  fixtures/corpus/golden-matrix.json
```

Select other local output and model directories:

```bash
uv run --frozen tcw inspect-corpus CORPUS_SPEC \
  --output-root build/corpus-inspection \
  --docling-artifacts .cache/docling/models
```

Verify a published corpus:

```bash
uv run --frozen tcw verify-corpus CORPUS_DIRECTORY
```

Compare the historical run with its current live inputs:

```bash
uv run --frozen tcw verify-corpus CORPUS_DIRECTORY \
  --spec CORPUS_SPEC
```

`inspect-corpus` writes one compact JSON line to stdout. The line contains the
corpus ID, snapshot ID, run ID, member count, status, and absolute manifest
path. Diagnostics use stderr.

## Corpus specification

The specification is a closed JSON document:

```json
{
  "corpus_id": "example-corpus",
  "title": "Example corpus",
  "members": [
    {
      "member_id": "example-md",
      "family": "example",
      "format": "md",
      "source": "example.md"
    }
  ]
}
```

Use `pdf`, `docx`, `md`, or `txt` as the format. Paths are relative to the
specification directory unless they are absolute.

List each source. The command does not accept URLs, stdin, directories, globs,
or automatic discovery. Member IDs and resolved source files must be unique.
The suffix and media type must match the declared format.

The command rejects symbolic links and unsafe filesystem nodes in the
specification, sources, model inventory, and revision bundles.

## Optional revision comparison

A member can list an existing applied revision:

```json
{
  "member_id": "example-md",
  "family": "example",
  "format": "md",
  "source": "example.md",
  "revisions": [
    {
      "refinement": "records/refinement",
      "diagnosis": "records/diagnosis",
      "base": "records/base"
    }
  ]
}
```

The three paths form one verification bundle. The refinement must have status
`APPLIED`. Artifact integrity, diagnosis state, base state, derivation, and
reversibility must all verify. The source hash and media type must match the
corpus member.

A rejected decision is not a revision because it has no prepared document.
Corpus inspection reads verified revisions. It does not call a refinement
draft or resolution function.

## Execution and output

The command validates the full specification and prepares the configured
extractors, diagnosis rules, and local model inventory before it processes a
member. It then processes members sequentially in sorted member-ID order.

Each member gets an observation. A usable Docling document also gets a
diagnosis. MarkItDown remains a descriptive comparison view and never creates
findings.

One member failure does not stop the remaining members. An unavailable
application dependency stops the run before publication.

The output layout is:

```text
<output-root>/<corpus-id>/<corpus-run-id>/
  corpus-manifest.json
  corpus-spec.json
  summary.json
  report/
    index.html
    styles.css
  members/
    <member-id>/
      observations/...
      diagnoses/...
```

The publisher builds this tree in one private sibling staging directory. It
performs the full self-contained corpus verification in that directory. It
then rechecks the specification, sources, model inventory, and revision
bundles immediately before one exclusive atomic rename. An invalid staged run
is never published. The publisher never overwrites an earlier run.

The user-authored specification has a strict closed schema. Generated corpus
records use compact structural schemas. Readable Python validation owns stage
and nullability rules. The verifier rebuilds the summary from nested evidence
and requires an exact match. This avoids a second copy of the aggregation
rules in JSON Schema.

## Snapshot and aggregation

The logical corpus ID comes from the specification. The snapshot ID binds:

- the normalized specification
- source identities and hashes
- extractor and diagnosis configuration
- the PDF model inventory when required
- verified revision identities and inventory fingerprints

The identity does not contain package, Python, dependency, lockfile, or build
metadata.

`summary.json` contains no arbitrary source passages. It groups:

- member status by family and format
- extractor availability
- exact Docling-minus-MarkItDown metrics
- findings by rule, severity, family, and format
- affected-member counts
- revisions by family, format, finding rule, and refiner
- revision lineage, hashes, and affected-reference counts
- stable sanitized member errors

The summary does not contain quality scores, extractor rankings, semantic
equivalence claims, aggregate severity scores, or automatic recommendations.

## Static report

Open `report/index.html` in a browser. The report needs no server and makes no
network request. It contains no JavaScript, analytics, remote font, or remote
resource.

Use the report sections to inspect:

- completion status
- the family-by-format matrix
- extractor comparison metrics
- findings by rule and severity
- revision and transformation history
- incomplete members and integrity notes

The report does not embed source or prepared-document passages. It links to
local evidence. Generated observation and diagnosis links stay inside the
corpus run.

Revision links point to the explicitly supplied external local records. If you
move those records, the links and live-input advisory states can change. This
does not alter the historical corpus artifact integrity.

## Example corpora

The golden matrix contains 12 members: three families in four formats. Every
member must complete with both extractor views and a diagnosis.

The expected golden finding outcome is exact:

- nine D009 findings
- D009 occurs only in the three TXT members
- zero D010 findings
- zero findings from every other rule

The TXT findings describe repeated spaces in aligned plain-text table rows.
They do not authorize whitespace normalization.

The quality corpus contains five sources. It must cover exactly D002, D003,
D004, D005, D007, D009, and D010.

## Status and exit codes

Corpus status is:

- `COMPLETE`: every member has both views, a usable canonical document, a
  completed diagnosis, and fully verified listed revisions.
- `PARTIAL`: some evidence is usable, but one member, extractor, or diagnosis
  is incomplete.
- `FAILED`: no member produced a usable extraction view.

The command rejects an invalid or unverifiable listed revision before member
processing. This condition is invalid specification input, not a partial
corpus result.

| Exit | Meaning |
| --- | --- |
| `0` | A complete report was published, or corpus integrity verified. |
| `1` | An unexpected internal failure occurred. |
| `2` | The command, specification, or corpus-directory argument is invalid. |
| `3` | A partial report was published. |
| `4` | A failed report was published with no usable member view. |
| `5` | An input changed, an unsafe path was found, integrity failed, or publication conflicted. |
| `6` | A required application dependency is unavailable. |

Missing PDF models produce member-level failures. Non-PDF members continue.
The command never downloads a model.

## Verification and live inputs

Default verification is self-contained. It checks:

- closed schemas and canonical JSON
- snapshot, member, revision, and nested-record identities
- hashes, descriptor sizes, statuses, counts, and recorded domain configuration
- every nested observation
- every nested diagnosis and a fresh deterministic rule evaluation
- exact regeneration of the summary, HTML, and CSS
- report navigation and link safety

`--spec` adds advisory checks for the original specification, sources, model
inventory, and external revision bundles. Advisory status is `MATCH`,
`CHANGED`, `MISSING`, or `ERROR`.

Advisory drift does not change exit `0` when the historical corpus artifact is
internally intact.

## Privacy and integrity limits

Corpus inspection runs locally and offline. It does not transmit a document.
The static report avoids arbitrary source text, but linked local evidence can
contain source-derived content.

Use project fixtures before private documents. Keep private report directories
under suitable filesystem access controls.

Hashes, closed schemas, snapshots, and atomic publication detect ordinary
corruption and uncoordinated changes. They are not signatures. They do not
prove authorship, authenticity, or a trusted timestamp.
