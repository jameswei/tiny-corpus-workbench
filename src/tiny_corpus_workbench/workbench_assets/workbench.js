"use strict";

const API_ROOT = "/api";
const OBSERVATION_POLL_INTERVAL_MS = 300;
const TOAST_DURATION_MS = 4000;
const LOCALE_KEY = "tcw.workbench.locale";
const RECONCILING_OBSERVATION = "RECONCILING";
const STAGES = ["observe", "diagnose", "refine", "revision"];

const catalogs = {
  en: {
    workspace: "Workspace", documents: "Documents", corpora: "Corpora", addDocument: "Add a document", skipToWorkspace: "Skip to workspace",
    workspaceNavigation: "Workspace navigation", stagesLabel: "Document preparation stages", inspectorLabel: "Stage inspector", corpusShell: "Corpus inspection",
    refreshWorkspace: "Refresh workspace", ruleReference: "Rule reference", switchLocale: "Switch to Simplified Chinese",
    close: "Close", closeNotification: "Close notification", emptyTitle: "Your workspace is empty",
    emptyBody: "Add a guided example or a supported local document to begin.", loadFailureTitle: "Workspace could not be loaded",
    loadFailureBody: "No partial state was accepted and no files were changed. Refresh after you correct the workspace records.",
    loading: "Loading the workspace…", contextDocument: "Document", contextCorpus: "Corpus", verifiedMembers: "Verified · {count} members",
    observeQuestion: "What did extraction produce?", diagnoseQuestion: "What needs attention?", refineQuestion: "What change is proposed?",
    revisionQuestion: "What was preserved?", currentStage: "Current stage", observe: "Observe", diagnose: "Diagnose", refine: "Refine", revision: "Revision",
    shellGuidance: "This stage workspace is ready for the lifecycle content in the next checkpoint.", summary: "Summary", evidence: "Evidence", artifacts: "Artifacts",
    inspectorSummary: "Stage guidance and status will appear here.", inspectorEvidence: "Verified supporting evidence will appear here.", inspectorArtifacts: "Published artifacts will appear here.",
    noDocuments: "No documents", noCorpora: "No corpora", addIntro: "Choose one path. A new source is selected and Observe starts immediately.",
    completePath: "Complete guided preparation", noFindingsPath: "Guided no-findings inspection", uploadTitle: "Upload one document",
    uploadFormats: ".docx, .md, .pdf, or .txt up to 32 MiB", startObserve: "Start Observe", observing: "Observe started for {name}.",
    reactivated: "This source already exists. Its document was selected; no new document or Observation was created.",
    refreshStarted: "Refreshing the workspace.", refreshSuccess: "Workspace refreshed.", refreshNoChange: "Workspace is already up to date.",
    refreshFailure: "Refresh failed. The last accepted workspace view was preserved.", observeFailure: "Observe could not start.",
    observationBusy: "An Observation is already running. Wait for it to finish before adding another document.",
    observationPublishedRefreshFailed: "The Observation was published, but the workspace could not refresh. The last accepted view was preserved. Use Refresh workspace; do not run Observe again.",
    observationStatusUnknown: "The Observation status could not be confirmed. The Workbench will reconcile it; no action was replayed.",
    observationWorkspaceReconciled: "The Observation outcome was lost after restart. The accepted workspace was reconciled; no action was replayed.",
    ruleIntro: "A finding is evidence from a fixed condition. It is not a verdict or permission to change a document.",
    credit: "An inspectable document-preparation project.", github: "GitHub Repository",
    "rule.D001.name": "Empty document", "rule.D001.about": "The canonical document contains no content items.",
    "rule.D002.name": "Suspiciously short document", "rule.D002.about": "The extracted text is within the fixed short-document range.",
    "rule.D003.name": "Replacement character", "rule.D003.about": "Extracted text contains the Unicode replacement character.",
    "rule.D004.name": "Duplicate text block", "rule.D004.about": "A sufficiently long text block occurs more than once.",
    "rule.D005.name": "Heading level jump", "rule.D005.about": "A heading skips more than one level from the prior heading.",
    "rule.D006.name": "Orphan caption", "rule.D006.about": "A caption has no supported nearby picture or table.",
    "rule.D007.name": "Repeated page-margin text", "rule.D007.about": "The same bounded text occurs near page margins on enough pages.",
    "rule.D008.name": "Missing PDF provenance", "rule.D008.about": "A PDF observation lacks the required extraction provenance.",
    "rule.D009.name": "Normalizable whitespace", "rule.D009.about": "Text contains whitespace that differs from the fixed normalized form.",
    "rule.D010.name": "Possible line-end hyphenation", "rule.D010.about": "A fixed line-end pattern may represent a split word.",
    "refiner.R001": "Whitespace normalization", "refiner.R002": "Repeated boilerplate removal", "refiner.R003": "Deterministic dehyphenation"
  },
  "zh-CN": {
    workspace: "工作区", documents: "文档", corpora: "语料库", addDocument: "添加文档", skipToWorkspace: "跳到工作区",
    workspaceNavigation: "工作区导航", stagesLabel: "文档准备阶段", inspectorLabel: "阶段检查器", corpusShell: "语料库检查",
    refreshWorkspace: "刷新工作区", ruleReference: "规则参考", switchLocale: "切换到英语",
    close: "关闭", closeNotification: "关闭通知", emptyTitle: "工作区为空",
    emptyBody: "添加引导示例或支持的本地文档以开始。", loadFailureTitle: "无法加载工作区",
    loadFailureBody: "未接受任何部分状态，也未更改任何文件。修正工作区记录后请刷新。",
    loading: "正在加载工作区…", contextDocument: "文档", contextCorpus: "语料库", verifiedMembers: "已验证 · {count} 个成员",
    observeQuestion: "提取得到了什么？", diagnoseQuestion: "哪些内容需要注意？", refineQuestion: "建议进行什么更改？",
    revisionQuestion: "保留了什么？", currentStage: "当前阶段", observe: "观察", diagnose: "诊断", refine: "改进", revision: "修订",
    shellGuidance: "此阶段工作区已就绪；生命周期内容将在下一检查点加入。", summary: "摘要", evidence: "证据", artifacts: "产物",
    inspectorSummary: "阶段指导和状态将在此显示。", inspectorEvidence: "已验证的支持证据将在此显示。", inspectorArtifacts: "已发布的产物将在此显示。",
    noDocuments: "没有文档", noCorpora: "没有语料库", addIntro: "请选择一种路径。新来源会被选中，并立即开始观察。",
    completePath: "完整引导式准备", noFindingsPath: "无发现引导式检查", uploadTitle: "上传一个文档",
    uploadFormats: ".docx、.md、.pdf 或 .txt，最大 32 MiB", startObserve: "开始观察", observing: "已开始观察 {name}。",
    reactivated: "此来源已存在。已选择其文档；未创建新文档或观察记录。",
    refreshStarted: "正在刷新工作区。", refreshSuccess: "工作区已刷新。", refreshNoChange: "工作区已是最新状态。",
    refreshFailure: "刷新失败。已保留上次接受的工作区视图。", observeFailure: "无法开始观察。",
    observationBusy: "一个观察任务正在运行。请等待其完成后再添加文档。",
    observationPublishedRefreshFailed: "观察记录已发布，但工作区无法刷新。已保留上次接受的视图。请使用“刷新工作区”，不要再次运行观察。",
    observationStatusUnknown: "无法确认观察状态。工作台将进行协调；未重放任何操作。",
    observationWorkspaceReconciled: "重启后无法恢复观察结果。已协调接受的工作区；未重放任何操作。",
    ruleIntro: "发现是固定条件产生的证据，不是裁决，也不是更改文档的授权。",
    credit: "一个可检查的文档准备项目。", github: "GitHub 仓库",
    "rule.D001.name": "空文档", "rule.D001.about": "规范文档不包含任何内容项。",
    "rule.D002.name": "文档短得可疑", "rule.D002.about": "提取文本处于固定的短文档范围内。",
    "rule.D003.name": "替换字符", "rule.D003.about": "提取文本包含 Unicode 替换字符。",
    "rule.D004.name": "重复文本块", "rule.D004.about": "足够长的文本块出现了多次。",
    "rule.D005.name": "标题级别跳跃", "rule.D005.about": "标题相对前一标题跳过了一个以上的级别。",
    "rule.D006.name": "孤立题注", "rule.D006.about": "题注附近没有支持的图片或表格。",
    "rule.D007.name": "重复页边文本", "rule.D007.about": "相同的有限文本在足够多页面的页边附近出现。",
    "rule.D008.name": "缺少 PDF 来源证据", "rule.D008.about": "PDF 观察缺少所需的提取来源证据。",
    "rule.D009.name": "可规范化空白", "rule.D009.about": "文本空白与固定的规范形式不同。",
    "rule.D010.name": "可能的行尾连字符", "rule.D010.about": "固定的行尾模式可能表示被拆分的单词。",
    "refiner.R001": "空白规范化", "refiner.R002": "重复样板移除", "refiner.R003": "确定性去连字符"
  }
};

