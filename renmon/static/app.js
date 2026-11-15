import { createFullscreen } from "./shared/fullscreen.js";
import { setupTheme } from "./shared/theme.js";
import { createSeriesPicker } from "./features/chart/series.js";
import { api } from "./shared/api.js";
import { $ } from "./shared/dom.js";
import { node } from "./shared/display.js";
import { setupLayout } from "./shared/layout.js";
import { createChart } from "./features/chart/view.js";
import { createTiles } from "./features/tiles/view.js";
import { createSignalLibrary } from "./features/parameters/library.js";
import { createTiming } from "./features/monitoring/timing.js";
import { createPortPicker } from "./features/connection/ports.js";
("use strict");
const colors = [
  "#b6ed98",
  "#7bbfea",
  "#ecb479",
  "#c4a4ef",
  "#ef8c9a",
  "#7dd9cb",
  "#d4d276",
  "#aabce9",
  "#f0a9d5",
  "#ffa58d",
];
let catalog,
  selected = new Set(["PR064", "PR383"]),
  charted = new Set(),
  state = { samples: [], codes: [] },
  busy = false,
  lastContact = 0,
  updatingSignals = false,
  signalRevision = 0,
  pollPending = null,
  renderKey = "";
const cadence = {};
async function setCadence(code, value) {
  const before = cadence[code] || 1;
  cadence[code] = value;
  try {
    if (busy) await api("cadence", { code, divisor: value });
  } catch (e) {
    cadence[code] = before;
    showError(e.message);
  } finally {
    renderCards();
  }
}
const fullscreen = createFullscreen(() => draw());
const { renderCards, orderedCodes, drawTiles } = createTiles({
  getState: () => state,
  getSelected: () => selected,
  getCadence: (code) => cadence[code] || 1,
  setCadence,
  fullscreen,
  getLastContact: () => lastContact,
  isUpdating: () => updatingSignals,
  active,
  colorOf,
  setSignal,
  draw: () => draw(),
});
const chart = createChart({ getState: () => state, graphed, colorOf });
const series = createSeriesPicker({
  active,
  getCharted: () => charted,
  colorOf,
  onChange: () => draw(),
});
function draw() {
  series.render();
  if ($("comparison").open) chart.draw();
  drawTiles();
}
$("comparison").addEventListener("toggle", () => {
  if ($("comparison").open) draw();
});
fullscreen.register($("chartpanel"), $("fullscreen"), "спільний графік");
fullscreen.register($("sensorpanel"), $("sensors-fullscreen"), "всі датчики");
setupTheme(() => {
  renderCards();
  draw();
});
const { renderSignals } = createSignalLibrary({
  getCatalog: () => catalog,
  getSelected: () => selected,
  isUpdating: () => updatingSignals,
  setSignal,
});
const { renderTiming } = createTiming({
  getState: () => state,
  isBusy: () => busy,
});
const { updatePorts, portCaption } = createPortPicker({
  api,
  isAndroid: () => catalog?.platform === "android",
  isBusy: () => busy,
  selectAdapter,
  showError,
});
setupLayout(draw);

