# Control a Document Revision

## Purpose

Connect one finding to a deterministic refiner. Inspect the proposal, then
record an explicit approval or rejection.

## Mental model

```text
finding -> supported refiner -> proposal -> human decision
                                      +-> approve -> prepared revision
                                      +-> reject  -> no revision
```

A proposal is a read-only suggestion. A decision supplies authority. An
approved revision preserves lineage, forward derivation, and reversal
evidence. It never overwrites its base.

## Draft D009 with R001

Observe the whitespace fixture:

```bash
corpus observe fixtures/refinement/whitespace-cleanup.md
```

Read the compact JSON output. Set `OBSERVATION_DIRECTORY` to the parent
directory of its `manifest` path. Then diagnose the observation:

```bash
corpus diagnose OBSERVATION_DIRECTORY
```

Read the diagnosis output. Set `DIAGNOSIS_DIRECTORY` to the parent directory
of its `manifest` path. Open `findings.json`, choose the D009 finding, and set
`FINDING_ID` to its finding ID.

```bash
corpus draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID \
  --base OBSERVATION_DIRECTORY \
  --output proposal.json
```

D009 maps to R001 whitespace normalization. Inspect `proposal.json`, but do
not edit it. It records proposal state `REQUESTED`, exact edits, inverse edits,
the diagnosis and base identities, and a draft ID.

## Approve and verify

```bash
corpus resolve-refinement proposal.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY \
  --approve
corpus verify-refinement REFINEMENT_DIRECTORY \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY
```

Inspect the approved record. It contains the proposal, report,
transformation, history, and prepared document artifacts. Its decision is
`APPROVED`; derivation and reversibility are `MATCH`; its revision ID is not
null. The history links the immutable successor to its base and exact edits.

## Reject and compare

Draft a second proposal with a different output filename:

```bash
corpus draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID \
  --base OBSERVATION_DIRECTORY \
  --output proposal-reject.json
```

Resolve it with `--reject`:

```bash
corpus resolve-refinement proposal-reject.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY \
  --reject
```

The rejected record contains a manifest, `proposal.json`, and `report.md`. Its
decision is `REJECTED`. Its revision ID and parent are null. It has no prepared
document, transformation, or history. Derivation and reversibility are
`NOT_APPLICABLE`.

Use exactly one decision flag. The CLI rejects zero flags or both flags before
publication. In the Workbench, choose **Approve** or **Reject**, then select
**Record decision**. These choices supply the same mutually exclusive
decision.

`refinement-manifest.json.decision` is the only persisted structured decision
authority. Proposal state `REQUESTED`, transformation state `APPLIED`, UI
state, HTTP state, and the action token are not decision authority.

## Safe integrity experiment

Copy one approved record, then change its report:

```bash
LAB_ROOT="$(mktemp -d)"
cp -R REFINEMENT_DIRECTORY "$LAB_ROOT/"
LAB_REFINEMENT="$LAB_ROOT/$(basename REFINEMENT_DIRECTORY)"
printf '\nlearner edit\n' >> "$LAB_REFINEMENT/report.md"
corpus verify-refinement "$LAB_REFINEMENT"
```

Expected result: verification exits `5`. The copied record is not repaired.

## Knowledge check

1. What connects D009 to a supported change?
2. Which field is persisted decision authority?
3. What evidence exists only after approval?
4. Why must you treat a proposal file as read-only?

## Answers

1. The D009-to-R001 finding-to-refiner mapping.
2. `refinement-manifest.json.decision`.
3. A prepared revision, transformation, lineage, derivation, and reversal evidence.
4. Resolution verifies the exact canonical proposal and its bound identities.

Next: [Inspect a corpus](inspect-a-corpus.md).
