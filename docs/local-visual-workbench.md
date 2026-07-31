# Local Visual Workbench

The Local Visual Workbench can run one observation and show verified records in
one local workspace. Published records stay immutable. The Workbench uses the
same observation, verification, and evidence contracts as the CLI.

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

## Observe a document

Select **Observe policy memo** for the guided model-free path. The Workbench
publishes a new observation, refreshes the complete workspace, and selects the
new record.

You can also select one `.docx`, `.md`, `.pdf`, or `.txt` file. The limit is
32 MiB. The Workbench derives the format from the filename and content. It
shows the filename, format, size, and SHA-256. It does not show or serve the
uploaded original.

The browser shows these real observation stages:

```text
PREPARING_SOURCE
EXTRACTING_DOCLING
EXTRACTING_MARKITDOWN
BUILDING_EVIDENCE
VERIFYING_AND_PUBLISHING
REFRESHING_WORKSPACE
```

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
POST /api/workbench/refresh
POST /api/observation-jobs/guided
POST /api/observation-jobs/upload?filename=NAME
```

The JSON routes are an internal interface for the bundled UI. They are not a
public interface. Artifact responses come from bytes captured during
admission. Disk changes do not alter those bytes until a successful refresh.
Opaque artifact keys never expose backing filesystem paths.

The refresh operation accepts an empty request body and runs synchronously.
Observation submissions return an accepted in-memory job. The bundled UI polls
only while that job is queued or running. The server bounds upload bodies
before it reads them. The bundled UI uses text-only DOM construction and makes
no remote requests.

The service is loopback-only, but other local processes can reach a loopback
port. An unrelated webpage can trigger a request without reading its response.
Do not treat the Workbench as an access-control or authentication boundary.
Stop the server when you finish.

## Integrity and authority limits

The Workbench can run observation. It cannot run diagnosis, refinement, or
corpus workflows. Use the existing CLI commands for those operations.

Diagnosis still does not authorize mutation. The Workbench cannot decide or
apply a proposal. It derives `APPROVED` or `REJECTED` only from `refinement-manifest.json.decision`;
it does not treat proposal state,
transformation state, or the derived report as authority. An approved, fully
verified refinement remains the only supported path to a successor revision.

Local hashes detect changes during admission under the trusted-local model.
They do not prove authorship or authenticity. The interface does not show
source or prepared document passages unless you explicitly retrieve an
admitted plain-text artifact.

See the [README](../README.md) for the complete CLI path, the
[v0.7 lesson](../learning/v0.7-web-observation-workflow.md) for browser
observation, and the [v0.6 lesson](../learning/v0.6-shared-workbench-workspace.md)
for manual workspace refresh.