function showError(e) {
  $("error").hidden = !e;
  $("error").textContent = e || "";
}
let chosenProfile = "";
let profileAction = false;
let autoProfilePort = "";
function updateProfileControls() {
  const live = $("mode").value === "live";
  $("auto-profile-control").hidden = !live;
  const auto = $("auto-profile");
  const select = $("profile-select");
  select.disabled = busy || profileAction || auto.checked;
  for (const id of ["mode", "port-toggle", "auto-connect"])
    $(id).disabled = busy || profileAction;
  auto.disabled =
    !catalog ||
    busy ||
    profileAction ||
    !live ||
    !$("port").value ||
    adapterPending > 0;
  $("start").disabled = !catalog || busy || profileAction || !chosenProfile;

  select.options[0].textContent = auto.checked
    ? profileAction
      ? "Визначення…"
      : chosenProfile
        ? `Авто · ${chosenProfile}`
        : "Не вдалося визначити"
    : "Оберіть профіль";
  if (!profileAction || auto.checked)
    select.value = auto.checked ? "" : chosenProfile;
  $("parameter-library").hidden = !chosenProfile;
  $("sensorpanel").hidden = !chosenProfile;
  $("comparison").hidden = !chosenProfile;
}
async function load(confirmProfile = false) {
  catalog = await api("catalog");
  if (catalog.platform === "android") {
    $("port-label").textContent = "Bluetooth-адаптер";
    $("port-options").setAttribute("aria-label", "Спарені Bluetooth-пристрої");
  }
  catalog.signals = catalog.signals.map((s) => ({
    ...s,
    source_unit: s.unit,
    unit: s.unit === "hPa" ? "mbar" : s.unit,
  }));
  if (confirmProfile) chosenProfile = catalog.ecu;
  else if (chosenProfile !== catalog.ecu) chosenProfile = "";
  const select = $("profile-select");
  const placeholder = node("option", "Оберіть профіль");
  placeholder.value = "";
  placeholder.disabled = true;
  select.replaceChildren(placeholder);
  for (const p of catalog.profiles) {
    const o = node(
      "option",
      p.ecu + " · " + p.doc + (p.available ? "" : " · " + p.reason),
    );
    o.value = p.ecu;
    o.disabled = !p.available;
    select.append(o);
  }
  updateProfileControls();
  selected = new Set(
    [...selected].filter((code) =>
      catalog.signals.some((s) => s.code === code),
    ),
  );
  updatePorts(catalog.ports);
  renderSignals();
  renderCards();
  draw();
}
async function profileChange(path, data) {
  if (profileAction || busy) return;
  profileAction = true;
  updateProfileControls();
  try {
    showError("");
    await api(path, data);
    chosenProfile = "";
    selected.clear();
    charted.clear();
    state = { samples: [], codes: [] };
    await load(true);
    await poll();
  } catch (e) {
    showError(e.message);
    $("profile-select").value = chosenProfile;
  } finally {
    profileAction = false;
    updateProfileControls();
  }
}
$("profile-select").onchange = () =>
  profileChange("profile", { ecu: $("profile-select").value });
