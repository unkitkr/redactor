import { UI, notice, request, timestamp } from "/static/format.js";
import {
  renderRuns, renderSteps, renderSummary, renderTasks,
} from "/static/queue_views.js";

const UNAVAILABLE = Object.freeze({
  missing: "No queue database or run is available yet.",
  busy: "The queue database is busy.",
  unavailable: "The queue snapshot is unavailable.",
});

export function createQueue() {
  const select = document.getElementById("run-select");
  const refreshButton = document.getElementById("queue-refresh");
  const banner = document.getElementById("queue-notice");
  const updated = document.getElementById("queue-updated");
  let visible = false;
  let inFlight = false;
  let timer;
  let selectedRun = "";
  let runRevision = 0;
  let hasSnapshot = false;
  renderSummary({});
  renderSteps([]);
  renderTasks([]);

  function unavailable(message) {
    notice(banner, message + (hasSnapshot
      ? " Showing the last successful snapshot; it may be stale."
      : " Refresh to try again."));
    updated.textContent = hasSnapshot
      ? "Snapshot may be stale"
      : "No snapshot available";
  }

  async function refresh() {
    clearTimeout(timer);
    if (!visible || inFlight) return;
    inFlight = true;
    refreshButton.disabled = true;
    const requestedRevision = runRevision;
    const query = selectedRun ? `?run=${encodeURIComponent(selectedRun)}` : "";
    updated.textContent = "Refreshing…";

    try {
      const snapshot = await request(`/api/queue${query}`);
      if (requestedRevision !== runRevision) return;
      if (snapshot.status !== "ready") {
        unavailable(UNAVAILABLE[snapshot.status] ?? UNAVAILABLE.unavailable);
        return;
      }
      renderRuns(snapshot.runs, selectedRun, select);
      renderSummary(snapshot);
      renderSteps(snapshot.steps);
      renderTasks(snapshot.tasks);
      document.getElementById("snapshot-run").textContent =
        `Snapshot run: ${snapshot.processing_version ?? UI.missing}`;
      updated.textContent = `Updated ${timestamp(snapshot.observed_at)}`;
      hasSnapshot = true;
      notice(banner, "");
    } catch {
      unavailable("Could not refresh the queue.");
    } finally {
      inFlight = false;
      refreshButton.disabled = false;
      if (visible) {
        const delay = requestedRevision !== runRevision ? 0 : UI.pollMilliseconds;
        timer = setTimeout(refresh, delay);
      }
    }
  }

  select.addEventListener("change", () => {
    selectedRun = select.value;
    runRevision += 1;
    if (hasSnapshot) {
      notice(banner,
        "Loading the selected run. The previous snapshot remains until it is ready.",
      );
    }
    refresh();
  });
  refreshButton.addEventListener("click", refresh);
  return {
    setVisible(value) {
      visible = value;
      clearTimeout(timer);
      if (visible) refresh();
    },
  };
}
