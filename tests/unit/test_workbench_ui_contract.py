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
from tiny_corpus_workbench.diagnosis_rules import CURRENT_RULES, CURRENT_RULESET
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
            'class="workspace-context-row"',
            'id="stage-stepper"',
            'data-i18n="observe">Observe',
            'data-i18n="diagnose">Diagnose',
            'data-i18n="refine">Refine',
            'data-i18n="revision">Revision',
            'data-stage-status="label"',
            'id="central-surface"',
            'class="inspector-title" data-i18n="inspector">Inspector',
            'role="tablist"',
            'id="add-modal"',
            'id="rule-modal"',
            'data-i18n="diagnosisRuleReference">Diagnosis rule reference',
            'class="rule-reference-intro"',
            'role="dialog" aria-modal="true"',
            "Created by James Wei",
            "An inspectable document-preparation workbench.",
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
        self.assertIn('class="path-card recommended-path"', html)
        self.assertIn('data-i18n="guidedPreparationTitle"', html)
        self.assertIn('data-i18n="guidedInspectionTitle"', html)
        self.assertIn('data-i18n="ownDocumentTitle"', html)
        self.assertIn('data-i18n="recommended"', html)
        self.assertEqual(html.count('class="path-action"'), 3)
        self.assertIn("whitespace-cleanup.md", html)
        self.assertIn("policy-memo.md", html)
        self.assertIn('accept=".docx,.md,.pdf,.txt"', html)
        self.assertIn("up to 32 MiB", html)

    def test_css_has_stable_desktop_shell_and_natural_narrow_reflow(self) -> None:
        css = (ASSETS / "workbench.css").read_text("utf-8")
        for marker in (
            "--sidebar: 17rem",
            "width: min(112rem, calc(100% - 2rem))",
            "box-shadow: 0 12px 28px rgba(31, 45, 35, .12)",
            "grid-template-columns: var(--sidebar) minmax(0, 1fr)",
            "width: var(--sidebar)",
            "-webkit-line-clamp: 2",
            "align-items: start",
            ".workspace-context-row",
            "justify-content: flex-start",
            ".inspector-title",
            "@media (max-width: 760px)",
            ".workbench-shell { display: block; }",
            '.rule-entry[data-severity="INFO"]',
            ".learner-question-icon",
            ".corpus-matrix",
            ".inspector-evidence-group",
            ".path-action { width: 100%; }",
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
            "entry.dataset.severity = rule.severity",
            'node("span", "?", "learner-question-icon")',
            'node("span", "!", "result-notification-icon")',
            't("diagnosisRulesReference")',
            'node("code", "corpus inspect", "terminal-token")',
            '"finding-rule-metadata"',
            '"refinement-map"',
            '"refineInspectorReady"',
            'state.selectedKind === "corpus"',
            '"corpus-matrix"',
            "corpusEvidenceGroup",
            'node("strong", detail.view.docling_document.name)',
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

    def test_t4_readers_are_local_isolated_and_accessible(self) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        css = (ASSETS / "workbench.css").read_text("utf-8")
        for marker in (
            'frame.setAttribute("sandbox", "")',
            'frame.setAttribute("referrerpolicy", "no-referrer")',
            'frame.setAttribute("tabindex", "-1")',
            "default-src 'none'",
            "connect-src 'none'",
            "form-action 'none'",
            "fetchText(`${API_ROOT}/artifacts/",
            'button.setAttribute("aria-pressed"',
            "JSON.stringify(JSON.parse(source), null, 2)",
            "comparisonComponent(comparisonView)",
            'descriptor.media_type === "text/html"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        self.assertIn(".source-reader.is-unwrapped { white-space: pre; }", css)
        self.assertIn(".html-report", css)
        self.assertIn("pointer-events: none", css)

    def test_t4_hash_renderer_is_presentation_only(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js 24.18.1 is required for Workbench contract tests")
        harness = r'''
global.__TCW_TEST_NO_START__ = true;
global.window = {};
require(process.argv[1]);
const api = window.__tcwWorkbench;
const full = "0123456789abcdef".repeat(4);
console.log(JSON.stringify([api.compactHash(full), full, api.isolatedHtml('<h1>Report</h1><a href="#x">Jump</a><link rel="stylesheet" href="styles.css">')]));
'''
        result = subprocess.run(
            [node, "-e", harness, str(ASSETS / "workbench.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        compact, full, isolated = json.loads(result.stdout)
        self.assertEqual(compact, "0123456789…89abcdef")
        self.assertEqual(full, "0123456789abcdef" * 4)
        self.assertIn("Content-Security-Policy", isolated)
        self.assertIn("<h1>Report</h1>", isolated)
        self.assertNotIn("href=", isolated)
        self.assertNotIn("<link", isolated)

    def test_node_backed_state_locale_toast_and_modal_scenarios(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js 24.18.1 is required for dynamic Workbench DOM tests")
        version = subprocess.run(
            [node, "--version"], check=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertRegex(version, r"^v\d+\.\d+\.\d+$")
        reference = {
            "ruleset": {
                "name": CURRENT_RULESET["name"],
                "version": CURRENT_RULESET["version"],
            },
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
            "readyDetail": ObservationJob(
                "job-1",
                "COMPLETED",
                None,
                job_input,
                JobObservation("SUCCESS", "obs-new", "f" * 64),
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
    querySelector(selector) {
      if (selector === ".modal-close") return this.closeButton;
      const data = selector.match(/^\[data-([a-z-]+)="([^"]+)"\]$/);
      if (!data) return null;
      const key = data[1].replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
      const nodes = [this]; for (let index = 0; index < nodes.length; index++) nodes.push(...(nodes[index].children || []));
      return nodes.find(value => value && value.dataset && String(value.dataset[key]) === data[2]) || null;
    },
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
function response(body, status = 200) { return {ok: status >= 200 && status < 300, status, async json() { return body; }, async text() { return typeof body === "string" ? body : JSON.stringify(body); }}; }
global.fetch = async (target, options = {}) => { requests.push([target, options.method || "GET"]); const value = responses.shift(); if (value instanceof Error) throw value; return value; };
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"), {filename: process.argv[1]});
const api = window.__tcwWorkbench;
const e = api.elements;
for (const id of ["workspace-navigation", "stage-inspector"]) registry[id] = fake("div", id);
Object.assign(e, {
  surface: fake(), version: fake(), ruleButton: fake("button"), localeToggle: fake("button"), refresh: fake("button"), add: fake("button"),
  documents: fake(), corpora: fake(), workspaceState: fake(), selected: fake(), contextKind: fake(), contextName: fake(),
  roundContext: fake(), stepper: fake("ol"), central: fake("section", "central-surface"), stageHeading: fake("h2", "stage-heading"), stageGuidance: fake(), inspectorPanel: fake(), tabs,
  toast: fake(), toastMessage: fake(), toastClose: fake("button"), polite: fake(), assertive: fake(),
  addModal: fake(), ruleModal: fake(), ruleList: fake(), file: fake("input"), upload: fake("button"),
  guidedWhitespace: fake("button"), guidedPolicy: fake("button")
});
e.stepper.stageEntries = ["observe", "diagnose", "refine", "revision"].map(stage => { const item = fake("li"); item.dataset.stage = stage; const status = fake("small"); status.dataset.stageStatus = "label"; item.append(status); return item; });
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
outputs.extractorStatuses = ["SUCCESS", "PARTIAL_SUCCESS", "FAILED"].map(status => { const icon = api.extractorStatus(status); return [icon.textContent, icon.dataset.status, icon.title, icon.attributes["aria-label"]]; });

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
api.openModal(modal); outputs.modalOpen = [modal.hidden, e.surface.inert, e.toast.inert, document.activeElement === close];
last.focus(); let prevented = 0; api.modalKeydown({currentTarget:modal,key:"Tab",shiftKey:false,preventDefault(){prevented++;}}); const wrappedForward = document.activeElement === close;
close.focus(); api.modalKeydown({currentTarget:modal,key:"Tab",shiftKey:true,preventDefault(){prevented++;}}); const wrappedBackward = document.activeElement === last;
api.modalKeydown({currentTarget:modal,key:"Escape",shiftKey:false,preventDefault(){prevented++;}}); outputs.modalKeys = [wrappedForward, wrappedBackward, modal.hidden, document.activeElement === opener, prevented];
opener.focus(); api.openModal(modal); api.backdropDismiss({target:modal,currentTarget:modal}); outputs.backdrop = [modal.hidden, document.activeElement === opener, !e.toast.inert];

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

api.applyProjection(projection("terminal-base", [oldDoc]), "doc-old"); api.state.stage = "diagnose"; api.state.inspector = "evidence"; const terminalAccepted = api.state.projection;
const terminalProjectionStart = requests.length; responses.push(response({job:backendJobs.ready}), response({message:"projection unavailable"}, 500)); await api.pollObservation("job-1");
outputs.terminalProjectionFailure = [api.state.projection === terminalAccepted, api.state.selectedKey, api.state.stage, api.state.inspector, api.state.activeObservationJobId, e.add.disabled, timers.size, e.toast.dataset.tone, e.toastMessage.textContent.includes("Use Refresh workspace"), e.toastMessage.textContent.includes("do not run Observe again"), requests.slice(terminalProjectionStart).every(item => item[1] === "GET")];

const detailDoc = {...newDoc, observation_record_key:"f".repeat(64)}; const terminalDetailStart = requests.length; responses.push(response({job:backendJobs.readyDetail}), response(projection("terminal-detail", [detailDoc, oldDoc])), response({message:"detail unavailable"}, 500)); await api.pollObservation("job-1");
outputs.terminalDetailFailure = [api.state.projection === terminalAccepted, api.state.selectedKey, api.state.stage, api.state.inspector, api.state.activeObservationJobId, e.add.disabled, timers.size, e.toast.dataset.tone, e.toastMessage.textContent.includes("Use Refresh workspace"), e.toastMessage.textContent.includes("do not run Observe again"), requests.slice(terminalDetailStart).every(item => item[1] === "GET")];

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
const noFindingsArtifacts=["diagnosis-manifest","diagnostic-findings","diagnostic-report"].map((role,index)=>({artifact_key:String(index+6).repeat(64),role,media_type:index===2?"text/markdown":"application/json",size:10,sha256:String(index+3).repeat(64),availability:"AVAILABLE"}));
const noFindings = {kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:noFindingsArtifacts,view:{subject_state:"MATCH",derivation_state:"MATCH",finding_total:0,findings:[]}};
api.state.projection = projection("life", [lifecycleDoc]); api.state.selectedKind = "document"; api.state.selectedKey = "doc-life"; api.state.selectedRound = 1; api.state.details = new Map([[diagnosisKey,noFindings]]); api.state.stage = "refine"; api.renderSelected();
const noFindingsRefine = treeText(e.central);const noFindingsRefineHeading=e.stageHeading.textContent;const noFindingsRefineGuidance=e.stageGuidance.textContent;api.state.stage = "revision"; api.renderSelected(); const noFindingsRevision = treeText(e.central);const noFindingsRevisionHeading=e.stageHeading.textContent;const noFindingsRevisionGuidance=e.stageGuidance.textContent;
api.state.stage="diagnose";api.state.inspector="summary";api.renderSelected();const noFindingsDiagnosis=treeText(e.central);const noFindingsSummary=treeText(e.inspectorPanel);api.state.inspector="evidence";api.renderSelected();const noFindingsEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const noFindingsInspectorArtifacts=treeText(e.inspectorPanel);
outputs.noFindingsStages = [noFindingsRefineHeading==="Refine",noFindingsRefineGuidance==="No supported change is needed for this round.",noFindingsRefine.includes("Not needed")&&!noFindingsRefine.includes("Valid"),noFindingsRevisionHeading==="Revision",noFindingsRevisionGuidance==="No prepared revision is needed for this round.",noFindingsRevision.includes("Not needed")&&!noFindingsRevision.includes("Passed"),!noFindingsDiagnosis.includes("NO_FINDINGS")&&!noFindingsDiagnosis.includes("How to read this result")&&(noFindingsDiagnosis.match(/No fixed rule matched\. No content changed\./g)||[]).length===1,noFindingsSummary.includes("Findings")&&noFindingsSummary.includes("Refinable findings")&&noFindingsSummary.includes("3 artifacts"),noFindingsEvidence.includes("Diagnosis subject")&&noFindingsEvidence.includes("Matched")&&noFindingsEvidence.includes("Evidence references")&&noFindingsEvidence.includes("0"),noFindingsInspectorArtifacts.includes("diagnosis-manifest")&&noFindingsInspectorArtifacts.includes("diagnostic-findings")&&noFindingsInspectorArtifacts.includes("diagnostic-report")];
api.state.stage="refine";api.state.inspector="summary";api.renderSelected();const noFindingsRefineSummary=treeText(e.inspectorPanel);api.state.inspector="evidence";api.renderSelected();const noFindingsRefineEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const noFindingsRefineArtifacts=treeText(e.inspectorPanel);api.state.stage="revision";api.state.inspector="summary";api.renderSelected();const noFindingsRevisionSummary=treeText(e.inspectorPanel);api.state.inspector="evidence";api.renderSelected();const noFindingsRevisionEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const noFindingsRevisionArtifacts=treeText(e.inspectorPanel);
outputs.noFindingsInspectors=[noFindingsRefineSummary.includes("Refinement not needed")&&noFindingsRefineSummary.includes("no supported change"),noFindingsRefineEvidence.includes("Diagnosis ended this round")&&noFindingsRefineEvidence.includes("Zero findings"),noFindingsRefineArtifacts.includes("No refinement artifacts")&&noFindingsRefineArtifacts.includes("No proposal or decision record"),noFindingsRevisionSummary.includes("Prepared revision not needed")&&noFindingsRevisionSummary.includes("no approved refinement"),noFindingsRevisionEvidence.includes("No revision evidence")&&noFindingsRevisionEvidence.includes("final published stage"),noFindingsRevisionArtifacts.includes("No revision artifacts")&&noFindingsRevisionArtifacts.includes("No prepared revision was created")];
outputs.stageOutcomes = e.stepper.stageEntries.map(item => [item.dataset.stage, item.dataset.outcome, treeText(item.children[0]).trim()]);

const finding = {finding_id:findingId,rule_id:"D009",summary:"Whitespace can be normalized",severity:"INFO",refiner:{refiner_id:"R001",name:"WHITESPACE_NORMALIZATION"},proposal_action:{status:"AVAILABLE"}};
api.state.details.set(diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}});
api.state.proposal = {draft_key:"5".repeat(64),finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[{target:{ref:"#/texts/0",field:"text"},before:"A  long\tline\ncontinued",after:"A long line continued"},{target:{ref:"#/texts/1",field:"text"},before:"Second   edit",after:"Second edit"}]}; api.state.stage = "refine"; api.state.decisionSelection = null; api.state.comparison = {index:0}; api.renderSelected();
const proposalText = treeText(e.central); const decisionButtons = treeNodes(e.central).filter(value => value.className === "decision-choice"); const completedProposalButton = treeNodes(e.central).find(value => value.textContent === "Create proposal");
const proposalMarks = treeNodes(e.central).filter(value => value.className === "change-mark");
outputs.proposalComparison = [proposalText.includes("What Refine does") && proposalText.includes("··") && proposalText.includes("→") && proposalText.includes("↵"), proposalText.includes("1 of 2"), !proposalText.includes("target"), Boolean(completedProposalButton && completedProposalButton.disabled), proposalText.includes("Why record a decision?"), decisionButtons.length === 2, decisionButtons.every(value => value.attributes["aria-pressed"] === "false"), proposalMarks.length >= 2];
const structural = api.comparisonComponent({mode:"proposal",title:"Move",edits:[{target:{ref:"#/texts/0",field:"content_layer"},before:{content_layer:"furniture",furniture_index:1},after:{content_layer:"body",body_index:2}}],ruleId:"D007",refinerId:"R002"});
outputs.structuralComparison = [treeText(structural).includes("Structural movement"), treeText(structural).includes("furniture · 1"), treeText(structural).includes("body · 2")];

const finding10={finding_id:"b".repeat(64),rule_id:"D010",summary:"Line-end hyphenation can be resolved",severity:"WARNING",refiner:{refiner_id:"R003",name:"DETERMINISTIC_DEHYPHENATION"},proposal_action:{status:"AVAILABLE"}};
const identityDiagnosisKey="9".repeat(64),otherDiagnosisKey="a".repeat(64);const identityDoc={document_key:"identity-doc",observation_record_key:observationKey,source:{name:"identity.md",media_type:"text/markdown"},rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:refinementKey,revision_record_key:refinementKey},{number:2,base_record_key:refinementKey,diagnosis_record_key:identityDiagnosisKey,refinement_record_key:null,revision_record_key:null}]};const otherIdentityDoc={document_key:"identity-other",observation_record_key:observationKey,source:{name:"identity-other.md",media_type:"text/markdown"},rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:otherDiagnosisKey,refinement_record_key:null,revision_record_key:null}]};
api.state.projection=projection("identity",[identityDoc,otherIdentityDoc]);api.state.selectedKind="document";api.state.selectedKey="identity-doc";api.state.selectedRound=2;api.state.stage="diagnose";api.state.details=new Map([[observationKey,{kind:"OBSERVATION",artifact_integrity:"VERIFIED",artifacts:[],view:{source:{key:"identity-source",name:"identity.md",media_type:"text/markdown",size:1,sha256:"d".repeat(64)},docling_document:{name:"DoclingDocument",version:"1.10.0"},extractors:[]}}],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[identityDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:2,findings:[finding,finding10]}}],[otherDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}]]);api.state.proposal=null;api.state.selectedFinding=null;api.state.actionToken="identity-token";api.render();api.state.stage="refine";api.renderSelected();const unselectedRefineText=treeText(e.central);outputs.multiFindingChoice=[unselectedRefineText.includes("Choose one finding"),!unselectedRefineText.includes("Create proposal")];api.changeStage("diagnose");
let d10Card=treeNodes(e.central).find(value=>value.className==="finding-card"&&treeText(value).includes("D010"));treeNodes(d10Card).find(value=>value.textContent==="Review the supported refinement").listeners.click();const selectedD10Text=treeText(e.central);const proposalActionInsideMap=treeNodes(e.central).some(value=>String(value.className||"").split(" ").includes("refinement-map")&&treeNodes(value).some(child=>child.textContent==="Create proposal"));let roundPicker=treeNodes(e.roundContext).find(value=>value.tag==="select");roundPicker.value="1";roundPicker.listeners.change();const roundSelectionCleared=api.state.selectedFinding===null;roundPicker=treeNodes(e.roundContext).find(value=>value.tag==="select");roundPicker.value="2";roundPicker.listeners.change();api.changeStage("diagnose");d10Card=treeNodes(e.central).find(value=>value.className==="finding-card"&&treeText(value).includes("D010"));treeNodes(d10Card).find(value=>value.textContent==="Review the supported refinement").listeners.click();
const identityStart=requests.length;responses.push(response({draft:{draft_key:"c".repeat(64),diagnosis_record_key:identityDiagnosisKey,base_record_key:refinementKey,finding:{finding_id:finding10.finding_id,rule_id:"D010",summary:finding10.summary},refiner:finding10.refiner,edits:[]}}));await treeNodes(e.central).find(value=>value.textContent==="Create proposal").listeners.click();const d10ProposalRequest=requests.slice(identityStart).some(item=>item[0].endsWith(`/${identityDiagnosisKey}/${finding10.finding_id}`));
api.applyProjection(projection("identity-same",[identityDoc,otherIdentityDoc]),"identity-doc");const sameDocumentProposalPreserved=api.state.proposal&&api.state.proposal.finding.rule_id==="D010";responses.push(response(projection("identity-duplicate",[identityDoc,otherIdentityDoc])));await api.handleObservationEnvelope({job:null,reactivation:{document_key:"identity-other",observation_record_key:observationKey}},"identity-other.md");api.changeStage("refine");const duplicateFindingText=treeText(e.central);const duplicateCleared=api.state.proposal===null&&api.state.proposalIdentity===null&&duplicateFindingText.includes("D009")&&!duplicateFindingText.includes("D010");
api.applyProjection(projection("identity-reset",[identityDoc,otherIdentityDoc]),"identity-doc");api.state.selectedRound=2;api.state.stage="refine";api.state.proposal={draft_key:"c".repeat(64),diagnosis_record_key:identityDiagnosisKey,base_record_key:refinementKey,finding:{finding_id:finding10.finding_id,rule_id:"D010",summary:finding10.summary},refiner:finding10.refiner,edits:[]};api.state.proposalIdentity={documentKey:"identity-doc",roundNumber:2,diagnosisKey:identityDiagnosisKey,baseKey:refinementKey};const completedDoc={document_key:"completed-d009",observation_record_key:"record-new",source:{name:"completed-d009.md",media_type:"text/markdown"},rounds:[{number:1,base_record_key:"record-new",diagnosis_record_key:otherDiagnosisKey,refinement_record_key:null,revision_record_key:null}]};responses.push(response(projection("identity-completed",[completedDoc,identityDoc,otherIdentityDoc])));await api.consumeObservationJob(backendJobs.ready,"job-1");api.changeStage("refine");const completedFindingText=treeText(e.central);const completedCleared=api.state.proposal===null&&api.state.proposalIdentity===null&&completedFindingText.includes("D009")&&!completedFindingText.includes("D010");outputs.findingIdentity=[selectedD10Text.includes("D010")&&!selectedD10Text.includes("D009"),proposalActionInsideMap,d10ProposalRequest,roundSelectionCleared,sameDocumentProposalPreserved,duplicateCleared,completedCleared];

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

const observationArtifact={artifact_key:"a".repeat(64),role:"observation-manifest",media_type:"application/json",size:100,sha256:"b".repeat(64),availability:"AVAILABLE"};
const observationDetail = {kind:"OBSERVATION",artifact_integrity:"VERIFIED",artifacts:[observationArtifact],view:{source:{key:"whitespace-cleanup-c960009a8c64",name:"whitespace-cleanup.md",media_type:"text/markdown",size:72,sha256:"a".repeat(64)},docling_document:{name:"DoclingDocument",version:"1.10.0"},extractors:[{name:"docling",version:"2.113.0",status:"SUCCESS"},{name:"markitdown",version:"0.1.6",status:"SUCCESS"}],comparison:{status:"COMPLETE",docling_minus_markitdown:{normalized_equal:true}}}};
const uploadedCollision = JSON.parse(JSON.stringify(observationDetail)); uploadedCollision.view.source.key="whitespace-cleanup-aabbccddeeff";
api.state.projection=projection("privacy",[{document_key:"guided",observation_record_key:observationKey,source:observationDetail.view.source,rounds:[]}]); api.state.selectedKind="document"; api.state.selectedKey="guided"; api.state.selectedRound=1; api.state.stage="observe"; api.state.inspector="summary"; api.state.details=new Map([[observationKey,observationDetail]]); api.renderSelected(); const guidedObserveText=treeText(e.central); const observeSummary=treeText(e.inspectorPanel);
const observeClasses=e.central.children.map(value=>value.className||"");outputs.observeOrder=[observeClasses.indexOf("learner-guidance"),observeClasses.findIndex(value=>value.includes("extraction-results")),observeClasses.findIndex(value=>value.includes("source-metadata"))];
const extractorCards=treeNodes(e.central).filter(value=>value.className==="extractor-result-card"); api.state.inspector="evidence";api.renderSelected();const observeEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const observeArtifacts=treeText(e.inspectorPanel);
outputs.observeStage=[guidedObserveText.includes("What Observe does")&&guidedObserveText.includes("records extraction evidence")&&!guidedObserveText.includes("Current stage"),extractorCards.length===4,guidedObserveText.includes("Succeeded")&&guidedObserveText.includes("Extraction agreement")&&guidedObserveText.includes("Docling and MarkItDown")&&guidedObserveText.includes("Normalized text views")&&guidedObserveText.includes("Equivalent")&&!guidedObserveText.includes("Equivalent after normalization")&&guidedObserveText.includes("Canonical representation")&&guidedObserveText.includes("DoclingDocument")&&guidedObserveText.includes("Ready")&&!guidedObserveText.includes("Ready for Diagnosis and Refine")&&!guidedObserveText.includes("↓"),observeSummary.includes("Observation")&&observeSummary.includes("Completed")&&observeSummary.includes("2 of 2 succeeded")&&observeSummary.includes("DoclingDocument · 1.10.0")&&observeSummary.includes("VERIFIED")&&observeSummary.includes("1 artifact"),observeEvidence.includes("aaaaaaaaaa…aaaaaaaa")&&observeEvidence.includes("Docling")&&observeEvidence.includes("2.113.0")&&observeEvidence.includes("MarkItDown")&&observeEvidence.includes("0.1.6")&&observeEvidence.includes("COMPLETE")&&observeEvidence.includes("Equivalent after normalization")&&observeEvidence.includes("corpus --help"),observeArtifacts.includes("observation-manifest")];
const pendingDiagnosisDoc={document_key:"pending-diagnosis",observation_record_key:observationKey,source:observationDetail.view.source,rounds:[]};api.state.projection=projection("pending-diagnosis",[pendingDiagnosisDoc]);api.state.selectedKind="document";api.state.selectedKey="pending-diagnosis";api.state.selectedRound=1;api.state.stage="diagnose";api.state.inspector="summary";api.state.details=new Map([[observationKey,observationDetail]]);api.renderSelected();const pendingDiagnosisSummary=treeText(e.inspectorPanel);api.state.inspector="evidence";api.renderSelected();const pendingDiagnosisEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const pendingDiagnosisArtifacts=treeText(e.inspectorPanel);
outputs.pendingDiagnosisInspector=[pendingDiagnosisSummary.includes("Diagnosis not run")&&pendingDiagnosisSummary.includes("Run Diagnosis"),pendingDiagnosisEvidence.includes("No diagnosis evidence yet")&&pendingDiagnosisEvidence.includes("after Diagnosis evaluates"),pendingDiagnosisArtifacts.includes("No diagnosis artifacts yet")&&pendingDiagnosisArtifacts.includes("published with the Diagnosis record")];
const diagnosisArtifact={artifact_key:"c".repeat(64),role:"diagnostic-findings",media_type:"application/json",size:80,sha256:"d".repeat(64),availability:"AVAILABLE"};const diagnosisDetail={kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[diagnosisArtifact],view:{subject_state:"MATCH",derivation_state:"MATCH",finding_total:1,findings:[{...finding,document_refs:["#/texts/0"]}]}};
api.state.projection=projection("diagnosis-inspector",[lifecycleDoc]);api.state.selectedKind="document";api.state.selectedKey="doc-life";api.state.selectedRound=1;api.state.stage="diagnose";api.state.inspector="summary";api.state.details=new Map([[observationKey,observationDetail],[diagnosisKey,diagnosisDetail]]);api.renderSelected();const diagnoseSummary=treeText(e.inspectorPanel);api.state.inspector="evidence";api.renderSelected();const diagnoseEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const diagnoseArtifacts=treeText(e.inspectorPanel);
outputs.diagnoseInspector=[diagnoseSummary.includes("Findings")&&diagnoseSummary.includes("Refinable findings")&&diagnoseSummary.includes("VERIFIED")&&diagnoseSummary.includes("1 artifact")&&!diagnoseSummary.includes("Extractor views"),diagnoseEvidence.includes("Diagnosis subject")&&diagnoseEvidence.includes("Diagnosis derivation")&&diagnoseEvidence.includes("Matched")&&diagnoseEvidence.includes("tcw-evidence-based-diagnosis")&&diagnoseEvidence.includes("v0.3")&&diagnoseEvidence.includes("Evidence references")&&diagnoseEvidence.includes("1")&&diagnoseEvidence.includes("corpus --help")&&!diagnoseEvidence.includes("MarkItDown"),diagnoseArtifacts.includes("diagnostic-findings")&&!diagnoseArtifacts.includes("observation-manifest")];
api.state.projection=projection("privacy-upload",[{document_key:"upload",observation_record_key:observationKey,source:uploadedCollision.view.source,rounds:[]}]); api.state.selectedKey="upload"; api.state.stage="observe"; api.state.details=new Map([[observationKey,uploadedCollision]]); api.renderSelected(); const uploadObserveText=treeText(e.central);
outputs.uploadPrivacyIdentity=[!guidedObserveText.includes("never displays or serves"),uploadObserveText.includes("never displays or serves")];

const approvedRefinement={kind:"REFINEMENT",artifact_integrity:"VERIFIED",artifacts:[],view:{decision:"APPROVED",proposal:{finding_id:findingId,refiner:finding.refiner},diagnosis_state:"MATCH",base_state:"MATCH",derivation_state:"MATCH",reversibility_state:"MATCH",transformations:[{}],revision_chain:[]}};
const rejectedRefinement={kind:"REFINEMENT",artifact_integrity:"VERIFIED",artifacts:[],view:{decision:"REJECTED",proposal:{finding_id:findingId,refiner:finding.refiner},diagnosis_state:"MATCH",base_state:"MATCH",derivation_state:"NOT_APPLICABLE",reversibility_state:"NOT_APPLICABLE",transformations:[],revision_chain:[]}};
const approvedDoc={document_key:"approved-doc",observation_record_key:observationKey,source:lifecycleDoc.source,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:refinementKey,revision_record_key:refinementKey}]};
const pendingDecisionDoc={...approvedDoc,rounds:[{...approvedDoc.rounds[0],refinement_record_key:null,revision_record_key:null}]};api.state.projection=projection("decision-focus",[pendingDecisionDoc]);api.state.selectedKind="document";api.state.selectedKey="approved-doc";api.state.selectedRound=1;api.state.stage="refine";api.state.inspector="summary";api.state.details=new Map([[observationKey,observationDetail],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]);api.state.proposal={draft_key:"5".repeat(64),diagnosis_record_key:diagnosisKey,base_record_key:observationKey,finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[{target:{field:"text"},before:"A  B",after:"A B"}]};api.state.proposalIdentity={documentKey:"approved-doc",roundNumber:1,diagnosisKey:diagnosisKey,baseKey:observationKey};api.state.decisionSelection="approve";api.state.decisionSubmitted=false;api.state.lifecyclePending=false;api.state.lifecycleReconciliationPending=false;api.state.actionToken="new-token";responses.push(response({publication:{kind:"REFINEMENT",decision:"APPROVED",record_key:refinementKey},refresh:{status:"READY"}}),response(projection("decision-focused",[approvedDoc])));await api.recordDecision();const focusedOutcome=treeNodes(e.central).find(value=>value.dataset.decisionOutcome==="true");outputs.decisionFocus=[Boolean(focusedOutcome),document.activeElement===focusedOutcome,focusedOutcome&&focusedOutcome.attributes.tabindex==="-1",treeText(e.central).includes("Why inspect the prepared revision?")&&treeText(e.central).includes("Available next step")];
api.state.projection=projection("approved",[approvedDoc]); api.state.selectedKind="document"; api.state.selectedKey="approved-doc"; api.state.selectedRound=1; api.state.stage="refine"; api.state.details=new Map([[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]); api.state.recordedProposal={finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[{target:{field:"text"},before:"A  B",after:"A B"}]};api.state.recordedProposalKey=refinementKey;api.state.lifecycleNotice=null; api.state.decisionSubmitted=false; api.state.inspector="summary";api.renderSelected(); const approvedText=treeText(e.central);const approvedCreate=treeNodes(e.central).find(value=>value.textContent==="Create proposal");const approvedSummary=treeText(e.inspectorPanel);api.state.inspector="evidence";api.renderSelected();const approvedEvidence=treeText(e.inspectorPanel);
const revisionArtifact={artifact_key:"e".repeat(64),role:"prepared-document-markdown",media_type:"text/markdown",size:20,sha256:"f".repeat(64),availability:"AVAILABLE"};approvedRefinement.artifacts=[revisionArtifact];api.state.stage="revision";api.state.inspector="summary";api.state.appliedProposal={finding:{rule_id:"D009"},refiner:finding.refiner,edits:[{target:{field:"text"},before:"A  B",after:"A B"}]};api.state.appliedComparisonOpen=false;api.renderSelected();const revisionClosedText=treeText(e.central);const revisionCurrent=treeNodes(e.central).find(value=>value.className==="lineage-node"&&value.attributes["aria-current"]==="true");const revisionHasCurrentWord=treeText(e.central).includes("Current");const showApplied=treeNodes(e.central).find(value=>value.className==="comparison-disclosure-toggle"&&value.attributes["aria-expanded"]==="false");const revisionSummary=treeText(e.inspectorPanel);await showApplied.listeners.click();const revisionOpenText=treeText(e.central);const openAppliedToggle=treeNodes(e.central).find(value=>value.className==="comparison-disclosure-toggle"&&value.attributes["aria-expanded"]==="true");await openAppliedToggle.listeners.click();const revisionClosedAgain=!treeNodes(e.central).some(value=>value.className==="comparison-shell");api.state.inspector="evidence";api.renderSelected();const revisionInspectorEvidence=treeText(e.inspectorPanel);api.state.inspector="artifacts";api.renderSelected();const revisionArtifacts=treeText(e.inspectorPanel);outputs.revisionStage=[revisionClosedText.includes("Inspect the immutable prepared result and its evidence."),revisionClosedText.includes("What Revision shows"),revisionClosedText.includes("Prepared revision created"),revisionClosedText.includes("Source finding")&&revisionClosedText.includes("Applied")&&revisionClosedText.includes("Supported refiner"),Boolean(revisionCurrent)&&revisionHasCurrentWord&&revisionClosedText.includes("Revision history"),Boolean(showApplied),revisionOpenText.includes("Applied comparison")&&Boolean(openAppliedToggle)&&treeNodes(e.central).every(value=>value.dataset.comparisonClose!=="true"),revisionClosedAgain,revisionSummary.includes("Prepared revision")&&revisionSummary.includes("Approved")&&revisionSummary.includes("D009")&&revisionSummary.includes("R001"),revisionInspectorEvidence.includes("Derived revision")&&revisionInspectorEvidence.includes("Inverse replay")&&revisionInspectorEvidence.includes("Matched")&&!revisionInspectorEvidence.includes("corpus CLI"),revisionArtifacts.includes("prepared-document-markdown")];
outputs.revisionStage[4]=Boolean(revisionCurrent)&&!treeNodes(e.central).some(value=>value.tag==="small"&&value.textContent==="Current");
approvedRefinement.artifacts=[];api.state.stage="refine";api.state.details.set(refinementKey,rejectedRefinement); approvedDoc.rounds[0].revision_record_key=null; api.renderSelected(); const rejectedText=treeText(e.central); api.state.stage="revision"; api.renderSelected(); const rejectedRevisionText=treeText(e.central);
outputs.decisionOutcomes=[approvedText.includes("What Refine does")&&approvedText.includes("D009")&&approvedText.includes("Proposed change")&&approvedText.includes("Approved")&&!approvedText.includes("How to read this recorded refinement")&&approvedText.includes("Why inspect the prepared revision?")&&approvedText.includes("View prepared revision"),Boolean(approvedCreate&&approvedCreate.disabled),approvedSummary.includes("Recorded decision")&&approvedSummary.includes("Approved")&&approvedSummary.includes("D009")&&approvedSummary.includes("R001"),approvedEvidence.includes("Diagnosis relation")&&approvedEvidence.includes("Derived revision")&&approvedEvidence.includes("Inverse replay")&&approvedEvidence.includes("Matched")&&!approvedEvidence.includes("corpus CLI"),rejectedText.includes("What Refine does")&&rejectedText.includes("Rejected")&&rejectedText.includes("base document remains current and unchanged")&&!rejectedText.includes("How to read this recorded refinement")&&!rejectedText.includes("Why inspect the prepared revision?"),rejectedRevisionText.includes("Not needed")];
const recordedDescriptor={artifact_key:"8".repeat(64),role:"refinement-proposal",media_type:"application/json",size:100,sha256:"9".repeat(64),availability:"AVAILABLE"};approvedRefinement.artifacts=[recordedDescriptor];api.state.projection=projection("recorded-hydration",[approvedDoc]);api.state.selectedKind="document";api.state.selectedKey="approved-doc";api.state.selectedRound=1;api.state.stage="refine";api.state.details=new Map([[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]);api.state.recordedProposal=null;api.state.recordedProposalKey=null;responses.push(response({forward_edits:[{target:{field:"text"},before:"A  B",after:"A B"}],finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner}));await api.hydrateRecordedProposal(approvedDoc,approvedDoc.rounds[0]);outputs.recordedProposalHydration=[api.state.recordedProposalKey===refinementKey,api.state.recordedProposal.edits.length===1,api.state.recordedProposal.finding.rule_id==="D009",api.state.recordedProposalLoading===null];

const secondRefinementKey="6".repeat(64), secondDiagnosisKey="7".repeat(64); const twoRoundDoc={document_key:"two-round",observation_record_key:observationKey,source:lifecycleDoc.source,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:refinementKey,revision_record_key:refinementKey},{number:2,base_record_key:refinementKey,diagnosis_record_key:secondDiagnosisKey,refinement_record_key:secondRefinementKey,revision_record_key:secondRefinementKey}]};
api.state.projection=projection("two-round",[twoRoundDoc]); api.state.selectedKind="document"; api.state.selectedKey="two-round"; api.state.selectedRound=1; api.state.stage="diagnose"; api.state.details=new Map([[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement],[secondDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[secondRefinementKey,approvedRefinement]]); api.renderSelected(); const historicalRoundText=treeText(e.central); const historicalBadgeVisible=e.stepper.stageEntries.every(entry=>treeText(entry.children[0]).includes("Read-only history"));
api.state.selectedRound=2; api.state.stage="revision"; api.renderSelected(); const latestRoundText=treeText(e.central);const roundOptions=treeNodes(e.roundContext).filter(value=>value.tag==="option").map(value=>value.textContent);
outputs.roundHistory=[historicalBadgeVisible&&!historicalRoundText.includes("Historical round · Read-only"),!historicalRoundText.includes("Run Diagnosis"),latestRoundText.includes("Original")&&latestRoundText.includes("Revision 1")&&latestRoundText.includes("Revision 2"),roundOptions.join(",")==="Round 1,Round 2",e.stepper.stageEntries.every(entry=>!treeText(entry.children[0]).includes("Read-only history"))];

api.state.projection=projection("rapid",[lifecycleDoc]); api.state.selectedKind="document"; api.state.selectedKey="doc-life"; api.state.selectedRound=1; api.state.stage="refine"; api.state.details=new Map([[observationKey,observationDetail],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]); api.state.proposal={draft_key:"5".repeat(64),diagnosis_record_key:diagnosisKey,base_record_key:observationKey,finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[]};api.state.proposalIdentity={documentKey:"doc-life",roundNumber:1,diagnosisKey:diagnosisKey,baseKey:observationKey}; api.state.decisionSelection="approve"; api.state.decisionSubmitted=false; api.state.lifecyclePending=false; api.state.lifecycleReconciliationPending=false; api.state.actionToken="new-token";
let resolveDecisionDeferred; const decisionDeferred=new Promise(resolve=>{resolveDecisionDeferred=resolve;}); responses.push(decisionDeferred); const rapidStart=requests.length; const rapidFirst=api.recordDecision();const pendingIdentity=api.state.pendingLifecycleMutation;const refreshPostsBefore=requests.filter(item=>item[0].endsWith("/workbench/refresh")&&item[1]==="POST").length;await api.refreshWorkspace();const concurrentRequestBlocked=requests.filter(item=>item[0].endsWith("/workbench/refresh")&&item[1]==="POST").length===refreshPostsBefore;const concurrentIdentityPreserved=api.state.pendingLifecycleMutation===pendingIdentity;const refreshStayedDisabled=e.refresh.disabled;await api.recordDecision();resolveDecisionDeferred(response({publication:{kind:"REFINEMENT",decision:"APPROVED",record_key:null},refresh:{status:"FAILED",message:"refresh failed"}})); await rapidFirst;const pendingAfterPublication=api.state.pendingLifecycleMutation===pendingIdentity&&api.state.lifecycleReconciliationPending;responses.push(response(null,204),response(projection("rapid-absent",[lifecycleDoc])));await api.refreshWorkspace();const absentDecisionStayedLocked=api.state.lifecycleReconciliationPending&&api.state.pendingLifecycleMutation===pendingIdentity;const rapidPublishedDoc=JSON.parse(JSON.stringify(lifecycleDoc));rapidPublishedDoc.rounds[0].refinement_record_key=refinementKey;rapidPublishedDoc.rounds[0].revision_record_key=refinementKey;responses.push(response(null,204),response(projection("rapid-visible",[rapidPublishedDoc])));await api.refreshWorkspace();const rapidProducerPosts=requests.slice(rapidStart).filter(item=>item[0].includes("/lifecycle/proposals/")&&item[0].endsWith("/approve")).length;outputs.rapidDecision=[concurrentRequestBlocked,concurrentIdentityPreserved,refreshStayedDisabled,pendingAfterPublication,absentDecisionStayedLocked,rapidProducerPosts,api.state.lifecycleReconciliationPending,api.state.pendingLifecycleMutation===null];

const pendingRoundDoc={document_key:"decision-doc",observation_record_key:observationKey,source:lifecycleDoc.source,rounds:[{number:1,base_record_key:observationKey,diagnosis_record_key:diagnosisKey,refinement_record_key:null,revision_record_key:null}]}; const publishedRoundDoc=JSON.parse(JSON.stringify(pendingRoundDoc)); publishedRoundDoc.rounds[0].refinement_record_key=refinementKey; publishedRoundDoc.rounds[0].revision_record_key=refinementKey;
function prepareUnknownDecision(){api.state.projection=projection("decision-base",[pendingRoundDoc]);api.state.selectedKind="document";api.state.selectedKey="decision-doc";api.state.selectedRound=1;api.state.stage="refine";api.state.details=new Map([[observationKey,observationDetail],[diagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[refinementKey,approvedRefinement]]);api.state.proposal={draft_key:"5".repeat(64),diagnosis_record_key:diagnosisKey,base_record_key:observationKey,finding:{finding_id:findingId,rule_id:"D009",summary:finding.summary},refiner:finding.refiner,edits:[]};api.state.proposalIdentity={documentKey:"decision-doc",roundNumber:1,diagnosisKey:diagnosisKey,baseKey:observationKey};api.state.decisionSelection="approve";api.state.decisionSubmitted=false;api.state.lifecyclePending=false;api.state.lifecycleReconciliationPending=false;api.state.lifecycleNotice=null;api.state.pendingLifecycleMutation=null;api.state.actionToken="new-token";}
prepareUnknownDecision(); const unknownPublishedStart=requests.length; responses.push(new Error("lost"),response(null,204),response(projection("decision-published",[publishedRoundDoc]))); await api.recordDecision(); outputs.unknownDecisionPublished=[requests.slice(unknownPublishedStart).filter(item=>item[1]==="POST").length,api.state.lifecycleReconciliationPending,api.state.proposal===null,api.state.stage,api.state.decisionSubmitted];
prepareUnknownDecision(); const unknownAbsentStart=requests.length; responses.push(new Error("lost"),response(null,204),response(projection("decision-absent",[pendingRoundDoc]))); await api.recordDecision(); outputs.unknownDecisionAbsent=[requests.slice(unknownAbsentStart).filter(item=>item[1]==="POST").length,api.state.lifecycleReconciliationPending,api.state.proposal!==null,api.state.decisionSubmitted];

const raceRefinement={...approvedRefinement,artifacts:[{role:"refinement-proposal",artifact_key:"8".repeat(64)}]}; api.state.projection=projection("race",[twoRoundDoc]);api.state.selectedKind="document";api.state.selectedKey="two-round";api.state.selectedRound=2;api.state.stage="revision";api.state.details=new Map([[secondDiagnosisKey,{kind:"DIAGNOSIS",artifact_integrity:"VERIFIED",artifacts:[],view:{finding_total:1,findings:[finding]}}],[secondRefinementKey,raceRefinement]]);api.state.appliedProposal=null;api.state.appliedProposalLoading=null;api.state.appliedComparisonOpen=false;api.state.lifecyclePending=false;api.state.lifecycleReconciliationPending=false;api.renderSelected(); const openRace=treeNodes(e.central).find(value=>value.className==="comparison-disclosure-toggle"); let resolveArtifact; const artifactDeferred=new Promise(resolve=>{resolveArtifact=resolve;});responses.push(artifactDeferred);const racePromise=openRace.listeners.click();api.state.selectedRound=1;api.state.stage="diagnose";api.renderSelected();resolveArtifact(response({forward_edits:[{target:{field:"text"},before:"before",after:"after"}],finding:{rule_id:"D009"},refiner:finding.refiner}));await racePromise;outputs.appliedRace=[api.state.appliedProposal===null,api.state.stage,api.state.selectedRound];

const corpusKey="c".repeat(64), artifactKey="d".repeat(64), artifactHash="e".repeat(64); const corpusItem={record_key:corpusKey,title:"Golden corpus",member_count:2,status:"VERIFIED"}; const corpusDetail={kind:"CORPUS",artifact_integrity:"VERIFIED",artifacts:[{artifact_key:artifactKey,role:"corpus-summary",media_type:"application/json",size:7,sha256:artifactHash,availability:"AVAILABLE"}],view:{totals:{member_count:2,finding_count:1,revision_count:0,failed:0},matrix:[{member_id:"policy-md",family:"policy",format:"md",status:"COMPLETE"},{member_id:"notice-txt",family:"notice",format:"txt",status:"COMPLETE"}],aggregates:{by_family:[{family:"policy"},{family:"notice"}],by_format:[{format:"md"},{format:"txt"}],extractors:[{name:"docling",available:2,unavailable:0},{name:"markitdown",available:2,unavailable:0}],findings:[{rule_id:"D009",family:"policy",format:"md",finding_count:1,affected_member_count:1}]}}};
 api.state.projection={session_id:"corpus",package_version:"0.8.1",reference,records:[],documents:[],corpora:[corpusItem]};api.state.selectedKind="corpus";api.state.selectedKey=corpusKey;api.state.stage="observe";api.state.inspector="summary";api.state.reader=null;api.state.details=new Map([[corpusKey,corpusDetail]]);api.renderSelected();outputs.corpusInspection=[e.stepper.hidden,treeText(e.central).includes("2 members"),treeText(e.central).includes("policy"),treeText(e.inspectorPanel).includes("CORPUS")];
api.state.inspector="evidence";api.renderSelected();outputs.corpusEvidence=[treeText(e.inspectorPanel).includes("Coverage"),treeText(e.inspectorPanel).includes("Families"),treeText(e.inspectorPanel).includes("Formats"),treeText(e.inspectorPanel).includes("Members"),treeText(e.inspectorPanel).includes("Docling"),treeText(e.inspectorPanel).includes("D009 · policy")];
api.state.inspector="artifacts";api.renderSelected();const artifactOpen=treeNodes(e.inspectorPanel).find(value=>value.dataset.artifactKey===artifactKey);responses.push(response('{"z":1,"name":"raw-value"}'));await artifactOpen.listeners.click();const jsonSource=treeNodes(e.central).find(value=>String(value.className).includes("source-reader"));const readerSelection=[api.state.selectedKind,api.state.selectedKey,api.state.stage];const readerHeading=treeNodes(e.central).find(value=>value.id==="artifact-reader-heading");const wrapToggle=treeNodes(e.central).find(value=>value.dataset.readerControl==="wrap");wrapToggle.focus();wrapToggle.listeners.click();const rerenderedWrap=treeNodes(e.central).find(value=>value.dataset.readerControl==="wrap");outputs.readerAccessibility=[e.central.attributes["aria-labelledby"]===readerHeading.id,document.activeElement===rerenderedWrap,rerenderedWrap!==wrapToggle];api.setLocale("zh-CN",false);outputs.jsonReader=[jsonSource.textContent==='{\n  "z": 1,\n  "name": "raw-value"\n}',treeText(e.central).includes("产物阅读器"),api.state.reader!==null,[api.state.selectedKind,api.state.selectedKey,api.state.stage].join(",")===readerSelection.join(",")];api.setLocale("en",false);api.closeReader();outputs.readerReturn=[api.state.reader===null,api.state.selectedKind,api.state.selectedKey,api.state.stage,!registry["stage-inspector"].hidden,e.central.attributes["aria-labelledby"]==="stage-heading",treeNodes(e.central).includes(e.stageHeading)];
const htmlDescriptor={artifact_key:"f".repeat(64),role:"corpus-report",media_type:"text/html",size:12,sha256:"1".repeat(64),availability:"AVAILABLE"};responses.push(response("<h1>Report</h1>"));await api.openArtifact(htmlDescriptor);const htmlFrame=treeNodes(e.central).find(value=>value.tag==="iframe");const sourceToggle=treeNodes(e.central).find(value=>value.dataset.readerControl==="html-source");sourceToggle.focus();sourceToggle.listeners.click();const htmlSource=treeNodes(e.central).find(value=>String(value.className).includes("source-reader"));const reportToggle=treeNodes(e.central).find(value=>value.dataset.readerControl==="html-source");const sourceFocus=document.activeElement===reportToggle&&reportToggle!==sourceToggle;reportToggle.listeners.click();const sourceToggleAgain=treeNodes(e.central).find(value=>value.dataset.readerControl==="html-source");const reportFocus=document.activeElement===sourceToggleAgain&&sourceToggleAgain!==reportToggle;outputs.htmlReader=[htmlFrame.attributes.sandbox==="",htmlFrame.attributes.referrerpolicy==="no-referrer",htmlFrame.attributes.tabindex==="-1",htmlFrame.srcdoc.includes("default-src 'none'"),htmlSource.textContent==="<h1>Report</h1>",sourceFocus,reportFocus,treeNodes(e.central).some(value=>value.tag==="iframe")];
api.closeReader();const largeDescriptor={artifact_key:"2".repeat(64),role:"large-report",media_type:"text/markdown",size:99999999,sha256:"3".repeat(64),availability:"TOO_LARGE"};await api.openArtifact(largeDescriptor);outputs.oversizedReader=[treeText(e.central).includes("too large"),treeText(e.central).includes("not truncated"),requests.every(item=>!item[0].includes(largeDescriptor.artifact_key))];
api.closeReader();const comparisonDescriptor={artifact_key:"4".repeat(64),role:"refinement-proposal",media_type:"application/json",size:100,sha256:"5".repeat(64),availability:"AVAILABLE"};responses.push(response({forward_edits:[{target:{field:"text"},before:"A  B",after:"A B"}],finding:{rule_id:"D009"},refiner:{refiner_id:"R001"}}));await api.openArtifact(comparisonDescriptor);const artifactComparisonText=treeText(e.central);outputs.artifactComparison=[treeNodes(e.central).some(value=>value.className==="comparison-shell"),artifactComparisonText.includes("··"),artifactComparisonText.includes("D009 → R001")];
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
        self.assertEqual(
            values["extractorStatuses"],
            [
                ["✓", "SUCCESS", "Succeeded", "Succeeded"],
                ["!", "PARTIAL_SUCCESS", "Partially succeeded", "Partially succeeded"],
                ["×", "FAILED", "Failed", "Failed"],
            ],
        )
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
        self.assertEqual(values["modalOpen"], [False, True, True, True])
        self.assertEqual(values["modalKeys"], [True, True, True, True, 3])
        self.assertEqual(values["backdrop"], [True, True, True])
        self.assertEqual(values["active"], ["job-1", True, True, True, 1])
        self.assertEqual(values["publishedRefreshFailed"], [True, "doc-old", "diagnose", "evidence", "failure", True, False])
        self.assertEqual(values["publishedRefreshFailedNoObservation"], [True, "doc-old", "failure", True])
        self.assertEqual(values["ready"], ["ready", "doc-new", "observe", "success", False])
        self.assertEqual(values["terminalProjectionFailure"], [True, "doc-old", "diagnose", "evidence", None, False, 0, "failure", True, True, True])
        self.assertEqual(values["terminalDetailFailure"], [True, "doc-old", "diagnose", "evidence", None, False, 0, "failure", True, True, True])
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
        self.assertEqual(values["noFindingsStages"], [True] * 10)
        self.assertEqual(values["noFindingsInspectors"], [True] * 6)
        self.assertEqual(
            values["stageOutcomes"],
            [
                ["observe", "stageCompleted", "Completed"],
                ["diagnose", "stageCompleted", "Completed"],
                ["refine", "notNeeded", "Not needed"],
                ["revision", "notNeeded", "Not needed"],
            ],
        )
        self.assertEqual(values["proposalComparison"], [True, True, True, True, True, True, True, True])
        self.assertEqual(values["structuralComparison"], [True, True, True])
        self.assertEqual(values["multiFindingChoice"], [True, True])
        self.assertEqual(values["findingIdentity"], [True, True, True, True, True, True, True])
        self.assertEqual(values["staleLifecycle"], [1, 2, "new-token", False, "staleToken"])
        self.assertEqual(values["prepublicationLifecycle"], [1, 0, False, "lifecyclePrepublicationFailure", True])
        self.assertEqual(values["publishedLifecycle"], [True, "doc-fresh", 1, True, 1, False, True, True])
        self.assertEqual(values["unknownLifecycle"], [2, 1, False, True, {"title": "lifecycleUnknown", "body": "lifecycleUnknown", "tone": "failure"}])
        self.assertEqual(values["manualLifecycleRecovery"], [1, 1, False, True, True])
        self.assertEqual(values["uploadPrivacyIdentity"], [True, True])
        self.assertEqual(values["observeOrder"], [3, 4, 5])
        self.assertEqual(values["observeStage"], [True] * 6)
        self.assertEqual(values["pendingDiagnosisInspector"], [True] * 3)
        self.assertEqual(values["diagnoseInspector"], [True] * 3)
        self.assertEqual(values["decisionFocus"], [True] * 4)
        self.assertEqual(values["decisionOutcomes"], [True, True, True, True, True, True])
        self.assertEqual(values["revisionStage"], [True] * 11)
        self.assertEqual(values["recordedProposalHydration"], [True, True, True, True])
        self.assertEqual(values["roundHistory"], [True, True, True, True, True])
        self.assertEqual(values["rapidDecision"], [True, True, True, True, True, 1, False, True])
        self.assertEqual(values["unknownDecisionPublished"], [2, False, True, "refine", True])
        self.assertEqual(values["unknownDecisionAbsent"], [2, False, True, False])
        self.assertEqual(values["appliedRace"], [True, "diagnose", 1])
        self.assertEqual(values["corpusInspection"], [True, True, True, True])
        self.assertEqual(values["corpusEvidence"], [True, True, True, True, True, True])
        self.assertEqual(values["readerAccessibility"], [True, True, True])
        self.assertEqual(values["jsonReader"], [True, True, True, True])
        self.assertEqual(values["readerReturn"], [True, "corpus", "c" * 64, "observe", True, True, True])
        self.assertEqual(values["htmlReader"], [True, True, True, True, True, True, True, True])
        self.assertEqual(values["oversizedReader"], [True, True, True])
        self.assertEqual(values["artifactComparison"], [True, True, True])

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
