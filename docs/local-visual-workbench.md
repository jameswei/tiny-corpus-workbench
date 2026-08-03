# Local Visual Workbench

The Local Visual Workbench guides one document from observation through an
explicit refinement decision. It groups immutable records by source and
preparation round. The Workbench and CLI use the same application services,
verification rules, and evidence records.

The Workbench is local software. It is not a hosted service. It binds only to
`127.0.0.1` and keeps one accepted workspace view in memory. It stores only an
explicit locale preference in the browser. The interface is available in
English and Simplified Chinese.

## Set up and start

Use CPython 3.12, activate a virtual environment, and install the project:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Start the Workbench without opening a browser automatically:

```bash
corpus workbench --no-open
```

The command prints only the serving address. The default address is
`http://127.0.0.1:8765/`.

Open the printed URL in a local browser. Press `Ctrl-C` in the terminal to stop
the server.

Use `--port PORT` to select an unused port from 1024 through 65535. Omit
`--no-open` to ask the operating system to open the browser after startup.

Use `--docling-artifacts MODEL_DIRECTORY` to select local Docling models for
PDF observation. The default is `.cache/docling/models`.

## Use the workspace shell

The sidebar shows Documents and Corpora at the same time. Select a document to
open its lifecycle. Select a corpus to open its verified summary without the
document stepper.

Use **Refresh workspace** to discover records that the CLI published after the
Workbench started. Refresh runs no producer. It preserves the current
selection and stage. If verification fails, the Workbench keeps the last
accepted view.

Documents are ordered by first Observation time, newest first. Later records,
selection, and duplicate reactivation do not change this order. One document
represents one source across all immutable revisions.

## Add a document

Select **Add a document**. The modal offers three paths:

- `whitespace-cleanup.md` for complete guided preparation;
- `policy-memo.md` for guided no-findings inspection; or
- one `.docx`, `.md`, `.pdf`, or `.txt` upload up to 32 MiB.

The new source is selected, and Observe starts immediately. The Workbench uses
content SHA-256 and media type as source identity. If you add the same guided
source or an unchanged upload again, the Workbench reactivates its document.
It does not publish another Observation.

For an upload, the Workbench shows the filename, media type, size, and SHA-256.
It does not display or serve the uploaded original. It stores an accepted
upload immutably at `WORKSPACE/inputs/SHA256/ORIGINAL_FILENAME`.

The browser shows these real observation stages in order:

```text
PREPARING_SOURCE
EXTRACTING_DOCLING
EXTRACTING_MARKITDOWN
BUILDING_EVIDENCE
VERIFYING_AND_PUBLISHING
REFRESHING_WORKSPACE
```

The page polls only while the job is queued or running. A fast stage can finish
between polls. The ordered list can show that stage as complete, but it does
not claim that the browser observed it live.

A published Observation can contain partial or failed extractor evidence. It
can continue only when admission verified a usable canonical Docling document.

## Follow the document lifecycle

The central surface asks one learner question at a time. Use Observe,
Diagnosis, Refine, and Revision. The Summary, Evidence, and Artifacts inspector
changes with the selected stage.

Observe is shared by the source. Each later cycle is a numbered preparation
round. A round starts from the Original or from an approved Revision. Only the
latest Revision can start another round. Earlier rounds and revisions remain
inspectable and read-only.

### Observe

Observe groups the source identity, extraction results, canonical evidence,
and published artifacts. Continue to Diagnosis when the canonical document is
eligible.

### Diagnosis

Select **Run Diagnosis**. Diagnosis is deterministic and read-only. It does not
change the source or current revision.

The result leads with document meaning and finding count. Each finding shows
its learner name, stable ID, canonical severity, reason, and available next
step. A finding is evidence that one fixed mechanical rule matched. It is not
an invalidity or compliance verdict.

`NO_FINDINGS` means that no fixed rule matched and no content changed. It does
not prove that the document is correct or complete. Refine and Revision stay
available as explanations marked **Not needed**.

### Refine

For a supported finding, review the finding and refiner. Select **Create
proposal**. A proposal describes one possible change. It does not change the
document.

The comparison shows before and after evidence. D009 makes whitespace visible.
Use the compact change controls for multiple edits. Open the full comparison
when you need more space.

