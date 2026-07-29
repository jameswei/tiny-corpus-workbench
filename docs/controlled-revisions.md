# Controlled Revisions

Controlled refinement turns one supported diagnosis finding into one proposal.
A finding never authorizes a change by itself. A person supplies the decision
with an explicit command flag.

## Commands

Create and verify a diagnosis:

```bash
uv run corpus diagnose DOCUMENT_DIRECTORY
uv run corpus verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject DOCUMENT_DIRECTORY
```

Draft one canonical proposal:

```bash
uv run corpus draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID \
  --base DOCUMENT_DIRECTORY \
  --output proposal.json
```

Inspect `proposal.json`. Do not edit it. The file is strict UTF-8 canonical
JSON with one final newline. Its exact descriptor is:

```text
path: proposal.json
role: refinement-proposal
media_type: application/json
```

Approve or reject with exactly one flag:

```bash
uv run corpus resolve-refinement proposal.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base DOCUMENT_DIRECTORY \
  --approve

uv run corpus resolve-refinement proposal.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base DOCUMENT_DIRECTORY \
  --reject
```

Zero decision flags or both decision flags are invalid. `--diagnosis` and
`--base` are required. Use `--output-root` to select another publication root.

Verify the publication:

```bash
uv run corpus verify-refinement REFINEMENT_DIRECTORY \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base DOCUMENT_DIRECTORY
```

## One structured decision authority

`refinement-manifest.json.decision` is the only machine-authoritative persisted decision field.
Its value is `APPROVED` or `REJECTED`. The manifest
has no refinement `status`.

Proposal state `REQUESTED` and transformation state `APPLIED` are lifecycle
facts. They do not authorize a revision. Transformation and history use
`draft_id`; they do not contain an actor, note, or another decision field.

`report.md` is a deterministic, non-authoritative human rendering. It can show
the manifest decision, draft, finding, refiner, and revision identities. The
verifier regenerates its exact bytes and rejects a changed report. No command
consults the report as authority.

## Exact publication matrix

An approved publication contains:

```text
refinement-manifest.json
proposal.json
report.md
transformation.json
history.json
prepared/document.json
prepared/document.md
```

Its manifest decision is `APPROVED`, `revision_id` is non-null, and the
transformation state is `APPLIED`. An observation base has `parent: null`. A
refinement base has a parent that matches the base revision, run, manifest
hash, and prepared-document hash.

A rejected publication contains only:

```text
refinement-manifest.json
proposal.json
report.md
```

Its manifest decision is `REJECTED`, `revision_id` and `parent` are null, and
derivation and reversibility are `NOT_APPLICABLE`. It has no transformation,
history, or prepared directory.

## Proposal freshness and publication safety

Resolution accepts one local non-symlink regular proposal file. It captures the
raw bytes and stable file identity, validates the proposal, and recomputes the
complete proposal from the diagnosis and base. The captured bytes must equal
the recomputed canonical bytes exactly.

Changed key order, whitespace, encoding, byte order mark, final newline,
fields, diagnosis evidence, or base evidence causes failure. Before atomic
publication, resolution rechecks the diagnosis, base, proposal identity, and
proposal bytes. Failure removes staging, publishes nothing, and does not
change the proposal or either input record. Publication stages the verified
captured proposal bytes without reserialization.

## Supported refiners

| Finding | Refiner | Change |
| --- | --- | --- |
| `TCW-D009` | `TCW-R001 WHITESPACE_NORMALIZATION` | Normalizes line endings and horizontal whitespace. |
| `TCW-D007` | `TCW-R002 REPEATED_BOILERPLATE_REMOVAL` | Moves repeated margin items from body to furniture. |
| `TCW-D010` | `TCW-R003 DETERMINISTIC_DEHYPHENATION` | Removes one supported line-end hyphen and line break. |

The refiners preserve `orig`, provenance, and stable references. Re-diagnose
an approved revision before drafting its successor.

## Verification and corpus eligibility

Verification checks the exact inventory, regular file kinds, hashes, canonical
JSON, identities, proposal freshness evidence, manifest decision, parent and
history chains, forward derivation, inverse replay, prepared Markdown, and the
derived report.

Only a record with manifest decision `APPROVED`, a non-null revision ID, the
exact approved inventory, coherent evidence, and all required verification
states can be a corpus revision. Rejected records are never revision inputs.
Persisted corpus JSON may reference refinement evidence but does not copy the
decision.

## Exit codes and limits

Success, including rejection, is `0`. Usage and input errors are `2`;
integrity failures are `5`; runtime contract failures are `6`; unexpected
internal failures are `1`. Canonical-document unavailability remains `4`
where that lifecycle operation applies.

The trusted-local hashes and checks detect ordinary corruption. They are not
signatures and do not establish authorship, authenticity, or a trusted
timestamp. Batch refinement, semantic rewriting, services, and downstream RAG
work remain outside this workflow.
