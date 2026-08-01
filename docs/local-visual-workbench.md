# Local Visual Workbench

The Local Visual Workbench guides one document from observation through an
explicit refinement decision. It shows verified records in one local
workspace. Published records stay immutable. The Workbench and CLI use the
same application services, verification rules, and evidence records.

The workbench is local software. It is not a hosted service. It binds only to
`127.0.0.1`, keeps one accepted projection in memory, and writes no session
state.

## One-time setup

Install the locked environment:

```bash
uv sync --frozen --python 3.12
```

Activate `.venv` to use `corpus` directly. You can instead prefix a usage
command with `uv run`.

## Start the workbench

Start the workbench without opening a browser automatically:

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

## Start a document

Select **Observe policy memo** for the guided model-free path. The Workbench
publishes a new observation, refreshes the complete workspace, and selects the
new record.

Select **Start whitespace lifecycle** for a model-free document with a
supported whitespace finding. This action publishes and selects only the
observation. Continue the lifecycle in the **Document lifecycle** area.

You can also select one `.docx`, `.md`, `.pdf`, or `.txt` file. The limit is
32 MiB. The Workbench derives the format from the filename and content. It
shows the filename, format, size, and SHA-256. It does not show or serve the
uploaded original.

The browser always lists these real observation stages in order:

```text
PREPARING_SOURCE
EXTRACTING_DOCLING
EXTRACTING_MARKITDOWN
BUILDING_EVIDENCE
VERIFYING_AND_PUBLISHING
REFRESHING_WORKSPACE
```

The Workbench marks the current stage from the latest server snapshot. A fast
stage can finish between polls. In that case, the ordered list shows the stage
as completed but does not claim that the browser observed it live.

Only one observation can run at a time. Job state stays in memory. A browser
reload restores the latest job from the running server. A server restart clears
the job but keeps accepted inputs and published observations.

An upload is stored immutably at
`WORKSPACE/inputs/SHA256/ORIGINAL_FILENAME`. Each observation is a new
immutable run. The guided fixture stays in the source checkout and is not
copied to `inputs/`.

A published observation is complete even when an extractor reports failure or
partial success. If automatic refresh rejects the complete candidate, the new
record stays on disk and the previous browser projection stays visible. Fix the
candidate, then use manual refresh.

The Workbench can diagnose an observation only when admission verified its
canonical Docling document. A partial observation remains diagnosable when the
Docling canonical artifact is available. A failed or MarkItDown-only
observation remains inspectable but cannot continue.

## Complete the browser lifecycle

Select an eligible observation, then select **Diagnose document**. Admission
verifies the complete workspace before the action becomes available. The new
diagnosis lists every finding and its evidence.

Three diagnosis rules have deterministic refiners:

| Finding | Refiner |
| --- | --- |
| D007 repeated page margin text | R002 repeated boilerplate removal |
| D009 normalizable whitespace | R001 whitespace normalization |
| D010 possible line-end hyphenation | R003 deterministic dehyphenation |

Select **Create proposal** for a supported, actionable finding. The browser
shows the named finding, refiner, affected references, and readable edits. It
does not ask you to edit JSON.

Select **Approve proposal** or **Reject proposal**. This click supplies the
human decision. Approval publishes one immutable prepared revision with
transformation, lineage, derivation, and reversal evidence. Rejection publishes
the decision without a prepared revision.

An approved refinement can be the subject of **Diagnose prepared revision**.
A rejected refinement cannot continue because it has no prepared revision.

Each displayed proposal belongs to its diagnosis. You can browse other records
while a proposal waits for a decision. The page restores a proposal only when
you return to its diagnosis during the same page process. A reload or server
restart does not discover drafts or restore proposal panels.

The Workbench disables record navigation only while a lifecycle request is in
progress. It does not retry a diagnosis, proposal, approval, or rejection. If
the action token changes after a restart, the page fetches a new token and asks
you to select the action again.

## Use the workspace

The default workspace is `build/`. Use a different workspace when necessary:

```bash
corpus workbench --workspace /tmp/my-workspace --no-open
```

Publish custom-workspace records with each existing producer's `--output-root`
option. Place them under the matching family directory:

```text
WORKSPACE/extraction-observatory/
WORKSPACE/evidence-based-diagnosis/
WORKSPACE/controlled-revisions/
WORKSPACE/corpus-inspection/
```

The Workbench creates the selected workspace and missing parents at startup.
It scans only these four families and their exact manifest names. It ignores
`inputs/`, unrelated directories, and `.staging-*` publication directories.
A missing family directory is empty. Corpus descriptors add their verified
contained observation and diagnosis records; those children do not become
separate top-level discoveries.

Startup and each manual refresh verify the complete candidate before accepting
it. A failed refresh keeps the previous session, record details, and captured
artifact bytes visible. Fix or remove the invalid candidate, then refresh
again. A successful refresh clears the error and replaces the snapshot.

Workbench proposals use `WORKSPACE/refinement-drafts/` in the current source.
These proposal files remain after approval or rejection. They are not
workspace records, and the Workbench does not discover them as records. This
location is current behavior, not a cross-version storage promise.

## Inspect the evidence

The record list shows kind, status, identity, run identifier, and relationship
state. Select a record to inspect its current evidence:

- observations show source metadata, extraction results, comparison metrics,
  and artifact integrity;
- diagnoses show rule summaries, findings, evidence, and affected references;
- refinements derive the decision from the refinement manifest and show the
  proposal, transformation, revision chain, and verification states;
- corpora show status counts, findings, family and format matrices, extractor
  comparisons, and contained records.

`MATCH` means the checked relationship or evidence agrees. `MISSING` means a
declared relationship target was not supplied. `NOT_CHECKED` means the current
view did not perform that optional check. `NOT_APPLICABLE` means the check does
not apply to that record state.

Artifact content is not loaded automatically. Use **Retrieve plain text** for
an authorized text artifact. The browser displays the response as text. It
does not execute artifact markup.

## API boundary

The browser uses these internal routes:

```text
GET or HEAD /
GET or HEAD /assets/workbench.css
GET or HEAD /assets/workbench.js
GET or HEAD /api/workbench
GET or HEAD /api/records/{record_key}
GET or HEAD /api/artifacts/{artifact_key}
GET or HEAD /api/observation-jobs
GET or HEAD /api/lifecycle/action-token
POST /api/workbench/refresh
POST /api/observation-jobs/guided/{guided_id}
POST /api/observation-jobs/upload?filename=NAME
POST /api/lifecycle/diagnoses/{subject_record_key}
POST /api/lifecycle/proposals/{diagnosis_record_key}/{finding_id}
POST /api/lifecycle/proposals/{draft_key}/approve
POST /api/lifecycle/proposals/{draft_key}/reject
```

The JSON routes are an internal interface for the bundled UI. They are not a
public interface. Artifact responses come from bytes captured during
admission. Disk changes do not alter those bytes until a successful refresh.
Opaque artifact keys never expose backing filesystem paths.

The refresh and lifecycle operations accept empty request bodies and run
synchronously. Observation submissions return an accepted in-memory job. The
bundled UI polls only while that job is queued or running. Observation and
lifecycle publication do not overlap. The server bounds upload bodies before
it reads them. The bundled UI uses text-only DOM construction and makes no
remote requests.

Lifecycle changes require a process-local action token that the bundled page
keeps only in memory. The token blocks ordinary cross-origin forms, but other
local processes can fetch it. It is not authentication or access control. Stop
the server when you finish.

## Integrity and authority limits

Diagnosis still does not authorize mutation. A token-bearing browser click
supplies an explicit decision to the refinement service. Only
`refinement-manifest.json.decision` is persisted decision authority. Proposal,
HTTP, UI, token, and transformation states are not authority.

The proposal panel includes expandable CLI continuation details. They contain
the exact proposal, diagnosis, base, and output-root paths for the unchanged
`corpus resolve-refinement` command. This optional path does not change the
browser decision model. Corpus execution remains a CLI workflow.

Local hashes detect changes during admission under the trusted-local model.
They do not prove authorship or authenticity. The interface does not show
source or prepared document passages unless you explicitly retrieve an
admitted plain-text artifact.

See the [README](../README.md) for the complete CLI path, the
[complete lifecycle lesson](../learning/complete-document-lifecycle.md) for
the browser lifecycle and manual workspace refresh.
