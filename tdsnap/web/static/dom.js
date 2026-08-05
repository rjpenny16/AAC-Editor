/* Small DOM helpers shared by every module. */

const $ = (id) => document.getElementById(id);

function setBusy(button, busy, busyLabel = "") {
  const label = button.querySelector(".btn-label") || button;
  if (busy && !label.dataset.idleLabel) label.dataset.idleLabel = label.textContent;
  if (busy && busyLabel) label.textContent = busyLabel;
  if (!busy && label.dataset.idleLabel) {
    label.textContent = label.dataset.idleLabel;
    delete label.dataset.idleLabel;
  }
  button.classList.toggle("loading", busy);
  button.disabled = busy;
  button.setAttribute("aria-busy", String(busy));
}

function setActivity(message = "") {
  const activity = $("app-activity");
  $("app-activity-text").textContent = message;
  activity.hidden = !message;
  document.body.setAttribute("aria-busy", String(Boolean(message)));
}

function setPreviewBusy(busy, message = "Loading the page layout…") {
  const workspace = document.querySelector(".preview-frame");
  const loading = $("preview-loading");
  workspace.classList.toggle("is-loading", busy);
  workspace.setAttribute("aria-busy", String(busy));
  $("preview-loading-text").textContent = message;
  loading.hidden = !busy;
}

/* Append "<lead> a, b and c" to *container* without building HTML strings. */
function appendNamedList(container, lead, items) {
  const text = document.createElement("span");
  text.textContent = lead;
  container.append(text);
  const list = document.createElement("ul");
  items.forEach((label) => {
    const item = document.createElement("li");
    item.textContent = label;
    list.append(item);
  });
  container.append(list);
}


export { $, setBusy, setActivity, setPreviewBusy, appendNamedList };
