import {
  UI, cells, element, empty, metric, notice, number, request, scrollableTable, table,
} from "/static/format.js";
import { renderImages, reportDetails } from "/static/benchmark_details.js";

const GROUPS = Object.freeze({
  text: "Text detection",
  ocr: "OCR accuracy",
  throughput: "Pipeline throughput",
  diagnostic: "Diagnostics",
});
const SUMMARY_METRICS = Object.freeze({
  text: [
    "Precision", "Recall", "F1", "False accepts",
    "Clinical overlaps", "Evaluation time",
  ],
  ocr: [
    "Identifiers localized", "Identifier targets", "Character error rate",
    "Boxes overlapping clinical text", "Inference time",
  ],
  throughput: [
    "Rows", "Elapsed time", "Rows per second", "Peak cgroup memory",
  ],
  diagnostic: [],
});

function appendReport(body, report, labels, identifier) {
  const row = element("tr");
  const model = element("div", null, "model-name");
  model.append(
    element("strong", report.model || "Not recorded"),
    element("small", report.mode || UI.missing, "cell-secondary"),
  );
  const detailRow = element("tr", null, "report-detail-row");
  detailRow.id = identifier;
  detailRow.hidden = true;
  const detailCell = element("td");
  detailCell.colSpan = labels.length + 2;
  detailRow.append(detailCell);

  const button = element("button", "Details", "detail-button");
  button.type = "button";
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", identifier);
  button.addEventListener("click", () => {
    if (!detailCell.children.length) detailCell.append(reportDetails(report));
    detailRow.hidden = !detailRow.hidden;
    button.setAttribute("aria-expanded", String(!detailRow.hidden));
    button.textContent = detailRow.hidden ? "Details" : "Close";
  });

  const values = labels.map((label) => {
    const item = report.metrics.find((entry) => entry.label === label);
    return item ? metric(item) : UI.missing;
  });
  cells(row, [model, ...values, button]);
  body.append(row, detailRow);
}

function comparison(kind, reports) {
  const section = element("section", null, "panel benchmark-group");
  const heading = element("div", null, "panel-heading");
  heading.append(element("h2", GROUPS[kind]));
  section.append(heading);
  const contexts = [...new Set(reports.map((report) => report.context))];

  contexts.forEach((context, groupIndex) => {
    section.append(element("h3", context || "Context not recorded", "comparison-context"));
    const labels = SUMMARY_METRICS[kind];
    const { node, body } = table(
      ["Model / configuration", ...labels, "Report"],
      `${GROUPS[kind]}: ${context}`,
    );
    reports.filter((report) => report.context === context).forEach((report, index) => {
      appendReport(body, report, labels, `report-${kind}-${groupIndex}-${index}`);
    });
    section.append(scrollableTable(node, `${GROUPS[kind]}: ${context}`));
  });
  return section;
}

export function createBenchmarks() {
  const search = document.getElementById("benchmark-search");
  const kind = document.getElementById("benchmark-kind");
  const refresh = document.getElementById("benchmark-refresh");
  const container = document.getElementById("benchmark-reports");
  const banner = document.getElementById("benchmark-notice");
  let reports = [];
  let loaded = false;
  let inFlight = false;

  function render() {
    const query = search.value.trim().toLocaleLowerCase();
    const filtered = reports.filter((report) => {
      const searchable = [
        report.model, report.mode, report.context, report.verifier_version, report.scope,
      ].join(" ").toLocaleLowerCase();
      return (!kind.value || report.kind === kind.value) && searchable.includes(query);
    });
    container.replaceChildren();
    for (const group of Object.keys(GROUPS)) {
      const matches = filtered.filter((report) => report.kind === group);
      if (matches.length) container.append(comparison(group, matches));
    }
    if (!filtered.length) {
      container.append(empty(reports.length
        ? "No reports match these filters."
        : "No benchmark reports are available yet."));
    }
    document.getElementById("benchmark-count").textContent =
      `${number(filtered.length)} of ${number(reports.length)} reports`;
  }

  async function load(force = false) {
    if (inFlight || (loaded && !force)) return;
    inFlight = true;
    refresh.disabled = true;
    notice(banner, "Loading benchmark reports…");
    try {
      const snapshot = await request("/api/benchmarks");
      if (snapshot.status !== "ready") throw new Error("unavailable");
      reports = snapshot.reports;
      loaded = true;
      render();
      renderImages(snapshot.images ?? []);
      const issues = document.getElementById("benchmark-issues");
      issues.replaceChildren();
      for (const issue of snapshot.issues ?? []) {
        issues.append(element("p", `${issue.source}: ${issue.reason}`, "notice"));
      }
      notice(banner, "");
    } catch {
      notice(banner, loaded
        ? "Could not refresh benchmarks. Previous reports may be stale."
        : "Benchmark reports are unavailable. Refresh to retry.");
      if (!loaded) render();
    } finally {
      inFlight = false;
      refresh.disabled = false;
    }
  }

  search.addEventListener("input", render);
  kind.addEventListener("change", render);
  refresh.addEventListener("click", () => load(true));
  return { load };
}
