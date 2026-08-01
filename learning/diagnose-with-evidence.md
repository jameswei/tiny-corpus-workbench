# Diagnose with Evidence

## Purpose

Use fixed rules to record document conditions. Do not treat a finding as
permission to change the document.

## Objectives and terms

After this lesson, you can explain a rule, finding, severity, document
reference, and diagnosis record. You can also compare different closed
evidence shapes and verify a diagnosis independently.

A rule tests one defined mechanical condition. A finding records one match,
its severity, affected document references, and rule-specific evidence. A
closed evidence shape accepts only the fields defined for that rule.

## Diagnose a short document

Create a model-free observation:

```bash
corpus observe fixtures/diagnosis/short-note.md
```

Set `OBSERVATION_DIRECTORY` from the output, then run:

```bash
corpus verify OBSERVATION_DIRECTORY
corpus diagnose OBSERVATION_DIRECTORY
```

Set `DIAGNOSIS_DIRECTORY` from the diagnosis output. Inspect
`findings.json`, `diagnosis-manifest.json`, and `report.md`.

Find D002. Its evidence contains the non-whitespace character count and a
document reference. The report presents the same evidence for people.

Verify the published diagnosis and rerun its rules against the subject:

```bash
corpus verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject OBSERVATION_DIRECTORY
```

Expected result: artifact integrity is `VERIFIED`, and supplied subject states
are `MATCH`.

## Compare structural evidence

Observe and diagnose `fixtures/diagnosis/structural-traps.md`. Inspect D003,
D004, and D005.

- D003 cites offset evidence.
- D004 cites references, a count, and a text hash.
- D005 records heading levels and the preceding heading reference.

The shapes differ because each rule must support a distinct, testable claim.
MarkItDown output does not create findings. Diagnosis reads the canonical
Docling document.

`NO_FINDINGS` means only that none of the ten fixed rules matched. It does not
prove that the document is correct, complete, or suitable for a later use.

## Workbench equivalence

The Workbench enables **Diagnose document** only for an admitted record with a
verified canonical Docling document. It calls the same diagnosis behavior and
shows the same named findings and evidence. A partial observation can be
eligible when its canonical document is usable.

Diagnosis publishes a separate immutable record. It does not edit the subject
and never supplies mutation authority.

## Knowledge check

1. Why can two rules use different evidence fields?
2. Why does MarkItDown not produce diagnosis findings?
3. What does `NO_FINDINGS` mean?
4. Does a finding authorize a refinement?

## Answers

1. Each rule supports a different closed and testable claim.
2. The canonical Docling document is the diagnosis content input.
3. No fixed rule matched.
4. No. A person must make an explicit decision later.

Next: [Control a document revision](control-document-revision.md).
