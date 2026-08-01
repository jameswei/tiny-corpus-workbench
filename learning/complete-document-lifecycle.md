# Complete the Document Lifecycle

## Purpose

Use the guided Workbench path to connect observation, admission verification,
diagnosis, proposal, decision, and immutable revision evidence.

## Guided exercise

Create an isolated workspace and start the loopback server:

```bash
LESSON_WORKSPACE="$(mktemp -d)"
corpus workbench --workspace "$LESSON_WORKSPACE" --no-open
```

Open the printed local address. Then complete these actions:

1. Select **Start whitespace lifecycle**.
2. Wait for observation publication and workspace admission.
3. Inspect the verified observation and its two extraction views.
4. Select **Diagnose document**.
5. Inspect the D009 finding and R001 refiner mapping.
6. Select **Create proposal**.
7. Compare the readable before-and-after evidence.
8. Select **Approve proposal** or **Reject proposal**.
9. Inspect the decision and verification states.
10. If approved, inspect the revision, lineage, derivation, and reversal evidence.

The actions map to the same persisted record families used by the CLI:

```text
observe -> observation record
diagnose -> diagnosis record
decide -> refinement record -> optional prepared revision
```

Rejection publishes no revision. Approval never overwrites the base. You can
diagnose an approved prepared revision to continue an immutable chain.
An approved record shows transformation and history evidence. A rejected
record shows the decision and has no prepared document.

The proposal panel also gives exact paths for optional CLI continuation with
`corpus resolve-refinement`. The CLI and Workbench are interfaces over the
same application behavior. Corpus execution remains CLI-only.

## Shared workspace behavior

The Workbench discovers observations, diagnoses, refinements, and corpora in
four fixed directories under its workspace. Startup and **Refresh records**
verify the complete candidate. A successful manual refresh replaces the
accepted in-memory snapshot transactionally.

You can upload one supported document. The server stores an accepted upload
under `inputs/` and publishes a new immutable observation. It shows source
metadata but does not serve the uploaded original. The server retains only the
latest in-memory observation job.

Each proposal belongs to its diagnosis. You can browse other records while a
proposal waits. The page restores its panel only when that diagnosis-owned
state still exists in the same page process. Draft files remain under
`refinement-drafts/`, but they are not workspace records.

Select any record to inspect its evidence and relationships. An observation
shows extraction and integrity evidence. A diagnosis shows findings and
affected references. A refinement shows its decision, proposal,
transformation, revision chain, and verification states. A corpus shows
status counts, findings, its family and format matrix, extractor comparisons,
contained records, and their relationships.

## Temporal rules

Use these rules when you interpret the page:

- Only one observation job runs at a time.
- The page polls snapshots and can miss a fast stage live.
- An ordered stage can appear complete without claiming that the browser
  observed it live.
- Reload restores the latest job only while the same server process remains.
- Restart clears the job, action token, and proposal panels. It retains
  accepted inputs, draft files, and published records.
- Observation and lifecycle publication do not overlap.
- The page does not retry lifecycle actions automatically.
- A refresh failure retains the last accepted projection. A successfully
  published record remains on disk.

Manual refresh is still useful for records that the CLI publishes while the
Workbench runs. Record selection changes the inspected view; it does not
change a record or transfer proposal state to another diagnosis.

## Trusted-local boundary

The server binds only to `127.0.0.1`. A process-local action token helps the
bundled page reject ordinary cross-origin form submissions. The token is not
authentication or access control. Other local processes can fetch it.

The Workbench is for one trusted local user. Its HTTP routes are an internal
bridge for the bundled interface, not a public API. Stop the server with
`Ctrl-C` when you finish.

Only `refinement-manifest.json.decision` is persisted structured decision
authority. The token, page state, proposal state, HTTP response, and
transformation state do not replace that authority.

## Knowledge check

1. Why can a completed stage lack a live browser snapshot?
2. What survives a server restart?
3. What happens when publication succeeds but refresh fails?
4. Is the action token authentication?
5. Which persisted field records decision authority?

## Answers

1. The stage can finish between browser polls.
2. Accepted inputs, draft files, and published records survive on disk.
3. The record remains on disk, while the page keeps the last accepted projection.
4. No. It is limited cross-origin-form mitigation in a trusted-local process.
5. `refinement-manifest.json.decision`.

Return to the [learning hub](README.md) or use the
[Local Visual Workbench guide](../docs/local-visual-workbench.md) for exact
current behavior.
