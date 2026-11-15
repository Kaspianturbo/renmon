import { $ } from "../../shared/dom.js";
import { fmt } from "../../shared/display.js";
export function createTiming({ getState, isBusy }) {
  function renderTiming() {
    const recent = getState().samples.slice(-6),
      last = recent.at(-1),
      target = getState().interval || Number($("interval").value);
    const reads = recent.map((p) => p.elapsed).filter(Number.isFinite),
      avg = reads.reduce((a, b) => a + b, 0) / Math.max(reads.length, 1);
    const period =
      recent.length > 1 ? (last.at - recent[0].at) / (recent.length - 1) : null;
    $("timing").textContent = last
      ? `Задано ${fmt(target)} с · фактично ${period ? fmt(period) + " с" : "вимірюємо…"} · читання ${Math.round(avg * 1000)} мс · запитів за цикл: ${last.requests ?? "—"}`
      : "Очікування першого вимірювання";
    const slow =
      getState().mode === "live" &&
      isBusy() &&
      reads.length >= 3 &&
      avg > target + Math.max(0.01, target * 0.1);
    $("pace-warning").hidden = !slow;
    if (slow)
      $("pace-warning").textContent =
        `Читання займає близько ${fmt(avg)} с — довше за задані ${fmt(target)} с. Дані оновлюються з фактичною швидкістю адаптера. Приберіть частину датчиків із плиток або збільште інтервал. Вимкнення серії на графіку не зменшує кількість запитів.`;
  }
  return { renderTiming };
}