const state = { projection: null, locale: "en", selectedKind: null, selectedKey: null, stage: "observe", inspector: "summary", initialFailure: false, activeObservationJobId: null, pendingReactivationKey: null, pendingTerminalToastKey: null, workspaceReconciliationPending: false };
const elements = {};
let toastTimer = null;
let toastRemaining = TOAST_DURATION_MS;
let toastStartedAt = 0;
let toastHovered = false;
let toastFocused = false;
let pollingTimer = null;
let modalReturnFocus = null;

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined && text !== null) value.textContent = String(text);
  if (className) value.className = className;
  return value;
}
function clear(value) { while (value.firstChild) value.removeChild(value.firstChild); }
function format(template, values = {}) { return Object.entries(values).reduce((result, [key, value]) => result.replace(`{${key}}`, String(value)), template); }
function t(key, values) { return format(catalogs[state.locale][key] || catalogs.en[key] || key, values); }
function catalogParity() {
  const en = Object.keys(catalogs.en).sort();
  const zh = Object.keys(catalogs["zh-CN"]).sort();
  return en.length === zh.length && en.every((key, index) => key === zh[index]);
}
function catalogCoversReference(reference) {
  if (!reference || !Array.isArray(reference.rules)) return false;
  const expectedRules = new Set(reference.rules.map((rule) => rule.rule_id));
  const expectedRefiners = new Set(reference.rules.filter((rule) => rule.refiner).map((rule) => rule.refiner.refiner_id));
  return Object.values(catalogs).every((catalog) => {
    const actualRuleNames = Object.keys(catalog).filter((key) => /^rule\.[^.]+\.name$/.test(key)).map((key) => key.split(".")[1]);
    const actualRuleCopy = Object.keys(catalog).filter((key) => /^rule\.[^.]+\.about$/.test(key)).map((key) => key.split(".")[1]);
    const actualRefiners = Object.keys(catalog).filter((key) => key.startsWith("refiner.")).map((key) => key.slice("refiner.".length));
    return setsEqual(expectedRules, new Set(actualRuleNames)) && setsEqual(expectedRules, new Set(actualRuleCopy)) && setsEqual(expectedRefiners, new Set(actualRefiners));
  });
}
function setsEqual(left, right) { return left.size === right.size && Array.from(left).every((value) => right.has(value)); }
function negotiatedLocale(languages, stored) {
  if (stored === "en" || stored === "zh-CN") return stored;
  return Array.from(languages || []).some((value) => String(value).toLowerCase().startsWith("zh")) ? "zh-CN" : "en";
}
function safeStoredLocale() { try { return localStorage.getItem(LOCALE_KEY); } catch (_) { return null; } }
function saveLocale(value) { try { localStorage.setItem(LOCALE_KEY, value); } catch (_) { /* browser storage can be unavailable */ } }
function setLocale(value, persist = true) {
  if (value !== "en" && value !== "zh-CN") return false;
  state.locale = value;
  if (persist) saveLocale(value);
  if (elements.localeToggle) render();
  return true;
}

