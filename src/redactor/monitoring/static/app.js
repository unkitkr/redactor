import { createQueue } from "/static/queue.js";
import { createBenchmarks } from "/static/benchmarks.js";

function start() {
  const queue = createQueue();
  const benchmarks = createBenchmarks();
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  let active = "queue";

  function select(name, focus = false) {
    active = name;
    for (const tab of tabs) {
      const selected = tab.id === `${name}-tab`;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
      if (selected && focus) tab.focus();
    }
    queue.setVisible(active === "queue" && !document.hidden);
    if (active === "benchmarks") benchmarks.load();
  }

  for (const tab of tabs) {
    tab.addEventListener("click", () => select(tab.id.replace("-tab", "")));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let index;
      if (event.key === "Home") index = 0;
      else if (event.key === "End") index = tabs.length - 1;
      else {
        const direction = event.key === "ArrowRight" ? 1 : -1;
        index = (tabs.indexOf(tab) + direction + tabs.length) % tabs.length;
      }
      select(tabs[index].id.replace("-tab", ""), true);
    });
  }
  document.addEventListener("visibilitychange", () => {
    queue.setVisible(active === "queue" && !document.hidden);
  });
  select(active);
}

start();
