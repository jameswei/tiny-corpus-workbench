"use strict";

const API_ROOT = "/api";
const COMPARISON_METRICS = [
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
];
const elements = {
  announcer: document.getElementById("announcer"),
  recordCount: document.getElementById("record-count"),
  recordList: document.getElementById("record-list"),
  recordView: document.getElementById("record-view"),
  recordHeading: document.getElementById("record-heading"),
  recordKind: document.getElementById("record-kind"),
  recordState: document.getElementById("record-state"),
  recordSummary: document.getElementById("record-summary"),
  recordContent: document.getElementById("record-content"),
  sessionState: document.getElementById("session-state"),
  sessionMessage: document.getElementById("session-message"),
  sessionFacts: document.getElementById("session-facts"),
  stateKey: document.getElementById("state-key"),
};

const stateHelp = {
  MATCH: "The admitted target is present and its recorded relationship matches.",
  MISSING: "The referenced record was not supplied. No absent record was opened.",
  NOT_CHECKED: "The required related record was not available, so evaluation did not run.",
  NOT_APPLICABLE: "This evaluation does not apply to the record state.",
  VERIFIED: "Intrinsic artifact integrity passed during admission.",
};

const statusTone = {
  AVAILABLE: "good",
  COMPLETE: "good",
  MATCH: "good",
  SUCCESS: "good",
  VERIFIED: "good",
  APPLIED: "good",
  APPROVED: "good",
  FAILED: "bad",
  MISSING: "bad",
  ERROR: "bad",
  INCOMPLETE: "warn",
  NOT_AVAILABLE: "warn",
  PARTIAL: "warn",
  PARTIAL_SUCCESS: "warn",
  REJECTED: "warn",
  TOO_LARGE: "warn",
  NOT_CHECKED: "neutral",
  NOT_APPLICABLE: "na",
};

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined && text !== null) {
    value.textContent = String(text);
  }
  if (className) {
    value.className = className;
  }
  return value;
}

function clear(value) {
  while (value.firstChild) {
    value.removeChild(value.firstChild);
  }
}