$("auto-profile").onchange = () => {
  if ($("auto-profile").checked) {
    autoProfilePort = $("port").value;
    chosenProfile = "";
    return profileChange("detect", {});
  }
  updateProfileControls();
};
async function setSignal(code, enabled) {
  if (updatingSignals) return;
  const before = new Set(selected),
    beforeCharted = new Set(charted);
  enabled ? selected.add(code) : selected.delete(code);
  if (!enabled) charted.delete(code);
  signalRevision++;
  updatingSignals = true;
  renderSignals();
  renderCards();
  draw();
  try {
    if (busy)
      await api("signals", {
        codes: [...selected],
        divisors: Object.fromEntries(
          [...selected].map((c) => [c, cadence[c] || 1]),
        ),
      });
  } catch (e) {
    selected = before;
    charted = beforeCharted;
    showError(e.message);
  } finally {
    signalRevision++;
    updatingSignals = false;
    renderSignals();
    renderCards();
    draw();
  }
}
function active() {
  return orderedCodes()
    .map((c) => catalog?.signals.find((s) => s.code === c))
    .filter(Boolean);
}
function graphed() {
  return active().filter((s) => charted.has(s.code));
}
function colorOf(s) {
  const palette =
    document.documentElement.dataset.theme === "light"
      ? [
          "#356b1f",
          "#156ba4",
          "#925512",
          "#7144aa",
          "#ad364d",
          "#147568",
          "#766609",
          "#47588f",
          "#943b7d",
          "#a33e26",
        ]
      : colors;
  return palette[[...selected].indexOf(s.code) % palette.length];
}
$("mode").onchange = () => {
  $("live").hidden = $("mode").value !== "live";
  if ($("live").hidden) $("auto-profile").checked = false;
  updateProfileControls();
  $("banner").textContent =
    $("mode").value === "demo"
      ? "ДЕМО · Синтетичні значення. З’єднання з автомобілем відсутнє."
      : "АВТОМОБІЛЬ · Читання параметрів ECU — після «Почати».";
};
const modeChanged = $("mode").onchange;
let adapterPending = 0;
let adapterRevision = 0;
async function selectAdapter() {
  if ($("auto-profile").checked && $("port").value !== autoProfilePort) {
    $("auto-profile").checked = false;
    chosenProfile = "";
  }
  adapterPending++;
  adapterRevision++;
  updateProfileControls();
  try {
    await api("adapter", {
      port: $("mode").value === "live" ? $("port").value : "",
      auto_connect: $("mode").value === "live" && $("auto-connect").checked,
    });
    showError("");
  } catch (e) {
    showError(e.message);
  } finally {
    adapterPending--;
    updateProfileControls();
  }
}
$("mode").onchange = () => {
  modeChanged();
  renderCards();
  draw();
  selectAdapter();
};
$("port").onchange = selectAdapter;
$("auto-connect").onchange = selectAdapter;
$("search").oninput = renderSignals;
$("view").onchange = draw;
$("window").onchange = draw;
window.addEventListener("resize", draw);
$("start").onclick = async () => {
  if ($("start").disabled) return;
  try {
    $("start").disabled = true;
    showError("");
    await api("start", {
      mode: $("mode").value,
      codes: [...selected],
      divisors: Object.fromEntries(
        [...selected].map((code) => [code, cadence[code] || 1]),
      ),
      port: $("port").value,
      interval: Number($("interval").value),
      performance: $("performance").checked,
    });
    await poll();
  } catch (e) {
    showError(e.message);
    updateProfileControls();
  }
};
$("export-csv").onclick = async () => {
  $("export-csv").disabled = true;
  try {
    await api("export");
  } catch (e) {
    showError(e.message);
  } finally {
    $("export-csv").disabled = false;
  }
};
$("stop").onclick = async () => {
  try {
    await api("stop", {});
    await poll();
  } catch (e) {
    showError(e.message);
  }
};
function poll() {
  if (!pollPending)
    pollPending = fetchState().finally(() => {
      pollPending = null;
    });
  return pollPending;
}
async function fetchState() {
  const revision = signalRevision;
  const linkRevision = adapterRevision;
  try {
    state = await api("state");
    lastContact = Date.now();
    if (!profileAction && state.ecu && state.ecu !== catalog.ecu) {
      selected.clear();
      charted.clear();
      await load();
    }
    busy = ["connecting", "running", "stopping"].includes(state.status);
    if (busy) {
      if (!updatingSignals && revision === signalRevision) {
        selected = new Set(state.codes);
        charted = new Set([...charted].filter((code) => selected.has(code)));
      }
      $("mode").value = state.mode;
      modeChanged();
    }
    if (busy) $("performance").checked = !!state.performance?.enabled;
    const perf = state.performance;
    $("performance-status").hidden = !perf || perf.status === "demo";
    $("performance-status").textContent = perf
      ? {
          off: "Окреме читання DID",
          demo: "",
          checking:
            "Performance: окреме читання; потрібні щонайменше 2 DID з перевіреною довжиною",
          active: "Performance: об’єднання до 3 DID",
          fallback: "Performance вимкнено для цього з’єднання: " + perf.reason,
        }[perf.status]
      : "";
    $("status").textContent = {
      idle: "Не підключено",
      connecting: "Підключення…",
      running: "● Моніторинг",
      stopping: "Зупинка…",
      stopped: "Зупинено",
      error: "Помилка",
    }[state.status];
    for (const id of [
      "mode",
      "port",
      "interval",
      "port-toggle",
      "auto-connect",
      "performance",
    ])
      $(id).disabled = busy;
    updateProfileControls();
    $("stop").disabled = !busy || state.status === "stopping";
    if (state.error) showError(state.error);
    const link = state.connection;
    $("connection-status").hidden = !link || link.status === "disabled";
    if (link && !adapterPending && linkRevision === adapterRevision)
      $("auto-connect").checked = !!link.auto_connect;
    if (link && link.status !== "disabled") {
      $("connection-status").textContent =
        {
          idle: "Порт обрано · підключення після запуску",
          waiting: "Очікуємо ELM · повтор кожні 3 с",
          connecting: "Підключення до ELM…",
          connected: "● ELM підключений",
        }[link.status] +
        (["waiting", "connecting"].includes(link.status) && link.attempts
          ? " · спроба " + link.attempts
          : "") +
        (link.error ? " · " + link.error : "");
    }
    renderSignals();
    const last = state.samples.at(-1);
    const key = JSON.stringify([
      last?.at,
      state.started,
      state.status,
      [...selected],
      $("mode").value,
      Math.floor(Date.now() / 1000),
    ]);
    if (key !== renderKey) {
      renderKey = key;
      renderCards();
      draw();
    }
    renderTiming();
    $("log").textContent =
      state.log_path || "Журнал буде створено після початку сеансу.";
  } catch (e) {
    showError("Немає зв’язку з Python: " + e.message);
    $("status").textContent = "Інтерфейс від’єднано";
    renderCards();
  }
}
(async () => {
  try {
    await load();
    await poll();
    if (state.connection?.port) {
      $("mode").value = "live";
      $("port").value = state.connection.port;
      portCaption();
      modeChanged();
    }
    schedulePoll();
  } catch (e) {
    showError(e.message);
  }
})();

function schedulePoll() {
  setTimeout(
    async () => {
      await poll();
      schedulePoll();
    },
    state.status === "running" ? 50 : 1000,
  );
}