function localizeStatic() {
  document.documentElement.lang = state.locale;
  document.querySelectorAll("[data-i18n]").forEach((item) => { item.textContent = t(item.dataset.i18n); });
  elements.localeToggle.textContent = state.locale === "en" ? "中" : "EN";
  elements.localeToggle.title = t("switchLocale"); elements.localeToggle.setAttribute("aria-label", t("switchLocale"));
  elements.ruleButton.title = t("ruleReference"); elements.ruleButton.setAttribute("aria-label", t("ruleReference"));
  elements.refresh.title = t("refreshWorkspace"); elements.refresh.setAttribute("aria-label", t("refreshWorkspace"));
  elements.add.title = t("addDocument"); elements.add.setAttribute("aria-label", t("addDocument"));
  elements.toastClose.title = t("closeNotification"); elements.toastClose.setAttribute("aria-label", t("closeNotification"));
  document.getElementById("workspace-navigation").setAttribute("aria-label", t("workspaceNavigation"));
  elements.stepper.setAttribute("aria-label", t("stagesLabel"));
  document.getElementById("stage-inspector").setAttribute("aria-label", t("inspectorLabel"));
  document.querySelectorAll(".modal-close").forEach((button) => { button.title = t("close"); button.setAttribute("aria-label", t("close")); });
}

