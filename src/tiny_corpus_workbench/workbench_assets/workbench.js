"use strict";

const API_ROOT = "/api";
const OBSERVATION_POLL_INTERVAL_MS = 300;
const TOAST_DURATION_MS = 4000;
const LOCALE_KEY = "tcw.workbench.locale";
const RECONCILING_OBSERVATION = "RECONCILING";
const STAGES = ["observe", "diagnose", "refine", "revision"];
const GUIDED_SOURCE_KEYS = new Set(["policy-memo-md", "whitespace-cleanup-c960009a8c64"]);

const catalogs = {
  en: {
    workspace: "Workspace", documents: "Documents", corpora: "Corpora", addDocument: "Add a document", skipToWorkspace: "Skip to workspace",
    workspaceNavigation: "Workspace navigation", stagesLabel: "Document preparation stages", inspectorLabel: "Stage inspector", corpusShell: "Corpus inspection",
    refreshWorkspace: "Refresh workspace", ruleReference: "Rule reference", diagnosisRuleReference: "Diagnosis rule reference", switchLocale: "Switch to Simplified Chinese",
    close: "Close", closeNotification: "Close notification", emptyTitle: "Your workspace is empty",
    emptyBody: "Add a guided example or a supported local document to begin.", loadFailureTitle: "Workspace could not be loaded",
    loadFailureBody: "No partial state was accepted and no files were changed. Refresh after you correct the workspace records.",
    loading: "Loading the workspace…", contextDocument: "Document", contextCorpus: "Corpus", verifiedMembers: "Verified · {count} members",
    observeQuestion: "What did extraction produce?", diagnoseQuestion: "What needs attention?", refineQuestion: "What change is proposed?",
    revisionQuestion: "What was preserved?", observe: "Observe", diagnose: "Diagnose", refine: "Refine", revision: "Revision", stageCompleted: "Completed", stageCurrent: "Current",
    shellGuidance: "Choose a stage to inspect this document's preparation evidence.", inspector: "Inspector", summary: "Summary", evidence: "Evidence", artifacts: "Artifacts",
    preparationRound: "Preparation round {current} of {total}", roundOption: "Round {number}", startsOriginal: "Starts from Original", startsRevision: "Starts from Revision {number}", chooseRound: "Choose preparation round",
    sourceObject: "Source object", filename: "Filename", mediaType: "Media type", size: "Size", sha256: "SHA-256", observationComplete: "Observation completed", observationMeaning: "Observe preserved the source and produced extraction views plus a canonical working document.", observeStageSubtitle: "Capture the source and compare independent extraction views.", observeGuideTitle: "What Observe does", observeGuideInspect: "Observe captures one immutable source and runs Docling and MarkItDown independently so you can compare what each extractor produced.", observeGuideBoundary: "It keeps DoclingDocument as the canonical working representation for later stages. Observe records extraction evidence; it does not judge or change document quality.", diagnosisGuideTitle: "How to read this result", revisionGuideTitle: "What Revision shows", observationStages: "Extraction results", extractionView: "Extraction view", extractorVersion: "Version {version}", extractionAgreement: "Extraction agreement", extractorAgreement: "Docling and MarkItDown", normalizedViews: "Normalized text views", equivalent: "Equivalent", different: "Different", ready: "Ready", canonicalReady: "Ready for Diagnosis and Refine", normalizedEquivalent: "Equivalent after normalization", normalizedDifferent: "Different after normalization", comparisonUnavailable: "Comparison unavailable", extractionEvidence: "Extraction evidence", statusSuccess: "Succeeded", statusPartialSuccess: "Partially succeeded", statusFailed: "Failed", uploadPrivacy: "Workbench shows source metadata and extracted artifacts. It never displays or serves the uploaded original.", diagnoseHandoff: "The observation is ready for deterministic, read-only Diagnosis.", continueDiagnosis: "Continue to Diagnosis",
    diagnosisStageSubtitle: "Fixed rules identify evidence that needs attention.", diagnosisReady: "Diagnosis is read-only", diagnosisReadyBody: "Fixed rules inspect the current document and record evidence. Diagnosis does not change the source, observation, or current revision.", diagnosisRulesReference: "The preset rules model common, broadly applicable mechanical checks for corpus preparation. Open Rule reference in the upper-right corner to review all of them.", diagnosisNotRunTitle: "Diagnosis not run", diagnosisNotRunBody: "Run Diagnosis to publish this stage record.", noDiagnosisEvidenceTitle: "No diagnosis evidence yet", noDiagnosisEvidenceBody: "Evidence appears after Diagnosis evaluates the current document.", noDiagnosisArtifactsTitle: "No diagnosis artifacts yet", noDiagnosisArtifactsBody: "Artifacts are published with the Diagnosis record.", runDiagnosis: "Run Diagnosis", diagnosisRunning: "Diagnosis is running…", diagnosisCompleted: "Diagnosis completed", findingsCount: "{count} findings", noFindingsMeaning: "No fixed rule matched. No content changed.", findingEvidenceLimit: "A finding is evidence that one fixed mechanical rule matched. It is not an invalidity or compliance verdict.", matchedRule: "Matched rule", ruleName: "Rule name", ruleIdentifier: "Rule ID", whyItMatters: "Why it matters", availableNextStep: "Available next step", refineFinding: "Review the supported refinement", severity: "Severity", unavailable: "Unavailable", notNeeded: "Not needed", unavailablePrerequisite: "This stage has no published prerequisite yet.", noFindingsNotNeeded: "No fixed rule matched, so no refinement or prepared revision is needed. Diagnosis evidence remains available.", refineNotNeededSubtitle: "No supported change is needed for this round.", revisionNotNeededSubtitle: "No prepared revision is needed for this round.", historicalReadOnly: "Historical round · Read-only", readOnlyHistory: "Read-only history", returnLatest: "Return to latest round",
    refineStageSubtitle: "Review a supported change and record an explicit decision.", refineReady: "What Refine does", refineReadyBody: "Refine handles one selected finding at a time. It maps the finding to a deterministic refiner, previews the exact change, and records an explicit decision. The base document remains unchanged unless you approve the proposal.", sourceFinding: "Source finding", supportedRefiner: "Supported refiner", chooseFindingTitle: "Choose one finding", chooseFindingBody: "This Diagnosis has multiple supported findings. Return to Diagnosis and choose the finding you want to refine.", returnToDiagnosis: "Return to Diagnosis", proposalStatus: "Proposal status", proposalNotCreated: "Not created", proposalTemporary: "Temporary · edits: {count}", diagnosisSourceEvidenceTitle: "Diagnosis is the source evidence", proposalEvidenceTitle: "Proposal evidence is temporary", refineInspectorReady: "The selected Diagnosis finding is the source evidence. No proposal or document change exists yet.", diagnosisInspectorEvidence: "Each finding keeps its matched rule, document references, and captured evidence in this immutable Diagnosis record.", noRefinementArtifactsTitle: "No published artifacts yet", noRefinementArtifacts: "Refinement artifacts are published only after you record Approve or Reject.", refineNoFindingsSummaryTitle: "Refinement not needed", refineNoFindingsSummaryBody: "Diagnosis found no supported change for this round.", refineNoFindingsEvidenceTitle: "Diagnosis ended this round", refineNoFindingsEvidenceBody: "Zero findings means there is no proposal to review or decide.", refineNoFindingsArtifactsTitle: "No refinement artifacts", refineNoFindingsArtifactsBody: "No proposal or decision record was published.", revisionNoFindingsSummaryTitle: "Prepared revision not needed", revisionNoFindingsSummaryBody: "This round has no approved refinement to apply.", revisionNoFindingsEvidenceTitle: "No revision evidence", revisionNoFindingsEvidenceBody: "Diagnosis is the final published stage for this round.", revisionNoFindingsArtifactsTitle: "No revision artifacts", revisionNoFindingsArtifactsBody: "No prepared revision was created.", createProposal: "Create proposal", proposalRunning: "Creating the proposal…", proposedChange: "Proposed change", before: "Before", after: "After", visibleWhitespace: "Visible whitespace: · space, → tab, ↵ line break", previousChange: "Previous change", nextChange: "Next change", changePosition: "Change {current} of {total}", changePositionShort: "{current} of {total}", structuralMovement: "Structural movement", chooseDecision: "Choose a decision", decisionExplanationTitle: "Why record a decision?", decisionExplanationBody: "The proposal is temporary and has not changed the document. Record Approve or Reject to preserve your choice in an immutable refinement record. Approval creates a prepared revision; rejection keeps the base document unchanged.", decisionGuidance: "Approval creates one immutable prepared revision. Rejection keeps the current document without a new revision.", recordedDecision: "Recorded decision", diagnosisRelation: "Diagnosis relation", baseRelation: "Base relation", derivationCheck: "Derived revision", reversibilityCheck: "Inverse replay", transformationCount: "Transformations", matched: "Matched", notChecked: "Not checked", notApplicable: "Not applicable", approve: "Approve", reject: "Reject", recordDecision: "Record decision", decisionRunning: "Recording the decision…", approved: "Approved", rejected: "Rejected", decisionApprovedBody: "The approved edit created one immutable prepared revision.", decisionRejectedBody: "No prepared revision was created. The base document remains current and unchanged.", nextRevisionExplanationTitle: "Why inspect the prepared revision?", nextRevisionExplanationBody: "Approval created a new immutable revision. Review it to confirm the applied change, inspect its comparison, and follow the preserved evidence back to this decision.", viewPreparedRevision: "View prepared revision", rejectedEvidence: "The proposal, human decision, and refinement report remain available. No forward or inverse transformation was applied.",
    revisionStageSubtitle: "Inspect the immutable prepared result and its evidence.", revisionCreated: "Prepared revision created", revisionMeaning: "The approved change produced a new immutable prepared revision. The base document remains preserved.", revisionEvidence: "Revision presents the prepared document produced by an approved refinement. Use its history, applied comparison, and verification evidence to trace the result back to its base document and decision.", revisionLineage: "Revision lineage", original: "Original", revisionNumber: "Revision {number}", current: "Current", preparedRevision: "Prepared revision", appliedRefiner: "Applied refiner", applied: "Applied", openAppliedComparison: "Applied comparison", loadingAppliedComparison: "Loading the applied comparison…", optionalNextStep: "Optional next step", nextRoundBody: "Diagnose the prepared revision to begin another Diagnose → Refine → Revision round.", startNextRound: "Start another Diagnosis", rejectedRevisionNotNeeded: "The recorded decision rejected the proposal. Only an approved proposal creates a prepared revision.", preservedEvidence: "Preserved and immutable evidence", forwardInverse: "Forward and inverse evidence verified", loadingStage: "Loading stage evidence…",
    lifecyclePrepublicationFailure: "The operation failed before publication. No record was created, and the accepted immutable source remains unchanged.", retry: "Retry", lifecyclePublishedRefreshFailed: "The record was published, but the workspace could not refresh. Keep this accepted view and use Refresh workspace; do not rerun the producer.", lifecycleUnknown: "The mutation outcome is unknown. Workbench is reconciling the workspace and will not replay the action.", staleToken: "The action token changed. It was refreshed; click again to confirm this action.", lifecycleBusy: "Another mutation is running. Wait for it to reach a terminal result.", decisionComplete: "This proposal already has a recorded decision.", noCliNeeded: "The browser completes this lifecycle; no CLI command or target JSON is required.",
    inspectorSummary: "Stage guidance and status will appear here.", inspectorEvidence: "Verified supporting evidence will appear here.", inspectorArtifacts: "Published artifacts will appear here.",
    verified: "Verified", recordKind: "Record", auditStatus: "Audit status", observationStatus: "Observation", extractorViews: "Extractor views", extractorSummary: "{successful} of {total} succeeded", canonicalRepresentation: "Canonical representation", comparisonStatus: "Comparison status", normalizedOutput: "Normalized output", diagnosisSubject: "Diagnosis subject", diagnosisDerivation: "Diagnosis derivation", ruleset: "Ruleset", evidenceReferences: "Evidence references", refinableFindings: "Refinable findings", bytes: "bytes", artifactCount: "{count} artifacts", openArtifact: "Open artifact", artifactReader: "Artifact reader", artifactRole: "Artifact role", copyArtifact: "Copy artifact", copiedArtifact: "Artifact copied.", copyFailed: "Artifact could not be copied.", toggleWrap: "Toggle line wrapping", showHtmlSource: "Show HTML source", showHtmlReport: "Show formatted HTML report", closeReader: "Close artifact reader", wrapped: "Lines wrap", unwrapped: "Lines do not wrap", oversizedTitle: "Artifact is too large to open", oversizedBody: "Workbench verified this artifact, but its {size} bytes exceed the reader limit. The content was not truncated.", readerFailure: "Artifact could not be opened.", htmlReaderTitle: "Verified project-generated HTML report", htmlReaderDescription: "The report is isolated from scripts, network resources, and navigation.", cliNoteStart: "Optional: the", cliNoteMiddle: "CLI can use this published record. Run", cliNoteEnd: "and use the lifecycle lessons in", cliNoteTail: "for the command workflow.", pendingProposalEvidence: "This proposal is temporary. It has not changed the document or published a record.", corpusSummary: "Corpus summary", corpusMeaning: "This verified corpus contains {count} members. Corpus creation and execution remain available through the CLI.", corpusTotals: "Corpus totals", members: "Members", families: "Families", formats: "Formats", findings: "Findings", revisions: "Revisions", failures: "Failures", memberMatrix: "Member evidence", memberStatus: "{family} · {format} · {status}", noArtifactContent: "No published artifact is available for this stage.",
    noDocuments: "No documents", noCorpora: "No corpora yet", corpusEmptyStart: "Create a corpus with", corpusEmptyEnd: ", then refresh this workspace.", addIntro: "Choose one learning path. Workbench selects the document and starts Observe immediately.",
    guidedPreparationTitle: "Prepare a sample document", recommended: "Recommended", guidedPreparationDetail: "Follow the complete Observe → Diagnose → Refine → Revision path with a sample that has one clear whitespace finding.", sampleFile: "Sample", startGuidedPreparation: "Start guided preparation",
    guidedInspectionTitle: "Explore a document with no matched rules", guidedInspectionDetail: "Observe and diagnose a policy memo, then learn what a no-findings result does—and does not—mean.", startGuidedInspection: "Start guided inspection",
    ownDocumentTitle: "Observe your own document", ownDocumentDetail: "Choose a supported file up to 32 MiB. Workbench shows its metadata and extracted artifacts, not a rendering of the original file.", chooseDocument: "Choose a document", uploadFormats: ".docx, .md, .pdf, or .txt up to 32 MiB", observeDocument: "Observe this document", observing: "Observe started for {name}.",
    reactivated: "This source already exists. Its document was selected; no new document or Observation was created.",
    refreshStarted: "Refreshing the workspace.", refreshSuccess: "Workspace refreshed.", refreshNoChange: "Workspace is already up to date.",
    refreshFailure: "Refresh failed. The last accepted workspace view was preserved.", observeFailure: "Observe could not start.",
    observationBusy: "An Observation is already running. Wait for it to finish before adding another document.",
    observationPublishedRefreshFailed: "The Observation was published, but the workspace could not refresh. The last accepted view was preserved. Use Refresh workspace; do not run Observe again.",
    observationStatusUnknown: "The Observation status could not be confirmed. The Workbench will reconcile it; no action was replayed.",
    observationWorkspaceReconciled: "The Observation outcome was lost after restart. The accepted workspace was reconciled; no action was replayed.",
    ruleIntro: "A finding means that one fixed rule matched. It is evidence, not an automatic verdict or permission to change the document.",
    credit: "An inspectable document-preparation workbench.", creatorCredit: "Created by James Wei", github: "GitHub Repository",
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
    refreshWorkspace: "刷新工作区", ruleReference: "规则参考", diagnosisRuleReference: "诊断规则参考", switchLocale: "切换到英语",
    close: "关闭", closeNotification: "关闭通知", emptyTitle: "工作区为空",
    emptyBody: "添加引导示例或支持的本地文档以开始。", loadFailureTitle: "无法加载工作区",
    loadFailureBody: "未接受任何部分状态，也未更改任何文件。修正工作区记录后请刷新。",
    loading: "正在加载工作区…", contextDocument: "文档", contextCorpus: "语料库", verifiedMembers: "已验证 · {count} 个成员",
    observeQuestion: "提取得到了什么？", diagnoseQuestion: "哪些内容需要注意？", refineQuestion: "建议进行什么更改？",
    revisionQuestion: "保留了什么？", observe: "观察", diagnose: "诊断", refine: "改进", revision: "修订", stageCompleted: "已完成", stageCurrent: "当前",
    shellGuidance: "选择一个阶段，检查此文档的准备证据。", inspector: "检查器", summary: "摘要", evidence: "证据", artifacts: "产物",
    preparationRound: "准备轮次 {current}/{total}", roundOption: "轮次 {number}", startsOriginal: "从原始版本开始", startsRevision: "从修订 {number} 开始", chooseRound: "选择准备轮次",
    sourceObject: "来源对象", filename: "文件名", mediaType: "媒体类型", size: "大小", sha256: "SHA-256", observationComplete: "观察已完成", observationMeaning: "观察保留了来源，并生成提取视图和规范工作文档。", observeStageSubtitle: "捕获来源，并比较相互独立的提取视图。", observeGuideTitle: "观察阶段做什么", observeGuideInspect: "观察阶段捕获一个不可变来源，并分别运行 Docling 和 MarkItDown，以便比较各个提取器生成的结果。", observeGuideBoundary: "它将 DoclingDocument 保留为后续阶段使用的规范工作表示。观察阶段记录提取证据，但不判断或更改文档质量。", diagnosisGuideTitle: "如何阅读此结果", revisionGuideTitle: "修订阶段展示什么", observationStages: "提取结果", extractionView: "提取视图", extractorVersion: "版本 {version}", extractionAgreement: "提取一致性", extractorAgreement: "Docling 与 MarkItDown", normalizedViews: "规范化文本视图", equivalent: "等价", different: "不同", ready: "就绪", canonicalReady: "已为诊断和改进阶段准备好", normalizedEquivalent: "规范化后等价", normalizedDifferent: "规范化后不同", comparisonUnavailable: "比较不可用", extractionEvidence: "提取证据", statusSuccess: "成功", statusPartialSuccess: "部分成功", statusFailed: "失败", uploadPrivacy: "工作台显示来源元数据和提取产物，绝不显示或提供上传的原始文件。", diagnoseHandoff: "观察已准备好，可进行确定性的只读诊断。", continueDiagnosis: "继续诊断",
    diagnosisStageSubtitle: "固定规则识别需要关注的证据。", diagnosisReady: "诊断为只读操作", diagnosisReadyBody: "固定规则检查当前文档并记录证据。诊断不会更改来源、观察记录或当前修订。", diagnosisRulesReference: "这些预设规则概括了语料准备中常见且普遍适用的机械检查。打开右上角的“规则参考”可查看全部规则。", diagnosisNotRunTitle: "尚未运行诊断", diagnosisNotRunBody: "运行诊断后，此阶段记录才会发布。", noDiagnosisEvidenceTitle: "尚无诊断证据", noDiagnosisEvidenceBody: "诊断评估当前文档后，证据会显示在这里。", noDiagnosisArtifactsTitle: "尚无诊断产物", noDiagnosisArtifactsBody: "诊断产物会随诊断记录一起发布。", runDiagnosis: "运行诊断", diagnosisRunning: "正在运行诊断…", diagnosisCompleted: "诊断已完成", findingsCount: "{count} 个发现", noFindingsMeaning: "没有固定规则匹配，内容未更改。", findingEvidenceLimit: "发现表示一个固定机械规则匹配。它不是无效性或合规性裁决。", matchedRule: "命中的规则", ruleName: "规则名称", ruleIdentifier: "规则编号", whyItMatters: "为什么重要", availableNextStep: "可用的下一步", refineFinding: "检查支持的改进", severity: "严重性", unavailable: "不可用", notNeeded: "不需要", unavailablePrerequisite: "此阶段尚无已发布的前置记录。", noFindingsNotNeeded: "没有固定规则匹配，因此不需要改进或准备修订。诊断证据仍可查看。", refineNotNeededSubtitle: "本轮不需要受支持的改进。", revisionNotNeededSubtitle: "本轮不需要准备修订。", historicalReadOnly: "历史轮次 · 只读", readOnlyHistory: "只读历史", returnLatest: "返回最新轮次",
    refineStageSubtitle: "检查一项受支持的更改，并记录明确的决定。", refineReady: "改进阶段做什么", refineReadyBody: "改进阶段一次处理一个已选择的发现。它把该发现映射到一个确定性的改进器，预览准确更改，并记录明确的决定。只有批准提案后，基础文档才会产生新的准备修订。", sourceFinding: "来源发现", supportedRefiner: "支持的改进器", chooseFindingTitle: "选择一个发现", chooseFindingBody: "此诊断有多个受支持的发现。请返回诊断并选择要改进的发现。", returnToDiagnosis: "返回诊断", proposalStatus: "提案状态", proposalNotCreated: "尚未创建", proposalTemporary: "临时 · 编辑数：{count}", diagnosisSourceEvidenceTitle: "诊断是来源证据", proposalEvidenceTitle: "提案证据是临时状态", refineInspectorReady: "所选诊断发现是来源证据。目前尚无提案，也未更改文档。", diagnosisInspectorEvidence: "每个发现都在此不可变诊断记录中保留命中的规则、文档引用和捕获的证据。", noRefinementArtifactsTitle: "尚无已发布产物", noRefinementArtifacts: "只有记录批准或拒绝后，才会发布改进产物。", refineNoFindingsSummaryTitle: "不需要改进", refineNoFindingsSummaryBody: "诊断未发现本轮需要处理的受支持更改。", refineNoFindingsEvidenceTitle: "诊断结束了本轮流程", refineNoFindingsEvidenceBody: "零个发现表示没有需要检查或决定的提案。", refineNoFindingsArtifactsTitle: "没有改进产物", refineNoFindingsArtifactsBody: "未发布提案或决定记录。", revisionNoFindingsSummaryTitle: "不需要准备修订", revisionNoFindingsSummaryBody: "本轮没有可应用的已批准改进。", revisionNoFindingsEvidenceTitle: "没有修订证据", revisionNoFindingsEvidenceBody: "诊断是本轮最后发布的阶段。", revisionNoFindingsArtifactsTitle: "没有修订产物", revisionNoFindingsArtifactsBody: "未创建准备修订。", createProposal: "创建提案", proposalRunning: "正在创建提案…", proposedChange: "建议的更改", before: "更改前", after: "更改后", visibleWhitespace: "可见空白：· 空格、→ 制表符、↵ 换行", previousChange: "上一个更改", nextChange: "下一个更改", changePosition: "更改 {current}/{total}", changePositionShort: "{current}/{total}", structuralMovement: "结构移动", chooseDecision: "选择决定", decisionExplanationTitle: "为什么要记录决定？", decisionExplanationBody: "提案只是临时预览，尚未更改文档。记录“批准”或“拒绝”会把你的选择保存为不可变的改进记录。批准会创建准备修订；拒绝会保持基础文档不变。", decisionGuidance: "批准会创建一个不可变的准备修订。拒绝会保留当前文档且不创建新修订。", recordedDecision: "已记录的决定", diagnosisRelation: "诊断关系", baseRelation: "基础版本关系", derivationCheck: "派生修订", reversibilityCheck: "逆向重放", transformationCount: "转换数量", matched: "匹配", notChecked: "未检查", notApplicable: "不适用", approve: "批准", reject: "拒绝", recordDecision: "记录决定", decisionRunning: "正在记录决定…", approved: "已批准", rejected: "已拒绝", decisionApprovedBody: "批准的编辑已创建一个不可变准备修订。", decisionRejectedBody: "未创建准备修订。基础文档保持当前状态且未更改。", nextRevisionExplanationTitle: "为什么要查看准备修订？", nextRevisionExplanationBody: "批准已创建一个新的不可变修订。查看它可确认实际应用的更改、检查对比，并沿着保留的证据追溯到本次决定。", viewPreparedRevision: "查看准备修订", rejectedEvidence: "提案、人工决定和改进报告仍可检查。未应用正向或逆向转换。",
    revisionStageSubtitle: "检查不可变的准备结果及其证据。", revisionCreated: "已创建准备修订", revisionMeaning: "批准的更改生成了一个新的不可变准备修订。基础文档保持保留。", revisionEvidence: "修订阶段展示经批准的改进所生成的准备文档。使用修订历史、已应用比较和验证证据，将结果追溯到基础文档和对应决定。", revisionLineage: "修订谱系", original: "原始版本", revisionNumber: "修订 {number}", current: "当前版本", preparedRevision: "准备修订", appliedRefiner: "已应用的改进器", applied: "已应用", openAppliedComparison: "已应用比较", loadingAppliedComparison: "正在加载已应用比较…", optionalNextStep: "可选的下一步", nextRoundBody: "诊断准备修订，开始另一个“诊断 → 改进 → 修订”轮次。", startNextRound: "开始另一次诊断", rejectedRevisionNotNeeded: "已记录的决定拒绝了提案。只有批准的提案才会创建准备修订。", preservedEvidence: "已保留的不可变证据", forwardInverse: "正向和逆向证据已验证", loadingStage: "正在加载阶段证据…",
    lifecyclePrepublicationFailure: "操作在发布前失败。未创建记录，已接受的不可变来源保持不变。", retry: "重试", lifecyclePublishedRefreshFailed: "记录已发布，但工作区无法刷新。请保留当前已接受的视图并使用“刷新工作区”；不要重新运行生成操作。", lifecycleUnknown: "变更结果未知。工作台正在协调工作区，且不会重放操作。", staleToken: "操作令牌已更改并完成刷新；请再次点击以确认此操作。", lifecycleBusy: "另一个变更正在运行。请等待它达到终态。", decisionComplete: "此提案已有已记录的决定。", noCliNeeded: "浏览器可完成此生命周期；不需要 CLI 命令或目标 JSON。",
    inspectorSummary: "阶段指导和状态将在此显示。", inspectorEvidence: "已验证的支持证据将在此显示。", inspectorArtifacts: "已发布的产物将在此显示。",
    verified: "已验证", recordKind: "记录", auditStatus: "审计状态", observationStatus: "观察", extractorViews: "提取器视图", extractorSummary: "{successful}/{total} 成功", canonicalRepresentation: "规范表示", comparisonStatus: "比较状态", normalizedOutput: "规范化输出", diagnosisSubject: "诊断对象", diagnosisDerivation: "诊断派生关系", ruleset: "规则集", evidenceReferences: "证据引用", refinableFindings: "可改进的发现", bytes: "字节", artifactCount: "{count} 个产物", openArtifact: "打开产物", artifactReader: "产物阅读器", artifactRole: "产物角色", copyArtifact: "复制产物", copiedArtifact: "已复制产物。", copyFailed: "无法复制产物。", toggleWrap: "切换自动换行", showHtmlSource: "显示 HTML 源码", showHtmlReport: "显示格式化 HTML 报告", closeReader: "关闭产物阅读器", wrapped: "行自动换行", unwrapped: "行不换行", oversizedTitle: "产物过大，无法打开", oversizedBody: "工作台已验证此产物，但其 {size} 字节超过阅读器限制。内容未被截断。", readerFailure: "无法打开产物。", htmlReaderTitle: "已验证的项目生成 HTML 报告", htmlReaderDescription: "该报告与脚本、网络资源和导航隔离。", cliNoteStart: "可选：", cliNoteMiddle: "CLI 可以使用此已发布记录。运行", cliNoteEnd: "并参阅", cliNoteTail: "中的生命周期课程了解命令工作流。", pendingProposalEvidence: "此提案是临时状态。它尚未更改文档，也未发布记录。", corpusSummary: "语料库摘要", corpusMeaning: "此已验证语料库包含 {count} 个成员。语料库创建和执行仍通过 CLI 完成。", corpusTotals: "语料库总计", members: "成员", families: "文档系列", formats: "格式", findings: "发现", revisions: "修订", failures: "失败", memberMatrix: "成员证据", memberStatus: "{family} · {format} · {status}", noArtifactContent: "此阶段没有可用的已发布产物。",
    noDocuments: "没有文档", noCorpora: "暂无语料库", corpusEmptyStart: "使用", corpusEmptyEnd: "创建语料库，然后刷新此工作区。", addIntro: "请选择一条学习路径。工作台会选中文档并立即开始观察。",
    guidedPreparationTitle: "准备一个示例文档", recommended: "推荐", guidedPreparationDetail: "使用一个具有明确空白问题的示例，完成“观察 → 诊断 → 改进 → 修订”全流程。", sampleFile: "示例", startGuidedPreparation: "开始引导式准备",
    guidedInspectionTitle: "探索一个未匹配规则的文档", guidedInspectionDetail: "观察并诊断一份政策备忘录，了解“无发现”结果表示什么以及不表示什么。", startGuidedInspection: "开始引导式检查",
    ownDocumentTitle: "观察你自己的文档", ownDocumentDetail: "选择一个最大 32 MiB 的受支持文件。工作台显示其元数据和提取产物，但不渲染原始文件。", chooseDocument: "选择一个文档", uploadFormats: ".docx、.md、.pdf 或 .txt，最大 32 MiB", observeDocument: "观察此文档", observing: "已开始观察 {name}。",
    reactivated: "此来源已存在。已选择其文档；未创建新文档或观察记录。",
    refreshStarted: "正在刷新工作区。", refreshSuccess: "工作区已刷新。", refreshNoChange: "工作区已是最新状态。",
    refreshFailure: "刷新失败。已保留上次接受的工作区视图。", observeFailure: "无法开始观察。",
    observationBusy: "一个观察任务正在运行。请等待其完成后再添加文档。",
    observationPublishedRefreshFailed: "观察记录已发布，但工作区无法刷新。已保留上次接受的视图。请使用“刷新工作区”，不要再次运行观察。",
    observationStatusUnknown: "无法确认观察状态。工作台将进行协调；未重放任何操作。",
    observationWorkspaceReconciled: "重启后无法恢复观察结果。已协调接受的工作区；未重放任何操作。",
    ruleIntro: "发现表示一条固定规则已匹配。它是证据，不是自动裁决，也不是更改文档的授权。",
    credit: "一个可检查的文档准备工作台。", creatorCredit: "由 James Wei 创建", github: "GitHub 仓库",
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

Object.assign(catalogs.en, { revisionHistory: "Revision history" });
Object.assign(catalogs["zh-CN"], { revisionHistory: "修订历史" });
Object.assign(catalogs.en, {
  rejectedDecisionExplanationTitle: "What Reject preserves",
  rejectedDecisionExplanationBody: "Reject records your decision, keeps the proposal and refinement report available, and leaves the base document unchanged. No prepared revision or transformation is created.",
});
Object.assign(catalogs["zh-CN"], {
  rejectedDecisionExplanationTitle: "拒绝决定保留了什么",
  rejectedDecisionExplanationBody: "拒绝会记录你的决定，保留提案和改进报告，并保持基础文档不变。不会创建准备修订或转换。",
});
Object.assign(catalogs.en, {
  corpusOverview: "Corpus overview", corpusMemberCoverage: "Member coverage", corpusFamily: "Family",
  corpusCoverage: "Coverage", corpusExtraction: "Extraction", corpusFindingEvidence: "Finding evidence", corpusRevisionEvidence: "Revision evidence",
  corpusStatus: "Status", corpusComplete: "Complete", corpusPartial: "Partial", corpusFailed: "Failed", corpusNoFindings: "No findings",
  corpusFindingValue: "{findings} findings · {members} affected · {format}",
});
Object.assign(catalogs["zh-CN"], {
  corpusOverview: "语料库概览", corpusMemberCoverage: "成员覆盖情况", corpusFamily: "文档系列",
  corpusCoverage: "覆盖情况", corpusExtraction: "提取", corpusFindingEvidence: "发现证据", corpusRevisionEvidence: "修订证据",
  corpusStatus: "状态", corpusComplete: "完整", corpusPartial: "部分完成", corpusFailed: "失败", corpusNoFindings: "无发现",
  corpusFindingValue: "{findings} 个发现 · 影响 {members} 个成员 · {format}",
});

const state = { projection: null, locale: "en", selectedKind: null, selectedKey: null, stage: "observe", inspector: "summary", selectedRound: null, selectedFinding: null, details: new Map(), proposal: null, proposalIdentity: null, recordedProposal: null, recordedProposalKey: null, recordedProposalLoading: null, appliedProposal: null, appliedProposalLoading: null, appliedComparisonOpen: false, decisionSelection: null, decisionSubmitted: false, comparison: {index: 0}, reader: null, lifecyclePending: false, lifecycleReconciliationPending: false, lifecycleNotice: null, pendingLifecycleMutation: null, actionToken: null, initialFailure: false, activeObservationJobId: null, pendingReactivationKey: null, pendingTerminalToastKey: null, workspaceReconciliationPending: false };
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
function clearSelectionScopedState() { state.selectedFinding = null; state.proposal = null; state.proposalIdentity = null; state.recordedProposal = null; state.recordedProposalKey = null; state.recordedProposalLoading = null; state.appliedProposal = null; state.appliedProposalLoading = null; state.appliedComparisonOpen = false; state.decisionSelection = null; state.decisionSubmitted = false; state.comparison = {index: 0}; state.reader = null; }
function resetTransientLifecycle() { clearSelectionScopedState(); state.lifecycleNotice = null; }
function selectItem(kind, key) {
  if (state.lifecyclePending || state.lifecycleReconciliationPending) return;
  state.selectedKind = kind; state.selectedKey = key; state.stage = "observe"; state.selectedRound = null; resetTransientLifecycle(); render();
  hydrateSelectedStage().then(render).catch(() => render());
}
function detailFor(key) { return key ? state.details.get(key) || null : null; }
async function ensureDetail(key) {
  if (!key || !/^[0-9a-f]{64}$/.test(key) || state.details.has(key)) return detailFor(key);
  const detail = await fetchJSON(`${API_ROOT}/records/${key}`); state.details.set(key, detail); return detail;
}
async function hydrateRecordedProposal(item, round) {
  const refinementKey = round && round.refinement_record_key;
  if (state.stage !== "refine" || !refinementKey) { state.recordedProposal = null; state.recordedProposalKey = null; state.recordedProposalLoading = null; return; }
  if (state.recordedProposal && state.recordedProposalKey === refinementKey) return;
  const detail = detailFor(refinementKey); const descriptor = detail && (detail.artifacts || []).find((artifact) => artifact.role === "refinement-proposal" && artifact.availability === "AVAILABLE");
  if (!descriptor) { state.recordedProposal = null; state.recordedProposalKey = null; state.recordedProposalLoading = null; return; }
  const request = {documentKey: item.document_key, roundNumber: round.number, refinementKey}; state.recordedProposalLoading = request;
  try {
    const proposal = await loadAppliedProposal(refinementKey); const currentItem = selectedItem(); const currentRound = currentItem && state.selectedKind === "document" ? selectedRoundData(currentItem) : null;
    if (state.recordedProposalLoading !== request || state.selectedKey !== request.documentKey || state.stage !== "refine" || !currentRound || currentRound.number !== request.roundNumber || currentRound.refinement_record_key !== request.refinementKey) return;
    state.recordedProposal = proposal; state.recordedProposalKey = refinementKey;
  } catch (_) {
    if (state.recordedProposalLoading === request) { state.recordedProposal = null; state.recordedProposalKey = null; }
  } finally {
    if (state.recordedProposalLoading === request) state.recordedProposalLoading = null;
  }
}
function latestRound(item) { const rounds = item && Array.isArray(item.rounds) ? item.rounds : []; return rounds.length ? rounds[rounds.length - 1] : null; }
function canStartNextRound(item) { const round = latestRound(item); return Boolean(round && round.revision_record_key); }
function selectedRoundNumber(item) {
  const rounds = Array.isArray(item.rounds) ? item.rounds : [];
  const maximum = rounds.length + ((state.selectedRound === rounds.length + 1 && canStartNextRound(item)) ? 1 : 0);
  if (state.selectedRound === null) state.selectedRound = Math.max(1, rounds.length);
  state.selectedRound = Math.max(1, Math.min(state.selectedRound, Math.max(1, maximum)));
  return state.selectedRound;
}
function selectedRoundData(item) { const number = selectedRoundNumber(item); return (item.rounds || []).find((round) => round.number === number) || null; }
function latestViewNumber(item) { return Math.max(1, (item.rounds || []).length + (canStartNextRound(item) && state.selectedRound === (item.rounds || []).length + 1 ? 1 : 0)); }
function isHistoricalRound(item) { const round = selectedRoundData(item); return Boolean(round && round.number < (item.rounds || []).length); }
function isNoFindings(detail) { return Boolean(detail && detail.kind === "DIAGNOSIS" && detail.view.finding_total === 0); }
async function hydrateSelectedStage() {
  const item = selectedItem(); if (!item) return;
  if (state.selectedKind === "corpus") { await ensureDetail(item.record_key); return; }
  const round = selectedRoundData(item); const keys = new Set([item.observation_record_key]);
  if (round) { keys.add(round.base_record_key); keys.add(round.diagnosis_record_key); keys.add(round.refinement_record_key); }
  await Promise.all(Array.from(keys).filter(Boolean).map(ensureDetail));
  await hydrateRecordedProposal(item, round);
}

function navigationCard(item, kind) {
  const key = kind === "document" ? item.document_key : item.record_key;
  const name = kind === "document" ? item.source.name : item.title;
  const button = node("button", null, "navigation-card"); button.type = "button"; button.title = name;
  button.disabled = state.lifecyclePending || state.lifecycleReconciliationPending;
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
  if (!state.projection.corpora.length) {
    const empty = node("div", null, "corpus-empty");
    const guidance = node("p", null, "corpus-empty-guidance");
    guidance.append(`${t("corpusEmptyStart")} `, node("code", "corpus inspect", "terminal-token"), ` ${t("corpusEmptyEnd")}`);
    empty.append(node("p", t("noCorpora"), "card-meta"), guidance); elements.corpora.append(empty);
  }
}
function renderEmptyOrFailure() {
  clear(elements.workspaceState); elements.selected.hidden = true; elements.workspaceState.hidden = false;
  const card = node("div", null, "state-card");
  card.append(node("h2", t(state.initialFailure ? "loadFailureTitle" : "emptyTitle")));
  card.append(node("p", t(state.initialFailure ? "loadFailureBody" : "emptyBody")));
  if (!state.initialFailure) { const add = node("button", t("addDocument"), "primary-button"); add.type = "button"; add.addEventListener("click", () => openModal(elements.addModal)); card.append(add); }
  elements.workspaceState.append(card);
}
function labeledValue(label, value, className = "") {
  const row = node("div", null, `metadata-row ${className}`.trim()); const description = node("dd"); if (value && typeof value === "object" && (value.tagName || value.tag)) description.append(value); else description.textContent = String(value); row.append(node("dt", label), description); return row;
}
function actionButton(label, handler, className = "primary-button") {
  const button = node("button", label, className); button.type = "button"; button.disabled = state.lifecyclePending || state.lifecycleReconciliationPending; button.addEventListener("click", handler); return button;
}
function banner(title, body, tone = "success") { const box = node("div", null, "result-banner"); box.dataset.tone = tone; const heading = node("div", null, "result-banner-heading"); const icon = node("span", "!", "result-notification-icon"); icon.setAttribute("aria-hidden", "true"); heading.append(icon, node("strong", title)); box.append(heading, node("p", body)); return box; }
function learnerGuidance(title, ...paragraphs) { const guidance = node("aside", null, "learner-guidance"); const heading = node("div", null, "learner-heading"); const icon = node("span", "?", "learner-question-icon"); icon.setAttribute("aria-hidden", "true"); heading.append(icon, node("h3", title)); guidance.append(heading, ...paragraphs.map((paragraph) => node("p", paragraph))); return guidance; }
function extractorLabel(name) { return name === "docling" ? "Docling" : name === "markitdown" ? "MarkItDown" : String(name); }
function extractorStatusLabel(status) { const key = {SUCCESS: "statusSuccess", PARTIAL_SUCCESS: "statusPartialSuccess", FAILED: "statusFailed"}[status]; return key ? t(key) : String(status); }
function extractorStatus(status) {
  const values = {SUCCESS: ["✓", "statusSuccess"], PARTIAL_SUCCESS: ["!", "statusPartialSuccess"], FAILED: ["×", "statusFailed"]};
  const [icon, labelKey] = values[status] || ["?", null]; const label = labelKey ? t(labelKey) : String(status);
  const value = node("span", icon, "extractor-status"); value.dataset.status = status; value.title = label; value.setAttribute("aria-label", label); return value;
}
function compactHash(value) { return typeof value === "string" && value.length === 64 ? `${value.slice(0, 10)}…${value.slice(-8)}` : String(value || "—"); }
function hashNode(value) { const hash = node("span", compactHash(value), "compact-hash"); hash.title = value || ""; return hash; }
function formatSize(value) { return new Intl.NumberFormat(state.locale).format(Number(value) || 0); }
function sourceMetadata(source) {
  const group = node("section", null, "stage-section source-metadata"); group.append(node("h3", t("sourceObject")));
  const values = node("dl", null, "metadata-list");
  values.append(labeledValue(t("filename"), source.name || "—"), labeledValue(t("mediaType"), source.media_type || "—"), labeledValue(t("size"), `${formatSize(source.size)} ${t("bytes")}`));
  values.append(labeledValue(t("sha256"), hashNode(source.sha256), "hash-value")); group.append(values); return group;
}
function renderRoundContext(item) {
  clear(elements.roundContext); elements.roundContext.hidden = false;
  const current = selectedRoundNumber(item); const total = latestViewNumber(item); const rounds = item.rounds || [];
  const copy = node("div", null, "round-copy"); copy.append(node("strong", t("preparationRound", {current, total})), node("span", current === 1 ? t("startsOriginal") : t("startsRevision", {number: current - 1})));
  elements.roundContext.append(copy);
  if (rounds.length > 1 || (current > rounds.length && canStartNextRound(item))) {
    const picker = node("select", null, "round-picker"); picker.setAttribute("aria-label", t("chooseRound"));
    const count = Math.max(rounds.length, current); for (let number = 1; number <= count; number += 1) { const option = node("option", t("roundOption", {number})); option.value = String(number); option.selected = number === current; picker.append(option); }
    picker.disabled = state.lifecyclePending || state.lifecycleReconciliationPending; picker.addEventListener("change", () => { state.selectedRound = Number(picker.value); resetTransientLifecycle(); render(); hydrateSelectedStage().then(render).catch(() => render()); }); elements.roundContext.append(picker);
  }
}
function stageOutcome(item, round, stage) {
  const diagnosis = detailFor(round && round.diagnosis_record_key);
  const refinement = detailFor(round && round.refinement_record_key);
  if (stage === "observe") return "stageCompleted";
  if (stage === "diagnose") return round && round.diagnosis_record_key ? "stageCompleted" : (state.stage === stage ? "stageCurrent" : null);
  if (stage === "refine") {
    if (round && round.refinement_record_key) {
      if (refinement && refinement.view && refinement.view.decision === "APPROVED") return "approved";
      if (refinement && refinement.view && refinement.view.decision === "REJECTED") return "rejected";
      return "stageCompleted";
    }
    if (isNoFindings(diagnosis)) return "notNeeded";
    if (!round || !round.diagnosis_record_key) return "unavailable";
    return state.stage === stage ? "stageCurrent" : null;
  }
  if (round && round.revision_record_key) return "stageCompleted";
  if (isNoFindings(diagnosis) || (refinement && refinement.view && refinement.view.decision === "REJECTED")) return "notNeeded";
  if (!round || !round.refinement_record_key) return "unavailable";
  return state.stage === stage ? "stageCurrent" : null;
}
function renderStageStepper(item, round) {
  const historical = isHistoricalRound(item);
  elements.stepper.querySelectorAll("li").forEach((entry) => {
    const current = entry.dataset.stage === state.stage;
    const outcome = stageOutcome(item, round, entry.dataset.stage);
    entry.dataset.current = String(current);
    entry.dataset.outcome = outcome || "";
    const status = entry.querySelector('[data-stage-status="label"]');
    if (status) { clear(status); status.textContent = ""; status.hidden = !outcome && !historical; if (outcome) status.append(node("span", t(outcome), "stage-outcome")); if (historical) status.append(node("span", t("readOnlyHistory"), "stage-history-badge")); }
  });
}
function renderUnavailable(reasonKey, titleKey = "unavailable") { elements.central.append(banner(t(titleKey), t(reasonKey), "neutral")); }
function renderObserve(item, detail) {
  elements.stageHeading.textContent = t("observe"); elements.stageGuidance.textContent = t("observeStageSubtitle");
  if (!detail) { elements.central.append(node("p", t("loadingStage"))); return; }
  elements.central.append(banner(t("observationComplete"), t("observationMeaning")), learnerGuidance(t("observeGuideTitle"), t("observeGuideInspect"), t("observeGuideBoundary")));
  const stages = node("section", null, "stage-section extraction-results"); stages.append(node("h3", t("observationStages"))); const views = node("div", null, "extractor-grid");
  for (const extractor of detail.view.extractors || []) { const card = node("article", null, "extractor-result-card"); const heading = node("div", null, "extractor-result-heading"); const copy = node("div"); copy.append(node("span", t("extractionView"), "eyebrow"), node("strong", extractorLabel(extractor.name)), node("small", t("extractorVersion", {version: extractor.version}))); const status = node("div", null, "extractor-result-status"); status.append(extractorStatus(extractor.status), node("span", extractorStatusLabel(extractor.status))); heading.append(copy, status); card.append(heading); views.append(card); }
  const comparison = detail.view.comparison || {}; const normalized = comparison.docling_minus_markitdown && comparison.docling_minus_markitdown.normalized_equal; const comparisonLabel = comparison.status === "COMPLETE" ? t(normalized ? "normalizedEquivalent" : "normalizedDifferent") : t("comparisonUnavailable"); const comparisonCardLabel = comparison.status === "COMPLETE" ? t(normalized ? "equivalent" : "different") : t("comparisonUnavailable"); const comparisonTone = comparison.status !== "COMPLETE" ? "UNKNOWN" : normalized === true ? "SUCCESS" : "PARTIAL_SUCCESS"; const comparisonIcon = node("span", comparisonTone === "SUCCESS" ? "✓" : comparisonTone === "PARTIAL_SUCCESS" ? "!" : "?", "extractor-status"); comparisonIcon.dataset.status = comparisonTone; comparisonIcon.title = comparisonLabel; comparisonIcon.setAttribute("aria-label", comparisonLabel); const comparisonCard = node("article", null, "extractor-result-card"); const comparisonHeading = node("div", null, "extractor-result-heading"); const comparisonCopy = node("div"); comparisonCopy.append(node("span", t("extractionAgreement"), "eyebrow"), node("strong", t("extractorAgreement")), node("small", t("normalizedViews"))); const comparisonResult = node("div", null, "extractor-result-status"); comparisonResult.append(comparisonIcon, node("span", comparisonCardLabel)); comparisonHeading.append(comparisonCopy, comparisonResult); comparisonCard.append(comparisonHeading); views.append(comparisonCard); stages.append(views);
  const canonicalLabel = t("canonicalReady"); const canonicalIcon = node("span", "✓", "extractor-status"); canonicalIcon.dataset.status = "SUCCESS"; canonicalIcon.title = canonicalLabel; canonicalIcon.setAttribute("aria-label", canonicalLabel); const canonicalCard = node("article", null, "extractor-result-card"); const canonicalHeading = node("div", null, "extractor-result-heading"); const canonicalCopy = node("div"); canonicalCopy.append(node("span", t("canonicalRepresentation"), "eyebrow"), node("strong", detail.view.docling_document.name), node("small", t("extractorVersion", {version: detail.view.docling_document.version}))); const canonicalResult = node("div", null, "extractor-result-status"); canonicalResult.append(canonicalIcon, node("span", t("ready"))); canonicalHeading.append(canonicalCopy, canonicalResult); canonicalCard.append(canonicalHeading); views.append(canonicalCard); elements.central.append(stages, sourceMetadata(detail.view.source));
  if (detail.view.source && !GUIDED_SOURCE_KEYS.has(detail.view.source.key)) elements.central.append(node("p", t("uploadPrivacy"), "privacy-note"));
  const next = node("section", null, "action-guidance"); next.append(node("h3", t("availableNextStep")), node("p", t("diagnoseHandoff")), actionButton(t("continueDiagnosis"), () => changeStage("diagnose"))); elements.central.append(next);
}
function findingCard(item, round, finding, actionable) {
  const card = node("article", null, "finding-card"); card.dataset.severity = finding.severity;
  const metadata = node("section", null, "finding-rule-metadata"); metadata.append(node("h4", t("matchedRule")));
  const values = node("dl", null, "finding-rule-values");
  for (const [label, value, className] of [[t("ruleName"), finding.summary, "rule-code"], [t("ruleIdentifier"), finding.rule_id, "rule-code"], [t("severity"), finding.severity, "severity-value"]]) {
    const entry = node("div"); entry.append(node("dt", label), node("dd", value, className)); values.append(entry);
  }
  metadata.append(values); card.append(node("h3", t(`rule.${finding.rule_id}.name`)), metadata);
  const why = learnerGuidance(t("whyItMatters"), t(`rule.${finding.rule_id}.about`)); why.className += " why-card"; card.append(why);
  if (actionable) { const next = node("section", null, "action-guidance"); next.append(node("h4", t("availableNextStep")), node("p", `${t("supportedRefiner")}: ${t(`refiner.${finding.refiner.refiner_id}`)} · ${finding.refiner.refiner_id}`), actionButton(t("refineFinding"), () => { state.selectedFinding = {documentKey: item.document_key, roundNumber: round.number, diagnosisKey: round.diagnosis_record_key, findingId: finding.finding_id}; changeStage("refine"); })); card.append(next); }
  return card;
}
function renderDiagnosis(item, round, detail) {
  elements.stageHeading.textContent = t("diagnose");
  if (!round || !round.diagnosis_record_key) {
    elements.stageGuidance.textContent = t("diagnosisStageSubtitle"); elements.central.append(learnerGuidance(t("diagnosisReady"), t("diagnosisReadyBody"), t("diagnosisRulesReference")));
    if (state.lifecycleNotice) elements.central.append(banner(t(state.lifecycleNotice.title), t(state.lifecycleNotice.body), state.lifecycleNotice.tone));
    if (state.lifecycleNotice && state.lifecycleNotice.title === "lifecyclePublishedRefreshFailed") return;
    elements.central.append(actionButton(state.lifecyclePending ? t("diagnosisRunning") : t(state.lifecycleNotice && state.lifecycleNotice.title === "lifecyclePrepublicationFailure" ? "retry" : "runDiagnosis"), () => runDiagnosis(item), "primary-button")); return;
  }
  if (!detail) { elements.central.append(node("p", t("loadingStage"))); return; }
  elements.stageGuidance.textContent = t("diagnosisStageSubtitle");
  const count = detail.view.finding_total; elements.central.append(banner(t("diagnosisCompleted"), count === 0 ? t("noFindingsMeaning") : t("findingsCount", {count})));
  if (count === 0) return;
  else { elements.central.append(learnerGuidance(t("diagnosisGuideTitle"), t("findingEvidenceLimit"), t("diagnosisRulesReference"))); for (const finding of detail.view.findings) elements.central.append(findingCard(item, round, finding, !isHistoricalRound(item) && finding.proposal_action.status === "AVAILABLE")); }
}
function visibleWhitespace(value) { return String(value).replace(/ /g, "·").replace(/\t/g, "→").replace(/\r?\n/g, "↵\n"); }
function comparisonValue(edit, side, ruleId) {
  const value = edit[side]; if (edit.target && edit.target.field === "content_layer") {
    const membership = value || {}; return `${membership.content_layer || "—"} · ${membership.body_index ?? membership.furniture_index ?? "—"}`;
  }
  return ruleId === "D009" ? visibleWhitespace(value) : String(value);
}
function comparisonSegments(edit, side, ruleId) {
  if (edit.target && edit.target.field === "content_layer") return [{text: comparisonValue(edit, side, ruleId), changed: false}];
  const before = String(edit.before ?? ""); const after = String(edit.after ?? ""); const value = side === "before" ? before : after; const other = side === "before" ? after : before;
  if (ruleId === "D009") {
    const tokens = value.match(/\s+|[^\s]+/g) || []; const otherTokens = other.match(/\s+|[^\s]+/g) || [];
    const aligned = tokens.length === otherTokens.length && tokens.every((token, index) => /\s/.test(token) || token === otherTokens[index]);
    if (aligned) return tokens.map((token, index) => ({text: visibleWhitespace(token), changed: token !== otherTokens[index]}));
  }
  let prefix = 0; while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0; while (suffix < before.length - prefix && suffix < after.length - prefix && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix += 1;
  const end = value.length - suffix; const format = (part) => ruleId === "D009" ? visibleWhitespace(part) : part;
  return [{text: format(value.slice(0, prefix)), changed: false}, {text: format(value.slice(prefix, end)), changed: true}, {text: format(value.slice(end)), changed: false}].filter((part) => part.text.length);
}
function comparisonPre(edit, side, ruleId) {
  const pre = node("pre"); for (const segment of comparisonSegments(edit, side, ruleId)) pre.append(segment.changed ? node("mark", segment.text, "change-mark") : node("span", segment.text, "comparison-text")); return pre;
}
function comparisonPanes(edit, ruleId) {
  const panes = node("div", null, "comparison-panes"); for (const side of ["before", "after"]) { const pane = node("section", null, "comparison-pane"); pane.append(node("h4", t(side)), comparisonPre(edit, side, ruleId)); panes.append(pane); } return panes;
}
function comparisonComponent(viewModel) {
  const edits = viewModel.edits || []; const current = Math.min(state.comparison.index, Math.max(0, edits.length - 1)); state.comparison.index = current; const edit = edits[current] || {before: "", after: "", target: {}};
  const shell = node("section", null, "comparison-shell"); shell.dataset.mode = viewModel.mode; if (viewModel.title) shell.append(node("h3", viewModel.title));
  const context = node("div", null, "comparison-context"); let hasContext = false;
  if (viewModel.mode !== "proposal") { context.append(node("strong", t(`rule.${viewModel.ruleId}.name`)), node("span", `${viewModel.ruleId} → ${viewModel.refinerId}`)); hasContext = true; }
  if (viewModel.ruleId === "D009") { context.append(node("span", t("visibleWhitespace"))); hasContext = true; }
  if (edit.target && edit.target.field === "content_layer") { context.append(node("span", t("structuralMovement"))); hasContext = true; }
  if (hasContext) shell.append(context); shell.append(comparisonPanes(edit, viewModel.ruleId));
  const navigation = node("div", null, "comparison-navigation"); const previous = actionButton("←", () => { state.comparison.index = Math.max(0, current - 1); renderSelected(); }, "icon-button"); previous.title = t("previousChange"); previous.setAttribute("aria-label", t("previousChange")); previous.disabled = current === 0 || state.lifecyclePending; const next = actionButton("→", () => { state.comparison.index = Math.min(edits.length - 1, current + 1); renderSelected(); }, "icon-button"); next.title = t("nextChange"); next.setAttribute("aria-label", t("nextChange")); next.disabled = current >= edits.length - 1 || state.lifecyclePending; navigation.append(previous, node("span", t("changePositionShort", {current: current + 1, total: Math.max(1, edits.length)})), next); navigation.setAttribute("aria-label", t("changePosition", {current: current + 1, total: Math.max(1, edits.length)})); shell.append(navigation); return shell;
}
function proposalFinding(item, round) {
  const diagnosis = round ? detailFor(round.diagnosis_record_key) : null; if (!diagnosis) return null;
  if (state.proposal) return diagnosis.view.findings.find((finding) => finding.finding_id === state.proposal.finding.finding_id) || null;
  const selected = state.selectedFinding;
  if (selected && selected.documentKey === item.document_key && selected.roundNumber === round.number && selected.diagnosisKey === round.diagnosis_record_key) {
    const finding = diagnosis.view.findings.find((item) => item.finding_id === selected.findingId && item.proposal_action.status === "AVAILABLE"); if (finding) return finding;
  }
  state.selectedFinding = null;
  const actionable = diagnosis.view.findings.filter((finding) => finding.proposal_action.status === "AVAILABLE"); return actionable.length === 1 ? actionable[0] : null;
}
function renderDecisionGuidance() {
  const guidance = node("section", null, "action-guidance decision-guidance"); guidance.append(node("h3", t("availableNextStep")), node("p", t("decisionGuidance")));
  const choices = node("div", null, "decision-choices");
  for (const [decision, icon, label] of [["approve", "✓", t("approve")], ["reject", "×", t("reject")]]) {
    const button = actionButton(icon, () => { state.decisionSelection = decision; renderSelected(); }, "decision-choice"); button.title = label; button.setAttribute("aria-label", label); button.setAttribute("aria-pressed", String(state.decisionSelection === decision)); choices.append(button);
  }
  const record = actionButton(state.lifecyclePending ? t("decisionRunning") : t("recordDecision"), recordDecision); record.disabled = !state.decisionSelection || state.lifecyclePending || state.lifecycleReconciliationPending; guidance.append(choices, record); return guidance;
}
function refinementMap(finding, proposalAction = null, directAction = false) {
  const map = node("section", null, "refinement-map"); if (proposalAction) map.className += " with-action";
  const source = node("div", null, "refinement-map-item");
  source.append(node("span", t("sourceFinding"), "eyebrow"), node("strong", t(`rule.${finding.rule_id}.name`)), node("code", `${finding.rule_id} · ${finding.summary}`));
  const refiner = node("div", null, "refinement-map-item");
  refiner.append(node("span", t("supportedRefiner"), "eyebrow"), node("strong", t(`refiner.${finding.refiner.refiner_id}`)), node("code", `${finding.refiner.refiner_id} · ${finding.refiner.name}`));
  map.append(source); if (proposalAction) { const action = directAction ? proposalAction : node("div", null, "refinement-map-action"); if (!directAction) action.append(proposalAction); map.append(action); } map.append(refiner); return map;
}
function renderRefine(item, round, diagnosis, refinement) {
  elements.stageHeading.textContent = t("refine");
  elements.stageGuidance.textContent = t("refineStageSubtitle");
  if (!round || !round.diagnosis_record_key) { const previous = latestRound(item); const noFindings = previous && isNoFindings(detailFor(previous.diagnosis_record_key)); if (noFindings) elements.stageGuidance.textContent = t("refineNotNeededSubtitle"); renderUnavailable(noFindings ? "noFindingsNotNeeded" : "unavailablePrerequisite", noFindings ? "notNeeded" : "unavailable"); return; }
  if (!diagnosis) { elements.central.append(node("p", t("loadingStage"))); return; }
  if (isNoFindings(diagnosis)) { elements.stageGuidance.textContent = t("refineNotNeededSubtitle"); renderUnavailable("noFindingsNotNeeded", "notNeeded"); return; }
  if (refinement) {
    const approved = refinement.view.decision === "APPROVED"; const finding = diagnosis.view.findings.find((candidate) => candidate.finding_id === refinement.view.proposal.finding_id);
    if (!finding) { elements.central.append(banner(t(approved ? "approved" : "rejected"), t(approved ? "decisionApprovedBody" : "decisionRejectedBody"))); return; }
    const proposalAction = actionButton(t("createProposal"), () => {}); proposalAction.disabled = true;
    elements.central.append(learnerGuidance(t("refineReady"), t("refineReadyBody")), refinementMap(finding, proposalAction));
    const recordedProposal = state.recordedProposal || state.proposal;
    if (recordedProposal) elements.central.append(comparisonComponent({mode: "proposal", title: t("proposedChange"), edits: recordedProposal.edits, ruleId: recordedProposal.finding.rule_id, refinerId: recordedProposal.refiner.refiner_id}));
    else elements.central.append(node("p", t("loadingStage")));
    const outcome = banner(t(approved ? "approved" : "rejected"), t(approved ? "decisionApprovedBody" : "decisionRejectedBody")); outcome.dataset.decisionOutcome = "true"; elements.central.append(outcome);
    if (approved) { const next = node("section", null, "action-guidance"); next.append(node("h3", t("availableNextStep")), node("p", t("decisionApprovedBody")), actionButton(t("viewPreparedRevision"), () => changeStage("revision"))); elements.central.append(learnerGuidance(t("nextRevisionExplanationTitle"), t("nextRevisionExplanationBody")), next); }
    else elements.central.append(learnerGuidance(t("rejectedDecisionExplanationTitle"), t("rejectedDecisionExplanationBody")));
    return;
  }
  const finding = proposalFinding(item, round); if (!finding) {
    const actionable = diagnosis.view.findings.filter((candidate) => candidate.proposal_action.status === "AVAILABLE");
    if (actionable.length > 1) { elements.stageGuidance.textContent = t("chooseFindingBody"); elements.central.append(learnerGuidance(t("chooseFindingTitle"), t("chooseFindingBody")), actionButton(t("returnToDiagnosis"), () => changeStage("diagnose"))); return; }
    renderUnavailable("unavailablePrerequisite"); return;
  }
  if (isHistoricalRound(item)) { elements.central.append(learnerGuidance(t("refineReady"), t("refineReadyBody")), refinementMap(finding)); return; }
  let proposalAction = null;
  if (!(state.lifecycleNotice && state.lifecycleNotice.title === "lifecyclePublishedRefreshFailed")) {
    proposalAction = actionButton(state.lifecyclePending ? t("proposalRunning") : t(state.lifecycleNotice && state.lifecycleNotice.title === "lifecyclePrepublicationFailure" ? "retry" : "createProposal"), () => createProposal(round, finding)); proposalAction.disabled = Boolean(state.proposal) || state.lifecyclePending || state.lifecycleReconciliationPending;
  }
  elements.central.append(learnerGuidance(t("refineReady"), t("refineReadyBody")), refinementMap(finding, proposalAction));
  if (state.lifecycleNotice) elements.central.append(banner(t(state.lifecycleNotice.title), t(state.lifecycleNotice.body), state.lifecycleNotice.tone));
  if (state.lifecycleNotice && state.lifecycleNotice.title === "lifecyclePublishedRefreshFailed") return;
  if (state.decisionSubmitted) return;
  if (!state.proposal) return;
  elements.central.append(comparisonComponent({mode: "proposal", title: t("proposedChange"), edits: state.proposal.edits, ruleId: state.proposal.finding.rule_id, refinerId: state.proposal.refiner.refiner_id}), learnerGuidance(t("decisionExplanationTitle"), t("decisionExplanationBody")), renderDecisionGuidance());
}
async function loadAppliedProposal(refinementKey) {
  const detail = await ensureDetail(refinementKey); const descriptor = (detail.artifacts || []).find((item) => item.role === "refinement-proposal"); if (!descriptor) return null;
  const proposal = await fetchJSON(`${API_ROOT}/artifacts/${descriptor.artifact_key}`); return {edits: proposal.forward_edits, finding: proposal.finding, refiner: proposal.refiner};
}
async function toggleAppliedComparison(round) {
  state.appliedComparisonOpen = !state.appliedComparisonOpen; state.comparison = {index: 0}; renderSelected();
  if (!state.appliedComparisonOpen || state.appliedProposal || state.appliedProposalLoading) return;
  const request = {documentKey: state.selectedKey, stage: state.stage, roundNumber: round.number, refinementKey: round.refinement_record_key}; state.appliedProposalLoading = request; renderSelected();
  const proposal = await loadAppliedProposal(request.refinementKey); const currentItem = selectedItem(); const currentRound = currentItem && state.selectedKind === "document" ? selectedRoundData(currentItem) : null;
  if (state.appliedProposalLoading !== request || state.selectedKey !== request.documentKey || state.stage !== "revision" || !currentRound || currentRound.number !== request.roundNumber || currentRound.refinement_record_key !== request.refinementKey) return;
  state.appliedProposalLoading = null; state.appliedProposal = proposal; renderSelected();
}
function revisionHistory(item, selected) {
  const history = node("section", null, "revision-lineage"); history.append(node("h3", t("revisionHistory"))); const path = node("div", null, "lineage-path"); const original = node("div", null, "lineage-node lineage-origin"); original.append(node("span", null, "lineage-marker"), node("span", t("original"), "lineage-label")); path.append(original); const revisions = (item.rounds || []).filter((round) => round.revision_record_key); const currentRevision = revisions.length ? revisions[revisions.length - 1].number : null;
  for (const round of revisions) { path.append(node("span", "→", "lineage-connector")); const label = node("button", null, "lineage-node"); label.type = "button"; label.disabled = state.lifecyclePending || state.lifecycleReconciliationPending; label.setAttribute("aria-current", String(round.number === currentRevision)); const copy = node("span", null, "lineage-copy"); copy.append(node("span", t("revisionNumber", {number: round.number}), "lineage-label")); if (round.number === currentRevision) copy.append(node("span", t("current"), "lineage-current")); label.append(node("span", null, "lineage-marker"), copy); label.addEventListener("click", () => { state.selectedRound = round.number; state.stage = "revision"; resetTransientLifecycle(); render(); hydrateSelectedStage().then(render); }); path.append(label); }
  history.append(path); return history;
}
function renderRevision(item, round, refinement) {
  elements.stageHeading.textContent = t("revision");
  elements.stageGuidance.textContent = t("revisionStageSubtitle");
  if (!round || !round.diagnosis_record_key) { renderUnavailable("unavailablePrerequisite"); return; }
  const diagnosis = detailFor(round.diagnosis_record_key); if (isNoFindings(diagnosis)) { elements.stageGuidance.textContent = t("revisionNotNeededSubtitle"); renderUnavailable("noFindingsNotNeeded", "notNeeded"); return; }
  if (!round.revision_record_key) { const rejected = refinement && refinement.view.decision === "REJECTED"; renderUnavailable(rejected ? "rejectedRevisionNotNeeded" : "unavailablePrerequisite", rejected ? "notNeeded" : "unavailable"); return; }
  if (!refinement) { elements.central.append(node("p", t("loadingStage"))); return; }
  elements.central.append(banner(t("revisionCreated"), t("revisionMeaning")), learnerGuidance(t("revisionGuideTitle"), t("revisionEvidence")), revisionHistory(item, round.number));
  const appliedFinding = diagnosis && diagnosis.view.findings.find((finding) => finding.finding_id === refinement.view.proposal.finding_id);
  if (appliedFinding) { const indicator = node("span", null, "applied-map-state"); indicator.append(node("span", "✓", "applied-map-icon"), node("strong", t("applied"))); const action = node("div", null, "refinement-map-action applied-map-action"); action.append(node("span", null, "applied-connector"), indicator, node("span", null, "applied-connector applied-connector-end")); elements.central.append(refinementMap({...appliedFinding, refiner: refinement.view.proposal.refiner}, action, true)); }
  const disclosure = node("section", null, "comparison-disclosure"); const toggle = actionButton(null, () => toggleAppliedComparison(round), "comparison-disclosure-toggle"); toggle.setAttribute("aria-expanded", String(state.appliedComparisonOpen)); toggle.append(node("span", state.appliedComparisonOpen ? "▾" : "▸", "disclosure-icon"), node("span", t("openAppliedComparison")), node("span", null, "disclosure-line")); disclosure.append(toggle);
  if (state.appliedComparisonOpen && state.appliedProposal) disclosure.append(comparisonComponent({mode: "applied", title: null, edits: state.appliedProposal.edits, ruleId: state.appliedProposal.finding.rule_id, refinerId: state.appliedProposal.refiner.refiner_id}));
  else if (state.appliedComparisonOpen && state.appliedProposalLoading) disclosure.append(node("p", t("loadingAppliedComparison")));
  elements.central.append(disclosure);
  if (!isHistoricalRound(item) && round.number === (item.rounds || []).length) { const next = node("section", null, "action-guidance optional-next"); next.append(node("h3", t("optionalNextStep")), node("p", t("nextRoundBody")), actionButton(t("startNextRound"), () => { state.selectedRound = round.number + 1; state.stage = "diagnose"; resetTransientLifecycle(); render(); })); elements.central.append(next); }
}
function selectedDetail(item, round) {
  if (state.selectedKind === "corpus") return detailFor(item.record_key);
  if (state.stage === "observe") return detailFor(item.observation_record_key);
  if (!round) return null;
  if (state.stage === "diagnose") return detailFor(round.diagnosis_record_key);
  return detailFor(round.refinement_record_key || round.diagnosis_record_key);
}
function artifactMetadata(descriptor) {
  const values = node("dl", null, "metadata-list artifact-metadata");
  values.append(labeledValue(t("artifactRole"), descriptor.role), labeledValue(t("mediaType"), descriptor.media_type), labeledValue(t("size"), `${formatSize(descriptor.size)} ${t("bytes")}`), labeledValue(t("sha256"), hashNode(descriptor.sha256), "hash-value"));
  return values;
}
function iconControl(icon, label, handler, pressed = null) {
  const button = actionButton(icon, handler, "icon-button reader-control"); button.title = label; button.setAttribute("aria-label", label); if (pressed !== null) button.setAttribute("aria-pressed", String(pressed)); return button;
}
function artifactList(detail) {
  const list = node("div", null, "artifact-list");
  for (const descriptor of detail.artifacts || []) {
    const row = node("article", null, "artifact-row"); const copy = node("div", null, "artifact-copy"); copy.append(node("strong", descriptor.role), node("span", `${descriptor.media_type} · ${formatSize(descriptor.size)} ${t("bytes")}`), hashNode(descriptor.sha256));
    const open = iconControl("↗", `${t("openArtifact")}: ${descriptor.role}`, () => openArtifact(descriptor)); open.dataset.artifactKey = descriptor.artifact_key; row.append(copy, open); list.append(row);
  }
  if (!(detail.artifacts || []).length) list.append(node("p", t("noArtifactContent")));
  return list;
}
async function copyReaderContent() {
  if (!state.reader || typeof state.reader.content !== "string") return;
  try { await navigator.clipboard.writeText(state.reader.content); elements.polite.textContent = ""; elements.polite.textContent = t("copiedArtifact"); showToast(t("copiedArtifact"), "success"); }
  catch (_) { showToast(t("copyFailed"), "failure"); }
}
function closeReader() { const key = state.reader ? state.reader.descriptor.artifact_key : null; state.reader = null; renderSelected(); if (key) { const target = elements.inspectorPanel.querySelector(`[data-artifact-key="${key}"]`); if (target) target.focus(); } }
async function openArtifact(descriptor) {
  const item = selectedItem(); const round = item && state.selectedKind === "document" ? selectedRoundData(item) : null; const detail = item ? selectedDetail(item, round) : null;
  const stylesheet = descriptor.media_type === "text/html" && detail ? (detail.artifacts || []).find((item) => item.role === "corpus-stylesheet" && item.availability === "AVAILABLE") : null;
  const request = {descriptor, content: null, stylesheet: null, loading: descriptor.availability !== "TOO_LARGE", oversized: descriptor.availability === "TOO_LARGE", error: null, wrap: true, htmlSource: false, focusReader: true, selection: {kind: state.selectedKind, key: state.selectedKey, stage: state.stage, round: state.selectedRound}}; state.reader = request; renderSelected();
  if (request.oversized) return;
  try { const [content, stylesheetContent] = await Promise.all([fetchArtifact(descriptor), stylesheet ? fetchArtifact(stylesheet) : null]); if (state.reader !== request) return; request.content = content; request.stylesheet = stylesheetContent; request.loading = false; request.focusReader = true; renderSelected(); }
  catch (error) { if (state.reader !== request) return; request.loading = false; request.error = error.code || "UNKNOWN"; request.focusReader = true; renderSelected(); }
}
function isolatedHtml(content, stylesheet = "") {
  const policy = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; navigate-to 'none'; base-uri 'none'";
  const documentContent = String(content).replace(/<link\b[^>]*>/gi, "").replace(/\s+href=(['"])[^'"]*\1/gi, "");
  const protections = `<meta http-equiv="Content-Security-Policy" content="${policy}"><style>${stylesheet}</style>`;
  return /<head(?:\s[^>]*)?>/i.test(documentContent) ? documentContent.replace(/<head((?:\s[^>]*)?)>/i, `<head$1>${protections}`) : `<!doctype html><html><head>${protections}</head><body>${documentContent}</body></html>`;
}
function comparisonArtifactView(reader) {
  if (reader.descriptor.role !== "refinement-proposal" || typeof reader.content !== "string") return null;
  try {
    const value = JSON.parse(reader.content); if (!Array.isArray(value.forward_edits) || !value.finding || !value.refiner) return null;
    const applied = state.stage === "revision"; return {mode: applied ? "applied" : "artifact-proposal", title: t(applied ? "openAppliedComparison" : "proposedChange"), edits: value.forward_edits, ruleId: value.finding.rule_id, refinerId: value.refiner.refiner_id};
  } catch (_) { return null; }
}
function renderArtifactReader() {
  const reader = state.reader; const descriptor = reader.descriptor;
  const comparisonView = comparisonArtifactView(reader);
  const shell = node("section", null, "artifact-reader"); const heading = node("div", null, "reader-heading"); const title = node("div"); const readerHeading = node("h2", descriptor.role); readerHeading.id = "artifact-reader-heading"; title.append(node("p", t("artifactReader"), "eyebrow"), readerHeading); const controls = node("div", null, "reader-controls");
  if (typeof reader.content === "string") { const wrap = iconControl("↵", `${t("toggleWrap")}: ${t(reader.wrap ? "wrapped" : "unwrapped")}`, () => { reader.wrap = !reader.wrap; reader.focusControl = "wrap"; renderSelected(); }, reader.wrap); wrap.dataset.readerControl = "wrap"; controls.append(wrap, iconControl("⧉", t("copyArtifact"), copyReaderContent)); }
  if (descriptor.media_type === "text/html" && typeof reader.content === "string") { const source = iconControl("</>", reader.htmlSource ? t("showHtmlReport") : t("showHtmlSource"), () => { reader.htmlSource = !reader.htmlSource; reader.focusControl = "html-source"; renderSelected(); }, reader.htmlSource); source.dataset.readerControl = "html-source"; controls.append(source); }
  const close = iconControl("×", t("closeReader"), closeReader); close.dataset.readerClose = "true"; controls.append(close); heading.append(title, controls); shell.append(heading, artifactMetadata(descriptor));
  if (reader.loading) shell.append(node("p", t("loadingStage")));
  else if (reader.oversized) shell.append(banner(t("oversizedTitle"), t("oversizedBody", {size: formatSize(descriptor.size)}), "neutral"));
  else if (reader.error) shell.append(banner(t("readerFailure"), reader.error, "failure"));
  else if (comparisonView) shell.append(comparisonComponent(comparisonView));
  else if (descriptor.media_type === "text/html" && !reader.htmlSource) { shell.append(node("p", t("htmlReaderDescription"), "privacy-note")); const frame = node("iframe"); frame.className = "html-report"; frame.title = t("htmlReaderTitle"); frame.setAttribute("sandbox", ""); frame.setAttribute("referrerpolicy", "no-referrer"); frame.setAttribute("tabindex", "-1"); frame.srcdoc = isolatedHtml(reader.content, reader.stylesheet); shell.append(frame); }
  else { let source = reader.content; if (descriptor.media_type === "application/json") { try { source = JSON.stringify(JSON.parse(source), null, 2); } catch (_) { /* verified bytes remain readable as source */ } } const pre = node("pre", source, `source-reader ${reader.wrap ? "is-wrapped" : "is-unwrapped"}`); shell.append(pre); }
  return shell;
}
function relationshipStateLabel(value) { return value ? t({MATCH: "matched", NOT_CHECKED: "notChecked", NOT_APPLICABLE: "notApplicable"}[value] || value) : "—"; }
function corpusStatusLabel(status) { return t({COMPLETE: "corpusComplete", PARTIAL: "corpusPartial", FAILED: "corpusFailed"}[status] || status); }
function corpusStatusGlyph(status) { return {COMPLETE: "✓", PARTIAL: "!", FAILED: "×"}[status] || "—"; }
function corpusName(value) { return String(value || "").replaceAll("-", " "); }
function corpusEvidenceGroup(title, values) { const group = node("section", null, "inspector-evidence-group"); group.append(node("h3", title)); const list = node("dl", null, "metadata-list"); for (const [label, value] of values) list.append(labeledValue(label, value)); group.append(list); return group; }
function cliInspectorNote() {
  const note = node("p", null, "inspector-note"); note.append(`${t("cliNoteStart")} `, node("code", "corpus", "terminal-token"), ` ${t("cliNoteMiddle")} `, node("code", "corpus --help", "terminal-token"), ` ${t("cliNoteEnd")} `, node("code", "learning/", "terminal-token"), ` ${t("cliNoteTail")}`); return note;
}
function inspectorState(title, body) { const value = node("section", null, "inspector-state"); value.append(node("strong", title), node("p", body)); return value; }
function renderInspector(item, round) {
  clear(elements.inspectorPanel);
  if (state.selectedKind === "corpus") {
    const detail = detailFor(item.record_key); if (!detail) { elements.inspectorPanel.append(node("p", t(state.inspector === "summary" ? "inspectorSummary" : state.inspector === "evidence" ? "inspectorEvidence" : "inspectorArtifacts"))); return; }
    if (state.inspector === "summary") { const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("recordKind"), detail.kind), labeledValue(t("corpusStatus"), corpusStatusLabel(item.status)), labeledValue(t("auditStatus"), detail.artifact_integrity), labeledValue(t("artifacts"), t("artifactCount", {count: detail.artifacts.length}))); elements.inspectorPanel.append(values); }
    else if (state.inspector === "evidence") {
      const aggregates = detail.view.aggregates || {}; const totals = detail.view.totals || {}; const byFamily = aggregates.by_family || []; const byFormat = aggregates.by_format || []; const extractors = aggregates.extractors || []; const findings = aggregates.findings || [];
      elements.inspectorPanel.append(corpusEvidenceGroup(t("corpusCoverage"), [[t("families"), new Intl.NumberFormat(state.locale).format(byFamily.length)], [t("formats"), new Intl.NumberFormat(state.locale).format(byFormat.length)], [t("members"), new Intl.NumberFormat(state.locale).format(totals.member_count || 0)]]));
      elements.inspectorPanel.append(corpusEvidenceGroup(t("corpusExtraction"), extractors.map((extractor) => [extractorLabel(extractor.name), `${extractor.available}/${extractor.available + extractor.unavailable}`])));
      elements.inspectorPanel.append(corpusEvidenceGroup(t("corpusFindingEvidence"), findings.length ? findings.map((finding) => [`${finding.rule_id} · ${corpusName(finding.family)}`, t("corpusFindingValue", {findings: new Intl.NumberFormat(state.locale).format(finding.finding_count), members: new Intl.NumberFormat(state.locale).format(finding.affected_member_count), format: String(finding.format).toUpperCase()})]) : [[t("findings"), t("corpusNoFindings")]]));
      elements.inspectorPanel.append(corpusEvidenceGroup(t("corpusRevisionEvidence"), [[t("revisions"), new Intl.NumberFormat(state.locale).format(totals.revision_count || 0)]]));
    } else elements.inspectorPanel.append(artifactList(detail));
    return;
  }
  const observation = state.selectedKind === "document" ? detailFor(item.observation_record_key) : null;
  if (state.selectedKind === "document" && state.stage === "observe" && observation) {
    const extractors = observation.view.extractors || []; const successful = extractors.filter((extractor) => extractor.status === "SUCCESS").length; const comparison = observation.view.comparison || {}; const normalized = comparison.docling_minus_markitdown && comparison.docling_minus_markitdown.normalized_equal;
    if (state.inspector === "summary") {
      const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("observationStatus"), t("stageCompleted")), labeledValue(t("extractorViews"), t("extractorSummary", {successful, total: extractors.length})), labeledValue(t("canonicalRepresentation"), `${observation.view.docling_document.name} · ${observation.view.docling_document.version}`), labeledValue(t("auditStatus"), observation.artifact_integrity), labeledValue(t("artifacts"), t("artifactCount", {count: observation.artifacts.length}))); elements.inspectorPanel.append(values);
    } else if (state.inspector === "evidence") {
      const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("sha256"), hashNode(observation.view.source.sha256), "hash-value")); for (const extractor of extractors) values.append(labeledValue(extractorLabel(extractor.name), `${extractorStatusLabel(extractor.status)} · ${extractor.version}`)); values.append(labeledValue(t("comparisonStatus"), comparison.status || "—"), labeledValue(t("normalizedOutput"), comparison.status === "COMPLETE" ? t(normalized ? "normalizedEquivalent" : "normalizedDifferent") : t("comparisonUnavailable"))); elements.inspectorPanel.append(values, cliInspectorNote());
    } else elements.inspectorPanel.append(artifactList(observation));
    return;
  }
  const diagnosis = state.selectedKind === "document" && round ? detailFor(round.diagnosis_record_key) : null;
  if (state.selectedKind === "document" && state.stage === "diagnose" && !diagnosis) {
    if (state.inspector === "summary") elements.inspectorPanel.append(inspectorState(t("diagnosisNotRunTitle"), t("diagnosisNotRunBody")));
    else if (state.inspector === "evidence") elements.inspectorPanel.append(inspectorState(t("noDiagnosisEvidenceTitle"), t("noDiagnosisEvidenceBody")));
    else elements.inspectorPanel.append(inspectorState(t("noDiagnosisArtifactsTitle"), t("noDiagnosisArtifactsBody")));
    return;
  }
  if (state.selectedKind === "document" && state.stage === "diagnose" && diagnosis) {
    const findings = diagnosis.view.findings || []; const refinable = findings.filter((finding) => finding.proposal_action && finding.proposal_action.status === "AVAILABLE").length; const references = findings.reduce((total, finding) => total + (finding.document_refs || []).length, 0); const ruleset = state.projection && state.projection.reference ? state.projection.reference.ruleset : null;
    if (state.inspector === "summary") {
      const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("findings"), new Intl.NumberFormat(state.locale).format(diagnosis.view.finding_total)), labeledValue(t("refinableFindings"), new Intl.NumberFormat(state.locale).format(refinable)), labeledValue(t("auditStatus"), diagnosis.artifact_integrity), labeledValue(t("artifacts"), t("artifactCount", {count: diagnosis.artifacts.length}))); elements.inspectorPanel.append(values);
    } else if (state.inspector === "evidence") {
      const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("diagnosisSubject"), relationshipStateLabel(diagnosis.view.subject_state)), labeledValue(t("diagnosisDerivation"), relationshipStateLabel(diagnosis.view.derivation_state))); if (ruleset) values.append(labeledValue(t("ruleset"), `${ruleset.name} · ${ruleset.version}`)); values.append(labeledValue(t("evidenceReferences"), new Intl.NumberFormat(state.locale).format(references))); elements.inspectorPanel.append(values, cliInspectorNote());
    } else elements.inspectorPanel.append(artifactList(diagnosis));
    return;
  }
  if (state.selectedKind === "document" && ["refine", "revision"].includes(state.stage) && isNoFindings(diagnosis)) {
    const stage = state.stage === "refine" ? "refine" : "revision";
    const section = state.inspector === "summary" ? "Summary" : state.inspector === "evidence" ? "Evidence" : "Artifacts";
    elements.inspectorPanel.append(inspectorState(t(`${stage}NoFindings${section}Title`), t(`${stage}NoFindings${section}Body`)));
    return;
  }
  const publishedRefinement = state.selectedKind === "document" && round ? detailFor(round.refinement_record_key) : null;
  if (state.selectedKind === "document" && ["refine", "revision"].includes(state.stage) && publishedRefinement) {
    const diagnosis = detailFor(round.diagnosis_record_key); const finding = diagnosis && diagnosis.view.findings.find((candidate) => candidate.finding_id === publishedRefinement.view.proposal.finding_id); const decision = publishedRefinement.view.decision;
    const hasPreparedRevision = state.stage === "revision" && Boolean(round.revision_record_key);
    if (state.inspector === "summary") {
      const values = node("dl", null, "metadata-list"); if (hasPreparedRevision) values.append(labeledValue(t("preparedRevision"), t("revisionNumber", {number: round.number}))); values.append(labeledValue(t("recordedDecision"), t(decision === "APPROVED" ? "approved" : "rejected")));
      if (finding) values.append(labeledValue(t("sourceFinding"), `${t(`rule.${finding.rule_id}.name`)} · ${finding.rule_id}`));
      values.append(labeledValue(t(hasPreparedRevision ? "appliedRefiner" : "supportedRefiner"), `${t(`refiner.${publishedRefinement.view.proposal.refiner.refiner_id}`)} · ${publishedRefinement.view.proposal.refiner.refiner_id}`), labeledValue(t("auditStatus"), publishedRefinement.artifact_integrity), labeledValue(t("artifacts"), t("artifactCount", {count: publishedRefinement.artifacts.length}))); elements.inspectorPanel.append(values);
    } else if (state.inspector === "evidence") {
      const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("diagnosisRelation"), relationshipStateLabel(publishedRefinement.view.diagnosis_state)), labeledValue(t("baseRelation"), relationshipStateLabel(publishedRefinement.view.base_state)), labeledValue(t("derivationCheck"), relationshipStateLabel(publishedRefinement.view.derivation_state)), labeledValue(t("reversibilityCheck"), relationshipStateLabel(publishedRefinement.view.reversibility_state)), labeledValue(t("transformationCount"), new Intl.NumberFormat(state.locale).format((publishedRefinement.view.transformations || []).length))); elements.inspectorPanel.append(values);
    } else elements.inspectorPanel.append(artifactList(publishedRefinement));
    return;
  }
  if (state.selectedKind === "document" && state.stage === "refine" && !publishedRefinement) {
    const finding = proposalFinding(item, round);
    if (state.inspector === "summary" && finding) {
      const values = node("dl", null, "metadata-list");
      values.append(labeledValue(t("sourceFinding"), `${t(`rule.${finding.rule_id}.name`)} · ${finding.rule_id}`), labeledValue(t("supportedRefiner"), `${t(`refiner.${finding.refiner.refiner_id}`)} · ${finding.refiner.refiner_id}`), labeledValue(t("proposalStatus"), state.proposal ? t("proposalTemporary", {count: state.proposal.edits.length}) : t("proposalNotCreated")));
      elements.inspectorPanel.append(values);
    } else if (state.inspector === "evidence") elements.inspectorPanel.append(inspectorState(t(state.proposal ? "proposalEvidenceTitle" : finding ? "diagnosisSourceEvidenceTitle" : "chooseFindingTitle"), t(state.proposal ? "pendingProposalEvidence" : finding ? "refineInspectorReady" : "chooseFindingBody")));
    else elements.inspectorPanel.append(inspectorState(t("noRefinementArtifactsTitle"), t("noRefinementArtifacts")));
    return;
  }
  const detail = selectedDetail(item, round);
  if (state.inspector === "summary") {
    if (!detail) elements.inspectorPanel.append(node("p", t("inspectorSummary")));
    else { const values = node("dl", null, "metadata-list"); values.append(labeledValue(t("recordKind"), detail.kind), labeledValue(t("auditStatus"), detail.artifact_integrity)); if (detail.kind === "DIAGNOSIS") values.append(labeledValue(t("findings"), new Intl.NumberFormat(state.locale).format(detail.view.finding_total))); values.append(labeledValue(t("artifacts"), t("artifactCount", {count: detail.artifacts.length}))); elements.inspectorPanel.append(values); }
  } else if (state.inspector === "evidence") {
    elements.inspectorPanel.append(node("p", detail ? t(state.stage === "diagnose" && detail.kind === "DIAGNOSIS" ? "diagnosisInspectorEvidence" : state.stage === "revision" ? "forwardInverse" : "preservedEvidence") : t("inspectorEvidence")));
    if (state.proposal && !detailFor(round && round.refinement_record_key)) elements.inspectorPanel.append(node("p", t("pendingProposalEvidence"), "inspector-note"));
    else if (detail && ["OBSERVATION", "DIAGNOSIS", "REFINEMENT"].includes(detail.kind)) {
      elements.inspectorPanel.append(cliInspectorNote());
    }
  } else elements.inspectorPanel.append(detail ? artifactList(detail) : node("p", t("inspectorArtifacts")));
}
function renderCorpus(item, detail) {
  elements.stageHeading.textContent = t("corpusSummary"); elements.stageGuidance.textContent = t("corpusMeaning", {count: item.member_count});
  if (!detail) { elements.central.append(node("p", t("loadingStage"))); return; }
  elements.central.append(banner(t("verified"), t("corpusMeaning", {count: item.member_count})));
  const totals = detail.view.totals || {}; const overview = node("section", null, "corpus-overview"); overview.append(node("h3", t("corpusOverview"))); const metrics = node("div", null, "corpus-metrics"); for (const [key, label] of [["member_count", "members"], ["finding_count", "findings"], ["revision_count", "revisions"], ["failed", "failures"]]) { const metric = node("div", null, "corpus-metric"); metric.append(node("strong", new Intl.NumberFormat(state.locale).format(totals[key] || 0)), node("span", t(label))); metrics.append(metric); } overview.append(metrics); elements.central.append(overview);
  const matrix = detail.view.matrix || []; const formats = [...new Set(matrix.map((member) => member.format))].sort(); const families = [...new Set(matrix.map((member) => member.family))].sort(); const membersByFamily = new Map(); for (const member of matrix) { let byFormat = membersByFamily.get(member.family); if (!byFormat) { byFormat = new Map(); membersByFamily.set(member.family, byFormat); } byFormat.set(member.format, member); } const members = node("section", null, "corpus-coverage"); members.append(node("h3", t("corpusMemberCoverage"))); const scroll = node("div", null, "corpus-matrix-scroll"); const table = node("table", null, "corpus-matrix"); const head = node("thead"); const headRow = node("tr"); const familyHead = node("th", t("corpusFamily")); familyHead.scope = "col"; headRow.append(familyHead); for (const format of formats) { const cell = node("th", String(format).toUpperCase()); cell.scope = "col"; headRow.append(cell); } head.append(headRow); const body = node("tbody"); for (const family of families) { const row = node("tr"); const heading = node("th", corpusName(family)); heading.scope = "row"; row.append(heading); for (const format of formats) { const member = membersByFamily.get(family)?.get(format); const cell = node("td"); const status = member ? member.status : ""; const marker = node("span", corpusStatusGlyph(status), "corpus-cell-status"); marker.dataset.status = status || "MISSING"; marker.title = member ? `${member.member_id} · ${corpusStatusLabel(status)}` : "—"; marker.setAttribute("aria-label", marker.title); cell.append(marker); row.append(cell); } body.append(row); } table.append(head, body); scroll.append(table); members.append(scroll, node("p", `✓ ${t("corpusComplete")} · ! ${t("corpusPartial")} · × ${t("corpusFailed")}`, "corpus-coverage-legend")); elements.central.append(members);
}
function renderSelected() {
  const item = selectedItem();
  if (!item) { state.selectedKind = null; state.selectedKey = null; renderEmptyOrFailure(); return; }
  elements.workspaceState.hidden = true; elements.selected.hidden = false;
  elements.contextKind.textContent = t(state.selectedKind === "document" ? "contextDocument" : "contextCorpus");
  elements.contextName.textContent = state.selectedKind === "document" ? item.source.name : item.title;
  elements.stepper.hidden = state.selectedKind === "corpus";
  const inspector = document.getElementById("stage-inspector"); inspector.hidden = Boolean(state.reader); elements.central.dataset.reader = String(Boolean(state.reader)); clear(elements.central);
  if (state.reader) { elements.central.setAttribute("aria-labelledby", "artifact-reader-heading"); const focusReader = state.reader.focusReader; const focusControl = state.reader.focusControl; state.reader.focusReader = false; state.reader.focusControl = null; elements.central.append(renderArtifactReader()); const target = focusReader ? elements.central.querySelector('[data-reader-close="true"]') : focusControl ? elements.central.querySelector(`[data-reader-control="${focusControl}"]`) : null; if (target) target.focus(); return; }
  elements.central.setAttribute("aria-labelledby", "stage-heading");
  elements.central.append(elements.stageHeading, elements.stageGuidance);
  if (state.selectedKind === "corpus") { elements.roundContext.hidden = true; renderCorpus(item, detailFor(item.record_key)); renderInspector(item, null); }
  else {
    renderRoundContext(item); const round = selectedRoundData(item);
    renderStageStepper(item, round);
    if (state.stage === "observe") renderObserve(item, detailFor(item.observation_record_key));
    else if (state.stage === "diagnose") renderDiagnosis(item, round, round ? detailFor(round.diagnosis_record_key) : null);
    else if (state.stage === "refine") renderRefine(item, round, round ? detailFor(round.diagnosis_record_key) : null, round ? detailFor(round.refinement_record_key) : null);
    else renderRevision(item, round, round ? detailFor(round.refinement_record_key) : null);
    renderInspector(item, round);
  }
  elements.tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.tab === state.inspector)));
}
function renderRuleReference() {
  clear(elements.ruleList);
  const rules = state.projection && state.projection.reference ? state.projection.reference.rules : [];
  for (const rule of rules) {
    const entry = node("article", null, "rule-entry");
    entry.dataset.severity = rule.severity;
    const heading = node("div", null, "rule-entry-heading"); heading.append(node("h3", `${rule.rule_id} · ${t(`rule.${rule.rule_id}.name`)}`), node("span", rule.severity)); entry.append(heading, node("p", t(`rule.${rule.rule_id}.about`)));
    if (rule.refiner) entry.append(node("span", `${rule.refiner.refiner_id} · ${t(`refiner.${rule.refiner.refiner_id}`)}`, "rule-refiner"));
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
function openModal(modal) { modalReturnFocus = document.activeElement; modal.hidden = false; elements.surface.inert = true; elements.toast.inert = true; const targets = focusable(modal); if (targets.length) targets[0].focus(); }
function closeModal(modal) { modal.hidden = true; elements.surface.inert = false; elements.toast.inert = false; if (modalReturnFocus && modalReturnFocus.focus) modalReturnFocus.focus(); modalReturnFocus = null; }
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
  if (!response.ok) { let body = {}; try { body = await response.json(); } catch (_) { /* status is sufficient */ } const error = new Error(body.message || `Request failed with status ${response.status}.`); error.code = body.code; error.status = response.status; error.confirmed = true; throw error; }
  return response.status === 204 ? null : response.json();
}
async function fetchText(target, mediaType) {
  const response = await fetch(target, {credentials: "same-origin", headers: {Accept: mediaType || "text/plain"}});
  if (!response.ok) { let body = {}; try { body = await response.json(); } catch (_) { /* status is sufficient */ } const error = new Error(body.message || `Request failed with status ${response.status}.`); error.code = body.code; error.status = response.status; throw error; }
  return response.text();
}
async function fetchArtifact(descriptor) { return fetchText(`${API_ROOT}/artifacts/${descriptor.artifact_key}`, descriptor.media_type); }
async function actionToken(force = false) {
  if (!state.actionToken || force) state.actionToken = (await fetchJSON(`${API_ROOT}/lifecycle/action-token`)).action_token;
  return state.actionToken;
}
function knownPrepublication(error) { return ["ACTION_NOT_AVAILABLE", "NOT_FOUND", "WORKSPACE_STALE", "LIFECYCLE_BUSY", "ACTION_TOKEN_INVALID", "INVALID_REQUEST"].includes(error.code); }
function reconciledMutationOutcome(projection, mutation) {
  if (!mutation) return {state: "UNKNOWN"};
  const document = projection.documents.find((item) => item.document_key === mutation.documentKey); if (!document) return {state: "UNKNOWN"};
  if (mutation.kind === "proposal") return {state: "NOT_PUBLISHED"};
  if (mutation.kind === "diagnosis") {
    const round = (document.rounds || []).find((item) => item.base_record_key === mutation.baseKey && item.diagnosis_record_key); return round ? {state: "PUBLISHED", recordKey: round.diagnosis_record_key} : {state: "NOT_PUBLISHED"};
  }
  const round = (document.rounds || []).find((item) => item.base_record_key === mutation.baseKey && item.diagnosis_record_key === mutation.diagnosisKey && item.refinement_record_key); return round ? {state: "PUBLISHED", recordKey: round.refinement_record_key} : {state: "NOT_PUBLISHED"};
}
async function authoritativeWorkspaceProjection() {
  await fetchJSON(`${API_ROOT}/workbench/refresh`, {method: "POST"}); return fetchJSON(`${API_ROOT}/workbench`);
}
async function reconcileLifecycleUnknown() {
  state.lifecycleReconciliationPending = true; state.lifecyclePending = false;
  if (!state.lifecycleNotice || state.lifecycleNotice.title !== "lifecyclePublishedRefreshFailed") state.lifecycleNotice = {title: "lifecycleUnknown", body: "lifecycleUnknown", tone: "failure"}; render();
  try {
    const confirmedPublished = state.lifecycleNotice && state.lifecycleNotice.title === "lifecyclePublishedRefreshFailed";
    const mutation = state.pendingLifecycleMutation; const projection = await authoritativeWorkspaceProjection(); const outcome = reconciledMutationOutcome(projection, mutation); applyProjection(projection, mutation ? mutation.documentKey : state.selectedKey);
    if (confirmedPublished && outcome.state !== "PUBLISHED") { render(); return false; }
    if (outcome.state === "UNKNOWN") { render(); return false; }
    if (outcome.state === "PUBLISHED") { state.selectedRound = null; state.stage = mutation.kind === "decision" ? "refine" : "diagnose"; state.proposal = mutation.kind === "decision" ? null : state.proposal; }
    else if (mutation && mutation.kind === "decision") state.decisionSubmitted = false;
    state.lifecycleReconciliationPending = false; state.pendingLifecycleMutation = null; state.lifecycleNotice = null; await hydrateSelectedStage(); render(); return true;
  } catch (_) { render(); return false; }
}
async function lifecyclePost(target) {
  const token = await actionToken(); return fetchJSON(target, {method: "POST", headers: {"X-TCW-Action-Token": token}});
}
async function handleLifecycleError(error) {
  if (error.code === "ACTION_TOKEN_INVALID") {
    try { await actionToken(true); } catch (_) { /* keep the rejected token state visible */ }
    state.lifecyclePending = false; elements.refresh.disabled = false; state.pendingLifecycleMutation = null; state.decisionSubmitted = false; state.lifecycleNotice = {title: "staleToken", body: "staleToken", tone: "failure"}; render(); return "STALE";
  }
  if (knownPrepublication(error)) {
    state.lifecyclePending = false; elements.refresh.disabled = false; state.pendingLifecycleMutation = null; state.decisionSubmitted = false; state.lifecycleNotice = {title: error.code === "LIFECYCLE_BUSY" ? "lifecycleBusy" : "lifecyclePrepublicationFailure", body: error.code === "LIFECYCLE_BUSY" ? "lifecycleBusy" : "lifecyclePrepublicationFailure", tone: "failure"}; render(); return "PREPUBLICATION";
  }
  await reconcileLifecycleUnknown(); elements.refresh.disabled = false; return "UNKNOWN";
}
async function acceptPublication(envelope, preferredStage) {
  if (!envelope || !envelope.publication) throw new Error("lifecycle response outcome is unknown");
  if (!envelope.refresh || envelope.refresh.status !== "READY" || !envelope.publication.record_key) {
    state.lifecyclePending = false; elements.refresh.disabled = false; state.lifecycleReconciliationPending = true; state.lifecycleNotice = {title: "lifecyclePublishedRefreshFailed", body: "lifecyclePublishedRefreshFailed", tone: "failure"}; render(); return false;
  }
  const projection = await fetchJSON(`${API_ROOT}/workbench`); applyProjection(projection, state.selectedKey); state.stage = preferredStage; state.selectedRound = null; state.lifecyclePending = false; elements.refresh.disabled = false; state.pendingLifecycleMutation = null; state.lifecycleNotice = null; await hydrateSelectedStage(); render(); return true;
}
function revealDecisionOutcome() {
  const target = Array.from(elements.central.children).find((child) => child.dataset && child.dataset.decisionOutcome === "true"); if (!target) return;
  target.setAttribute("tabindex", "-1"); target.focus({preventScroll: true});
  if (target.scrollIntoView) target.scrollIntoView({block: "center"});
}
function currentBaseKey(item) {
  const rounds = item.rounds || []; if (!rounds.length) return item.observation_record_key;
  const last = rounds[rounds.length - 1]; return last.revision_record_key || last.base_record_key;
}
async function runDiagnosis(item) {
  if (state.lifecyclePending || state.lifecycleReconciliationPending || isHistoricalRound(item)) return;
  const baseKey = currentBaseKey(item); state.pendingLifecycleMutation = {kind: "diagnosis", documentKey: item.document_key, baseKey}; state.lifecyclePending = true; elements.refresh.disabled = true; state.lifecycleNotice = null; render();
  try { const envelope = await lifecyclePost(`${API_ROOT}/lifecycle/diagnoses/${baseKey}`); await acceptPublication(envelope, "diagnose"); }
  catch (error) { await handleLifecycleError(error); }
}
async function createProposal(round, finding) {
  if (state.lifecyclePending || state.lifecycleReconciliationPending || state.proposal) return;
  const identity = {documentKey: state.selectedKey, roundNumber: round.number, diagnosisKey: round.diagnosis_record_key, baseKey: round.base_record_key}; state.pendingLifecycleMutation = {kind: "proposal", ...identity}; state.lifecyclePending = true; elements.refresh.disabled = true; state.lifecycleNotice = null; render();
  try { const envelope = await lifecyclePost(`${API_ROOT}/lifecycle/proposals/${round.diagnosis_record_key}/${finding.finding_id}`); state.proposal = envelope.draft; state.proposalIdentity = identity; state.pendingLifecycleMutation = null; state.lifecyclePending = false; elements.refresh.disabled = false; state.decisionSelection = null; state.comparison = {index: 0}; render(); }
  catch (error) { await handleLifecycleError(error); }
}
async function recordDecision() {
  if (!state.proposal || !state.decisionSelection || state.decisionSubmitted || state.lifecyclePending || state.lifecycleReconciliationPending) return;
  state.pendingLifecycleMutation = {kind: "decision", documentKey: state.selectedKey, diagnosisKey: state.proposal.diagnosis_record_key, baseKey: state.proposal.base_record_key, draftKey: state.proposal.draft_key, decision: state.decisionSelection}; state.decisionSubmitted = true; state.lifecyclePending = true; elements.refresh.disabled = true; state.lifecycleNotice = null; render();
  let published = false;
  try { const envelope = await lifecyclePost(`${API_ROOT}/lifecycle/proposals/${state.proposal.draft_key}/${state.decisionSelection}`); published = await acceptPublication(envelope, "refine"); }
  catch (error) { await handleLifecycleError(error); }
  if (published) revealDecisionOutcome();
}
function changeStage(stage) {
  if (!STAGES.includes(stage) || state.reader || state.lifecyclePending || state.lifecycleReconciliationPending) return;
  state.stage = stage; state.recordedProposal = null; state.recordedProposalKey = null; state.recordedProposalLoading = null; state.appliedProposal = null; state.appliedProposalLoading = null; state.appliedComparisonOpen = false; state.comparison = {index: 0}; render(); hydrateSelectedStage().then(render).catch(() => render());
}
async function loadProjection({initial = false, preferredKey = null} = {}) {
  try {
    const projection = await fetchJSON(`${API_ROOT}/workbench`);
    applyProjection(projection, preferredKey);
    await hydrateSelectedStage(); render(); elements.refresh.disabled = false; return true;
  } catch (error) {
    if (initial) { state.initialFailure = true; state.projection = null; render(); elements.assertive.textContent = t("loadFailureTitle"); elements.refresh.disabled = false; }
    throw error;
  }
}
function applyProjection(projection, preferredKey = null) {
    if (!catalogCoversReference(projection.reference)) throw new Error("locale catalogs do not match the canonical reference");
    const selectedKeyBefore = state.selectedKey; const selectedKindBefore = state.selectedKind; const priorKey = preferredKey || state.selectedKey; const priorKind = state.selectedKind;
    state.projection = projection; state.initialFailure = false;
    const documentExists = projection.documents.some((item) => item.document_key === priorKey);
    const corpusExists = projection.corpora.some((item) => item.record_key === priorKey);
    if ((priorKind === "document" && documentExists) || (priorKind === "corpus" && corpusExists)) { state.selectedKey = priorKey; state.selectedKind = priorKind; }
    else if (preferredKey && documentExists) { state.selectedKey = preferredKey; state.selectedKind = "document"; state.stage = "observe"; }
    else if (state.selectedKey && !documentExists && !corpusExists) { state.selectedKey = null; state.selectedKind = null; }
    if (!state.selectedKey && projection.documents.length) { state.selectedKind = "document"; state.selectedKey = projection.documents[0].document_key; }
    else if (!state.selectedKey && projection.corpora.length) { state.selectedKind = "corpus"; state.selectedKey = projection.corpora[0].record_key; }
    const selectionChanged = selectedKeyBefore !== state.selectedKey || selectedKindBefore !== state.selectedKind;
    if (selectionChanged) clearSelectionScopedState();
    else if (state.proposal) {
      const identity = state.proposalIdentity; const document = identity && projection.documents.find((item) => item.document_key === identity.documentKey);
      const round = document && (document.rounds || []).find((item) => item.number === identity.roundNumber);
      const selectedRound = document ? (state.selectedRound === null ? Math.max(1, (document.rounds || []).length) : state.selectedRound) : null;
      if (!identity || state.selectedKind !== "document" || state.selectedKey !== identity.documentKey || selectedRound !== identity.roundNumber || !round || round.diagnosis_record_key !== identity.diagnosisKey || round.base_record_key !== identity.baseKey) clearSelectionScopedState();
    }
    if (state.selectedFinding) {
      const document = projection.documents.find((item) => item.document_key === state.selectedFinding.documentKey);
      const round = document && (document.rounds || []).find((item) => item.number === state.selectedFinding.roundNumber);
      if (!document || !round || round.diagnosis_record_key !== state.selectedFinding.diagnosisKey || state.selectedKey !== state.selectedFinding.documentKey) state.selectedFinding = null;
    }
    return state.projection;
}
function observationIsActive(job) { return Boolean(job && (job.state === "QUEUED" || job.state === "RUNNING")); }
function setObservationActive(job) {
  state.activeObservationJobId = observationIsActive(job) ? job.job_id : null;
  updateObservationControls();
}
function updateObservationControls() {
  if (!elements.add) return;
  const disabled = state.initialFailure || !state.projection || state.activeObservationJobId !== null || state.lifecyclePending || state.lifecycleReconciliationPending;
  elements.add.disabled = disabled;
  if (elements.guidedWhitespace) elements.guidedWhitespace.disabled = disabled;
  if (elements.guidedPolicy) elements.guidedPolicy.disabled = disabled;
  if (elements.file) elements.file.disabled = disabled;
  if (elements.upload) elements.upload.disabled = disabled || !(elements.file.files && elements.file.files.length === 1);
}
async function refreshWorkspace() {
  if (state.lifecyclePending) return false;
  const selected = state.selectedKey; const before = state.projection ? state.projection.session_id : null;
  elements.refresh.disabled = true; elements.polite.textContent = t("refreshStarted");
  try {
    if (state.lifecycleReconciliationPending) { if (!await reconcileLifecycleUnknown()) throw new Error("lifecycle reconciliation remains unresolved"); }
    else { await fetchJSON(`${API_ROOT}/workbench/refresh`, {method: "POST"}); await loadProjection({preferredKey: selected}); state.pendingLifecycleMutation = null; state.lifecycleNotice = null; }
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
    const acceptedState = {...state, details: new Map(state.details)};
    let document;
    try {
      const projected = await fetchJSON(`${API_ROOT}/workbench`);
      document = projected.documents.find((item) => item.observation_record_key === job.observation.record_key);
      applyProjection(projected, document ? document.document_key : null);
      if (document) state.stage = "observe";
      await hydrateSelectedStage();
      render();
    } catch (_) {
      Object.assign(state, acceptedState);
      setObservationActive(null);
      state.pendingTerminalToastKey = null;
      showToast(t("observationPublishedRefreshFailed"), "failure");
      return;
    }
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
  const ids = ["app-surface", "package-version", "rule-reference", "locale-toggle", "refresh-workspace", "add-document", "document-list", "corpus-list", "workspace-state", "selected-workspace", "context-kind", "context-name", "round-context", "stage-stepper", "central-surface", "stage-heading", "stage-guidance", "inspector-panel", "toast", "toast-message", "toast-close", "polite-announcer", "assertive-announcer", "add-modal", "rule-modal", "rule-list", "observation-file", "add-upload", "add-whitespace", "add-policy"];
  for (const id of ids) elements[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = document.getElementById(id);
  Object.assign(elements, {surface: elements.appSurface, version: elements.packageVersion, ruleButton: elements.ruleReference, localeToggle: elements.localeToggle, refresh: elements.refreshWorkspace, add: elements.addDocument, documents: elements.documentList, corpora: elements.corpusList, workspaceState: elements.workspaceState, selected: elements.selectedWorkspace, contextKind: elements.contextKind, contextName: elements.contextName, roundContext: elements.roundContext, stepper: elements.stageStepper, central: elements.centralSurface, stageHeading: elements.stageHeading, stageGuidance: elements.stageGuidance, inspectorPanel: elements.inspectorPanel, toastMessage: elements.toastMessage, toastClose: elements.toastClose, polite: elements.politeAnnouncer, assertive: elements.assertiveAnnouncer, addModal: elements.addModal, ruleModal: elements.ruleModal, ruleList: elements.ruleList, file: elements.observationFile, upload: elements.addUpload, guidedWhitespace: elements.addWhitespace, guidedPolicy: elements.addPolicy});
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
  elements.stepper.querySelectorAll("li button").forEach((button) => button.addEventListener("click", () => changeStage(button.parentElement.dataset.stage)));
  elements.tabs.forEach((tab) => tab.addEventListener("click", () => { state.inspector = tab.dataset.tab; renderSelected(); }));
}
async function start() {
  if (!catalogParity()) throw new Error("locale catalogs must contain identical keys");
  bindElements(); state.locale = negotiatedLocale(navigator.languages || [navigator.language], safeStoredLocale()); state.activeObservationJobId = RECONCILING_OBSERVATION; addListeners(); localizeStatic();
  elements.workspaceState.append(node("p", t("loading")));
  try { await loadProjection({initial: true}); } catch (_) { /* durable initial failure is rendered */ }
  await discoverActiveObservation();
}

if (typeof window !== "undefined") window.__tcwWorkbench = {catalogs, state, elements, t, catalogParity, catalogCoversReference, negotiatedLocale, setLocale, applyProjection, hydrateRecordedProposal, showToast, pauseToast, resumeToast, setToastHover, setToastFocus, dismissToast, loadProjection, refreshWorkspace, handleObservationEnvelope, reconcilePendingReactivation, reconcileMissingObservationSnapshot, claimObservationSubmission, submitGuidedObservation, submitUploadedObservation, observationIsActive, setObservationActive, consumeObservationJob, pollObservation, discoverActiveObservation, updateObservationControls, render, renderSelected, comparisonComponent, visibleWhitespace, compactHash, isolatedHtml, selectedDetail, artifactMetadata, artifactList, openArtifact, closeReader, renderArtifactReader, renderCorpus, changeStage, runDiagnosis, createProposal, recordDecision, actionToken, reconcileLifecycleUnknown, openModal, closeModal, modalKeydown, backdropDismiss, extractorStatus};
if (!globalThis.__TCW_TEST_NO_START__) start();
