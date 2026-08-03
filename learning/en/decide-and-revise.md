<p class="guide-kicker">Lesson 4</p>

# Decide and revise

A supported refiner connects one finding to one deterministic kind of change.
It can create a proposal, but the proposal is still only a read-only
description of exact edits and inverse edits.

## What you will learn

You will learn why a proposal is not a document change, why approval and
rejection are both useful outcomes, and how an approved revision remains linked
to the evidence that led to it.

## Move from a finding to one possible change

Diagnosis says that a fixed condition matched. A supported refiner says that
the project knows one bounded, deterministic way to address that condition. It
does not say that the change must be applied.

For example, D009 can map to R001, which normalizes supported line endings and
horizontal whitespace. The mapping is specific. It does not offer an open-ended
editor or ask the application to invent a rewrite.

~~~text
finding -> supported refiner -> proposal -> explicit decision
                                          -> approve -> prepared revision
                                          -> reject  -> evidence only
~~~

The proposal makes the possible change visible before publication. Read the
before-and-after comparison. For whitespace, the Workbench renders invisible
characters visibly so that spaces, tabs, and line endings do not look identical.
The proposal may contain more than one edit; use its position control to inspect
each edit without losing the relationship to the same finding and refiner.

## Make authority explicit

The Workbench and CLI both require one mutually exclusive decision:

- **Approve** publishes an immutable refinement record and one prepared
  revision. The base remains unchanged.
- **Reject** publishes the proposal and decision evidence, but creates no
  prepared revision.

The persisted refinement decision is the only structured decision authority.
Page state, a proposal state, an HTTP response, and a transformation state do
not replace it.

Approval is not “accept whatever the application did.” It is an explicit human
choice after reviewing a bounded proposal. Rejection is not failure. It records
that the proposal was considered and preserves the original document and the
supporting evidence.

## Read a revision as history

An approved revision records its parent, exact applied edits, before-and-after
hashes, forward derivation, and reversal evidence. It is a successor, not an
overwrite. You can diagnose that revision in a later preparation round.

The Workbench's Revision stage presents this as a short history rather than a
replacement of the earlier document. If you choose a historical preparation
round, it remains inspectable and read-only. Only the latest approved revision
can begin another diagnosis-refine-revision cycle.

## Try both decision paths

Continue from D009 in `whitespace-cleanup.md`. Review the supported refiner,
select **Create proposal**, and read the complete visible whitespace comparison.
The main panel now shows the proposal. It has not changed the document yet.

Choose **Approve** or **Reject**, then select **Record decision**.

- If you approve, open Revision. Confirm that a prepared revision, applied
  comparison, and revision history exist.
- If you reject, confirm that the decision evidence exists but no prepared
  revision exists. Revision is correctly marked as not needed.

In both cases, use the Inspector to compare what is now published with what was
temporary before you recorded the decision.

::: warning Common mistake
Do not edit a proposal file. Resolution verifies the exact canonical proposal
and its bound identities before publication.
:::

::: tip What to remember
A finding identifies a condition. A proposal makes one supported change visible.
Only an explicit recorded decision creates a revision, and only approval creates
one.
:::

Next: [Inspect a Corpus](./inspect-a-corpus.md).