function selectedItem() {
  if (!state.projection) return null;
  const values = state.selectedKind === "corpus" ? state.projection.corpora : state.projection.documents;
  const key = state.selectedKind === "corpus" ? "record_key" : "document_key";
  return values.find((item) => item[key] === state.selectedKey) || null;
}
function selectItem(kind, key) { state.selectedKind = kind; state.selectedKey = key; state.stage = "observe"; render(); }

function navigationCard(item, kind) {
  const key = kind === "document" ? item.document_key : item.record_key;
  const name = kind === "document" ? item.source.name : item.title;
  const button = node("button", null, "navigation-card"); button.type = "button"; button.title = name;
  button.setAttribute("aria-current", String(state.selectedKind === kind && state.selectedKey === key));
  button.append(node("span", name, "card-name"));
  button.append(node("span", kind === "document" ? item.source.media_type : t("verifiedMembers", {count: item.member_count}), "card-meta"));
  button.addEventListener("click", () => selectItem(kind, key));
  return button;
}
function renderNavigation() {
  clear(elements.documents); clear(elements.corpora);
  for (const item of state.projection.documents) elements.documents.append(navigationCard(item, "document"));
  for (const item of state.projection.corpora) elements.corpora.append(navigationCard(item, "corpus"));
  if (!state.projection.documents.length) elements.documents.append(node("p", t("noDocuments"), "card-meta"));
  if (!state.projection.corpora.length) elements.corpora.append(node("p", t("noCorpora"), "card-meta"));
}
function renderEmptyOrFailure() {
  clear(elements.workspaceState); elements.selected.hidden = true; elements.workspaceState.hidden = false;
  const card = node("div", null, "state-card");
  card.append(node("h2", t(state.initialFailure ? "loadFailureTitle" : "emptyTitle")));
  card.append(node("p", t(state.initialFailure ? "loadFailureBody" : "emptyBody")));
  if (!state.initialFailure) { const add = node("button", t("addDocument"), "primary-button"); add.type = "button"; add.addEventListener("click", () => openModal(elements.addModal)); card.append(add); }
  elements.workspaceState.append(card);
}
function renderSelected() {
  const item = selectedItem();
  if (!item) { state.selectedKind = null; state.selectedKey = null; renderEmptyOrFailure(); return; }
  elements.workspaceState.hidden = true; elements.selected.hidden = false;
  elements.contextKind.textContent = t(state.selectedKind === "document" ? "contextDocument" : "contextCorpus");
  elements.contextName.textContent = state.selectedKind === "document" ? item.source.name : item.title;
  elements.stepper.hidden = state.selectedKind === "corpus";
  elements.stepper.querySelectorAll("li").forEach((entry) => entry.dataset.current = String(entry.dataset.stage === state.stage));
  elements.stageHeading.textContent = t(state.selectedKind === "corpus" ? "corpusShell" : state.stage); elements.stageGuidance.textContent = t("shellGuidance");
  elements.tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.tab === state.inspector)));
  elements.inspectorPanel.textContent = t(`inspector${state.inspector[0].toUpperCase()}${state.inspector.slice(1)}`);
}
function renderRuleReference() {
  clear(elements.ruleList);
  const rules = state.projection && state.projection.reference ? state.projection.reference.rules : [];
  for (const rule of rules) {
    const entry = node("article", null, "rule-entry");
    entry.append(node("h3", `${t(`rule.${rule.rule_id}.name`)} · ${rule.rule_id}`));
    const meta = rule.refiner ? `${rule.severity} · ${rule.refiner.refiner_id} ${t(`refiner.${rule.refiner.refiner_id}`)}` : rule.severity;
    entry.append(node("p", meta, "rule-meta"), node("p", t(`rule.${rule.rule_id}.about`)));
    elements.ruleList.append(entry);
  }
}
function render() {
  localizeStatic();
  if (state.projection) { elements.version.textContent = `v${state.projection.package_version}`; renderNavigation(); renderRuleReference(); }
  const hasWorkspace = state.projection && (state.projection.documents.length || state.projection.corpora.length);
  elements.add.disabled = state.initialFailure || !state.projection;
  updateObservationControls();
  if (!hasWorkspace && !selectedItem()) renderEmptyOrFailure(); else renderSelected();
}

