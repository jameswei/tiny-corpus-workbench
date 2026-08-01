from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.validate_workbench_assets import validate


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src/tiny_corpus_workbench/workbench_assets"


class WorkbenchUIContractTests(unittest.TestCase):
    def test_bundled_assets_pass_the_offline_validator(self) -> None:
        self.assertEqual(validate(ASSETS), [])

    def test_asset_inventory_has_no_build_or_runtime_dependency(self) -> None:
        self.assertEqual(
            {path.name for path in ASSETS.iterdir() if path.is_file()},
            {"index.html", "workbench.css", "workbench.js"},
        )

    def test_html_has_semantic_navigation_and_live_focus_targets(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        for marker in (
            '<a class="skip-link" href="#workspace">',
            "<header",
            "<nav",
            "<main",
            'role="status"',
            'aria-live="polite"',
            'id="record-heading" tabindex="-1"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_styles_cover_focus_narrow_screen_reduced_motion_and_non_color_state(
        self,
    ) -> None:
        css = (ASSETS / "workbench.css").read_text("utf-8")
        for marker in (
            ":focus-visible",
            "@media (max-width:",
            "@media (prefers-reduced-motion: reduce)",
            ".status::before",
            ".status-na::before",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, css)

    def test_script_contains_every_required_view_and_state_explanation(self) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for marker in (
            "renderObservation",
            "renderDiagnosis",
            "renderRefinement",
            "renderCorpus",
            "Source metadata",
            "Ten extractor comparison metrics",
            "Affected references",
            "Revision chain",
            "Family and format matrix",
            "Artifact integrity",
            "MATCH:",
            "MISSING:",
            "NOT_CHECKED:",
            "NOT_APPLICABLE:",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        self.assertIn(
            "return `${displayName(record.status)} ${displayName(record.kind)} ${shortHash(record.primary_identity.value)} context ${recordContext(record)}`",
            script,
        )

    def test_manual_refresh_and_selection_contracts_are_visible(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        script = (ASSETS / "workbench.js").read_text("utf-8")
        self.assertIn('id="refresh-records"', html)
        for marker in (
            'fetch(`${API_ROOT}/workbench/refresh`',
            'method: "POST"',
            "elements.refreshButton.disabled = true",
            'elements.refreshButton.textContent = "Refreshing…"',
            "Observe a document here, or publish a CLI record and refresh.",
            "selectedRecordKey",
            "record.record_key === selectedRecordKey",
            "currentProjection.refresh = {status: \"FAILED\"",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)

    def test_observation_controls_are_accessible_and_metadata_only(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for marker in (
            "Run local observations and inspect immutable prepared-document evidence.",
            "Published records stay immutable",
            'id="observe-guided"',
            ">Observe policy memo<",
            'id="observation-file" type="file"',
            'accept=".docx,.md,.pdf,.txt"',
            "One file, up to 32 MiB.",
            'id="observation-alert" class="notice" role="alert" tabindex="-1"',
            'aria-label="Observation source metadata"',
            'aria-label="Observation job status"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)
        self.assertNotIn("Read only", html)
        for marker in (
            '["Filename", job.input.name]',
            '["Format", job.input.media_type]',
            '["Size", formatBytes(job.input.size)]',
            '["SHA-256", job.input.sha256, true]',
            "The previous record view remains available.",
            "selectedRecordKey = job.observation.record_key",
            "encodeURIComponent(file.name)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        for forbidden in ("FileReader", "readAsText", "readAsDataURL", "percentage"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)

    def test_lifecycle_surface_and_local_transport_contract_are_visible(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for marker in (
            'id="document-lifecycle"',
            'id="lifecycle-heading">Document lifecycle',
            'id="start-lifecycle"',
            ">Start whitespace lifecycle<",
            'id="lifecycle-alert" class="notice" role="alert" tabindex="-1"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)
        for marker in (
            'submitObservation(`/guided/${guidedId}`)',
            'fetch(`${API_ROOT}/lifecycle/action-token`',
            '"X-TCW-Action-Token": actionToken',
            "const proposalsByDiagnosis = new Map();",
            "proposalsByDiagnosis.get(selectedRecord.record_key)",
            "proposal.diagnosis_record_key",
            "resolveProposal(proposal, \"approve\")",
            "The lifecycle action token changed. It was refreshed; choose the action again.",
            "Verified during workspace admission.",
            "Diagnosis unavailable · canonical document is not available",
            "No supported deterministic refiner",
            "diagnosis subject is not actionable in this workspace",
            "Continue with the CLI",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        for forbidden in ("localStorage", "sessionStorage", "innerHTML", "activeProposal"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)

    def test_observation_polling_uses_one_fixed_terminal_aware_interval(self) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        self.assertIn("const OBSERVATION_POLL_INTERVAL_MS = 300;", script)
        self.assertEqual(script.count("setTimeout("), 1)
        self.assertNotIn("setInterval(", script)
        self.assertIn(
            'job.state === "QUEUED" || job.state === "RUNNING"',
            script,
        )
        self.assertIn("stopObservationPolling();", script)
        self.assertIn("handledTerminalJobId !== job.job_id", script)
        self.assertIn("announcedActiveStage !== activeStage", script)
        self.assertIn("Observation stage:", script)
        self.assertIn("Use Refresh records to load and select it.", script)

    def test_observation_stage_sequence_survives_skipped_poll_snapshots(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable for the stage cadence test")
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function fakeElement(id = "") {
  return {
    id,
    appended: [],
    attributes: {},
    className: "",
    dataset: {},
    disabled: false,
    files: [],
    hidden: false,
    listeners: {},
    textContent: "",
    firstChild: null,
    append(...values) { this.appended.push(...values); },
    addEventListener(type, handler) { this.listeners[type] = handler; },
    click() { return this.listeners.click && this.listeners.click(); },
    focus() {},
    querySelectorAll() { return []; },
    removeChild() { this.firstChild = null; },
    replaceWith() {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

const ids = [
  "announcer", "observe-guided", "start-lifecycle", "observe-upload", "observation-file",
  "observation-state", "observation-message", "observation-alert",
  "observation-source", "observation-progress", "refresh-records",
  "record-count", "record-list", "record-view", "record-heading", "record-kind",
  "record-state", "record-summary", "record-content", "session-state",
  "session-message", "session-facts", "state-key", "lifecycle-state",
  "lifecycle-message", "lifecycle-alert", "lifecycle-content",
];
const registry = Object.fromEntries(ids.map((id) => [id, fakeElement(id)]));
global.Node = class {};
global.document = {
  createDocumentFragment: () => fakeElement(),
  createElement: () => fakeElement(),
  getElementById: (id) => registry[id],
  querySelector: (selector) => selector.startsWith("#document-lifecycle")
    ? registry["lifecycle-state"]
    : registry["observation-state"],
};

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\nstart\(\);\s*$/, "");
source += `
function job(jobId, state, overrides = {}) {
  return Object.assign({
    job_id: jobId,
    state,
    stage: null,
    input: {
      kind: "GUIDED",
      name: "policy-memo.md",
      media_type: "text/markdown",
      size: 20,
      sha256: "a".repeat(64),
    },
    observation: null,
    refresh: null,
    error: null,
  }, overrides);
}

function renderedStages() {
  const wrapper = elements.observationProgress.appended.at(-1);
  const value = wrapper.appended[1];
  return value.appended[0].appended;
}

function assertSequence(expectedStates, expectedCurrent = null) {
  const stages = renderedStages();
  const names = stages.map((item) => item.dataset.stage);
  if (names.join("|") !== OBSERVATION_STAGES.join("|")) {
    throw new Error("ordered stage sequence was not always present");
  }
  const states = stages.map((item) => item.dataset.stageState);
  if (states.join("|") !== expectedStates.join("|")) {
    throw new Error("dishonest stage states: " + states.join("|"));
  }
  const current = stages
    .filter((item) => item.attributes["aria-current"] === "step")
    .map((item) => item.dataset.stage);
  const expected = expectedCurrent === null ? [] : [expectedCurrent];
  if (current.join("|") !== expected.join("|")) {
    throw new Error("current real snapshot stage was not exact");
  }
}

renderObservationJob(job("jump", "RUNNING", {stage: "PREPARING_SOURCE"}));
assertSequence(
  ["Current", "Waiting", "Waiting", "Waiting", "Waiting", "Waiting"],
  "PREPARING_SOURCE",
);

renderObservationJob(job("jump", "RUNNING", {stage: "EXTRACTING_MARKITDOWN"}));
assertSequence(
  ["Completed", "Completed", "Current", "Waiting", "Waiting", "Waiting"],
  "EXTRACTING_MARKITDOWN",
);

renderObservationJob(job("jump", "COMPLETED", {
  observation: {status: "SUCCESS", observation_id: "ready", record_key: "r".repeat(64)},
  refresh: {status: "READY", message: null},
}));
assertSequence(["Completed", "Completed", "Completed", "Completed", "Completed", "Completed"]);

renderObservationJob(job("refresh-failed", "COMPLETED", {
  observation: {status: "SUCCESS", observation_id: "published", record_key: null},
  refresh: {status: "FAILED", message: "candidate rejected"},
}));
assertSequence(["Completed", "Completed", "Completed", "Completed", "Completed", "Failed"]);

renderObservationJob(job("reloaded-failure", "FAILED", {
  error: {code: "OBSERVATION_RUNTIME_FAILED", message: "observation failed"},
}));
assertSequence(["Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Not reached"]);

renderObservationJob(job("observed-failure", "RUNNING", {stage: "BUILDING_EVIDENCE"}));
renderObservationJob(job("observed-failure", "FAILED", {
  error: {code: "OBSERVATION_INTERNAL_FAILED", message: "observation failed"},
}));
assertSequence([
  "Completed",
  "Completed",
  "Completed",
  "Last observed",
  "Not reached or unknown",
  "Not reached",
]);
`;
vm.runInThisContext(source, {filename: process.argv[1]});
"""
        completed = subprocess.run(
            [node, "-e", harness, str(ASSETS / "workbench.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_observation_job_behavior_recovers_polls_selects_and_retains(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable for the bundled UI behavior test")
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function fakeElement(id = "") {
  return {
    id,
    appended: [],
    className: "",
    dataset: {},
    disabled: false,
    files: [],
    focusCount: 0,
    hidden: false,
    textContent: "",
    firstChild: null,
    append(...values) { this.appended.push(...values); },
    addEventListener() {},
    focus() { this.focusCount += 1; },
    querySelectorAll() { return []; },
    removeChild() { this.firstChild = null; },
    replaceWith() {},
    setAttribute() {},
  };
}

const ids = [
  "announcer", "observe-guided", "start-lifecycle", "observe-upload", "observation-file",
  "observation-state", "observation-message", "observation-alert",
  "observation-source", "observation-progress", "refresh-records",
  "record-count", "record-list", "record-view", "record-heading", "record-kind",
  "record-state", "record-summary", "record-content", "session-state",
  "session-message", "session-facts", "state-key", "lifecycle-state",
  "lifecycle-message", "lifecycle-alert", "lifecycle-content",
];
const registry = Object.fromEntries(ids.map((id) => [id, fakeElement(id)]));
global.Node = class {};
global.document = {
  createDocumentFragment: () => fakeElement(),
  createElement: () => fakeElement(),
  getElementById: (id) => registry[id],
  querySelector: (selector) => selector.startsWith("#observation")
    ? registry["observation-state"]
    : selector.startsWith("#document-lifecycle")
      ? registry["lifecycle-state"]
      : fakeElement(),
};

let scheduled = [];
global.setTimeout = (callback, delay) => {
  scheduled.push({callback, delay});
  return scheduled.length;
};
global.clearTimeout = () => {};

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\nstart\(\);\s*$/, "");
source += `
const capabilities = {
  guided: [
    {id: "policy-memo-md", name: "policy-memo.md", media_type: "text/markdown"},
    {id: "whitespace-cleanup-md", name: "whitespace-cleanup.md", media_type: "text/markdown"},
  ],
  upload: {extensions: [".docx", ".md", ".pdf", ".txt"], max_bytes: 33554432},
};
function input(kind = "GUIDED") {
  return {
    kind,
    name: kind === "UPLOAD" ? "learner memo.md" : "policy-memo.md",
    media_type: "text/markdown",
    size: 20,
    sha256: "a".repeat(64),
  };
}
function job(state, overrides = {}) {
  return Object.assign({
    job_id: "job-one",
    state,
    stage: null,
    input: input(),
    observation: null,
    refresh: null,
    error: null,
  }, overrides);
}

(async () => {
  const announcements = [];
  announce = (message) => { announcements.push(message); };
  let projectionLoads = 0;
  loadProjection = async () => {
    projectionLoads += 1;
    if (selectedRecordKey !== "r".repeat(64)) {
      throw new Error("returned observation record was not selected");
    }
    return true;
  };

  await handleObservationEnvelope({
    capabilities,
    job: job("RUNNING", {stage: "EXTRACTING_MARKITDOWN"}),
  });
  if (!elements.guidedButton.disabled || !elements.uploadButton.disabled) {
    throw new Error("active job did not disable both submits");
  }
  if (scheduled.length !== 1 || scheduled[0].delay !== 300) {
    throw new Error("active job did not schedule the one fixed interval");
  }
  if (!elements.observationMessage.textContent.includes("Extracting Markitdown")) {
    throw new Error("exact current stage was not presented");
  }
  if (announcements.join("|") !== "Observation stage: Extracting Markitdown.") {
    throw new Error("first active stage was not announced");
  }

  scheduled = [];
  await handleObservationEnvelope({
    capabilities,
    job: job("RUNNING", {stage: "EXTRACTING_MARKITDOWN"}),
  });
  if (announcements.length !== 1) {
    throw new Error("unchanged active stage was announced again");
  }

  scheduled = [];
  await handleObservationEnvelope({
    capabilities,
    job: job("RUNNING", {stage: "BUILDING_EVIDENCE"}),
  });
  if (announcements[1] !== "Observation stage: Building Evidence.") {
    throw new Error("changed active stage was not announced");
  }

  scheduled = [];
  await handleObservationEnvelope({
    capabilities,
    job: job("COMPLETED", {
      observation: {
        status: "SUCCESS",
        observation_id: "observation",
        record_key: "r".repeat(64),
      },
      refresh: {status: "READY", message: null},
    }),
  });
  if (projectionLoads !== 1) throw new Error("terminal READY did not reload projection");
  if (scheduled.length !== 0) throw new Error("terminal job continued polling");
  if (elements.guidedButton.disabled) throw new Error("terminal job kept guided disabled");

  let retainedLoads = projectionLoads;
  await handleObservationEnvelope({
    capabilities,
    job: job("COMPLETED", {
      job_id: "job-two",
      observation: {
        status: "SUCCESS",
        observation_id: "published",
        record_key: null,
      },
      refresh: {status: "FAILED", message: "candidate records are invalid"},
    }),
  });
  if (projectionLoads !== retainedLoads) {
    throw new Error("refresh failure replaced the current projection");
  }
  if (!elements.observationAlert.textContent.includes("was published")) {
    throw new Error("refresh failure did not distinguish publication");
  }
  if (!elements.observationAlert.textContent.includes("previous record view")) {
    throw new Error("refresh failure did not explain retention");
  }

  scheduled = [];
  const announcementsBeforeSuperseded = announcements.length;
  const alertFocusBeforeSuperseded = elements.observationAlert.focusCount;
  loadProjection = async () => false;
  await handleObservationEnvelope({
    capabilities,
    job: job("COMPLETED", {
      job_id: "job-superseded",
      observation: {
        status: "SUCCESS",
        observation_id: "published-superseded",
        record_key: "t".repeat(64),
      },
      refresh: {status: "READY", message: null},
    }),
  });
  if (selectedRecordKey !== "t".repeat(64)) {
    throw new Error("superseded terminal load discarded the returned record key");
  }
  if (handledTerminalJobId !== "job-superseded") {
    throw new Error("superseded terminal load was not marked handled");
  }
  if (!elements.observationAlert.hidden || elements.observationAlert.textContent) {
    throw new Error("superseded terminal load showed a false error");
  }
  if (elements.observationAlert.focusCount !== alertFocusBeforeSuperseded) {
    throw new Error("superseded terminal load moved focus to an error");
  }
  if (announcements.length !== announcementsBeforeSuperseded) {
    throw new Error("superseded terminal load announced an outcome");
  }
  if (scheduled.length !== 0) {
    throw new Error("superseded terminal load scheduled another poll");
  }

  let manualSelectedSupersededKey = false;
  loadProjection = async () => {
    manualSelectedSupersededKey = selectedRecordKey === "t".repeat(64);
    return true;
  };
  fetch = async (url) => {
    if (url === "/api/workbench/refresh") return {ok: true};
    throw new Error("unexpected superseding refresh URL " + url);
  };
  await refreshRecords();
  if (!manualSelectedSupersededKey) {
    throw new Error("manual refresh did not own the stored superseded selection");
  }
  if (announcements[announcements.length - 1] !== "Workspace records refreshed.") {
    throw new Error("manual refresh did not own the success announcement");
  }

  scheduled = [];
  loadProjection = async () => {
    throw new Error("detail route unavailable");
  };
  await handleObservationEnvelope({
    capabilities,
    job: job("COMPLETED", {
      job_id: "job-view-failure",
      observation: {
        status: "SUCCESS",
        observation_id: "published-ready",
        record_key: "s".repeat(64),
      },
      refresh: {status: "READY", message: null},
    }),
  });
  if (selectedRecordKey !== "s".repeat(64)) {
    throw new Error("terminal view failure discarded the returned record key");
  }
  if (handledTerminalJobId !== "job-view-failure") {
    throw new Error("terminal view failure was not marked handled");
  }
  if (!elements.observationAlert.textContent.includes("refresh succeeded")) {
    throw new Error("terminal view failure did not preserve refresh outcome");
  }
  if (!elements.observationAlert.textContent.includes("Use Refresh records")) {
    throw new Error("terminal view failure omitted manual recovery");
  }
  if (elements.observationAlert.textContent.includes("try again while the job is active")) {
    throw new Error("terminal view failure promised an active-job retry");
  }
  if (scheduled.length !== 0) {
    throw new Error("terminal view failure scheduled another poll");
  }

  let manualSelectedStoredKey = false;
  loadProjection = async () => {
    manualSelectedStoredKey = selectedRecordKey === "s".repeat(64);
    return true;
  };
  fetch = async (url) => {
    if (url === "/api/workbench/refresh") return {ok: true};
    throw new Error("unexpected manual recovery URL " + url);
  };
  await refreshRecords();
  if (!manualSelectedStoredKey) {
    throw new Error("manual refresh could not reuse the stored record key");
  }
  if (!announcements.includes("Workspace records refreshed.")) {
    throw new Error("manual refresh recovery was not announced");
  }

  const requests = [];
  elements.uploadInput.files = [{
    name: "learner memo.md",
    size: 20,
    bytes: "# Browser upload",
  }];
  latestObservationJob = null;
  observationCapabilities = capabilities;
  fetch = async (url, options) => {
    requests.push({url, options});
    return {
      ok: true,
      json: async () => ({job: job("QUEUED", {
        job_id: "job-three",
        input: input("UPLOAD"),
      })}),
    };
  };
  await submitUploadedObservation();
  if (requests[0].url !== "/api/observation-jobs/upload?filename=learner%20memo.md") {
    throw new Error("upload filename was not encoded into the local route");
  }
  if (requests[0].options.body !== elements.uploadInput.files[0]) {
    throw new Error("selected upload bytes were not submitted");
  }
})().catch((error) => {
  process.stderr.write(error.stack + "\\n");
  process.exitCode = 1;
});
`;
vm.runInThisContext(source, {filename: process.argv[1]});
"""
        completed = subprocess.run(
            [node, "-e", harness, str(ASSETS / "workbench.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_startup_failures_are_isolated_between_projection_and_observation(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable for the bundled UI behavior test")
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function fakeElement(id = "") {
  return {
    id,
    appended: [],
    className: "",
    dataset: {},
    disabled: true,
    files: [],
    hidden: false,
    textContent: "",
    firstChild: null,
    append(...values) { this.appended.push(...values); },
    addEventListener() {},
    focus() {},
    querySelectorAll() { return []; },
    removeChild() { this.firstChild = null; },
    replaceWith() {},
    setAttribute() {},
  };
}

const ids = [
  "announcer", "observe-guided", "start-lifecycle", "observe-upload", "observation-file",
  "observation-state", "observation-message", "observation-alert",
  "observation-source", "observation-progress", "refresh-records",
  "record-count", "record-list", "record-view", "record-heading", "record-kind",
  "record-state", "record-summary", "record-content", "session-state",
  "session-message", "session-facts", "state-key", "lifecycle-state",
  "lifecycle-message", "lifecycle-alert", "lifecycle-content",
];
const registry = Object.fromEntries(ids.map((id) => [id, fakeElement(id)]));
global.Node = class {};
global.document = {
  createDocumentFragment: () => fakeElement(),
  createElement: () => fakeElement(),
  getElementById: (id) => registry[id],
  querySelector: (selector) => selector.startsWith("#observation")
    ? registry["observation-state"]
    : selector.startsWith("#document-lifecycle")
      ? registry["lifecycle-state"]
      : registry["session-state"],
};

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\nstart\(\);\s*$/, "");
source += `
const capabilities = {
  guided: [
    {id: "policy-memo-md", name: "policy-memo.md", media_type: "text/markdown"},
    {id: "whitespace-cleanup-md", name: "whitespace-cleanup.md", media_type: "text/markdown"},
  ],
  upload: {extensions: [".docx", ".md", ".pdf", ".txt"], max_bytes: 33554432},
};

(async () => {
  renderStateKey = () => {};
  const announcements = [];
  announce = (message) => { announcements.push(message); };

  loadProjection = async () => {
    elements.sessionState.dataset.state = "READY";
    elements.sessionMessage.textContent = "Projection ready.";
    return true;
  };
  readObservationJobs = async () => {
    throw new Error("jobs unavailable");
  };
  await start();
  if (elements.sessionMessage.textContent !== "Projection ready.") {
    throw new Error("jobs failure replaced the successful projection");
  }
  if (elements.sessionState.dataset.state !== "READY") {
    throw new Error("jobs failure falsely marked the projection failed");
  }
  if (elements.observationMessage.textContent !== "Observation controls are unavailable.") {
    throw new Error("jobs failure did not identify the failed surface");
  }
  if (!elements.observationAlert.textContent.includes("Restart the local Workbench")) {
    throw new Error("jobs failure omitted accurate recovery guidance");
  }
  if (!elements.guidedButton.disabled || !elements.uploadButton.disabled) {
    throw new Error("unavailable observation controls were enabled");
  }
  if (elements.refreshButton.disabled) {
    throw new Error("projection recovery control remained disabled");
  }
  if (announcements.includes("The workbench projection is unavailable. Use Refresh records.")) {
    throw new Error("jobs failure announced a false projection failure");
  }

  const secondAnnouncementStart = announcements.length;
  elements.refreshButton.disabled = true;
  elements.guidedButton.disabled = true;
  elements.uploadButton.disabled = true;
  elements.observationAlert.hidden = false;
  elements.observationAlert.textContent = "old failure";
  observationCapabilities = null;
  latestObservationJob = null;
  loadProjection = async () => {
    throw new Error("projection unavailable");
  };
  readObservationJobs = async () => {
    observationCapabilities = capabilities;
    renderObservationJob(null);
  };
  await start();
  if (!elements.sessionMessage.textContent.includes("Use Refresh records")) {
    throw new Error("projection failure omitted manual recovery guidance");
  }
  if (elements.observationMessage.textContent !== "Run the guided example or observe one local document.") {
    throw new Error("projection failure replaced successful observation controls");
  }
  if (elements.guidedButton.disabled) {
    throw new Error("projection failure disabled successful guided controls");
  }
  if (!elements.observationAlert.hidden || elements.observationAlert.textContent) {
    throw new Error("projection failure showed a false observation error");
  }
  if (elements.refreshButton.disabled) {
    throw new Error("projection recovery control remained disabled");
  }
  const secondAnnouncements = announcements.slice(secondAnnouncementStart);
  if (!secondAnnouncements.includes("The workbench projection is unavailable. Use Refresh records.")) {
    throw new Error("projection failure was not announced accurately");
  }
  if (secondAnnouncements.includes("Observation controls are unavailable.")) {
    throw new Error("projection failure announced a false jobs failure");
  }
})().catch((error) => {
  process.stderr.write(error.stack + "\\n");
  process.exitCode = 1;
});
`;
vm.runInThisContext(source, {filename: process.argv[1]});
"""
        completed = subprocess.run(
            [node, "-e", harness, str(ASSETS / "workbench.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_proposals_are_isolated_by_diagnosis_and_dispatch_once(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable for the lifecycle state test")
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function fakeElement(id = "") {
  return {
    id,
    appended: [],
    attributes: {},
    className: "",
    dataset: {},
    disabled: false,
    hidden: false,
    listeners: {},
    textContent: "",
    firstChild: null,
    append(...values) { this.appended.push(...values); },
    addEventListener(type, handler) { this.listeners[type] = handler; },
    click() { return this.listeners.click && this.listeners.click(); },
    focus() {},
    querySelectorAll() { return []; },
    removeChild() { this.firstChild = null; },
    replaceWith() {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

const ids = [
  "announcer", "observe-guided", "start-lifecycle", "observe-upload",
  "observation-file", "observation-state", "observation-message",
  "observation-alert", "observation-source", "observation-progress",
  "refresh-records", "record-count", "record-list", "record-view",
  "record-heading", "record-kind", "record-state", "record-summary",
  "record-content", "session-state", "session-message", "session-facts",
  "state-key", "lifecycle-state", "lifecycle-message", "lifecycle-alert",
  "lifecycle-content",
];
const registry = Object.fromEntries(ids.map((id) => [id, fakeElement(id)]));
const navButtons = [fakeElement("nav-a"), fakeElement("nav-b")];
registry["record-list"].querySelectorAll = () => navButtons;
global.Node = class {};
global.document = {
  createDocumentFragment: () => fakeElement(),
  createElement: () => fakeElement(),
  getElementById: (id) => registry[id],
  querySelector: (selector) => selector.startsWith("#document-lifecycle")
    ? registry["lifecycle-state"]
    : fakeElement(),
};

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\nstart\(\);\s*$/, "");
source += `
function proposal(diagnosis, key) {
  return {
    draft_key: key,
    draft_id: "draft-" + key,
    diagnosis_record_key: diagnosis,
    base_record_key: "f".repeat(64),
    finding: {finding_id: "1".repeat(64), rule_id: "D009", summary: "whitespace"},
    refiner: {refiner_id: "R001", name: "Whitespace normalization", version: "1"},
    affected_refs: ["#/texts/0"],
    edits: [{target: {reference: "#/texts/0"}, before: "  before", after: "before"}],
    cli_continuation: {
      proposal_path: "/draft.json", diagnosis_path: "/diagnosis",
      base_path: "/base", output_root_path: "/revisions",
    },
  };
}

(async () => {
  const a = "a".repeat(64);
  const b = "b".repeat(64);
  const keyA = "1".repeat(64);
  const keyB = "2".repeat(64);
  actionToken = "token";
  announce = () => {};
  let displayed = null;
  renderDocumentLifecycle = () => {
    displayed = proposalsByDiagnosis.get(selectedRecordKey) || null;
  };
  const urls = [];
  fetch = async (url) => {
    urls.push(url);
    if (url.endsWith("/" + a + "/" + "1".repeat(64))) {
      return {ok: true, json: async () => ({draft: proposal(a, keyA)})};
    }
    if (url.endsWith("/" + b + "/" + "1".repeat(64))) {
      return {ok: true, json: async () => ({draft: proposal(b, keyB)})};
    }
    if (url.endsWith("/" + keyA + "/approve")) {
      return {ok: true, json: async () => ({
        publication: {decision: "APPROVED", record_key: null},
        refresh: {status: "FAILED", message: "candidate rejected"},
      })};
    }
    throw new Error("unexpected URL " + url);
  };

  selectedRecordKey = a;
  await createProposal(a, "1".repeat(64));
  if (displayed === null || displayed.draft_key !== keyA) {
    throw new Error("proposal A was not displayed in diagnosis A");
  }
  selectedRecordKey = b;
  renderDocumentLifecycle();
  if (displayed !== null) {
    throw new Error("proposal A leaked into diagnosis B");
  }
  await createProposal(b, "1".repeat(64));
  if (displayed === null || displayed.draft_key !== keyB) {
    throw new Error("proposal B was not displayed in diagnosis B");
  }
  selectedRecordKey = a;
  renderDocumentLifecycle();
  if (displayed === null || displayed.draft_key !== keyA) {
    throw new Error("returning to diagnosis A did not restore proposal A");
  }

  let release;
  fetch = (url) => {
    urls.push(url);
    return new Promise((resolve) => {
      release = () => resolve({ok: true, json: async () => ({draft: proposal(a, keyA)})});
    });
  };
  const pending = createProposal(a, "1".repeat(64));
  if (!navButtons.every((button) => button.disabled)) {
    throw new Error("record navigation stayed enabled during a lifecycle POST");
  }
  selectedRecordKey = b;
  release();
  await pending;
  if (navButtons.some((button) => button.disabled)) {
    throw new Error("record navigation stayed disabled after the lifecycle POST");
  }
  if (displayed !== proposalsByDiagnosis.get(b)) {
    throw new Error("the A response overwrote the selected B context");
  }

  registry["record-list"].appended = [];
  selectRecord = (record) => {
    selectedRecordKey = record.record_key;
    displayed = proposalsByDiagnosis.get(selectedRecordKey) || null;
    return Promise.resolve(true);
  };
  const equivalent = [a, b].map((record_key) => ({
    record_key,
    kind: "DIAGNOSIS",
    status: "FINDINGS",
    run_id: "same-run",
    primary_identity: {name: "diagnosis_id", value: "same-identity"},
    origin: "TOP_LEVEL",
    artifact_count: 3,
  }));
  selectedRecordKey = a;
  await renderNavigation({records: equivalent}, 0);
  const renderedButtons = registry["record-list"].appended;
  if (renderedButtons[0].appended[1].textContent === renderedButtons[1].appended[1].textContent) {
    throw new Error("equivalent diagnosis navigation labels were identical");
  }
  if (renderedButtons[0].attributes["aria-label"] === renderedButtons[1].attributes["aria-label"]) {
    throw new Error("equivalent diagnosis accessibility names were identical");
  }
  await renderedButtons[1].click();
  if (selectedRecordKey !== b || displayed.draft_key !== keyB) {
    throw new Error("diagnosis B navigation did not select and restore proposal B");
  }
  await renderedButtons[0].click();
  if (selectedRecordKey !== a || displayed.draft_key !== keyA) {
    throw new Error("returning through navigation did not restore proposal A");
  }

  fetch = async (url) => {
    urls.push(url);
    return {ok: true, json: async () => ({
      publication: {decision: "APPROVED", record_key: null},
      refresh: {status: "FAILED", message: "candidate rejected"},
    })};
  };
  const explicitA = proposalsByDiagnosis.get(a);
  const explicitB = proposalsByDiagnosis.get(b);
  await resolveProposal(explicitA, "approve");
  await resolveProposal(explicitA, "approve");
  await resolveProposal(explicitB, "reject");
  const resolutionUrls = urls.filter((url) => url.endsWith("/" + keyA + "/approve"));
  if (resolutionUrls.length !== 1) {
    throw new Error("a dispatched draft resolved more than once");
  }
  if (urls.filter((url) => url.endsWith("/" + keyB + "/reject")).length !== 1) {
    throw new Error("diagnosis B did not resolve with proposal B's draft key");
  }

  const tokenKey = "3".repeat(64);
  const tokenProposal = proposal(a, tokenKey);
  actionToken = "stale";
  let mutationAttempts = 0;
  let tokenFetches = 0;
  const rejectedUrls = [];
  fetch = async (url) => {
    if (url.endsWith("/lifecycle/action-token")) {
      tokenFetches += 1;
      return {ok: true, json: async () => ({action_token: "fresh"})};
    }
    mutationAttempts += 1;
    rejectedUrls.push(url);
    return {ok: false, status: 403, json: async () => ({
      code: "ACTION_TOKEN_INVALID", message: "invalid token",
    })};
  };
  await resolveProposal(tokenProposal, "approve");
  if (
    mutationAttempts !== 1
    || tokenFetches !== 1
    || actionToken !== "fresh"
    || dispatchedDraftKeys.has(tokenKey)
    || !rejectedUrls[0].endsWith("/" + tokenKey + "/approve")
  ) {
    throw new Error("token recovery replayed a mutation or failed to refresh the token");
  }
  fetch = async (url) => {
    urls.push(url);
    return {ok: true, json: async () => ({
      publication: {decision: "APPROVED", record_key: null},
      refresh: {status: "FAILED", message: "candidate rejected"},
    })};
  };
  await resolveProposal(tokenProposal, "approve");
  if (urls.filter((url) => url.endsWith("/" + tokenKey + "/approve")).length !== 1) {
    throw new Error("the second explicit click did not use the same exact draft key");
  }
})().catch((error) => {
  process.stderr.write(error.stack + "\\n");
  process.exitCode = 1;
});
`;
vm.runInThisContext(source, {filename: process.argv[1]});
"""
        completed = subprocess.run(
            [node, "-e", harness, str(ASSETS / "workbench.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_reordered_detail_responses_cannot_replace_active_selection(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable for the bundled UI behavior test")
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function fakeElement(id = "") {
  return {
    id,
    appended: [],
    dataset: {},
    disabled: false,
    hidden: false,
    textContent: "",
    firstChild: null,
    append(...values) { this.appended.push(...values); },
    addEventListener() {},
    focus() {},
    querySelectorAll() { return []; },
    removeChild() {},
    replaceWith() {},
    setAttribute() {},
  };
}

const ids = [
  "announcer", "refresh-records", "record-count", "record-list", "record-view",
  "record-heading", "record-kind", "record-state", "record-summary",
  "record-content", "session-state", "session-message", "session-facts",
  "state-key", "lifecycle-state", "lifecycle-message", "lifecycle-alert",
  "lifecycle-content",
];
const registry = Object.fromEntries(ids.map((id) => [id, fakeElement(id)]));
global.Node = class {};
global.document = {
  createDocumentFragment: () => fakeElement(),
  createElement: () => fakeElement(),
  getElementById: (id) => registry[id],
  querySelector: () => fakeElement(),
};

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\nstart\(\);\s*$/, "");
source += `
const renders = [];
const announcements = [];
renderRecordSummary = (record) => { renders.push(record.record_key); };
renderRelationships = () => fakeElement();
renderObservation = () => fakeElement();
announce = (message) => { announcements.push(message); };

function record(key) {
  return {
    record_key: key,
    kind: "OBSERVATION",
    status: "SUCCESS",
    primary_identity: {value: key},
  };
}
function detail() {
  return {kind: "OBSERVATION", artifacts: [], relationships: [], view: {}};
}
function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return {promise, resolve};
}

(async () => {
  const pending = new Map();
  fetch = (url) => {
    const value = deferred();
    pending.set(url, value);
    return value.promise;
  };
  const first = loadRecord(record("first"));
  const second = loadRecord(record("second"));
  pending.get("/api/records/second").resolve({
    ok: true,
    json: async () => detail(),
  });
  if (await second !== true) throw new Error("active detail did not render");
  pending.get("/api/records/first").resolve({
    ok: true,
    json: async () => detail(),
  });
  if (await first !== false) throw new Error("stale detail was not rejected");
  if (renders.join(",") !== "second") {
    throw new Error("stale detail replaced the active selection");
  }
  if (selectedRecordKey !== "second") throw new Error("selection changed");

  const detailResponse = deferred();
  const projection = {
    session_id: "session",
    counts: {
      record_count: 1,
      top_level_record_count: 1,
      contained_record_count: 0,
    },
    refresh: {status: "READY", message: null},
    records: [record("refreshed")],
  };
  fetch = async (url) => {
    if (url === "/api/workbench/refresh") return {ok: true};
    if (url === "/api/workbench") {
      return {ok: true, json: async () => projection};
    }
    if (url === "/api/records/refreshed") return detailResponse.promise;
    throw new Error("unexpected URL " + url);
  };
  const refresh = refreshRecords();
  await Promise.resolve();
  await Promise.resolve();
  if (!elements.refreshButton.disabled) {
    throw new Error("refresh control enabled before detail completed");
  }
  if (announcements.includes("Workspace records refreshed.")) {
    throw new Error("refresh announced completion before detail completed");
  }
  detailResponse.resolve({ok: true, json: async () => detail()});
  await refresh;
  if (elements.refreshButton.disabled) {
    throw new Error("refresh control remained disabled");
  }
  if (!announcements.includes("Workspace records refreshed.")) {
    throw new Error("refresh completion was not announced");
  }
})().catch((error) => {
  process.stderr.write(error.stack + "\\n");
  process.exitCode = 1;
});
`;
vm.runInThisContext(source, {filename: process.argv[1]});
"""
        completed = subprocess.run(
            [node, "-e", harness, str(ASSETS / "workbench.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_ui_uses_exactly_the_ten_comparison_metrics(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        start = script.index("const COMPARISON_METRICS = [")
        end = script.index("];", start)
        block = script[start:end]
        expected = {
            "bytes",
            "characters",
            "non_whitespace_characters",
            "lines",
            "non_empty_lines",
            "atx_headings",
            "unordered_list_items",
            "ordered_list_items",
            "pipe_table_rows",
            "visible_urls",
        }
        self.assertEqual(
            {
                line.strip().strip('",')
                for line in block.splitlines()[1:]
                if line.strip()
            },
            expected,
        )
        self.assertEqual(script.count("COMPARISON_METRICS.map"), 1)
        self.assertIn(
            '"Member extractor comparison metrics"',
            script,
        )
        self.assertIn(
            '"Member normalized equality"',
            script,
        )
        self.assertIn(
            '{label: "Docling", render: (row) => metricValue(row.docling, row.metric)}',
            script,
        )
        self.assertIn(
            '{label: "MarkItDown", render: (row) => metricValue(row.markitdown, row.metric)}',
            script,
        )
        self.assertIn(
            '{label: "Signed delta", render: (row) => signedMetricValue(row.delta, row.metric)}',
            script,
        )

    def test_corpus_comparison_unavailable_and_signed_values_are_explicit(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        self.assertIn('return view === null ? "Not available" : view[metric];', script)
        self.assertIn('return value >= 0 ? `+${value}` : String(value);', script)
        self.assertIn(
            'row.docling_minus_markitdown === null ? "Not available"',
            script,
        )

    def test_artifact_content_requires_a_button_action_and_plain_text_fetch(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        self.assertIn('"Retrieve plain text"', script)
        self.assertIn('headers: {"Accept": "text/plain"}', script)
        self.assertIn("await response.text()", script)
        self.assertIn('result.textContent = await response.text()', script)

    def test_script_has_no_html_execution_navigation_or_persistence_capability(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for forbidden in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
            "window.open",
            "location",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "serviceWorker",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)
        self.assertIn("document.createElement", script)
        self.assertIn(".textContent", script)

    def test_validator_rejects_remote_assets_and_unsafe_dom_construction(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            copy = Path(temporary)
            for source in ASSETS.iterdir():
                shutil.copyfile(source, copy / source.name)
            js_path = copy / "workbench.js"
            js_path.write_text(
                js_path.read_text("utf-8")
                + '\ndocument.body.innerHTML = "<img>";\n'
                + 'fetch("https://example.invalid/data");\n',
                "utf-8",
            )
            errors = validate(copy)
        self.assertTrue(any("remote" in error for error in errors))
        self.assertTrue(any("innerHTML" in error for error in errors))

    def test_validator_rejects_external_html_resource(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            copy = Path(temporary)
            for source in ASSETS.iterdir():
                shutil.copyfile(source, copy / source.name)
            html_path = copy / "index.html"
            html_path.write_text(
                html_path.read_text("utf-8").replace(
                    "</head>",
                    '<link rel="stylesheet" href="https://example.invalid/x.css"></head>',
                ),
                "utf-8",
            )
            errors = validate(copy)
        self.assertTrue(any("non-local" in error for error in errors))
        self.assertTrue(any("remote" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
