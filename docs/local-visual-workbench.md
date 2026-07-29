# Local Visual Workbench

The Local Visual Workbench gives you a read-only browser view of explicit v0.5
records. It uses the same verification and evidence contracts as the CLI.

The workbench is local software. It is not a hosted service. It binds only to
`127.0.0.1`, keeps one frozen projection in memory, and writes no session
state.

## One-time setup

Install the locked environment:

```bash
uv sync --frozen --python 3.12
```

Activate `.venv` to use `corpus` directly. You can instead prefix a usage
command with `uv run`.

## Start the workbench

Create an observation that needs no model files:

```bash
corpus observe fixtures/golden/policy-memo.md \
  --output-root /tmp/corpus-workbench-observations
```

The command prints one JSON object. Use the parent directory of its `manifest`
value as `OBSERVATION_DIRECTORY`.

Start the workbench without opening a browser automatically:

```bash
corpus workbench OBSERVATION_DIRECTORY --no-open
```

The command prints only the serving address. The default address is
`http://127.0.0.1:8765/`.

Open the printed URL in a local browser. Press `Ctrl-C` in the terminal to stop
the server.

Use `--port PORT` to select an unused port from 1024 through 65535. Omit
`--no-open` to ask the operating system to open the browser after startup.

## Supply records explicitly

Pass one or more record root directories:

```bash
corpus workbench OBSERVATION_DIRECTORY \
  DIAGNOSIS_DIRECTORY REFINEMENT_DIRECTORY CORPUS_DIRECTORY --no-open
```

Each root must contain one supported v0.5 root manifest. The command accepts
observation, diagnosis, refinement, and corpus records. Before startup, it
verifies current record integrity, relationships, containment, file type,
recorded size, and recorded hashes. It also captures the admitted manifest and
listed-artifact bytes once and keeps them in memory.

The workbench does not scan parent directories. It does not follow source
paths or accept URLs. Corpus records can add their verified contained
observation and diagnosis records. Equal logical copies collapse to one
record. Conflicting logical copies stop startup.

Old v0.1 through v0.4 artifacts are unsupported. Regenerate them with v0.5
before you use this workbench.

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
```

The JSON routes are an internal interface for the bundled UI. They are not a
public interface. Artifact responses come from bytes captured during
admission. Restart the workbench to admit changed records. Opaque artifact
keys never expose backing filesystem paths.

The server returns `404` for unknown routes or keys and `405` for methods other
than `GET` and `HEAD`. The bundled UI uses text-only DOM construction and makes
no remote requests.

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
