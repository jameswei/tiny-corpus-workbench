<p class="guide-kicker">Lesson 3</p>

# Inspect and diagnose

Diagnosis applies fixed mechanical rules to the canonical `DoclingDocument`.
It records conditions that match. It does not repair the document and it does
not use the comparison view as a source of findings.

## What you will learn

You will learn how to read a finding, what severity means, why evidence matters,
and why `NO_FINDINGS` is a limited result rather than a broad quality claim.

## A diagnosis is not a verdict on the document

The rules are deliberately narrow. They can identify conditions such as a
replacement character, an unexpected heading-level jump, repeated text, or
normalizable whitespace. They cannot decide whether a document is truthful,
complete, legally compliant, or suitable for every later use.

This limit is useful. A rule can make a claim only when the canonical document
contains the evidence that supports that claim. It does not need to guess what a
reader or a downstream system might prefer.

## Read a finding as a claim with evidence

A finding has a stable rule identifier, a display name, a severity, affected
document references, and rule-specific evidence. The evidence shape varies
because each rule supports a different claim.

For example, a whitespace finding can identify exact affected content and the
condition that made it match. A structural finding can cite headings, offsets,
or repeated text. Severity communicates how the fixed rule classifies the
condition. It does not grant authority to change the document.

Read a finding in this order:

1. Read the display name to understand the reported condition.
2. Read the stable ID, such as D009, when you need to identify the rule exactly.
3. Read the severity as the rule's fixed category, not your final priority.
4. Read the evidence and affected references before considering a change.
5. Check whether a supported refiner is available for that specific finding.

The Rule reference in the Workbench helps with step 2. It lists the fixed rules,
their names, severities, and the conditions they detect. It is a dictionary for
the learner, not a scorecard for a document.

## Understand `NO_FINDINGS`

`NO_FINDINGS` means that none of the fixed rules matched in this preparation
round. It does not mean that the document is correct, complete, compliant, or
ready for every future use.

This result still has value. It records which canonical document was diagnosed,
which rules were used, and what the diagnosis concluded. In the Workbench,
Refine and Revision are marked as not needed for that round because there is no
supported change to decide. The diagnosis record remains available in the
Inspector.

## Preserve the subject

Diagnosis publishes a separate immutable record. The source, Observation, and
canonical document remain unchanged. This lets you inspect a finding without
making a hidden change part of the diagnostic act.

That separation matters when you disagree with a rule result. You can inspect
the evidence, decide not to refine it, or choose a different later workflow.
The diagnosis itself remains an honest statement of what the fixed rule found.

## Try it in the Workbench

Add the guided `whitespace-cleanup.md` document, then select **Run Diagnosis**.
Read D009 before you continue. Notice its display name, stable identifier,
severity, evidence, and “why it matters” explanation.

Open the Inspector's Summary and Evidence tabs. The Summary gives the diagnosis
result for the current stage. The Evidence tab tells you why the result exists.
Use Artifacts only after you have a question that requires the underlying
published file.

Then add `policy-memo.md` and run Diagnosis. Compare its no-findings result
with D009. The important contrast is not “good document” versus “bad document.”
It is “a fixed condition matched” versus “no fixed condition matched.”

::: tip What to remember
Evidence answers “what happened?” A human decision answers “should we change
it?” Keep these questions separate.
:::

Next: [Decide and Revise](./decide-and-revise.md).
