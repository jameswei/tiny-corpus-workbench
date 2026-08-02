from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tiny_corpus_workbench.application.workbench import WorkbenchState
from tiny_corpus_workbench.application.refinement import supported_refiner
from tiny_corpus_workbench.application.observation_jobs import (
    JobInput,
    JobError,
    JobObservation,
    JobRefresh,
    ObservationJob,
)
from tiny_corpus_workbench.diagnosis_rules import CURRENT_RULES
from tiny_corpus_workbench.workbench_server import WorkbenchApplication
from tools.validate_workbench_assets import validate


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src/tiny_corpus_workbench/workbench_assets"


class WorkbenchUIContractTests(unittest.TestCase):
    def test_assets_are_exactly_the_build_free_validated_inventory(self) -> None:
        self.assertEqual(validate(ASSETS), [])
        self.assertEqual(
            {path.name for path in ASSETS.iterdir() if path.is_file()},
            {"index.html", "workbench.css", "workbench.js"},
        )

    def test_candidate_a_shell_and_modal_contract_are_semantic(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        for marker in (
            "<h1>Corpus Workbench</h1>",
            'id="package-version"',
            'id="rule-reference"',
            'id="locale-toggle"',
            'id="refresh-workspace"',
            'id="document-list"',
            'id="corpus-list"',
            'id="stage-stepper"',
            'id="central-surface"',
            'role="tablist"',
            'id="add-modal"',
            'id="rule-modal"',
            'role="dialog" aria-modal="true"',
            ">GitHub Repository<",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)
        self.assertNotIn("Local workspace · Ready", html)
        self.assertNotIn("Observe again", html)
        self.assertNotIn(">https://github.com", html)

    def test_add_modal_has_exactly_two_guides_and_one_supported_upload(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        self.assertEqual(html.count('class="path-card'), 3)
        self.assertIn("whitespace-cleanup.md", html)
        self.assertIn("policy-memo.md", html)
        self.assertIn('accept=".docx,.md,.pdf,.txt"', html)
        self.assertIn("up to 32 MiB", html)

    def test_css_has_stable_desktop_shell_and_natural_narrow_reflow(self) -> None:
        css = (ASSETS / "workbench.css").read_text("utf-8")
        for marker in (
            "--sidebar: 17rem",
            "grid-template-columns: var(--sidebar) minmax(0, 1fr)",
            "width: var(--sidebar)",
            "-webkit-line-clamp: 2",
            "align-items: start",
            "@media (max-width: 760px)",
            ".workbench-shell { display: block; }",
            "@media (prefers-reduced-motion: reduce)",
            ":focus-visible",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, css)

    def test_script_uses_t1_payload_and_same_origin_routes_without_unsafe_dom(self) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for marker in (
            "projection.documents",
            "projection.corpora",
            "projection.package_version",
            "projection.reference.rules",
            '`${API_ROOT}/workbench/refresh`',
            '`${API_ROOT}/observation-jobs/guided/${guidedId}`',
            '`${API_ROOT}/observation-jobs/upload?filename=${encodeURIComponent(file.name)}`',
            "envelope.reactivation.document_key",
            "document.createElement",
            ".textContent",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        for forbidden in ("innerHTML", "insertAdjacentHTML", "window.open", "WebSocket"):
            self.assertNotIn(forbidden, script)

    def test_node_backed_state_locale_toast_and_modal_scenarios(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js 24.18.1 is required for dynamic Workbench DOM tests")
        version = subprocess.run(
            [node, "--version"], check=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertRegex(version, r"^v\d+\.\d+\.\d+$")
        reference = {
            "rules": [
                {**rule, "refiner": supported_refiner(rule["rule_id"])}
                for rule in CURRENT_RULES
            ]
        }
        job_input = JobInput(
            "GUIDED", "new.md", "text/markdown", 10, "a" * 64
        )
        backend_jobs = {
            "queued": ObservationJob(
                "job-1", "QUEUED", None, job_input, None, None, None
            ).to_dict(),
            "running": ObservationJob(
                "job-1", "RUNNING", "EXTRACTING_DOCLING", job_input, None, None, None
            ).to_dict(),
            "ready": ObservationJob(
                "job-1",
                "COMPLETED",
                None,
                job_input,
                JobObservation("SUCCESS", "obs-new", "record-new"),
                JobRefresh("READY", None),
                None,
            ).to_dict(),
            "refreshFailed": ObservationJob(
                "job-1",
                "COMPLETED",
                None,
                job_input,
                JobObservation("SUCCESS", "obs-new", None),
                JobRefresh("FAILED", "candidate invalid"),
                None,
            ).to_dict(),
            "refreshFailedNoObservation": ObservationJob(
                "job-1",
                "COMPLETED",
                None,
                job_input,
                None,
                JobRefresh("FAILED", "metadata construction failed"),
                None,
            ).to_dict(),
            "failed": ObservationJob(
                "job-1",
                "FAILED",
                None,
                job_input,
                None,
                None,
                JobError("INPUT_ERROR", "source was not accepted"),
            ).to_dict(),
            "runningB": ObservationJob(
                "job-2", "RUNNING", "BUILDING_EVIDENCE", job_input, None, None, None
            ).to_dict(),
            "failedB": ObservationJob(
                "job-2",
                "FAILED",
                None,
                job_input,
                None,
                None,
                JobError("INPUT_ERROR", "second source was not accepted"),
            ).to_dict(),
            "refreshFailedB": ObservationJob(
                "job-2",
                "COMPLETED",
                None,
                job_input,
                None,
                JobRefresh("FAILED", "second publication refresh failed"),
                None,
            ).to_dict(),
        }
        harness = r'''
const fs = require("fs");
const vm = require("vm");
global.__TCW_TEST_NO_START__ = true;
global.window = {};
global.localStorage = {value: null, getItem() { return this.value; }, setItem(_k, v) { this.value = v; }};
const registry = {};
const i18nNodes = [];
const tabs = [fake("button"), fake("button"), fake("button")];
for (const [tab, name] of tabs.map((value, index) => [value, ["summary", "evidence", "artifacts"][index]])) tab.dataset.tab = name;
function fake(tag = "div", id = "") {
  return {
    tag, id, children: [], dataset: {}, attributes: {}, hidden: false, inert: false,
    textContent: "", title: "", firstChild: null, listeners: {}, disabled: false, files: [],
    append(...values) { this.children.push(...values); this.firstChild = this.children[0] || null; },
    removeChild() { this.children.shift(); this.firstChild = this.children[0] || null; },
    addEventListener(type, fn) { this.listeners[type] = fn; },
    setAttribute(k, v) { this.attributes[k] = v; },
    querySelector(selector) { return selector === ".modal-close" ? this.closeButton : null; },
    querySelectorAll(selector) { return selector === "li" ? (this.stageEntries || []) : (this.focusables || []); },
    contains(value) { return this === value || this.children.includes(value); },
    focus() { document.activeElement = this; },
  };
}
global.document = {
  activeElement: null,
  documentElement: {lang: "en"},
  createElement(tag) { return fake(tag); },
  getElementById(id) { return registry[id]; },
  querySelectorAll(selector) { if (selector === "[data-i18n]") return i18nNodes; if (selector === "[role=tab]") return tabs; return []; },
};
let nextTimer = 1;
const timers = new Map();
global.setTimeout = (fn, delay) => { const id = nextTimer++; timers.set(id, {fn, delay}); return id; };
global.clearTimeout = (id) => timers.delete(id);
const requests = [];
const responses = [];
function response(body, status = 200) { return {ok: status >= 200 && status < 300, status, async json() { return body; }}; }
global.fetch = async (target, options = {}) => { requests.push([target, options.method || "GET"]); const value = responses.shift(); if (value instanceof Error) throw value; return value; };
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"), {filename: process.argv[1]});
const api = window.__tcwWorkbench;
const e = api.elements;
for (const id of ["workspace-navigation", "stage-inspector"]) registry[id] = fake("div", id);
Object.assign(e, {
  surface: fake(), version: fake(), ruleButton: fake("button"), localeToggle: fake("button"), refresh: fake("button"), add: fake("button"),
  documents: fake(), corpora: fake(), workspaceState: fake(), selected: fake(), contextKind: fake(), contextName: fake(),
  roundContext: fake(), stepper: fake("ol"), central: fake(), stageHeading: fake(), stageGuidance: fake(), inspectorPanel: fake(), tabs,
  toast: fake(), toastMessage: fake(), toastClose: fake("button"), polite: fake(), assertive: fake(),
  addModal: fake(), ruleModal: fake(), ruleList: fake(), file: fake("input"), upload: fake("button"),
  guidedWhitespace: fake("button"), guidedPolicy: fake("button")
});
e.stepper.stageEntries = ["observe", "diagnose", "refine", "revision"].map(stage => { const item = fake("li"); item.dataset.stage = stage; return item; });
const summaryLabel = fake(); summaryLabel.dataset.i18n = "summary"; i18nNodes.push(summaryLabel);
const reference = JSON.parse(process.argv[2]);
const backendJobs = JSON.parse(process.argv[3]);
function projection(session, docs) { return {session_id: session, package_version: "0.8.1", reference, records: [], documents: docs, corpora: []}; }
const oldDoc = {document_key: "doc-old", observation_record_key: "record-old", source: {name: "old.md", media_type: "text/markdown"}, rounds: []};
const newDoc = {document_key: "doc-new", observation_record_key: "record-new", source: {name: "new.md", media_type: "text/markdown"}, rounds: []};
(async () => {
const outputs = {};
outputs.parity = api.catalogParity();
outputs.registryCoverage = [api.catalogCoversReference(reference), api.catalogCoversReference({rules: reference.rules.slice(0, 9)})];
outputs.negotiated = api.negotiatedLocale(["zh-Hans-CN", "en"], null);
outputs.fallback = api.negotiatedLocale(["fr-FR"], null);
outputs.override = api.negotiatedLocale(["zh-CN"], "en");

api.state.selectedKind = "document"; api.state.selectedKey = "doc-b"; api.state.stage = "refine"; api.state.inspector = "artifacts";
const stableProjection = {session_id: "two", package_version: "0.8.1", reference, records: [],
  documents: [{document_key: "doc-a", source: {name: "a.md"}}, {document_key: "doc-b", source: {name: "b.md"}}], corpora: []};
api.applyProjection(stableProjection);
outputs.selection = [api.state.selectedKey, api.state.stage, api.state.inspector, api.state.projection.documents.map(x => x.document_key).join(",")];
api.setLocale("zh-CN", false);
outputs.localeStable = [api.state.locale, api.state.selectedKey, api.state.stage, api.state.inspector, document.documentElement.lang, e.localeToggle.textContent, e.localeToggle.attributes["aria-label"], registry["workspace-navigation"].attributes["aria-label"], summaryLabel.textContent];

api.showToast("ok", "success");
outputs.successToast = [e.toast.hidden, e.polite.textContent, e.assertive.textContent, Array.from(timers.values())[0].delay];
api.setToastHover(true); api.setToastFocus(true); api.setToastHover(false); outputs.hoverFocusHeld = timers.size; api.setToastFocus(false); outputs.hoverFocusReleased = timers.size;
api.showToast("ok2", "success"); api.setToastFocus(true); api.setToastHover(true); api.setToastFocus(false); outputs.focusHoverHeld = timers.size; api.setToastHover(false); outputs.focusHoverReleased = timers.size;
api.showToast("bad", "failure"); outputs.failureToast = [timers.size, e.assertive.textContent, e.toast.dataset.tone];
api.showToast("recovered", "success"); outputs.replaced = [e.toastMessage.textContent, e.toast.dataset.tone, timers.size];
api.dismissToast(); outputs.dismissed = e.toast.hidden;

e.surface = fake(); const opener = fake("button"); opener.focus();
const close = fake("button"), last = fake("button"), modal = fake(); modal.focusables = [close, last];
api.openModal(modal); outputs.modalOpen = [modal.hidden, e.surface.inert, document.activeElement === close];
last.focus(); let prevented = 0; api.modalKeydown({currentTarget:modal,key:"Tab",shiftKey:false,preventDefault(){prevented++;}}); const wrappedForward = document.activeElement === close;
close.focus(); api.modalKeydown({currentTarget:modal,key:"Tab",shiftKey:true,preventDefault(){prevented++;}}); const wrappedBackward = document.activeElement === last;
api.modalKeydown({currentTarget:modal,key:"Escape",shiftKey:false,preventDefault(){prevented++;}}); outputs.modalKeys = [wrappedForward, wrappedBackward, modal.hidden, document.activeElement === opener, prevented];
opener.focus(); api.openModal(modal); api.backdropDismiss({target:modal,currentTarget:modal}); outputs.backdrop = [modal.hidden, document.activeElement === opener];

api.state.locale = "en"; api.applyProjection(projection("old", [oldDoc]), "doc-old"); api.state.stage = "diagnose"; api.state.inspector = "evidence"; api.render();
const acceptedView = api.state.projection;
await api.consumeObservationJob(backendJobs.queued, "job-1");
outputs.active = [api.state.activeObservationJobId, e.add.disabled, e.guidedWhitespace.disabled, e.file.disabled, timers.size];
await api.consumeObservationJob(backendJobs.refreshFailed, "job-1");
outputs.publishedRefreshFailed = [api.state.projection === acceptedView, api.state.selectedKey, api.state.stage, api.state.inspector, e.toast.dataset.tone, e.toastMessage.textContent.includes("published"), e.add.disabled];
await api.consumeObservationJob(backendJobs.refreshFailedNoObservation, "job-1");
outputs.publishedRefreshFailedNoObservation = [api.state.projection === acceptedView, api.state.selectedKey, e.toast.dataset.tone, e.toastMessage.textContent.includes("Use Refresh workspace")];

responses.push(response(projection("ready", [newDoc, oldDoc])));
await api.consumeObservationJob(backendJobs.ready, "job-1");
outputs.ready = [api.state.projection.session_id, api.state.selectedKey, api.state.stage, e.toast.dataset.tone, e.add.disabled];

responses.push(response(projection("duplicate", [oldDoc, newDoc])));
await api.handleObservationEnvelope({job:null,reactivation:{document_key:"doc-old",observation_record_key:"record-old"}}, "old.md");
outputs.duplicate = [api.state.selectedKey, api.state.projection.documents.map(x => x.document_key).join(","), e.toastMessage.textContent.includes("already exists")];

responses.push(response({job:null,reactivation:{document_key:"doc-old",observation_record_key:"record-old"}}), response({message:"projection unavailable"}, 500));
await api.submitGuidedObservation("policy-memo-md", "policy-memo.md");
outputs.reactivationLoadUnknown = [api.state.activeObservationJobId, e.add.disabled, timers.size > 0, e.toastMessage.textContent.includes("no action was replayed")];
responses.push(response({job:null}), response(projection("reactivated-recovered", [oldDoc, newDoc]))); await api.discoverActiveObservation();
outputs.reactivationRecovered = [api.state.pendingReactivationKey, api.state.activeObservationJobId, api.state.selectedKey, e.add.disabled, e.addModal.hidden, e.toastMessage.textContent.includes("already exists")];

api.state.stage = "refine"; api.state.inspector = "artifacts";
responses.push(response(null, 204), response(projection("manual-new", [oldDoc, newDoc]))); await api.refreshWorkspace();
outputs.refreshSuccess = [api.state.selectedKey, api.state.stage, api.state.inspector, e.toastMessage.textContent === "Workspace refreshed."];
const beforeRefresh = api.state.projection;
responses.push(response(null, 204), response(beforeRefresh)); await api.refreshWorkspace();
outputs.refreshNoChange = [api.state.selectedKey, api.state.stage, api.state.inspector, e.toastMessage.textContent.includes("up to date")];
responses.push(response({code:"WORKSPACE_REFRESH_FAILED",message:"invalid"}, 409)); await api.refreshWorkspace();
outputs.refreshFailure = [api.state.projection === beforeRefresh, api.state.selectedKey, e.toast.dataset.tone, e.toastMessage.textContent.includes("preserved")];

api.state.projection = null; api.state.selectedKey = null; api.state.selectedKind = null; responses.push(response({message:"bad"}, 500));
await api.loadProjection({initial:true}).catch(() => {}); const initialFailure = [api.state.initialFailure, e.add.disabled, e.assertive.textContent];
responses.push(response(null, 204), response(projection("recovered", [oldDoc]))); await api.refreshWorkspace();
outputs.initialRecovery = [initialFailure[0], initialFailure[1], initialFailure[2].includes("could not be loaded"), api.state.initialFailure, api.state.selectedKey, e.add.disabled];

api.setObservationActive(backendJobs.running); const requestsBeforeBusy = requests.length; await api.submitGuidedObservation("policy-memo-md", "policy-memo.md");
outputs.localBusy = [requests.length === requestsBeforeBusy, e.toastMessage.textContent.includes("already running"), e.add.disabled];
api.setObservationActive(null);
let resolveDeferred; const deferredPost = new Promise(resolve => { resolveDeferred = resolve; }); responses.push(deferredPost);
const requestsBeforeDeferred = requests.length; const firstSubmission = api.submitGuidedObservation("policy-memo-md", "policy-memo.md");
const immediateClaim = [api.state.activeObservationJobId, e.add.disabled, e.guidedPolicy.disabled, requests.length === requestsBeforeDeferred + 1];
await api.submitGuidedObservation("policy-memo-md", "policy-memo.md"); const rapidSecondSentNoRequest = requests.length === requestsBeforeDeferred + 1;
resolveDeferred(response({job:backendJobs.queued})); await firstSubmission;
outputs.deferredClaim = [...immediateClaim, rapidSecondSentNoRequest, api.state.activeObservationJobId, timers.size > 0];

api.setObservationActive(null); responses.push(new Error("transport lost")); const requestsBeforeUnknown = requests.length; await api.submitGuidedObservation("policy-memo-md", "policy-memo.md");
outputs.submissionUnknown = [requests.length === requestsBeforeUnknown + 1, api.state.activeObservationJobId, e.add.disabled, timers.size > 0, e.toastMessage.textContent.includes("no action was replayed")];

api.setObservationActive(null); responses.push(response({code:"OBSERVATION_BUSY",message:"one observation is already active"}, 409), response({job:backendJobs.running})); const beforeServerBusy = requests.length; await api.submitGuidedObservation("policy-memo-md", "policy-memo.md");
outputs.serverBusy = [requests.length === beforeServerBusy + 2, e.toastMessage.textContent.includes("already running"), e.toast.dataset.tone, api.state.activeObservationJobId];

api.applyProjection(projection("startup-base", [oldDoc]), "doc-old"); const startupAccepted = api.state.projection; api.state.stage = "diagnose"; api.state.inspector = "evidence";
responses.push(response({job:backendJobs.ready}), response(projection("startup-ready", [newDoc, oldDoc]))); await api.discoverActiveObservation();
outputs.startupReady = [api.state.projection.session_id, api.state.selectedKey, api.state.stage, e.toast.dataset.tone];

api.applyProjection(projection("startup-preserved", [oldDoc]), "doc-old"); const startupPreserved = api.state.projection; api.state.stage = "refine"; api.state.inspector = "artifacts";
responses.push(response({job:backendJobs.refreshFailed})); await api.discoverActiveObservation();
outputs.startupRefreshFailed = [api.state.projection === startupPreserved, api.state.selectedKey, api.state.stage, api.state.inspector, e.toast.dataset.tone, e.toastMessage.textContent.includes("do not run Observe again")];

responses.push(response({job:backendJobs.failed})); await api.discoverActiveObservation();
outputs.startupFailed = [api.state.projection === startupPreserved, api.state.activeObservationJobId, e.add.disabled, e.toast.dataset.tone, e.toastMessage.textContent === "Observe could not start."];

responses.push(response({job:backendJobs.refreshFailedNoObservation})); await api.discoverActiveObservation();
outputs.startupRefreshFailedNoObservation = [api.state.projection === startupPreserved, api.state.selectedKey, e.toast.dataset.tone, e.toastMessage.textContent.includes("do not run Observe again")];

responses.push(response({job:backendJobs.running})); await api.discoverActiveObservation(); outputs.startupActive = [api.state.activeObservationJobId, e.add.disabled, timers.size > 0];
responses.push(new Error("transient")); const requestCount = requests.length; await api.pollObservation("job-1"); outputs.transient = [api.state.activeObservationJobId, e.add.disabled, timers.size > 0, requests.length === requestCount + 1, e.toastMessage.textContent.includes("no action was replayed")];

responses.push(response({job:backendJobs.runningB})); await api.pollObservation("job-1"); const followedB = [api.state.activeObservationJobId, e.add.disabled, timers.size > 0];
responses.push(response({job:backendJobs.failedB})); await api.pollObservation("job-2");
outputs.jobMismatch = [...followedB, api.state.activeObservationJobId, e.add.disabled, timers.size, e.toastMessage.textContent === "Observe could not start."];

api.applyProjection(projection("combined-base", [oldDoc, newDoc]), "doc-new");
const combinedRequestStart = requests.length;
responses.push(response({job:null,reactivation:{document_key:"doc-old",observation_record_key:"record-old"}}), response({message:"projection unavailable"}, 500));
await api.submitGuidedObservation("policy-memo-md", "policy-memo.md");
responses.push(response({job:backendJobs.runningB})); await api.discoverActiveObservation();
const combinedRunning = [api.state.pendingReactivationKey, api.state.activeObservationJobId, e.add.disabled];
responses.push(response({job:backendJobs.refreshFailedB}), response(projection("combined-recovered", [oldDoc, newDoc]))); await api.pollObservation("job-2");
outputs.combinedPendingTerminal = [...combinedRunning, api.state.pendingReactivationKey, api.state.activeObservationJobId, api.state.selectedKey, e.add.disabled, timers.size, e.toastMessage.textContent.includes("do not run Observe again"), requests.slice(combinedRequestStart).filter(item => item[1] === "POST").length];

api.applyProjection(projection("null-base", [oldDoc, newDoc]), "doc-old"); api.state.stage = "refine"; api.state.inspector = "evidence"; api.setObservationActive(backendJobs.running);
const nullSuccessStart = requests.length; responses.push(response({job:null}), response(projection("null-reconciled", [newDoc, oldDoc]))); await api.pollObservation("job-1");
outputs.nullSnapshotSuccess = [api.state.projection.session_id, api.state.selectedKey, api.state.stage, api.state.inspector, api.state.workspaceReconciliationPending, api.state.activeObservationJobId, e.add.disabled, timers.size, e.toast.dataset.tone, e.toastMessage.textContent.includes("lost after restart"), requests.slice(nullSuccessStart).every(item => item[1] === "GET")];

api.applyProjection(projection("null-failure-base", [oldDoc, newDoc]), "doc-old"); const nullFailureAccepted = api.state.projection; api.setObservationActive(backendJobs.running);
const nullFailureStart = requests.length; responses.push(response({job:null}), response({message:"projection unavailable"}, 500)); await api.pollObservation("job-1");
const nullFailureLocked = [api.state.projection === nullFailureAccepted, api.state.workspaceReconciliationPending, api.state.activeObservationJobId, e.add.disabled, timers.size > 0];
responses.push(response({job:null}), response(projection("null-retry-reconciled", [oldDoc, newDoc]))); await api.discoverActiveObservation();
outputs.nullSnapshotFailureRetry = [...nullFailureLocked, api.state.projection.session_id, api.state.selectedKey, api.state.workspaceReconciliationPending, api.state.activeObservationJobId, e.add.disabled, timers.size, e.toastMessage.textContent.includes("no action was replayed"), requests.slice(nullFailureStart).every(item => item[1] === "GET")];

function treeText(value) { return [value.textContent || "", ...(value.children || []).map(treeText)].join(" "); }
function treeNodes(value) { return [value, ...(value.children || []).flatMap(treeNodes)]; }
const observationKey = "1".repeat(64), diagnosisKey = "2".repeat(64), refinementKey = "3".repeat(64), findingId = "4".repeat(64);
const lifecycleDoc = {document_key:"doc-life", observation_record_key:observationKey, source:{name:"whitespace-cleanup.md",media_type:"text/markdown",size:72,sha256:"a".repeat(64)}, rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:null,revision_record_key:null}]};
const noFindings = {kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:0,findings:[]}};
api.state.projection = projection("life", [lifecycleDoc]); api.state.selectedKind = "document"; api.state.selectedKey = "doc-life"; api.state.selectedRound = 1; api.state.details = new Map([[diagnosisKey,noFindings]]); api.state.stage = "refine"; api.renderSelected();
const noFindingsRefine = treeText(e.central); api.state.stage = "revision"; api.renderSelected(); const noFindingsRevision = treeText(e.central);
outputs.noFindingsStages = [noFindingsRefine.includes("Not needed"), noFindingsRevision.includes("Not needed"), !noFindingsRefine.includes("Valid"), !noFindingsRevision.includes("Passed")];

const finding = {finding_id:findingId,rule_id:"D009",summary:"Whitespace can be normalized",severity:"INFO",refiner:{refiner_id:"R001",name:"WHITESPACE_NORMALIZATION"},proposal_action:{status:"AVAILABLE"}};
api.state.details.set(diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}});
api.state.proposal = {draft_key:"5".repeat(64),finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[{target:{ref:"#/texts/0",field:"text"},before:"A  long\tline\ncontinued",after:"A long line continued"},{target:{ref:"#/texts/1",field:"text"},before:"Second   edit",after:"Second edit"}]}; api.state.stage = "refine"; api.state.decisionSelection = null; api.state.comparison = {expanded:false,index:0}; api.renderSelected();
const proposalText = treeText(e.central); const decisionButtons = treeNodes(e.central).filter(value => value.className === "decision-choice");
outputs.proposalComparison = [proposalText.includes("A··long→line↵"), proposalText.includes("1 of 2"), !proposalText.includes("target"), decisionButtons.length === 2, decisionButtons.every(value => value.attributes["aria-pressed"] === "false")];
const structural = api.comparisonComponent({mode:"proposal",title:"Move",edits:[{target:{ref:"#/texts/0",field:"content_layer"},before:{content_layer:"furniture",furniture_index:1},after:{content_layer:"body",body_index:2}}],ruleId:"D007",refinerId:"R002"});
outputs.structuralComparison = [treeText(structural).includes("Structural movement"), treeText(structural).includes("furniture · 1"), treeText(structural).includes("body · 2")];

const finding10={finding_id:"b".repeat(64),rule_id:"D010",summary:"Line-end hyphenation can be resolved",severity:"WARNING",refiner:{refiner_id:"R003",name:"DETERMINISTIC_DEHYPHENATION"},proposal_action:{status:"AVAILABLE"}};
const identityDiagnosisKey="9".repeat(64),otherDiagnosisKey="a".repeat(64);const identityDoc={document_key:"identity-doc",observation_record_key:observationKey,source:{name:"identity.md",media_type:"text/markdown"},rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:refinementKey,revision_record_key:refinementKey},{number:2,base_record_key:refinementKey,diagnosis_record_key:identityDiagnosisKey,refinement_record_key:null,revision_record_key:null}]};const otherIdentityDoc={document_key:"identity-other",observation_record_key:observationKey,source:{name:"identity-other.md",media_type:"text/markdown"},rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:otherDiagnosisKey,refinement_record_key:null,revision_record_key:null}]};
api.state.projection=projection("identity",[identityDoc,otherIdentityDoc]);api.state.selectedKind="document";api.state.selectedKey="identity-doc";api.state.selectedRound=2;api.state.stage="diagnose";api.state.details=new Map([[observationKey,{kind:"OBSERVATION",artifact_integrity:"VERIFIED",artifacts:[],view:{source:{key:"identity-source",name:"identity.md",media_type:"text/markdown",size:1,sha256:"d".repeat(64)},docling_document:{name:"DoclingDocument",version:"1.10.0"},extractors:[]}}],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[identityDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:2,findings:[finding,finding10]}}],[otherDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}]]);api.state.proposal=null;api.state.selectedFinding=null;api.state.actionToken="identity-token";api.render();
let d10Card=treeNodes(e.central).find(value=>value.className==="finding-card"&&treeText(value).includes("D010"));treeNodes(d10Card).find(value=>value.textContent==="Review the supported refinement").listeners.click();const selectedD10Text=treeText(e.central);let roundPicker=treeNodes(e.roundContext).find(value=>value.tag==="select");roundPicker.value="1";roundPicker.listeners.change();const roundSelectionCleared=api.state.selectedFinding===null;roundPicker=treeNodes(e.roundContext).find(value=>value.tag==="select");roundPicker.value="2";roundPicker.listeners.change();api.changeStage("diagnose");d10Card=treeNodes(e.central).find(value=>value.className==="finding-card"&&treeText(value).includes("D010"));treeNodes(d10Card).find(value=>value.textContent==="Review the supported refinement").listeners.click();
const identityStart=requests.length;responses.push(response({draft:{draft_key:"c".repeat(64),diagnosis_record_key:identityDiagnosisKey,base_record_key:refinementKey,finding:{finding_id:finding10.finding_id,rule_id:"D010",summary:finding10.summary},refiner:finding10.refiner,edits:[]}}));await treeNodes(e.central).find(value=>value.textContent==="Create proposal").listeners.click();const d10ProposalRequest=requests.slice(identityStart).some(item=>item[0].endsWith(`/${identityDiagnosisKey}/${finding10.finding_id}`));
api.applyProjection(projection("identity-same",[identityDoc,otherIdentityDoc]),"identity-doc");const sameDocumentProposalPreserved=api.state.proposal&&api.state.proposal.finding.rule_id==="D010";responses.push(response(projection("identity-duplicate",[identityDoc,otherIdentityDoc])));await api.handleObservationEnvelope({job:null,reactivation:{document_key:"identity-other",observation_record_key:observationKey}},"identity-other.md");api.changeStage("refine");const duplicateFindingText=treeText(e.central);const duplicateCleared=api.state.proposal===null&&api.state.proposalIdentity===null&&duplicateFindingText.includes("D009")&&!duplicateFindingText.includes("D010");
api.applyProjection(projection("identity-reset",[identityDoc,otherIdentityDoc]),"identity-doc");api.state.selectedRound=2;api.state.stage="refine";api.state.proposal={draft_key:"c".repeat(64),diagnosis_record_key:identityDiagnosisKey,base_record_key:refinementKey,finding:{finding_id:finding10.finding_id,rule_id:"D010",summary:finding10.summary},refiner:finding10.refiner,edits:[]};api.state.proposalIdentity={documentKey:"identity-doc",roundNumber:2,diagnosisKey:identityDiagnosisKey,baseKey:refinementKey};const completedDoc={document_key:"completed-d009",observation_record_key:"record-new",source:{name:"completed-d009.md",media_type:"text/markdown"},rounds:[{number:1,base_record_key:"record-new",diagnosis_record_key:otherDiagnosisKey,refinement_record_key:null,revision_record_key:null}]};responses.push(response(projection("identity-completed",[completedDoc,identityDoc,otherIdentityDoc])));await api.consumeObservationJob(backendJobs.ready,"job-1");api.changeStage("refine");const completedFindingText=treeText(e.central);const completedCleared=api.state.proposal===null&&api.state.proposalIdentity===null&&completedFindingText.includes("D009")&&!completedFindingText.includes("D010");outputs.findingIdentity=[selectedD10Text.includes("D010")&&!selectedD10Text.includes("D009"),d10ProposalRequest,roundSelectionCleared,sameDocumentProposalPreserved,duplicateCleared,completedCleared];

api.state.proposal={draft_key:"5".repeat(64),diagnosis_record_key:diagnosisKey,base_record_key:observationKey,finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[]};api.state.actionToken = null; api.state.decisionSubmitted = false; api.state.decisionSelection = "approve"; api.state.lifecycleNotice = null;
const staleStart = requests.length; responses.push(response({action_token:"old-token"}), response({code:"ACTION_TOKEN_INVALID",message:"stale"},403), response({action_token:"new-token"})); await api.recordDecision();
outputs.staleLifecycle = [requests.slice(staleStart).filter(item => item[1] === "POST").length, requests.slice(staleStart).filter(item => item[0].includes("action-token")).length, api.state.actionToken, api.state.decisionSubmitted, api.state.lifecycleNotice.title];

const freshDoc = {document_key:"doc-fresh",observation_record_key:observationKey,source:{name:"fresh.md",media_type:"text/markdown",size:1,sha256:"b".repeat(64)},rounds:[]};
api.state.projection = projection("failure",[freshDoc]); api.state.selectedKind="document"; api.state.selectedKey="doc-fresh"; api.state.selectedRound=1; api.state.stage="diagnose"; api.state.actionToken="new-token"; api.state.lifecycleNotice=null;
const prepublicationStart = requests.length; responses.push(response({code:"ACTION_NOT_AVAILABLE",message:"not available"},409)); await api.runDiagnosis(freshDoc);
outputs.prepublicationLifecycle = [requests.slice(prepublicationStart).filter(item => item[1] === "POST").length, requests.slice(prepublicationStart).filter(item => item[1] === "GET").length, api.state.lifecyclePending, api.state.lifecycleNotice.title, treeText(e.central).includes("Retry")];

api.state.projection=projection("failure",[freshDoc,oldDoc]);api.state.lifecycleNotice=null; const publishedStart=requests.length; responses.push(response({publication:{kind:"DIAGNOSIS",run_id:"run",record_key:null},refresh:{status:"FAILED",message:"refresh failed"}})); await api.runDiagnosis(freshDoc);
const publishedLocked=api.state.lifecycleReconciliationPending; const oldNavigation=treeNodes(e.documents).find(value=>value.title==="old.md");oldNavigation.listeners.click();const freshNavigation=treeNodes(e.documents).find(value=>value.title==="fresh.md");freshNavigation.listeners.click();await api.runDiagnosis(freshDoc);const blockedReplayPosts=requests.slice(publishedStart).filter(item=>item[1]==="POST").length;
responses.push(response(null,204),response(projection("published-not-visible",[freshDoc,oldDoc])));await api.refreshWorkspace();const confirmedAbsentStayedLocked=api.state.lifecycleReconciliationPending;await api.runDiagnosis(freshDoc);
const publishedFresh={...freshDoc,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:null,revision_record_key:null}]};api.state.details.set(observationKey,{kind:"OBSERVATION",artifact_integrity:"VERIFIED",artifacts:[],view:{}});responses.push(response(null,204),response(projection("published-recovered",[publishedFresh,oldDoc])));await api.refreshWorkspace();const publishedProducerPosts=requests.slice(publishedStart).filter(item=>item[0].includes("/lifecycle/diagnoses/")).length;
outputs.publishedLifecycle = [publishedLocked,api.state.selectedKey,blockedReplayPosts,confirmedAbsentStayedLocked,publishedProducerPosts,api.state.lifecycleReconciliationPending,api.state.pendingLifecycleMutation===null,api.state.lifecycleNotice===null];

api.state.projection=projection("unknown",[freshDoc]);api.state.selectedKind="document";api.state.selectedKey="doc-fresh";api.state.selectedRound=1;api.state.stage="diagnose";api.state.lifecycleNotice=null; const unknownStart=requests.length; responses.push(new Error("transport lost"), response(null,204), response(projection("reconciled",[]))); await api.runDiagnosis(freshDoc);
outputs.unknownLifecycle = [requests.slice(unknownStart).filter(item => item[1] === "POST").length, requests.slice(unknownStart).filter(item => item[1] === "GET").length, api.state.lifecyclePending, api.state.lifecycleReconciliationPending, api.state.lifecycleNotice];
const manualRecoveryStart=requests.length; responses.push(response(null,204),response(projection("manual-recovery",[freshDoc]))); await api.refreshWorkspace();
outputs.manualLifecycleRecovery=[requests.slice(manualRecoveryStart).filter(item=>item[1]==="POST").length,requests.slice(manualRecoveryStart).filter(item=>item[1]==="GET").length,api.state.lifecycleReconciliationPending,api.state.pendingLifecycleMutation===null,api.state.lifecycleNotice===null];

const observationDetail = {kind:"OBSERVATION",artifact_integrity:"VERIFIED",artifacts:[],view:{source:{key:"whitespace-cleanup-c960009a8c64",name:"whitespace-cleanup.md",media_type:"text/markdown",size:72,sha256:"a".repeat(64)},docling_document:{name:"DoclingDocument",version:"1.10.0"},extractors:[],comparison:{}}};
const uploadedCollision = JSON.parse(JSON.stringify(observationDetail)); uploadedCollision.view.source.key="whitespace-cleanup-aabbccddeeff";
api.state.projection=projection("privacy",[{document_key:"guided",observation_record_key:observationKey,source:observationDetail.view.source,rounds:[]}]); api.state.selectedKind="document"; api.state.selectedKey="guided"; api.state.selectedRound=1; api.state.stage="observe"; api.state.details=new Map([[observationKey,observationDetail]]); api.renderSelected(); const guidedObserveText=treeText(e.central);
api.state.projection=projection("privacy-upload",[{document_key:"upload",observation_record_key:observationKey,source:uploadedCollision.view.source,rounds:[]}]); api.state.selectedKey="upload"; api.state.details=new Map([[observationKey,uploadedCollision]]); api.renderSelected(); const uploadObserveText=treeText(e.central);
outputs.uploadPrivacyIdentity=[!guidedObserveText.includes("never displays or serves"),uploadObserveText.includes("never displays or serves")];

const approvedRefinement={kind:"REFINEMENT",artifact_integrity:"VERIFIED",artifacts:[],view:{decision:"APPROVED",proposal:{finding_id:findingId,refiner:finding.refiner},transformations:[{}],revision_chain:[]}};
const rejectedRefinement={kind:"REFINEMENT",artifact_integrity:"VERIFIED",artifacts:[],view:{decision:"REJECTED",proposal:{finding_id:findingId,refiner:finding.refiner},transformations:[],revision_chain:[]}};
const approvedDoc={document_key:"approved-doc",observation_record_key:observationKey,source:lifecycleDoc.source,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:refinementKey,revision_record_key:refinementKey}]};
api.state.projection=projection("approved",[approvedDoc]); api.state.selectedKind="document"; api.state.selectedKey="approved-doc"; api.state.selectedRound=1; api.state.stage="refine"; api.state.details=new Map([[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]); api.state.lifecycleNotice=null; api.state.decisionSubmitted=false; api.renderSelected(); const approvedText=treeText(e.central);
api.state.details.set(refinementKey,rejectedRefinement); approvedDoc.rounds[0].revision_record_key=null; api.renderSelected(); const rejectedText=treeText(e.central); api.state.stage="revision"; api.renderSelected(); const rejectedRevisionText=treeText(e.central);
outputs.decisionOutcomes=[approvedText.includes("Approved")&&approvedText.includes("View prepared revision"),rejectedText.includes("Rejected")&&rejectedText.includes("base document remains current and unchanged"),rejectedRevisionText.includes("Not needed")];

const secondRefinementKey="6".repeat(64), secondDiagnosisKey="7".repeat(64); const twoRoundDoc={document_key:"two-round",observation_record_key:observationKey,source:lifecycleDoc.source,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:refinementKey,revision_record_key:refinementKey},{number:2,base_record_key:refinementKey,diagnosis_record_key:secondDiagnosisKey,refinement_record_key:secondRefinementKey,revision_record_key:secondRefinementKey}]};
api.state.projection=projection("two-round",[twoRoundDoc]); api.state.selectedKind="document"; api.state.selectedKey="two-round"; api.state.selectedRound=1; api.state.stage="diagnose"; api.state.details=new Map([[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement],[secondDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[secondRefinementKey,approvedRefinement]]); api.renderSelected(); const historicalRoundText=treeText(e.central);
api.state.selectedRound=2; api.state.stage="revision"; api.renderSelected(); const latestRoundText=treeText(e.central);
outputs.roundHistory=[historicalRoundText.includes("Historical round · read-only"),!historicalRoundText.includes("Run Diagnosis"),latestRoundText.includes("Original")&&latestRoundText.includes("Revision 1")&&latestRoundText.includes("Revision 2")];

api.state.projection=projection("rapid",[lifecycleDoc]); api.state.selectedKind="document"; api.state.selectedKey="doc-life"; api.state.selectedRound=1; api.state.stage="refine"; api.state.details=new Map([[observationKey,observationDetail],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]); api.state.proposal={draft_key:"5".repeat(64),diagnosis_record_key:diagnosisKey,base_record_key:observationKey,finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[]};api.state.proposalIdentity={documentKey:"doc-life",roundNumber:1,diagnosisKey:diagnosisKey,baseKey:observationKey}; api.state.decisionSelection="approve"; api.state.decisionSubmitted=false; api.state.lifecyclePending=false; api.state.lifecycleReconciliationPending=false; api.state.actionToken="new-token";
let resolveDecisionDeferred; const decisionDeferred=new Promise(resolve=>{resolveDecisionDeferred=resolve;}); responses.push(decisionDeferred); const rapidStart=requests.length; const rapidFirst=api.recordDecision();const pendingIdentity=api.state.pendingLifecycleMutation;const refreshPostsBefore=requests.filter(item=>item[0].endsWith("/workbench/refresh")&&item[1]==="POST").length;await api.refreshWorkspace();const concurrentRequestBlocked=requests.filter(item=>item[0].endsWith("/workbench/refresh")&&item[1]==="POST").length===refreshPostsBefore;const concurrentIdentityPreserved=api.state.pendingLifecycleMutation===pendingIdentity;const refreshStayedDisabled=e.refresh.disabled;await api.recordDecision();resolveDecisionDeferred(response({publication:{kind:"REFINEMENT",decision:"APPROVED",record_key:null},refresh:{status:"FAILED",message:"refresh failed"}})); await rapidFirst;const pendingAfterPublication=api.state.pendingLifecycleMutation===pendingIdentity&&api.state.lifecycleReconciliationPending;responses.push(response(null,204),response(projection("rapid-absent",[lifecycleDoc])));await api.refreshWorkspace();const absentDecisionStayedLocked=api.state.lifecycleReconciliationPending&&api.state.pendingLifecycleMutation===pendingIdentity;const rapidPublishedDoc=JSON.parse(JSON.stringify(lifecycleDoc));rapidPublishedDoc.rounds[0].refinement_record_key=refinementKey;rapidPublishedDoc.rounds[0].revision_record_key=refinementKey;responses.push(response(null,204),response(projection("rapid-visible",[rapidPublishedDoc])));await api.refreshWorkspace();const rapidProducerPosts=requests.slice(rapidStart).filter(item=>item[0].includes("/lifecycle/proposals/")&&item[0].endsWith("/approve")).length;outputs.rapidDecision=[concurrentRequestBlocked,concurrentIdentityPreserved,refreshStayedDisabled,pendingAfterPublication,absentDecisionStayedLocked,rapidProducerPosts,api.state.lifecycleReconciliationPending,api.state.pendingLifecycleMutation===null];

const pendingRoundDoc={document_key:"decision-doc",observation_record_key:observationKey,source:lifecycleDoc.source,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:null,revision_record_key:null}]}; const publishedRoundDoc=JSON.parse(JSON.stringify(pendingRoundDoc)); publishedRoundDoc.rounds[0].refinement_record_key=refinementKey; publishedRoundDoc.rounds[0].revision_record_key=refinementKey;
function prepareUnknownDecision(){api.state.projection=projection("decision-base",[pendingRoundDoc]);api.state.selectedKind="document";api.state.selectedKey="decision-doc";api.state.selectedRound=1;api.state.stage="refine";api.state.details=new Map([[observationKey,observationDetail],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]);api.state.proposal={draft_key:"5".repeat(64),diagnosis_record_key:diagnosisKey,base_record_key:observationKey,finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[]};api.state.proposalIdentity={documentKey:"decision-doc",roundNumber:1,diagnosisKey:diagnosisKey,baseKey:observationKey};api.state.decisionSelection="approve";api.state.decisionSubmitted=false;api.state.lifecyclePending=false;api.state.lifecycleReconciliationPending=false;api.state.lifecycleNotice=null;api.state.pendingLifecycleMutation=null;api.state.actionToken="new-token";}
prepareUnknownDecision(); const unknownPublishedStart=requests.length; responses.push(new Error("lost"),response(null,204),response(projection("decision-published",[publishedRoundDoc]))); await api.recordDecision(); outputs.unknownDecisionPublished=[requests.slice(unknownPublishedStart).filter(item=>item[1]==="POST").length,api.state.lifecycleReconciliationPending,api.state.proposal===null,api.state.stage,api.state.decisionSubmitted];
prepareUnknownDecision(); const unknownAbsentStart=requests.length; responses.push(new Error("lost"),response(null,204),response(projection("decision-absent",[pendingRoundDoc]))); await api.recordDecision(); outputs.unknownDecisionAbsent=[requests.slice(unknownAbsentStart).filter(item=>item[1]==="POST").length,api.state.lifecycleReconciliationPending,api.state.proposal!==null,api.state.decisionSubmitted];

const raceRefinement={...approvedRefinement,artifacts:[{role:"refinement-proposal",artifact_key:"8".repeat(64)}]}; api.state.projection=projection("race",[twoRoundDoc]);api.state.selectedKind="document";api.state.selectedKey="two-round";api.state.selectedRound=2;api.state.stage="revision";api.state.details=new Map([[secondDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[secondRefinementKey,raceRefinement]]);api.state.appliedProposal=null;api.state.appliedProposalLoading=null;api.state.lifecyclePending=false;api.state.lifecycleReconciliationPending=false;api.renderSelected(); const openRace=treeNodes(e.central).find(value=>value.textContent==="Open applied comparison"&&value.tag==="button"); let resolveArtifact; const artifactDeferred=new Promise(resolve=>{resolveArtifact=resolve;});responses.push(artifactDeferred);const racePromise=openRace.listeners.click();api.state.selectedRound=1;api.state.stage="diagnose";api.renderSelected();resolveArtifact(response({forward_edits:[{target:{field:"text"},before:"before",after:"after"}],finding:{rule_id:"D009"},refiner:finding.refiner}));await racePromise;outputs.appliedRace=[api.state.appliedProposal===null,api.state.stage,api.state.selectedRound];
console.log(JSON.stringify(outputs));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run(
            [
                node,
                "-e",
                harness,
                str(ASSETS / "workbench.js"),
                json.dumps(reference),
                json.dumps(backend_jobs),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertTrue(values["parity"])
        self.assertEqual(values["registryCoverage"], [True, False])
        self.assertEqual(values["negotiated"], "zh-CN")
        self.assertEqual(values["fallback"], "en")
        self.assertEqual(values["override"], "en")
        self.assertEqual(values["selection"], ["doc-b", "refine", "artifacts", "doc-a,doc-b"])
        self.assertEqual(values["localeStable"], ["zh-CN", "doc-b", "refine", "artifacts", "zh-CN", "EN", "切换到英语", "工作区导航", "摘要"])
        self.assertEqual(values["successToast"], [False, "ok", "", 4000])
        self.assertEqual(values["hoverFocusHeld"], 0)
        self.assertEqual(values["hoverFocusReleased"], 1)
        self.assertEqual(values["focusHoverHeld"], 0)
        self.assertEqual(values["focusHoverReleased"], 1)
        self.assertEqual(values["failureToast"], [0, "bad", "failure"])
        self.assertEqual(values["replaced"], ["recovered", "success", 1])
        self.assertTrue(values["dismissed"])
        self.assertEqual(values["modalOpen"], [False, True, True])
        self.assertEqual(values["modalKeys"], [True, True, True, True, 3])
        self.assertEqual(values["backdrop"], [True, True])
        self.assertEqual(values["active"], ["job-1", True, True, True, 1])
        self.assertEqual(values["publishedRefreshFailed"], [True, "doc-old", "diagnose", "evidence", "failure", True, False])
        self.assertEqual(values["publishedRefreshFailedNoObservation"], [True, "doc-old", "failure", True])
        self.assertEqual(values["ready"], ["ready", "doc-new", "observe", "success", False])
        self.assertEqual(values["duplicate"], ["doc-old", "doc-old,doc-new", True])
        self.assertEqual(values["reactivationLoadUnknown"], ["RECONCILING", True, True, True])
        self.assertEqual(values["reactivationRecovered"], [None, None, "doc-old", False, True, True])
        self.assertEqual(values["refreshSuccess"], ["doc-old", "refine", "artifacts", True])
        self.assertEqual(values["refreshNoChange"], ["doc-old", "refine", "artifacts", True])
        self.assertEqual(values["refreshFailure"], [True, "doc-old", "failure", True])
        self.assertEqual(values["initialRecovery"], [True, True, True, False, "doc-old", False])
        self.assertEqual(values["localBusy"], [True, True, True])
        self.assertEqual(values["deferredClaim"], ["RECONCILING", True, True, True, True, "job-1", True])
        self.assertEqual(values["submissionUnknown"], [True, "RECONCILING", True, True, True])
        self.assertEqual(values["serverBusy"], [True, True, "failure", "job-1"])
        self.assertEqual(values["startupReady"], ["startup-ready", "doc-new", "observe", "success"])
        self.assertEqual(values["startupRefreshFailed"], [True, "doc-old", "refine", "artifacts", "failure", True])
        self.assertEqual(values["startupFailed"], [True, None, False, "failure", True])
        self.assertEqual(values["startupRefreshFailedNoObservation"], [True, "doc-old", "failure", True])
        self.assertEqual(values["startupActive"], ["job-1", True, True])
        self.assertEqual(values["transient"], ["job-1", True, True, True, True])
        self.assertEqual(values["jobMismatch"], ["job-2", True, True, None, False, 0, True])
        self.assertEqual(values["combinedPendingTerminal"], ["doc-old", "job-2", True, None, None, "doc-old", False, 0, True, 1])
        self.assertEqual(values["nullSnapshotSuccess"], ["null-reconciled", "doc-old", "refine", "evidence", False, None, False, 0, "failure", True, True])
        self.assertEqual(values["nullSnapshotFailureRetry"], [True, True, "RECONCILING", True, True, "null-retry-reconciled", "doc-old", False, None, False, 0, True, True])
        self.assertEqual(values["noFindingsStages"], [True, True, True, True])
        self.assertEqual(values["proposalComparison"], [True, True, True, True, True])
        self.assertEqual(values["structuralComparison"], [True, True, True])
        self.assertEqual(values["findingIdentity"], [True, True, True, True, True, True])
        self.assertEqual(values["staleLifecycle"], [1, 2, "new-token", False, "staleToken"])
        self.assertEqual(values["prepublicationLifecycle"], [1, 0, False, "lifecyclePrepublicationFailure", True])
        self.assertEqual(values["publishedLifecycle"], [True, "doc-fresh", 1, True, 1, False, True, True])
        self.assertEqual(values["unknownLifecycle"], [2, 1, False, True, {"title": "lifecycleUnknown", "body": "lifecycleUnknown", "tone": "failure"}])
        self.assertEqual(values["manualLifecycleRecovery"], [1, 1, False, True, True])
        self.assertEqual(values["uploadPrivacyIdentity"], [True, True])
        self.assertEqual(values["decisionOutcomes"], [True, True, True])
        self.assertEqual(values["roundHistory"], [True, True, True])
        self.assertEqual(values["rapidDecision"], [True, True, True, True, True, 1, False, True])
        self.assertEqual(values["unknownDecisionPublished"], [2, False, True, "refine", True])
        self.assertEqual(values["unknownDecisionAbsent"], [2, False, True, False])
        self.assertEqual(values["appliedRace"], [True, "diagnose", 1])

    def test_static_assets_are_served_from_same_origin_with_expected_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            application = WorkbenchApplication(
                WorkbenchState(Path(directory) / "workspace"),
                Path(directory) / "models",
            )
            try:
                expected = {
                    "/": "text/html; charset=utf-8",
                    "/assets/workbench.css": "text/css; charset=utf-8",
                    "/assets/workbench.js": "text/javascript; charset=utf-8",
                }
                for target, content_type in expected.items():
                    with self.subTest(target=target):
                        response = application.route(target)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.content_type, content_type)
                        self.assertTrue(response.body)
            finally:
                application.close()


if __name__ == "__main__":
    unittest.main()
