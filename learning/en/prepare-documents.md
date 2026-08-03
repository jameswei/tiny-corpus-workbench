<p class="guide-kicker">Lesson 1</p>

# Prepare documents for a corpus

Before a system can search, rank, or generate from a corpus, someone must
decide what the corpus contains and how its documents became ready for use.
This project teaches that earlier preparation work.

## What you will learn

By the end of this lesson, you should be able to explain why readable text
alone is not a prepared document. You should also be able to separate a
technical observation from a human decision to change a document.

## Ask the right question

Do not begin with “Can I extract text?” Begin with these questions:

- Which source bytes did the work start from?
- What did each extractor produce?
- Which conditions need attention, and what evidence supports them?
- Who decided to change a document?
- Which prepared revision came from that decision?

A usable prepared document is not only readable text. It has an inspectable
path from its source through extraction, diagnosis, and any approved change.

Think of the lifecycle as a chain of claims. Each claim needs a record that
supports it:

| Claim | Supporting record |
| --- | --- |
| “This is the source we processed.” | The captured-source identity in an Observation. |
| “These tools produced these results.” | Extractor outputs and comparison evidence. |
| “This condition exists.” | A Diagnosis finding and its rule-specific evidence. |
| “We chose to change it.” | One persisted approve or reject decision. |
| “This is the resulting document.” | An approved immutable Revision. |

Without this chain, a later reader can see only the latest text. They cannot
tell whether it came from the original source, an extraction error, or an
unexplained edit.

## Keep evidence and authority separate

Extraction produces views. Diagnosis produces findings. A proposal describes a
possible change. None of these actions authorizes mutation.

Only an explicit human decision can approve or reject a supported proposal.
Approval creates a new immutable revision. Rejection preserves the evidence and
leaves the base document unchanged.

~~~text
evidence: source -> extraction -> finding -> proposal
authority:                            person -> approve or reject
result:                                          prepared revision or no revision
~~~

This separation prevents a useful observation from silently becoming an
unexplained edit. It also makes a rejection useful: the proposal and evidence
remain inspectable, while the document remains unchanged.

## Read the lifecycle as a boundary

The lifecycle has deliberate limits. It is not a general document editor and
it is not a quality score for all possible uses.

- The original source remains available for inspection.
- Extraction produces a canonical working document and readable views. It does
  not decide that the document is good.
- Diagnosis records conditions that fixed rules can support. It does not make a
  compliance, truth, or business judgment.
- A refiner can propose only a supported deterministic change. It cannot apply
  that change until a person records a decision.
- A prepared revision is an output for later corpus work. It is not an index,
  an embedding set, or a retrieval result.

## Try it in the Workbench

Start the local Workbench:

~~~bash
corpus workbench --no-open
~~~

Open the printed address. Do not run a lifecycle yet. Look at the four stages:
Observe, Diagnose, Refine, and Revision. They match the evidence-and-authority
path above. The sidebar also separates individual Documents from aggregate
Corpora.

Choose the rule-reference button in the header. Read the short explanation of
what a finding means. You do not need to memorize the rules yet. The important
point is that a rule gives the application a bounded reason to report a
condition; it does not give the application permission to edit a document.

## What to look for

When you later add a document, the Workbench keeps one document in focus. Its
stage navigator shows the current preparation round. The Inspector has three
views:

- **Summary** gives the current stage's main facts.
- **Evidence** explains the record or relationship that supports those facts.
- **Artifacts** lists published files that you can inspect when you need more
  detail.

You do not need to read every JSON artifact to learn the lifecycle. Start with
the stage explanation and the result shown in the main area. Use the Inspector
when you have a specific question about how that result was supported.

::: tip What to remember
Corpus preparation is not a silent cleanup step. It is a traceable decision
process that ends with a prepared revision.
:::

Next: [Capture and Extract](./capture-and-extract.md).
