# Complete the Document Lifecycle

## Purpose

Use the guided Workbench path to connect observation, diagnosis, proposal,
decision, and immutable revision evidence.

## Guided exercise

Create an isolated workspace and start the loopback server:

```bash
LESSON_WORKSPACE="$(mktemp -d)"
corpus workbench --workspace "$LESSON_WORKSPACE" --no-open
```

Open the printed local address. Then complete these steps:

1. Select **Add a document**.
2. Select `whitespace-cleanup.md`.
3. Wait for Observe to publish and refresh the workspace.
4. Inspect the source, extraction, and canonical evidence.
5. Select **Continue to Diagnosis**.
6. Select **Run Diagnosis**.
7. Inspect the D009 finding and its INFO severity.
8. Review R001 in **Available next step**.
9. Open Refine and select **Create proposal**.
10. Inspect the visible-whitespace comparison.
11. Choose **Approve** or **Reject**.
12. Select **Record decision**.
13. Inspect the completed Refine outcome.
14. If approved, select **View prepared revision**.
15. Inspect the applied comparison, history, and forward and inverse evidence.

Use the stage-scoped Summary, Evidence, and Artifacts tabs during the exercise.
They keep learner guidance on the central surface and audit detail in the
inspector.

The actions publish the same record families as the CLI:

```text
Observe -> Observation record
Diagnosis -> Diagnosis record
Decision -> Refinement record -> optional prepared Revision
```

Rejection publishes no Revision. Approval never overwrites the base. An
approved Revision can start another numbered preparation round. Historical
rounds remain inspectable and read-only.

## Compare the no-findings path

Select **Add a document**, then select `policy-memo.md`. Run Diagnosis after
Observe finishes.

Expected result: no fixed rule matches, and no content changes. Refine and
Revision remain clickable. Each explains why the stage is **Not needed**. The
Diagnosis evidence remains available.

Do not interpret `NO_FINDINGS` as Valid or Passed. It means only that no fixed
rule matched.

## Use the shared workspace

The sidebar groups records under one document across its immutable revisions.
It also lists verified corpora. Use **Refresh workspace** to discover records
that the CLI published while the Workbench runs. Refresh runs no producer and
preserves your selection and stage.

Add an unchanged guided source again. The Workbench reactivates its document.
It does not publish another Observation.

You can also upload one supported document up to 32 MiB. The Workbench shows
source metadata and extracted artifacts. It does not display or serve the
uploaded original.

The CLI remains the full lifecycle interface. It can use the same published
records. The Workbench does not generate continuation commands, and it does
not require a CLI command to finish this exercise.

## Inspect readers and rules

Open a published artifact from the Artifacts tab. JSON is pretty-printed.
Markdown appears as literal source. Verified project-generated HTML opens in
an isolated formatted view and can switch to source mode.

Select **Rule reference**. Find D009 and R001. The reference uses canonical
rule identities, severities, and refiner mappings from the Python registries.

Switch between EN and 中. Confirm that the selected document, round, stage, and
inspector tab stay unchanged. Filenames, stable IDs, hashes, and artifact
content do not translate.

## Interpret recovery behavior

Use these rules when you interpret the page:

- The page polls only while an observation job is active.
- A fast stage can finish between polls.
- Observation and lifecycle publication do not overlap.
- The page disables repeated submission during an unresolved mutation.
- A refresh failure keeps the last accepted workspace view.
- A published record stays on disk when its automatic refresh fails.
- The page never replays a mutation automatically.
- A stale action token requires a new explicit click.
- Reload or restart restores only published records and decisions.

An unpublished proposal panel and its selected decision do not survive reload
or restart. Create the deterministic proposal again. Draft files are private
mechanics, not decision authority.

## Trusted-local boundary

The server binds only to `127.0.0.1`. A process-local action token helps the
bundled page reject ordinary cross-origin form submissions. The token is not
authentication or access control. Other local processes can fetch it.

The Workbench is for one trusted local user. Its HTTP routes are an internal
bridge, not a public API. Stop the server with `Ctrl-C` when you finish.

Only `refinement-manifest.json.decision` is persisted structured decision
authority. The token, page state, proposal state, HTTP response, and
transformation state do not replace that authority.

## Knowledge check

1. Why is Observe shared across preparation rounds?
2. What does a finding authorize?
3. What happens after a rejected decision?
4. What survives a server restart?
5. Is the action token authentication?

## Answers

1. Observe records the source once. Later rounds start from the Original or
   latest approved Revision.
2. Nothing. A finding records evidence and does not authorize mutation.
3. The decision and evidence remain, but no prepared Revision exists.
4. Accepted inputs, draft files, and published records survive on disk.
5. No. It is limited cross-origin-form mitigation for a trusted local process.

Return to the [learning hub](README.md) or use the
[Local Visual Workbench guide](../docs/local-visual-workbench.md) for exact
current behavior.