function dismissToast() { if (toastTimer !== null) clearTimeout(toastTimer); toastTimer = null; toastHovered = false; toastFocused = false; elements.toast.hidden = true; }
function scheduleToast() { toastStartedAt = Date.now(); toastTimer = setTimeout(dismissToast, toastRemaining); }
function pauseToast() { if (toastTimer === null) return; clearTimeout(toastTimer); toastTimer = null; toastRemaining = Math.max(0, toastRemaining - (Date.now() - toastStartedAt)); }
function resumeToast() { if (!toastHovered && !toastFocused && !elements.toast.hidden && elements.toast.dataset.tone !== "failure" && toastTimer === null) scheduleToast(); }
function setToastHover(value) { toastHovered = value; if (value) pauseToast(); else resumeToast(); }
function setToastFocus(value) { toastFocused = value; if (value) pauseToast(); else resumeToast(); }
function showToast(message, tone = "info") {
  dismissToast(); elements.toastMessage.textContent = message; elements.toast.dataset.tone = tone; elements.toast.hidden = false;
  const announcer = tone === "failure" ? elements.assertive : elements.polite; announcer.textContent = ""; announcer.textContent = message;
  if (tone !== "failure") { toastRemaining = TOAST_DURATION_MS; scheduleToast(); }
}