Choose **Approve** or **Reject**, then select **Record decision**. Approval
creates one immutable prepared revision. Rejection keeps the base unchanged
and creates no revision. Both outcomes retain the proposal and decision
evidence.

### Revision

An approved result leads with **Prepared revision created**. It explains the
preserved base, immutable successor, applied edit, and forward and inverse
evidence. The revision history shows Original, each Revision, and the current
result.

You can diagnose the latest prepared revision to begin another Diagnosis,
Refine, and Revision round. The Workbench does not force this optional step.

## Inspect evidence and artifacts

Use the stage-scoped inspector to keep guidance separate from audit detail:

- **Summary** explains the selected stage and its outcome.
- **Evidence** shows verified supporting facts.
- **Artifacts** opens published record content.

The Workbench can show a low-emphasis CLI note for a published record. The CLI
remains a full interface over the same record workflow. The browser does not
generate commands or require the CLI to complete a document lifecycle.

Artifact readers pretty-print JSON and show Markdown as literal source.
Verified project-generated HTML opens in an isolated formatted view with a
source-mode option. Reader controls close the reader, wrap text, copy content,
or switch HTML mode. Oversized artifacts are identified without showing
truncated content.

Visible hashes use a compact first-10 and last-8 form. Hover over a hash to see
the full 64-character value. Records, internal payloads, identity checks, and
copied values keep the full hash.

Corpus inspection uses the same Summary, Evidence, and Artifacts composition.
It shows verified member and finding evidence. Corpus creation and execution
remain CLI-only.

## Use localization and the rule reference

Use the EN/中 control to switch the Workbench-owned interface. The change does
not reload the page or reset the selected document, round, stage, inspector
tab, proposal, or reader. The Workbench remembers an explicit locale choice in
the browser. It does not translate filenames, artifact content, hashes, stable
IDs, schemas, records, or backend evidence.

Select **Rule reference** to open the canonical D001-D010 reference. It shows
each rule ID, learner name, severity, condition, and supported refiner when one
exists. Rule identity, severity, parameters, and refiner mappings come from the
Python registries.

## Refresh, reload, and recover

Only one observation or lifecycle mutation owns publication at a time. The
page disables repeated submission and record navigation while a lifecycle
mutation is unresolved. It never replays a mutation automatically.

If an operation fails before publication, the Workbench states that no record
was created and the source remains unchanged. It offers Retry only for a
confirmed pre-publication failure. If publication succeeds but refresh fails,
the record remains on disk. Use Refresh; do not rerun the producer.

If the outcome is unknown, the Workbench reconciles the workspace before it
allows another mutation. If the action token becomes stale, it refreshes the
token and requires a new explicit click.

A page reload or server restart returns to the latest published record. It
does not restore an unpublished proposal panel or decision selection. Create
the deterministic proposal again when necessary. Completed decisions return
only from immutable Refinement records.

The default workspace is `build/`. Use a different workspace when necessary:

```bash
corpus workbench --workspace /tmp/my-workspace --no-open
```

The Workbench scans only the four record families under its workspace. It
accepts the complete candidate or keeps the previous accepted view. A valid
empty workspace is different from a verification failure.

The v0.9 workspace accepts one Observation root for each source identity. If a
development-era workspace has more than one root for the same source, the
Workbench rejects the complete candidate and changes no file. Use a new or
clean workspace. It does not migrate or hide old roots.

Proposal drafts under `WORKSPACE/refinement-drafts/` are private mechanics.
They are not workspace records or decision authority.

## Trusted-local boundary

The Workbench binds only to `127.0.0.1`. Its HTTP routes are an internal bridge
for the bundled interface, not a public API. It makes no remote request and
does not provide multi-user access.

Lifecycle changes require a process-local action token. The token blocks
ordinary cross-origin forms, but another local process can fetch it. It is not
authentication or access control. Stop the server when you finish.

Only `refinement-manifest.json.decision` is persisted structured decision
authority. Proposal, HTTP, UI, token, and transformation states are not
authority. Local hashes detect ordinary corruption under the trusted-local
model. They do not prove authorship, authenticity, or a trusted timestamp.

See the [README](https://github.com/jameswei/tiny-corpus-workbench/blob/main/README.md) for the complete CLI path and the
[complete lifecycle lesson](https://lifeplayer.space/tiny-corpus-workbench/learn/en/complete-lifecycle.html)
for a guided browser exercise.
