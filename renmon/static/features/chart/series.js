import { $ } from "../../shared/dom.js";
import { node, labelOf } from "../../shared/display.js";
export function createSeriesPicker({ active, getCharted, colorOf, onChange }) {
  const rows = new Map();
  function render() {
    const signals = active(),
      selected = getCharted();
    for (const [code, row] of rows)
      if (!signals.some((s) => s.code === code)) {
        row.label.remove();
        rows.delete(code);
        selected.delete(code);
      }
    $("legend").replaceChildren();
    for (const signal of signals) {
      let row = rows.get(signal.code);
      if (!row) {
        const label = node("label", undefined, "series-option");
        const check = node("input");
        check.type = "checkbox";
        check.setAttribute("aria-label", "Порівнювати " + signal.code);
        const caption = node("span");
        label.append(check, caption);
        row = { label, check, caption };
        rows.set(signal.code, row);
        $("series-options").append(label);
      }
      // Resolve the current set; it can be replaced after a failed API update.
      row.check.onchange = () => {
        row.check.checked
          ? getCharted().add(signal.code)
          : getCharted().delete(signal.code);
        onChange();
      };
      row.caption.textContent = `${signal.code} · ${labelOf(signal)}`;
      row.check.checked = selected.has(signal.code);
      if (row.check.checked) {
        const key = node(
          "span",
          `● ${signal.code}${signal.unit ? " · " + signal.unit : ""}`,
        );
        key.style.color = colorOf(signal);
        $("legend").append(key);
      }
    }
    $("series-summary").textContent =
      `Параметри для порівняння · ${signals.filter((s) => selected.has(s.code)).length}/${signals.length}`;
    $("series-empty").hidden = signals.length > 0;
  }
  return { render };
}
