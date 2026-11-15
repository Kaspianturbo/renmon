import { createTimeSeries } from "../../shared/time-series.js";
import { $ } from "../../shared/dom.js";
import {
  node,
  labelOf,
  interpretation,
  displayValue,
} from "../../shared/display.js";
export function createTiles({
  getState,
  getSelected,
  getCadence,
  setCadence,
  fullscreen,
  getLastContact,
  isUpdating,
  active,
  colorOf,
  setSignal,
  draw,
}) {
  let tileOrder = [];
  let chartModes = new Set();
  try {
    const saved = JSON.parse(
      localStorage.getItem("renmon-tile-charts") || "[]",
    );
    if (Array.isArray(saved))
      chartModes = new Set(saved.filter((v) => typeof v === "string"));
  } catch {}
  function drawTiles() {
    for (const [code, entry] of cardNodes)
      if (chartModes.has(code)) entry.chart.draw();
  }
  try {
    const saved = JSON.parse(localStorage.getItem("renmon-tile-order") || "[]");
    if (Array.isArray(saved))
      tileOrder = [...new Set(saved.filter((c) => typeof c === "string"))];
  } catch {}
  function orderedCodes() {
    return [
      ...tileOrder.filter((c) => getSelected().has(c)),
      ...[...getSelected()].filter((c) => !tileOrder.includes(c)),
    ];
  }
  function saveOrder(codes) {
    tileOrder = [...codes, ...tileOrder.filter((c) => !codes.includes(c))];
    try {
      localStorage.setItem("renmon-tile-order", JSON.stringify(tileOrder));
    } catch {}
    renderCards();
    draw();
  }
  function shiftTile(code, delta) {
    const codes = orderedCodes(),
      from = codes.indexOf(code),
      to = Math.max(0, Math.min(codes.length - 1, from + delta));
    if (from < 0 || from === to) return;
    codes.splice(from, 1);
    codes.splice(to, 0, code);
    saveOrder(codes);
    cardNodes.get(code)?.move.focus();
  }
  let dragging = null;
  function makeMoveHandle(card, code) {
    const move = node("button", "⠿", "move-tile");
    move.type = "button";
    move.title =
      "Перетягніть для зміни порядку. Натисніть для переміщення кнопками.";
    move.setAttribute("aria-label", "Перемістити " + code);
    const menu = node("div", undefined, "move-menu");
    menu.hidden = true;
    for (const [label, delta] of [
      ["← Раніше", -1],
      ["Пізніше →", 1],
    ]) {
      const b = node("button", label);
      b.type = "button";
      b.onclick = () => {
        menu.hidden = true;
        move.setAttribute("aria-expanded", "false");
        shiftTile(code, delta);
      };
      menu.append(b);
    }
    let suppressClick = false;
    move.onclick = () => {
      if (suppressClick) {
        suppressClick = false;
        return;
      }
      menu.hidden = !menu.hidden;
      move.setAttribute("aria-expanded", String(!menu.hidden));
    };
    move.onkeydown = (e) => {
      if (["ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"].includes(e.key)) {
        e.preventDefault();
        shiftTile(code, ["ArrowLeft", "ArrowUp"].includes(e.key) ? -1 : 1);
      }
      if (e.key === "Escape") {
        menu.hidden = true;
        move.setAttribute("aria-expanded", "false");
      }
    };
    move.onpointerdown = (e) => {
      if (e.button !== 0) return;
      dragging = {
        code,
        x: e.clientX,
        y: e.clientY,
        active: false,
        target: null,
        after: false,
      };
      move.setPointerCapture(e.pointerId);
    };
    move.onpointermove = (e) => {
      if (!dragging || dragging.code !== code) return;
      if (
        !dragging.active &&
        Math.hypot(e.clientX - dragging.x, e.clientY - dragging.y) < 8
      )
        return;
      dragging.active = true;
      card.classList.add("dragging");
      menu.hidden = true;
      document
        .querySelectorAll(".drop-before,.drop-after")
        .forEach((el) => el.classList.remove("drop-before", "drop-after"));
      const target = document
        .elementFromPoint(e.clientX, e.clientY)
        ?.closest(".card");
      dragging.target = null;
      if (target && target !== card) {
        const rect = target.getBoundingClientRect();
        const sameRow =
          Math.abs(rect.top - card.getBoundingClientRect().top) < 30;
        dragging.after = sameRow
          ? e.clientX > rect.left + rect.width / 2
          : e.clientY > rect.top + rect.height / 2;
        dragging.target = target.dataset.code;
        target.classList.add(dragging.after ? "drop-after" : "drop-before");
      }
      const panel = $("sensorpanel"),
        scroll = panel.matches(":fullscreen,.expanded")
          ? panel
          : document.scrollingElement;
      if (e.clientY < 75) scroll.scrollBy(0, -20);
      else if (e.clientY > innerHeight - 75) scroll.scrollBy(0, 20);
    };
    const end = (e) => {
      if (!dragging || dragging.code !== code) return;
      const d = dragging;
      dragging = null;
      suppressClick = d.active;
      card.classList.remove("dragging");
      document
        .querySelectorAll(".drop-before,.drop-after")
        .forEach((el) => el.classList.remove("drop-before", "drop-after"));
      if (e.type === "pointerup" && d.active && d.target) {
        const codes = orderedCodes().filter((c) => c !== code),
          at = codes.indexOf(d.target);
        codes.splice(at + (d.after ? 1 : 0), 0, code);
        saveOrder(codes);
      }
      if (move.hasPointerCapture(e.pointerId))
        move.releasePointerCapture(e.pointerId);
    };
    move.onpointerup = end;
    move.onpointercancel = end;
    card.append(menu);
    return move;
  }
  const cardNodes = new Map();
  function renderCards() {
    const samples =
      getState().mode === $("mode").value ? getState().samples : [];
    for (const [code, entry] of cardNodes) {
      if (!getSelected().has(code)) {
        entry.dispose();
        entry.card.remove();
        cardNodes.delete(code);
      }
    }
    $("sensor-count").textContent = getSelected().size;
    $("sensor-mode").textContent =
      $("mode").value === "demo" ? "ДЕМО · штучні дані" : "ECU";
    $("cards-empty").hidden = getSelected().size > 0;
    active().forEach((s) => {
      const latest = samples.findLast(
        (sample) =>
          Object.hasOwn(sample.values, s.code) ||
          Object.hasOwn(sample.errors, s.code),
      );
      const stale =
        latest &&
        (Date.now() / 1000 - latest.at >
          Math.max(5, (getState().interval || 1) * getCadence(s.code) * 3) ||
          Date.now() - getLastContact() > 5000);
      let entry = cardNodes.get(s.code);
      if (!entry) {
        const card = node("article", undefined, "card"),
          code = node("div", s.code, "code");
        card.dataset.code = s.code;
        const remove = node("button", "×", "remove-signal");
        remove.type = "button";
        remove.setAttribute("aria-label", "Прибрати " + s.code);
        remove.title = "Прибрати з моніторингу";
        remove.onclick = () => setSignal(s.code, false);
        const label = node("div", labelOf(s), "label");
        label.title = s.label;
        const value = node(
          "div",
          undefined,
          "value" + (s.kind === "state" ? " state-value" : ""),
        );
        const number = node("span", "—"),
          unit = node("small", s.unit);
        value.append(number, unit);
        const detail = node("p", "", "state-detail"),
          fault = node("p", "", "fault");
        const graph = node("button", "", "graph-toggle");
        const icon = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "svg",
        );
        icon.setAttribute("viewBox", "0 0 24 24");
        icon.setAttribute("width", "17");
        icon.setAttribute("height", "17");
        icon.setAttribute("aria-hidden", "true");
        const line = document.createElementNS(icon.namespaceURI, "path");
        line.setAttribute("d", "M4 4v16h16M7 15l4-5 4 3 5-7");
        line.setAttribute("fill", "none");
        line.setAttribute("stroke", "currentColor");
        line.setAttribute("stroke-width", "1.7");
        line.setAttribute("stroke-linecap", "round");
        line.setAttribute("stroke-linejoin", "round");
        icon.append(line);
        graph.append(icon);
        graph.type = "button";
        graph.onclick = () => {
          chartModes.has(s.code)
            ? chartModes.delete(s.code)
            : chartModes.add(s.code);
          try {
            localStorage.setItem(
              "renmon-tile-charts",
              JSON.stringify([...chartModes]),
            );
          } catch {}
          renderCards();
          draw();
        };
        const expand = node("button", "⛶", "tile-expand");
        expand.type = "button";
        expand.title = "На весь екран";
        expand.setAttribute("aria-label", "Розгорнути " + s.code);
        const plot = node("div", undefined, "tile-plot");
        const canvas = node("canvas");
        canvas.setAttribute("aria-label", "Графік " + s.code);
        const hover = node(
          "div",
          "Торкніться графіка або наведіть курсор",
          "hint tile-hover",
        );
        const rangeLabel = node("label", "Вікно", "tile-window");
        const range = node("select");
        range.setAttribute("aria-label", "Вікно графіка " + s.code);
        for (const [seconds, caption] of [
          [5, "5 с"],
          [10, "10 с"],
          [15, "15 с"],
          [30, "30 с"],
          [60, "1 хв"],
          [300, "5 хв"],
          [900, "15 хв"],
        ]) {
          const option = node("option", caption);
          option.value = seconds;
          range.append(option);
        }
        const control = node("span", undefined, "select-control");
        range.value = "60";
        control.append(range);
        rangeLabel.append(control);
        plot.append(rangeLabel, canvas, hover);
        const chart = createTimeSeries({
          getState,
          graphed: () => active().filter((signal) => signal.code === s.code),
          colorOf,
          canvas,
          hover,
          compact: true,
          isCurrentMode: () => getState().mode === $("mode").value,
          windowSeconds: () => Number(range.value),
          comparison: () => false,
        });
        range.onchange = () => chart.draw();
        const dispose = fullscreen.register(card, expand, s.code, true);
        const move = makeMoveHandle(card, s.code);
        const toolbar = node("div", undefined, "tile-toolbar");
        const cadenceLabel = node("span", undefined, "tile-cadence");
        const cadenceCaption = node("span", "×1");
        cadenceCaption.setAttribute("aria-hidden", "true");
        const cadenceSelect = node("select");
        cadenceSelect.setAttribute(
          "aria-label",
          "Частота опитування " + s.code,
        );
        cadenceSelect.title =
          "Кількість базових циклів між запитами. Спільний DID читається за найчастішим параметром.";
        for (const n of [1, 2, 3, 5, 10]) {
          const option = node(
            "option",
            n === 1 ? "Кожен цикл" : `Кожен ${n}-й цикл`,
          );
          option.value = n;
          cadenceSelect.append(option);
        }
        cadenceSelect.onchange = async () => {
          cadenceSelect.disabled = true;
          await setCadence(s.code, Number(cadenceSelect.value));
          cadenceSelect.disabled = false;
          cadenceSelect.value = getCadence(s.code);
        };
        cadenceLabel.append(cadenceCaption, cadenceSelect);
        toolbar.append(move, cadenceLabel, graph, expand, remove);
        card.append(toolbar, code, label, value, detail, plot, fault);
        $("cards").append(card);
        entry = {
          card,
          cadenceSelect,
          cadenceCaption,
          plot,
          chart,
          dispose,
          code,
          remove,
          number,
          detail,
          fault,
          graph,
          move,
          label,
          unit,
          value,
        };
        cardNodes.set(s.code, entry);
      }
      if (!entry.cadenceSelect.disabled)
        entry.cadenceSelect.value = getCadence(s.code);
      entry.cadenceCaption.textContent = "×" + getCadence(s.code);
      entry.cadenceSelect.title =
        getCadence(s.code) === 1
          ? "Опитувати кожен цикл"
          : `Опитувати кожен ${getCadence(s.code)}-й цикл`;
      entry.label.textContent = labelOf(s);
      entry.label.title = s.label;
      entry.unit.textContent = s.unit;
      entry.value.classList.toggle("state-value", s.kind === "state");
      entry.code.style.color = colorOf(s);
      entry.remove.disabled = isUpdating();
      const value = latest?.values[s.code],
        item = interpretation(s, value);
      entry.number.textContent = displayValue(s, value);
      entry.detail.textContent = item
        ? item.description_uk || item.description || ""
        : "";
      entry.detail.hidden = !entry.detail.textContent;
      entry.number.title =
        s.kind === "state" && Number.isFinite(value)
          ? `Код стану: ${value} · ${item?.label || "Unknown"}`
          : "";
      const fault =
        latest?.errors[s.code] || (stale ? "Застаріле значення" : "");
      entry.fault.textContent = fault;
      entry.fault.hidden = !fault;
      const on = chartModes.has(s.code);
      entry.plot.hidden = !on;
      entry.card.classList.toggle("tile-chart", on);
      entry.graph.title = on ? "Показати значення" : "Показати графік";
      entry.graph.setAttribute("aria-pressed", String(on));
      entry.graph.setAttribute(
        "aria-label",
        (on ? "Показати значення " : "Показати графік ") + s.code,
      );
    });
    if (!dragging) {
      orderedCodes().forEach((code, i) => {
        const card = cardNodes.get(code)?.card;
        if (card && $("cards").children[i] !== card)
          $("cards").insertBefore(card, $("cards").children[i] || null);
      });
    }
  }

  return { renderCards, orderedCodes, drawTiles };
}
