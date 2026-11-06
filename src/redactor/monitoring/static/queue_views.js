import { UI, cells, element, empty, number, table, timestamp } from "/static/format.js";

export function renderRuns(runs, selected, select) {
  const latest = element("option", "Latest available run");
  latest.value = "";
  select.replaceChildren(latest);
  for (const run of runs) {
    const option = element(
      "option",
      `${run.processing_version} · ${number(run.task_count)} tasks`,
    );
    option.value = run.processing_version;
    select.append(option);
  }
  if (selected && !runs.some((run) => run.processing_version === selected)) {
    const option = element("option", `${selected} · selected run`);
    option.value = selected;
    select.append(option);
  }
  select.value = selected;
}

export function renderSummary(snapshot) {
  const container = document.getElementById("queue-summary");
  container.replaceChildren();
  const entries = [
    ["Tasks", snapshot.task_count, "Across all pipeline steps"],
    ["Published", snapshot.published_files, "Files accepted for publication"],
    ["Quarantined", snapshot.quarantined_files, "Files withheld from publication"],
    ["Resolution tasks", snapshot.resolve_tasks, "Run-level identity work"],
  ];
  for (const [label, value, description] of entries) {
    const item = element("div", null, "summary-card");
    item.append(
      element("p", label, "summary-label"),
      element("p", number(value), "summary-value"),
      element("p", description, "summary-detail"),
    );
    container.append(item);
  }
}

export function renderSteps(steps) {
  const container = document.getElementById("queue-steps");
  const { node, body } = table(
    ["Step", "Pending", "Running", "Succeeded", "Failed", "Total"],
    "Committed task counts by pipeline step",
  );
  for (const step of steps) {
    const row = element("tr");
    const counts = ["pending", "running", "succeeded", "failed", "total"]
      .map((status) => number(step[status]));
    cells(row, [element("span", step.step, "step-name"), ...counts]);
    body.append(row);
  }
  container.replaceChildren(steps.length
    ? node
    : empty("No pipeline steps have been registered for this run."));
}

export function renderTasks(tasks) {
  const container = document.getElementById("queue-tasks");
  const { node, body } = table(
    ["Task", "Step", "State", "Attempts", "Durable checkpoint", "Updated", "Failure code"],
    "Most recently updated durable tasks",
  );
  for (const task of tasks) {
    const row = element("tr");
    const identifier = element("code", String(task.task_id).slice(0, 12), "task-id");
    identifier.title = task.task_id;
    const status = element("span", task.status, "status-pill");
    if (["pending", "running", "succeeded", "failed"].includes(task.status)) {
      status.classList.add(`status-${task.status}`);
    }
    const checkpoint = element("div", task.checkpoint_records == null
      ? UI.missing
      : `${number(task.checkpoint_records)} records`);
    if (task.input_offset != null) {
      checkpoint.append(element(
        "small", `${number(task.input_offset)} source bytes`, "cell-secondary",
      ));
    }
    cells(row, [
      identifier, task.step, status, number(task.attempt_count), checkpoint,
      timestamp(task.updated_at), task.failure_code || UI.missing,
    ]);
    body.append(row);
  }
  container.replaceChildren(tasks.length
    ? node
    : empty("No tasks have been registered for this run."));
}