function displayName(value) {
  return String(value).replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortHash(value) {
  if (typeof value !== "string" || value.length < 18) {
    return value === null ? "None" : String(value);
  }
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function status(value) {
  const label = value === null || value === undefined ? "Unknown" : String(value);
  const badge = node("span", displayName(label), `status status-${statusTone[label] || "neutral"}`);
  badge.dataset.state = label;
  return badge;
}

function announce(message) {
  elements.announcer.textContent = message;
}

function factList(entries) {
  const list = node("dl", undefined, "facts");
  for (const [label, value, monospaced] of entries) {
    const wrapper = node("div");
    wrapper.append(node("dt", label), node("dd", value, monospaced ? "mono" : undefined));
    list.append(wrapper);
  }
  return list;
}

function section(title, description) {
  const wrapper = node("section", undefined, "section");
  wrapper.append(node("h3", title));
  if (description) {
    wrapper.append(node("p", description));
  }
  return wrapper;
}

function stateCard(label, value) {
  const card = node("div", undefined, "state-card");
  const heading = node("h4", label);
  heading.append(" ", status(value));
  card.append(heading);
  if (stateHelp[value]) {
    card.append(node("p", stateHelp[value]));
  }
  return card;
}

function makeTable(captionText, columns, rows) {
  const wrapper = node("div", undefined, "table-wrap");
  const table = node("table");
  table.append(node("caption", captionText));
  const head = node("thead");
  const headingRow = node("tr");
  for (const column of columns) {
    const th = node("th", column.label);
    th.scope = "col";
    headingRow.append(th);
  }
  head.append(headingRow);
  table.append(head);
  const body = node("tbody");
  for (const row of rows) {
    const tr = node("tr");
    columns.forEach((column, index) => {
      const cell = node(index === 0 ? "th" : "td");
      if (index === 0) {
        cell.scope = "row";
      }
      const content = column.render ? column.render(row) : row[column.key];
      if (content instanceof Node) {
        cell.append(content);
      } else {
        cell.textContent = content === null || content === undefined ? "—" : String(content);
      }
      tr.append(cell);
    });
    body.append(tr);
  }
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

function jsonText(value) {
  return node("pre", JSON.stringify(value, null, 2), "evidence");
}

function metricValue(view, metric) {
  return view === null ? "Not available" : view[metric];
}

function signedMetricValue(view, metric) {
  if (view === null) {
    return "Not available";
  }
  const value = view[metric];
  return value >= 0 ? `+${value}` : String(value);
}

function renderStateKey() {
  const wrapper = section("State key", "Relationship and evaluation states have separate meanings.");
  const grid = node("div", undefined, "state-grid");
  for (const value of ["MATCH", "MISSING", "NOT_CHECKED", "NOT_APPLICABLE"]) {
    grid.append(stateCard(displayName(value), value));
  }
  wrapper.append(grid);
  elements.stateKey.append(wrapper);
}

function renderOverview(projection) {
  elements.sessionState.replaceWith(status("AVAILABLE"));
  elements.sessionState = document.querySelector("#session-overview .section-heading .status");
  elements.sessionMessage.textContent = "The projection is derived in memory. It cannot edit records or run workflows.";
  const counts = projection.counts;
  const facts = [
    ["Records", counts.record_count],
    ["Top-level records", counts.top_level_record_count],
    ["Contained records", counts.contained_record_count],
    ["Session ID", shortHash(projection.session_id), true],
  ];
  clear(elements.sessionFacts);
  for (const [label, value, monospaced] of facts) {
    const wrapper = node("div");
    wrapper.append(node("dt", label), node("dd", value, monospaced ? "mono" : undefined));
    elements.sessionFacts.append(wrapper);
  }
}

function recordLabel(record) {
  return `${displayName(record.status)} ${displayName(record.kind)} ${shortHash(record.primary_identity.value)}`;
}

function renderNavigation(projection) {
  elements.recordCount.textContent = String(projection.records.length);
  elements.recordCount.setAttribute("aria-label", `${projection.records.length} records`);
  clear(elements.recordList);
  for (const record of projection.records) {
    const button = node("button", undefined, "record-button");
    button.type = "button";
    button.dataset.recordKey = record.record_key;
    button.append(node("strong", displayName(record.kind)));
    button.append(node("small", `${displayName(record.status)} · ${shortHash(record.primary_identity.value)}`));
    button.setAttribute("aria-label", `Open ${recordLabel(record)}`);
    button.addEventListener("click", () => loadRecord(record));
    elements.recordList.append(button);
  }
}

function renderRecordSummary(record, detail) {
  clear(elements.recordSummary);
  const identity = `${displayName(record.primary_identity.name)}: ${shortHash(record.primary_identity.value)}`;
  elements.recordSummary.append(factList([
    ["Run ID", record.run_id, true],
    ["Identity", identity, true],
    ["Origin", displayName(record.origin)],
    ["Artifacts", record.artifact_count],
    ["Artifact integrity", detail.artifact_integrity],
  ]));
}

function renderRelationships(detail) {
  const wrapper = section("Integrity and relationships", "Intrinsic integrity is independent from cross-record relationship and replay evaluation.");
  const grid = node("div", undefined, "state-grid");
  grid.append(stateCard("Artifact integrity", detail.artifact_integrity));
  if (detail.relationships.length === 0) {
    const empty = node("div", undefined, "state-card");
    empty.append(node("h4", "Relationships"), node("p", "This record declares no cross-record relationship."));
    grid.append(empty);
  } else {
    for (const edge of detail.relationships) {
      const card = stateCard(displayName(edge.relation), edge.state);
      card.append(node("p", `Expected ${displayName(edge.target_kind)} ${shortHash(edge.target_identity.value)}.`, "mono"));
      grid.append(card);
    }
  }
  wrapper.append(grid);
  return wrapper;
}

function renderSource(source) {
  const wrapper = section("Source metadata", "The source itself is not available from the workbench.");
  wrapper.append(factList([
    ["Name", source.name || source.key],
    ["Media type", source.media_type],
    ["Size", `${source.size} bytes`],
    ["SHA-256", source.sha256, true],
  ]));
  return wrapper;
}

function renderObservation(detail) {
  const value = detail.view;
  const fragment = document.createDocumentFragment();
  fragment.append(renderSource(value.source));

  const extractors = section("Extractor comparison", "Extractor results remain separate. A comparison can be incomplete.");
  extractors.append(factList([
    ["Canonical document", value.docling_document.name],
    ["Document version", value.docling_document.version],
  ]));
  const cards = node("div", undefined, "card-grid");
  for (const extractor of value.extractors) {
    const card = node("article", undefined, "card");
    const heading = node("h4", `${displayName(extractor.name)} ${extractor.version}`);
    heading.append(" ", status(extractor.status));
    card.append(heading);
    card.append(node("p", `Upstream state: ${extractor.upstream_status === null ? "Not reported" : displayName(extractor.upstream_status)}.`));
    if (extractor.error) {
      card.append(node("p", `${extractor.error.code}: ${extractor.error.message}`, "error"));
    }
    cards.append(card);
  }
  extractors.append(cards);

  const comparison = value.comparison;
  const comparisonState = node("p");
  comparisonState.append("Comparison ", status(comparison.status));
  extractors.append(comparisonState);
  if (comparison.docling || comparison.markitdown) {
    if (comparison.docling_minus_markitdown) {
      extractors.append(node(
        "p",
        `Normalized text equal: ${comparison.docling_minus_markitdown.normalized_equal ? "Yes" : "No"}.`,
      ));
    }
    extractors.append(makeTable(
      "Ten extractor comparison metrics",
      [
        {label: "Metric", render: (row) => displayName(row)},
        {label: "Docling", render: (row) => comparison.docling ? comparison.docling[row] : "—"},
        {label: "MarkItDown", render: (row) => comparison.markitdown ? comparison.markitdown[row] : "—"},
        {label: "Delta", render: (row) => comparison.docling_minus_markitdown ? comparison.docling_minus_markitdown[row] : "—"},
      ],
      COMPARISON_METRICS,
    ));
  }
  fragment.append(extractors);
  return fragment;
}

function renderDiagnosis(detail) {
  const value = detail.view;
  const fragment = document.createDocumentFragment();
  fragment.append(renderSource(value.source));
  const evaluations = section("Evaluation states");
  const grid = node("div", undefined, "state-grid");
  grid.append(stateCard("Subject identity", value.subject_state));
  grid.append(stateCard("Diagnosis derivation", value.derivation_state));
  evaluations.append(grid);
  fragment.append(evaluations);

  const findings = section("Findings", `${value.finding_total} evidence-backed finding(s). Evidence is displayed as literal text.`);
  if (value.findings.length === 0) {
    findings.append(node("p", "No rule matched this document.", "empty"));
  }
  for (const finding of value.findings) {
    const card = node("article", undefined, "card subsection");
    const heading = node("h4", `${finding.rule_id} · ${displayName(finding.summary)}`);
    heading.append(" ", status(finding.severity));
    card.append(heading);
    card.append(factList([
      ["Finding ID", finding.finding_id, true],
      ["Rule version", finding.rule_version],
      ["Affected references", finding.document_refs.join(", "), true],
    ]));
    card.append(node("h5", "Evidence"));
    card.append(jsonText(finding.evidence));
    findings.append(card);
  }
  fragment.append(findings);
  return fragment;
}

function renderRefinement(detail) {
  const value = detail.view;
  const fragment = document.createDocumentFragment();
  fragment.append(renderSource(value.source));

  const decision = section("Decision", "The workbench reports the recorded human decision. It cannot change it.");
  const decisionHeading = node("p");
  decisionHeading.append("Decision ", status(value.decision.state));
  decision.append(decisionHeading);
  decision.append(factList([
    ["Decided by", value.decision.decided_by],
    ["Note", value.decision.note === null ? "None" : value.decision.note],
  ]));
  fragment.append(decision);

  const evaluations = section("Evaluation states");
  const grid = node("div", undefined, "state-grid");
  grid.append(stateCard("Diagnosis identity", value.diagnosis_state));
  grid.append(stateCard("Base identity", value.base_state));
  grid.append(stateCard("Forward derivation", value.derivation_state));
  grid.append(stateCard("Reversibility", value.reversibility_state));
  evaluations.append(grid);
  fragment.append(evaluations);

  const transformations = section("Transformations", "Before and after hashes bind each deterministic change.");
  if (value.transformations.length === 0) {
    transformations.append(node("p", "No transformation was applied.", "empty"));
  } else {
    transformations.append(makeTable(
      "Applied transformations",
      [
        {label: "Step", key: "ordinal"},
        {label: "Refiner", render: (row) => `${row.refiner.refiner_id} · ${displayName(row.refiner.name)}`},
        {label: "Before", render: (row) => shortHash(row.before_sha256)},
        {label: "After", render: (row) => shortHash(row.after_sha256)},
        {label: "References", key: "affected_reference_count"},
      ],
      value.transformations,
    ));
  }
  fragment.append(transformations);

  const chain = section("Revision chain");
  if (value.revision_chain.length === 0) {
    chain.append(node("p", "A rejected decision has no revision chain.", "empty"));
  } else {
    chain.append(makeTable(
      "Immutable revision lineage",
      [
        {label: "Revision", render: (row) => shortHash(row.revision_id)},
        {label: "Parent revision", render: (row) => row.parent_revision_id ? shortHash(row.parent_revision_id) : "Source observation"},
        {label: "Refiner", render: (row) => row.refiner.refiner_id},
        {label: "Before", render: (row) => shortHash(row.before_sha256)},
        {label: "After", render: (row) => shortHash(row.after_sha256)},
      ],
      value.revision_chain,
    ));
  }
  fragment.append(chain);
  return fragment;
}

function renderCorpus(detail) {
  const value = detail.view;
  const fragment = document.createDocumentFragment();
  const summary = section("Corpus summary");
  const summaryLine = node("p");
  summaryLine.append("Corpus state ", status(value.status));
  summary.append(summaryLine, factList([
    ["Corpus ID", value.corpus_id],
    ["Snapshot ID", value.snapshot_id, true],
    ["Members", value.totals.member_count],
    ["Complete", value.totals.complete],
    ["Partial", value.totals.partial],
    ["Failed", value.totals.failed],
    ["Findings", value.totals.finding_count],
    ["Revisions", value.totals.revision_count],
  ]));
  fragment.append(summary);

  const matrix = section("Family and format matrix", "Each member keeps its complete, partial, or failed state.");
  matrix.append(makeTable(
    "Corpus members by family and format",
    [
      {label: "Member", key: "member_id"},
      {label: "Family", key: "family"},
      {label: "Format", key: "format"},
      {label: "Source", render: (row) => row.source.name || row.source.key},
      {label: "State", render: (row) => status(row.status)},
      {label: "Observation", render: (row) => row.observation_record_key ? shortHash(row.observation_record_key) : "Not available"},
      {label: "Diagnosis", render: (row) => row.diagnosis_record_key ? shortHash(row.diagnosis_record_key) : "Not available"},
      {label: "Explanation", render: (row) => row.error ? `${row.error.code}: ${row.error.message}` : "Complete"},
    ],
    value.matrix,
  ));
  fragment.append(matrix);

  const aggregates = section("Aggregates");
  aggregates.append(makeTable(
    "Family totals",
    [
      {label: "Family", key: "name"},
      {label: "Members", key: "member_count"},
      {label: "Complete", key: "complete"},
      {label: "Partial", key: "partial"},
      {label: "Failed", key: "failed"},
    ],
    value.aggregates.by_family,
  ));
  aggregates.append(makeTable(
    "Format totals",
    [
      {label: "Format", key: "name"},
      {label: "Members", key: "member_count"},
      {label: "Complete", key: "complete"},
      {label: "Partial", key: "partial"},
      {label: "Failed", key: "failed"},
    ],
    value.aggregates.by_format,
  ));
  aggregates.append(makeTable(
    "Extractor availability",
    [
      {label: "Extractor", key: "name"},
      {label: "Available", key: "available"},
      {label: "Unavailable", key: "unavailable"},
    ],
    value.aggregates.extractors,
  ));
  aggregates.append(makeTable(
    "Member normalized equality",
    [
      {label: "Member", key: "member_id"},
      {label: "State", render: (row) => status(row.status)},
      {label: "Normalized equal", render: (row) => row.docling_minus_markitdown === null ? "Not available" : row.docling_minus_markitdown.normalized_equal ? "Yes" : "No"},
    ],
    value.aggregates.comparisons,
  ));
  const comparisonRows = value.aggregates.comparisons.flatMap((comparison) =>
    COMPARISON_METRICS.map((metric) => ({
      member_id: comparison.member_id,
      status: comparison.status,
      metric,
      docling: comparison.docling,
      markitdown: comparison.markitdown,
      delta: comparison.docling_minus_markitdown,
    }))
  );
  aggregates.append(makeTable(
    "Member extractor comparison metrics",
    [
      {label: "Member", key: "member_id"},
      {label: "State", render: (row) => status(row.status)},
      {label: "Metric", render: (row) => displayName(row.metric)},
      {label: "Docling", render: (row) => metricValue(row.docling, row.metric)},
      {label: "MarkItDown", render: (row) => metricValue(row.markitdown, row.metric)},
      {label: "Signed delta", render: (row) => signedMetricValue(row.delta, row.metric)},
    ],
    comparisonRows,
  ));
  aggregates.append(makeTable(
    "Finding totals",
    [
      {label: "Rule", key: "rule_id"},
      {label: "Severity", render: (row) => status(row.severity)},
      {label: "Family", key: "family"},
      {label: "Format", key: "format"},
      {label: "Findings", key: "finding_count"},
      {label: "Members", key: "affected_member_count"},
    ],
    value.aggregates.findings,
  ));
  aggregates.append(makeTable(
    "Revision groups",
    [
      {label: "Family", key: "family"},
      {label: "Format", key: "format"},
      {label: "Finding rule", key: "finding_rule"},
      {label: "Refiner", key: "refiner_id"},
      {label: "Revisions", key: "revision_count"},
    ],
    value.aggregates.revision_groups,
  ));
  aggregates.append(makeTable(
    "Revision summaries",
    [
      {label: "Member", key: "member_id"},
      {label: "Finding", key: "finding_rule"},
      {label: "Refiner", render: (row) => row.refiner.refiner_id},
      {label: "Chain length", key: "chain_length"},
      {label: "Before", render: (row) => shortHash(row.before_document_sha256)},
      {label: "After", render: (row) => shortHash(row.after_document_sha256)},
    ],
    value.aggregates.revisions,
  ));
  fragment.append(aggregates);

  const external = section("External revisions", "External refinement records are admitted only when explicitly supplied.");
  if (value.external_revisions.length === 0) {
    external.append(node("p", "No external revision was listed.", "empty"));
  } else {
    external.append(makeTable(
      "External revision relationships",
      [
        {label: "Member", key: "member_id"},
        {label: "Revision", render: (row) => shortHash(row.revision_id)},
        {label: "Relationship", render: (row) => status(row.relationship_state)},
      ],
      value.external_revisions,
    ));
  }
  fragment.append(external);
  return fragment;
}

function artifactCard(descriptor) {
  const card = node("article", undefined, "card");
  const heading = node("h4", displayName(descriptor.role));
  heading.append(" ", status(descriptor.availability));
  card.append(heading);
  card.append(factList([
    ["Media type", descriptor.media_type],
    ["Size", `${descriptor.size} bytes`],
    ["SHA-256", descriptor.sha256, true],
  ]));
  const button = node("button", descriptor.availability === "AVAILABLE" ? "Retrieve plain text" : "Artifact is too large", "artifact-button");
  button.type = "button";
  button.disabled = descriptor.availability !== "AVAILABLE";
  const result = node("pre", undefined, "evidence artifact-result");
  result.hidden = true;
  button.addEventListener("click", async () => {
    button.disabled = true;
    result.hidden = false;
    result.textContent = "Loading plain text…";
    announce(`Retrieving ${displayName(descriptor.role)}.`);
    try {
      const response = await fetch(`${API_ROOT}/artifacts/${descriptor.artifact_key}`, {
        credentials: "same-origin",
        headers: {"Accept": "text/plain"},
      });
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}.`);
      }
      result.textContent = await response.text();
      announce(`${displayName(descriptor.role)} retrieved as plain text.`);
    } catch (error) {
      result.textContent = "The artifact could not be retrieved. Restart the local workbench and try again.";
      announce("Artifact retrieval failed.");
    } finally {
      button.disabled = false;
    }
  });
  card.append(button, result);
  return card;
}

function renderArtifacts(detail) {
  const wrapper = section("Artifacts", "Content is not fetched until you choose Retrieve plain text. HTML and Markdown remain literal text.");
  const grid = node("div", undefined, "card-grid");
  for (const descriptor of detail.artifacts) {
    grid.append(artifactCard(descriptor));
  }
  wrapper.append(grid);
  return wrapper;
}

async function loadRecord(record) {
  for (const button of elements.recordList.querySelectorAll("button")) {
    button.setAttribute("aria-current", String(button.dataset.recordKey === record.record_key));
  }
  elements.recordView.hidden = false;
  elements.recordKind.textContent = displayName(record.kind);
  elements.recordHeading.textContent = `${displayName(record.kind)} details`;
  elements.recordState.replaceWith(status(record.status));
  elements.recordState = document.querySelector("#record-view .section-heading .status");
  clear(elements.recordSummary);
  clear(elements.recordContent);
  elements.recordContent.append(node("p", "Loading record details…"));
  announce(`Loading ${recordLabel(record)}.`);
  try {
    const response = await fetch(`${API_ROOT}/records/${record.record_key}`, {
      credentials: "same-origin",
      headers: {"Accept": "application/json"},
    });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}.`);
    }
    const detail = await response.json();
    renderRecordSummary(record, detail);
    clear(elements.recordContent);
    elements.recordContent.append(renderRelationships(detail));
    if (detail.kind === "OBSERVATION") {
      elements.recordContent.append(renderObservation(detail));
    } else if (detail.kind === "DIAGNOSIS") {
      elements.recordContent.append(renderDiagnosis(detail));
    } else if (detail.kind === "REFINEMENT") {
      elements.recordContent.append(renderRefinement(detail));
    } else {
      elements.recordContent.append(renderCorpus(detail));
    }
    elements.recordContent.append(renderArtifacts(detail));
    elements.recordHeading.focus();
    announce(`${recordLabel(record)} loaded.`);
  } catch (error) {
    clear(elements.recordContent);
    elements.recordContent.append(node("p", "The record details are unavailable.", "error"));
    elements.recordHeading.focus();
    announce("Record details could not be loaded.");
  }
}

async function start() {
  renderStateKey();
  try {
    const response = await fetch(`${API_ROOT}/workbench`, {
      credentials: "same-origin",
      headers: {"Accept": "application/json"},
    });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}.`);
    }
    const projection = await response.json();
    renderOverview(projection);
    renderNavigation(projection);
    announce(`${projection.counts.record_count} records are ready.`);
  } catch (error) {
    elements.sessionState.replaceWith(status("FAILED"));
    elements.sessionState = document.querySelector("#session-overview .section-heading .status");
    elements.sessionMessage.textContent = "The workbench projection is unavailable. Restart the local workbench and try again.";
    announce("The workbench projection is unavailable.");
  }
}

start();
