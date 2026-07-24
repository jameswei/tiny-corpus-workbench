# Controlled Revisions

Milestone v0.3 turns one supported diagnosis finding into one explicit
decision. An approval creates one immutable successor revision. A rejection
creates an immutable decision record and no prepared document.

A finding never authorizes a change by itself. The person who resolves the
decision supplies an actor label in `decided_by`.

## Commands

Diagnose an observation or an applied v0.3 revision:

```bash
uv run --frozen tcw diagnose DOCUMENT_DIRECTORY
uv run --frozen tcw verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject DOCUMENT_DIRECTORY
```

Draft one supported finding:

```bash
uv run --frozen tcw draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID \
  --base DOCUMENT_DIRECTORY \
  --output decision.json
```

The draft is a closed JSON document. Its proposal is immutable. Edit only:

- `decision.state`: change `PENDING` to `APPROVED` or `REJECTED`
- `decision.decided_by`: set a nonempty actor label
- `decision.note`: keep `null` or add a short note

Resolve and verify the decision:

```bash
uv run --frozen tcw resolve-refinement decision.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base DOCUMENT_DIRECTORY

uv run --frozen tcw verify-refinement REFINEMENT_DIRECTORY \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base DOCUMENT_DIRECTORY
```

Use `--output-root` with `resolve-refinement` to select another publication
root. The default is `build/controlled-revisions`.

## Supported findings and refiners

| Finding | Refiner | Change |
| --- | --- | --- |
| `TCW-D009 NORMALIZABLE_WHITESPACE` | `TCW-R001 WHITESPACE_NORMALIZATION` | Normalizes line endings and horizontal whitespace. |
| `TCW-D007 REPEATED_PAGE_MARGIN_TEXT` | `TCW-R002 REPEATED_BOILERPLATE_REMOVAL` | Moves repeated margin items from body to furniture. |
| `TCW-D010 POSSIBLE_LINE_END_HYPHENATION` | `TCW-R003 DETERMINISTIC_DEHYPHENATION` | Removes an approved line-end hyphen and its one line break. |

The refiners change `text`, not `orig`. They preserve provenance and stable
item references. Boilerplate removal changes the content layer and body or
furniture membership. It does not delete the item.

## Decision and publication states

A draft starts with proposal state `REQUESTED` and decision state `PENDING`.
Resolution rejects `PENDING`.

An approved result has manifest status `APPLIED` and contains:

```text
refinement-manifest.json
decision.json
report.md
transformation.json
history.json
prepared/document.json
prepared/document.md
```

A rejected result has status `REJECTED`. It contains only the manifest,
decision, and report. Its `revision_id` is null.

The publisher snapshots and rechecks the decision, diagnosis, and base. It
uses an exclusive atomic directory rename. It does not overwrite a result or
publish inside an input directory.

## Revision lineage

One approval creates one successor. The transformation records the parent,
finding, decision, actor, refiner version, affected references, exact edits,
and whole-document hashes.

An applied child copies the verified parent history and appends one
transformation. Re-diagnose the child before you draft another change:

```bash
uv run --frozen tcw diagnose FIRST_REFINEMENT_DIRECTORY
```

Use that new diagnosis and the first refinement directory as the base for the
next draft and resolution.

## Verification and reversibility

`verify-refinement` always checks the closed schemas, exact inventory, regular
file kinds, sizes, hashes, identities, status, and history shape.

Without optional inputs, diagnosis and base states are `NOT_CHECKED`. A
rejected record uses `NOT_APPLICABLE` for derivation and reversibility.

With matching `--diagnosis` and `--base`, verification recomputes the forward
edit and requires byte equality with `prepared/document.json`. It also replays
the inverse evidence and requires the original base document bytes.

Copy a publication before a tamper experiment. For example, edit `report.md`
in the copy and verify it. The verifier reports an integrity failure and exits
`5`. Never edit the original publication for an experiment.

## Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | The operation completed, including a recorded rejection. |
| `1` | An unexpected internal failure occurred. |
| `2` | Input, usage, decision, or supported-finding validation failed. |
| `4` | The canonical Docling document is unavailable. |
| `5` | Input integrity changed, verification failed, or publication conflicted. |
| `6` | The locked runtime, schema, or Docling API is incompatible. |

## Integrity limits

The project uses a trusted-local model. Hashes, closed schemas, snapshots, and
exclusive publication detect ordinary corruption and uncoordinated changes.
They are not signatures. They do not establish authorship, authenticity, or a
trusted timestamp. A coordinated rewrite of a complete local record is outside
this boundary.

Batch refinement, semantic rewriting, heading repair, table reconstruction,
duplicate-block deletion, LLM cleanup, services, and downstream RAG work are
outside v0.3.
