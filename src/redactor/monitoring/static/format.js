export const UI = Object.freeze({
  pollMilliseconds: 5000,
  requestMilliseconds: 10000,
  missing: "n/a",
});

export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

export function number(value, digits = 0) {
  if (typeof value !== "number" || !Number.isFinite(value)) return UI.missing;
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function metric(item) {
  if (item.value === null || item.value === undefined) return UI.missing;
  if (typeof item.value !== "number") return String(item.value);
  if (item.unit === "percent") return `${number(item.value * 100, 1)}%`;
  const suffix = {
    seconds: " s", mib: " MiB", count: "", text: "",
  }[item.unit] ?? "";
  return number(item.value, item.unit === "count" ? 0 : 2) + suffix;
}

export function timestamp(value) {
  if (value === null || value === undefined || value === "") return UI.missing;
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? UI.missing : date.toLocaleString();
}

export function table(headers, caption) {
  const node = element("table");
  node.append(element("caption", caption, "sr-only"));
  const head = element("thead");
  const row = element("tr");
  for (const label of headers) {
    const cell = element("th", label);
    cell.scope = "col";
    row.append(cell);
  }
  head.append(row);
  const body = element("tbody");
  node.append(head, body);
  return { node, body };
}

export function cells(row, values) {
  for (const value of values) {
    const cell = element("td");
    cell.append(value instanceof Node
      ? value
      : document.createTextNode(String(value ?? UI.missing)));
    row.append(cell);
  }
}

export function scrollableTable(tableNode, label, className = "table-scroll") {
  const container = element("div", null, className);
  container.tabIndex = 0;
  container.setAttribute("role", "region");
  container.setAttribute("aria-label", label);
  container.append(tableNode);
  return container;
}

export function empty(message) {
  return element("p", message, "empty-state");
}

export function notice(node, message) {
  node.textContent = message;
  node.hidden = !message;
}

export async function request(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UI.requestMilliseconds);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("request_failed");
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}
