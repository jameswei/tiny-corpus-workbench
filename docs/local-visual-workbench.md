# Local Visual Workbench

The Local Visual Workbench gives you a read-only browser view of records in one
local workspace. It uses the same verification and evidence contracts as the
CLI.

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

Create an observation that needs no model files. The default producer output
already uses the default workspace:

```bash
corpus observe fixtures/golden/policy-memo.md
```

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

The Workbench scans only these four families and their exact manifest names.
It ignores `inputs/`, unrelated directories, and `.staging-*` publication
directories. A missing workspace or family directory is empty and is not
created. Corpus descriptors add their verified contained observation and
diagnosis records; those children do not become separate top-level discoveries.

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

The browser uses these read-only routes:

```text
GET or HEAD /
GET or HEAD /assets/workbench.css
GET or HEAD /assets/workbench.js
GET or HEAD /api/workbench
GET or HEAD /api/records/{record_key}
GET or HEAD /api/artifacts/{artifact_key}
POST /api/workbench/refresh
```

The JSON routes are an internal interface for the bundled UI. They are not a
public interface. Artifact responses come from bytes captured during
admission. Disk changes do not alter those bytes until a successful refresh.
Opaque artifact keys never expose backing filesystem paths.

The refresh operation accepts an empty request body and runs synchronously.
The server returns `404` for unknown routes or keys, `405` for unsupported
methods, `400` for a nonempty refresh body, and `409` when a refresh candidate
fails. The bundled UI uses text-only DOM construction and makes no remote
requests.

The service is loopback-only, but other local processes can reach a loopback
port. Do not treat the workbench as an access-control or authentication
boundary. Stop the server when you finish.

## Integrity and authority limits

The workbench is read-only. It cannot run extraction, diagnosis, refinement,
or corpus workflows. Use the existing CLI commands for those operations.

Diagnosis still does not authorize mutation. The Workbench cannot decide or
apply a proposal. It derives `APPROVED` or `REJECTED` only from `refinement-manifest.json.decision`;
it does not treat proposal state,
transformation state, or the derived report as authority. An approved, fully
verified refinement remains the only supported path to a successor revision.

Local hashes detect changes during admission under the trusted-local model.
They do not prove authorship or authenticity. The interface does not show
source or prepared document passages unless you explicitly retrieve an
admitted plain-text artifact.

See the [README](../README.md) for the complete CLI path and the
[v0.5 lesson](../learning/v0.5-local-visual-workbench.md) for a short guided
exercise.
