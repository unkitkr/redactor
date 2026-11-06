import { UI, cells, element, metric, number, scrollableTable, table } from "/static/format.js";

function caseTable(report) {
  const labels = [...new Set(
    report.cases.flatMap((item) => item.metrics.map((entry) => entry.label)),
  )];
  const { node, body } = table(
    ["Case", ...labels],
    `Per-case measurements for ${report.model}`,
  );

  for (const item of report.cases) {
    const row = element("tr");
    const values = labels.map((label) => {
      const result = item.metrics.find((entry) => entry.label === label);
      return result ? metric(result) : UI.missing;
    });
    cells(row, [item.case_id, ...values]);
    body.append(row);
  }

  return scrollableTable(
    node, `Per-case measurements for ${report.model}`, "table-scroll case-table",
  );
}

export function reportDetails(report) {
  const content = element("div", null, "report-details");
  const context = element("dl", null, "report-metadata");
  const metadata = [
    ["Context", report.context],
    ["Platform", report.platform],
    ["Mode", report.mode],
    ["Verifier", report.verifier_version],
    ["Scope", report.scope],
    ["Cases", number(report.case_count)],
    ["Corpus SHA256", report.corpus_sha256],
    ["Source", report.source],
  ];

  for (const [label, value] of metadata) {
    context.append(element("dt", label), element("dd", value || UI.missing));
  }
  content.append(context);

  const measurements = element("dl", null, "report-metrics");
  for (const item of report.metrics) {
    measurements.append(element("dt", item.label), element("dd", metric(item)));
  }
  content.append(element("h3", "All measurements"), measurements);

  if (report.cases?.length) {
    const details = element("details", null, "case-details");
    details.append(element("summary", `${number(report.cases.length)} case results`));
    let rendered = false;
    details.addEventListener("toggle", () => {
      if (details.open && !rendered) {
        details.append(caseTable(report));
        rendered = true;
      }
    });
    content.append(details);
  }
  return content;
}

export function renderImages(images) {
  const gallery = document.getElementById("benchmark-images");
  gallery.replaceChildren();

  for (const item of images) {
    const url = new URL(item.url, window.location.origin);
    if (url.origin !== window.location.origin) continue;
    if (!["http:", "https:"].includes(url.protocol)) continue;

    const figure = element("figure", null, "image-card");
    const image = element("img");
    image.src = url.href;
    image.alt = `Synthetic OCR reference input: ${item.case_id}`;
    image.loading = "lazy";

    const link = element("a");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute(
      "aria-label",
      `Open reference image ${item.case_id} in a new tab`,
    );
    link.append(image);
    figure.append(link, element("figcaption", item.case_id));
    gallery.append(figure);
  }
  document.getElementById("image-section").hidden = !gallery.children.length;
}