function focusable(modal) { return Array.from(modal.querySelectorAll("button:not([disabled]), input:not([disabled])")); }
function openModal(modal) { modalReturnFocus = document.activeElement; modal.hidden = false; elements.surface.inert = true; const targets = focusable(modal); if (targets.length) targets[0].focus(); }
function closeModal(modal) { modal.hidden = true; elements.surface.inert = false; if (modalReturnFocus && modalReturnFocus.focus) modalReturnFocus.focus(); modalReturnFocus = null; }
function modalKeydown(event) {
  const modal = event.currentTarget;
  if (event.key === "Escape") { event.preventDefault(); closeModal(modal); return; }
  if (event.key !== "Tab") return;
  const targets = focusable(modal); if (!targets.length) return;
  const first = targets[0], last = targets[targets.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
function backdropDismiss(event) { if (event.target === event.currentTarget) closeModal(event.currentTarget); }

async function fetchJSON(target, options = {}) {
  const response = await fetch(target, {credentials: "same-origin", headers: {Accept: "application/json", ...(options.headers || {})}, ...options});
  if (!response.ok) { let body = {}; try { body = await response.json(); } catch (_) { /* status is sufficient */ } const error = new Error(body.message || `Request failed with status ${response.status}.`); error.code = body.code; error.confirmed = true; throw error; }
  return response.status === 204 ? null : response.json();
}
async function loadProjection({initial = false, preferredKey = null} = {}) {
  try {
    const projection = await fetchJSON(`${API_ROOT}/workbench`);
    applyProjection(projection, preferredKey);
    render(); elements.refresh.disabled = false; return true;
  } catch (error) {
    if (initial) { state.initialFailure = true; state.projection = null; render(); elements.assertive.textContent = t("loadFailureTitle"); elements.refresh.disabled = false; }
    throw error;
  }
}
function applyProjection(projection, preferredKey = null) {
    if (!catalogCoversReference(projection.reference)) throw new Error("locale catalogs do not match the canonical reference");
    const priorKey = preferredKey || state.selectedKey; const priorKind = state.selectedKind;
    state.projection = projection; state.initialFailure = false;
    const documentExists = projection.documents.some((item) => item.document_key === priorKey);
    const corpusExists = projection.corpora.some((item) => item.record_key === priorKey);
    if ((priorKind === "document" && documentExists) || (priorKind === "corpus" && corpusExists)) { state.selectedKey = priorKey; state.selectedKind = priorKind; }
    else if (preferredKey && documentExists) { state.selectedKey = preferredKey; state.selectedKind = "document"; state.stage = "observe"; }
    else if (state.selectedKey && !documentExists && !corpusExists) { state.selectedKey = null; state.selectedKind = null; }
    if (!state.selectedKey && projection.documents.length) { state.selectedKind = "document"; state.selectedKey = projection.documents[0].document_key; }
    else if (!state.selectedKey && projection.corpora.length) { state.selectedKind = "corpus"; state.selectedKey = projection.corpora[0].record_key; }
    return state.projection;
}
function observationIsActive(job) { return Boolean(job && (job.state === "QUEUED" || job.state === "RUNNING")); }
function setObservationActive(job) {
  state.activeObservationJobId = observationIsActive(job) ? job.job_id : null;
  updateObservationControls();
}
function updateObservationControls() {
  if (!elements.add) return;
  const disabled = state.initialFailure || !state.projection || state.activeObservationJobId !== null;
  elements.add.disabled = disabled;
  if (elements.guidedWhitespace) elements.guidedWhitespace.disabled = disabled;
  if (elements.guidedPolicy) elements.guidedPolicy.disabled = disabled;
  if (elements.file) elements.file.disabled = disabled;
  if (elements.upload) elements.upload.disabled = disabled || !(elements.file.files && elements.file.files.length === 1);
}
async function refreshWorkspace() {
  const selected = state.selectedKey; const before = state.projection ? state.projection.session_id : null;
  elements.refresh.disabled = true; elements.polite.textContent = t("refreshStarted");
  try {
    await fetchJSON(`${API_ROOT}/workbench/refresh`, {method: "POST"}); await loadProjection({preferredKey: selected});
    showToast(t(before === state.projection.session_id ? "refreshNoChange" : "refreshSuccess"), "success");
  } catch (_) { showToast(t("refreshFailure"), "failure"); }
  finally { elements.refresh.disabled = false; }
}
async function handleObservationEnvelope(envelope, inputName) {
  if (envelope.reactivation) {
    state.pendingReactivationKey = envelope.reactivation.document_key;
    await reconcilePendingReactivation();
    return;
  }
  closeModal(elements.addModal); showToast(t("observing", {name: inputName}), "info");
  if (envelope.job) { await consumeObservationJob(envelope.job, envelope.job.job_id); return; }
  throw new Error("observation response outcome is unknown");
}
async function reconcilePendingReactivation({announce = true, announceFailure = true} = {}) {
  const documentKey = state.pendingReactivationKey;
  if (documentKey === null) return true;
  try { await loadProjection({preferredKey: documentKey}); }
  catch (_) { retainUnknownObservationOwnership(announceFailure); return false; }
  if (!state.projection.documents.some((document) => document.document_key === documentKey)) { retainUnknownObservationOwnership(announceFailure); return false; }
  state.pendingReactivationKey = null;
  setObservationActive(null);
  closeModal(elements.addModal);
  if (announce) showToast(t("reactivated"), "info");
  return true;
}
function claimObservationSubmission() {
  if (state.activeObservationJobId !== null) return false;
  state.activeObservationJobId = RECONCILING_OBSERVATION;
  updateObservationControls();
  return true;
}
function scheduleObservationDiscovery() {
  if (pollingTimer !== null) clearTimeout(pollingTimer);
  pollingTimer = setTimeout(discoverActiveObservation, OBSERVATION_POLL_INTERVAL_MS);
}
function retainUnknownObservationOwnership(announce = true) {
  state.activeObservationJobId = RECONCILING_OBSERVATION;
  updateObservationControls();
  if (announce) showToast(t("observationStatusUnknown"), "failure");
  scheduleObservationDiscovery();
}
async function settleTerminalOwnership({announceReactivation = false, preserveToast = false} = {}) {
  if (state.pendingReactivationKey !== null) {
    return reconcilePendingReactivation({announce: announceReactivation, announceFailure: !preserveToast});
  }
  setObservationActive(null);
  return true;
}
async function reconcileMissingObservationSnapshot() {
  state.workspaceReconciliationPending = true;
  const preferredKey = state.pendingReactivationKey || state.selectedKey;
  try { await loadProjection({preferredKey}); }
  catch (_) { retainUnknownObservationOwnership(); return false; }
  if (state.pendingReactivationKey !== null && !state.projection.documents.some((document) => document.document_key === state.pendingReactivationKey)) {
    retainUnknownObservationOwnership();
    return false;
  }
  if (state.pendingReactivationKey !== null) {
    state.pendingReactivationKey = null;
    closeModal(elements.addModal);
  }
  state.workspaceReconciliationPending = false;
  setObservationActive(null);
  showToast(t("observationWorkspaceReconciled"), "failure");
  return true;
}
async function handleObservationSubmissionError(error) {
  if (!error.confirmed || error.ownershipUnresolved) { retainUnknownObservationOwnership(); return; }
  if (error.code === "OBSERVATION_BUSY") {
    showToast(t("observationBusy"), "failure");
    await discoverActiveObservation();
    return;
  }
  setObservationActive(null);
  showToast(t("observeFailure"), "failure");
}
async function submitGuidedObservation(guidedId, name) {
  if (state.activeObservationJobId !== null) { showToast(t("observationBusy"), "failure"); return; }
  claimObservationSubmission();
  try { await handleObservationEnvelope(await fetchJSON(`${API_ROOT}/observation-jobs/guided/${guidedId}`, {method: "POST"}), name); }
  catch (error) { await handleObservationSubmissionError(error); }
}
async function submitUploadedObservation() {
  if (state.activeObservationJobId !== null) { showToast(t("observationBusy"), "failure"); return; }
  const file = elements.file.files && elements.file.files[0]; if (!file) return;
  claimObservationSubmission();
  try {
    const envelope = await fetchJSON(`${API_ROOT}/observation-jobs/upload?filename=${encodeURIComponent(file.name)}`, {method: "POST", body: file, headers: {"Content-Type": file.type || "application/octet-stream"}});
    await handleObservationEnvelope(envelope, file.name);
  } catch (error) { await handleObservationSubmissionError(error); }
}
function scheduleObservationPoll(jobId) {
  if (pollingTimer !== null) clearTimeout(pollingTimer);
  pollingTimer = setTimeout(() => pollObservation(jobId), OBSERVATION_POLL_INTERVAL_MS);
}
async function consumeObservationJob(job, expectedJobId) {
  if (!job) {
    await reconcileMissingObservationSnapshot();
    return;
  }
  if (job.job_id !== expectedJobId) {
    await consumeObservationJob(job, job.job_id);
    return;
  }
  if (observationIsActive(job)) {
    setObservationActive(job);
    scheduleObservationPoll(job.job_id);
    return;
  }
  if (pollingTimer !== null) clearTimeout(pollingTimer);
  pollingTimer = null;
  if (job.state === "COMPLETED" && job.refresh && job.refresh.status === "FAILED") {
    const reconciled = await settleTerminalOwnership({preserveToast: true});
    state.pendingTerminalToastKey = reconciled ? null : "observationPublishedRefreshFailed";
    showToast(t("observationPublishedRefreshFailed"), "failure");
    return;
  }
  if (job.state === "COMPLETED" && job.observation && job.refresh && job.refresh.status === "READY" && job.observation.record_key) {
    const projected = await fetchJSON(`${API_ROOT}/workbench`);
    const document = projected.documents.find((item) => item.observation_record_key === job.observation.record_key);
    applyProjection(projected, document ? document.document_key : null);
    if (document) state.stage = "observe";
    render();
    const hadPendingReactivation = state.pendingReactivationKey !== null;
    const reconciled = await settleTerminalOwnership({announceReactivation: true});
    if (reconciled && !hadPendingReactivation) showToast(t("refreshSuccess"), "success");
    return;
  }
  const reconciled = await settleTerminalOwnership({preserveToast: true});
  state.pendingTerminalToastKey = reconciled ? null : "observeFailure";
  showToast(t("observeFailure"), "failure");
}
async function pollObservation(jobId) {
  if (pollingTimer !== null) { clearTimeout(pollingTimer); pollingTimer = null; }
  try {
    const envelope = await fetchJSON(`${API_ROOT}/observation-jobs`); const job = envelope.job;
    await consumeObservationJob(job, jobId);
  } catch (_) {
    state.activeObservationJobId = jobId;
    updateObservationControls();
    showToast(t("observationStatusUnknown"), "failure");
    scheduleObservationPoll(jobId);
  }
}
async function discoverActiveObservation() {
  if (pollingTimer !== null) { clearTimeout(pollingTimer); pollingTimer = null; }
  try {
    const envelope = await fetchJSON(`${API_ROOT}/observation-jobs`);
    if (envelope.job !== null) { await consumeObservationJob(envelope.job, envelope.job.job_id); return; }
    if (state.workspaceReconciliationPending) { await reconcileMissingObservationSnapshot(); return; }
    if (state.pendingReactivationKey !== null) {
      const terminalToastKey = state.pendingTerminalToastKey;
      const reconciled = await reconcilePendingReactivation({announce: terminalToastKey === null, announceFailure: terminalToastKey === null});
      if (terminalToastKey !== null) {
        if (reconciled) state.pendingTerminalToastKey = null;
        showToast(t(terminalToastKey), "failure");
      }
      return;
    }
    setObservationActive(null);
  } catch (_) {
    state.activeObservationJobId = RECONCILING_OBSERVATION;
    updateObservationControls();
    if (!state.initialFailure) showToast(t("observationStatusUnknown"), "failure");
    scheduleObservationDiscovery();
  }
}

function bindElements() {
  const ids = ["app-surface", "package-version", "rule-reference", "locale-toggle", "refresh-workspace", "add-document", "document-list", "corpus-list", "workspace-state", "selected-workspace", "context-kind", "context-name", "stage-stepper", "stage-heading", "stage-guidance", "inspector-panel", "toast", "toast-message", "toast-close", "polite-announcer", "assertive-announcer", "add-modal", "rule-modal", "rule-list", "observation-file", "add-upload", "add-whitespace", "add-policy"];
  for (const id of ids) elements[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = document.getElementById(id);
  Object.assign(elements, {surface: elements.appSurface, version: elements.packageVersion, ruleButton: elements.ruleReference, localeToggle: elements.localeToggle, refresh: elements.refreshWorkspace, add: elements.addDocument, documents: elements.documentList, corpora: elements.corpusList, workspaceState: elements.workspaceState, selected: elements.selectedWorkspace, contextKind: elements.contextKind, contextName: elements.contextName, stepper: elements.stageStepper, stageHeading: elements.stageHeading, stageGuidance: elements.stageGuidance, inspectorPanel: elements.inspectorPanel, toastMessage: elements.toastMessage, toastClose: elements.toastClose, polite: elements.politeAnnouncer, assertive: elements.assertiveAnnouncer, addModal: elements.addModal, ruleModal: elements.ruleModal, ruleList: elements.ruleList, file: elements.observationFile, upload: elements.addUpload, guidedWhitespace: elements.addWhitespace, guidedPolicy: elements.addPolicy});
  elements.tabs = Array.from(document.querySelectorAll("[role=tab]"));
}
function addListeners() {
  elements.refresh.addEventListener("click", refreshWorkspace); elements.add.addEventListener("click", () => openModal(elements.addModal));
  elements.ruleButton.addEventListener("click", () => openModal(elements.ruleModal));
  elements.localeToggle.addEventListener("click", () => setLocale(state.locale === "en" ? "zh-CN" : "en"));
  elements.toastClose.addEventListener("click", dismissToast); elements.toast.addEventListener("mouseenter", () => setToastHover(true)); elements.toast.addEventListener("mouseleave", () => setToastHover(false)); elements.toast.addEventListener("focusin", () => setToastFocus(true)); elements.toast.addEventListener("focusout", (event) => { if (!elements.toast.contains(event.relatedTarget)) setToastFocus(false); });
  document.querySelectorAll(".modal-backdrop").forEach((modal) => { modal.addEventListener("keydown", modalKeydown); modal.querySelector(".modal-close").addEventListener("click", () => closeModal(modal)); modal.addEventListener("mousedown", backdropDismiss); });
  document.getElementById("add-whitespace").addEventListener("click", () => submitGuidedObservation("whitespace-cleanup-md", "whitespace-cleanup.md"));
  document.getElementById("add-policy").addEventListener("click", () => submitGuidedObservation("policy-memo-md", "policy-memo.md"));
  elements.file.addEventListener("change", updateObservationControls); elements.upload.addEventListener("click", submitUploadedObservation);
  elements.stepper.querySelectorAll("li button").forEach((button) => button.addEventListener("click", () => { state.stage = button.parentElement.dataset.stage; renderSelected(); }));
  elements.tabs.forEach((tab) => tab.addEventListener("click", () => { state.inspector = tab.dataset.tab; renderSelected(); }));
}
async function start() {
  if (!catalogParity()) throw new Error("locale catalogs must contain identical keys");
  bindElements(); state.locale = negotiatedLocale(navigator.languages || [navigator.language], safeStoredLocale()); state.activeObservationJobId = RECONCILING_OBSERVATION; addListeners(); localizeStatic();
  elements.workspaceState.append(node("p", t("loading")));
  try { await loadProjection({initial: true}); } catch (_) { /* durable initial failure is rendered */ }
  await discoverActiveObservation();
}

if (typeof window !== "undefined") window.__tcwWorkbench = {catalogs, state, elements, t, catalogParity, catalogCoversReference, negotiatedLocale, setLocale, applyProjection, showToast, pauseToast, resumeToast, setToastHover, setToastFocus, dismissToast, loadProjection, refreshWorkspace, handleObservationEnvelope, reconcilePendingReactivation, reconcileMissingObservationSnapshot, claimObservationSubmission, submitGuidedObservation, submitUploadedObservation, observationIsActive, setObservationActive, consumeObservationJob, pollObservation, discoverActiveObservation, updateObservationControls, render, openModal, closeModal, modalKeydown, backdropDismiss};
if (!globalThis.__TCW_TEST_NO_START__) start();
