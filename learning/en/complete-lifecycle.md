<p class="guide-kicker">Lesson 6</p>

# Practice the complete lifecycle

This exercise connects the earlier lessons. The Workbench is not a second
workflow. It is a learner-focused interface over the same published records
that the CLI can use.

## What you will learn

You will use one document to practise the full evidence-and-authority path. You
will then compare it with a no-findings path and learn which results survive a
page reload or server restart.

## Set up a temporary learning workspace

From the repository root, start a fresh local workspace:

~~~bash
LESSON_WORKSPACE="$(mktemp -d)"
corpus workbench --workspace "$LESSON_WORKSPACE" --no-open
~~~

Open the printed local address. Press `Ctrl-C` in this terminal when you finish.
The Workbench binds only to `127.0.0.1`; it is not a hosted service.

## Path A: inspect one supported change

Use the guided `whitespace-cleanup.md` document. Follow the stages in order.

### 1. Observe

Add the document and let Observe complete. Read the stage explanation first.
Then identify:

- the captured source metadata;
- the two extraction views;
- the canonical `DoclingDocument` handoff; and
- the comparison result.

Do not decide whether the document needs a change yet. Observation has only
published evidence about the source and extraction results.

### 2. Diagnose

Continue to Diagnosis and run it. The guided document produces D009. Read the
finding's name, stable ID, severity, affected content, and evidence. Open the
Rule reference if you need to understand why D009 exists.

Ask one narrow question: “What condition did this rule identify?” Do not turn
the finding into a broad statement that the document is unusable.

### 3. Refine

Choose the supported refinement for D009 and create its proposal. Read the
visible whitespace comparison. The proposal is temporary. It shows a possible
deterministic change, but no document has changed.

Choose either **Approve** or **Reject**, then select **Record decision**. Read
the explanation beside this action before you continue. It tells you why a
decision must be persisted instead of remaining a page-level choice.

### 4. Read the outcome

If you approved, open Revision. Check the prepared revision, the applied
comparison, and the revision history. The original source and the base record
still exist.

If you rejected, check the published decision evidence in Refine. Revision is
marked as not needed because there is no approved change to inspect. This is a
complete path, not an incomplete user action.

## Path B: compare no findings

Add the guided `policy-memo.md` document and run Diagnosis. It produces no
fixed-rule match. Read the result carefully:

- Observation and Diagnosis still publish inspectable records.
- Refine and Revision are not needed in this preparation round.
- The result does not say that the document is universally correct or complete.

Compare this path with D009. The difference is whether a fixed rule supplied a
supported condition for further review, not whether one document “passed” and
the other “failed.”

## Use the Workbench deliberately

The main area gives one learner question for the selected stage. The Inspector
keeps related detail close without making every stage a JSON dashboard.

- Use **Summary** first for the current stage's main result.
- Use **Evidence** when you want to know why that result exists.
- Use **Artifacts** when you need to inspect a published file.

The document list keeps your practice records separate from aggregate corpus
records. Refresh the workspace only when a CLI command has published new
records outside the running Workbench.

## Recover safely

Published records and decisions remain on disk. A page reload or server restart
restores published state after the workspace is read again. A temporary proposal
panel and an unrecorded decision do not survive. Create that deterministic
proposal again and make a new explicit choice.

::: tip What to remember
The Workbench teaches the lifecycle. The CLI exposes its complete precise
interface. Both preserve the same distinction between evidence and authority.
:::

You can now return to any earlier lesson, inspect a corpus, or use a project
fixture to repeat a single stage with a specific learning question.
