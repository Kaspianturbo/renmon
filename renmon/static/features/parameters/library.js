import { $ } from "../../shared/dom.js";
import { node, labelOf } from "../../shared/display.js";
export function createSignalLibrary({
  getCatalog,
  getSelected,
  isUpdating,
  setSignal,
}) {
  let signalsSignature = "";
  function renderSignals() {
    const { max_signals: limit, signals } = getCatalog();
    const query = $("search").value.toLowerCase();
    const signature = JSON.stringify([
      getCatalog().ecu,
      query,
      limit,
      [...getSelected()],
      isUpdating(),
    ]);
    if (signature === signalsSignature) return;
    signalsSignature = signature;
    $("signals").replaceChildren();
    $("count").textContent = getSelected().size + "/" + limit;
    for (const s of signals) {
      if (
        !`${s.code} ${s.label} ${s.label_uk || ""} ${s.unit}`
          .toLowerCase()
          .includes(query)
      )
        continue;
      const l = node(
          "label",
          undefined,
          "signal" + (getSelected().has(s.code) ? " selected" : ""),
        ),
        c = node("input");
      c.type = "checkbox";
      c.checked = getSelected().has(s.code);
      c.disabled = isUpdating() || (!c.checked && getSelected().size >= limit);
      c.onchange = () => setSignal(s.code, c.checked);
      let t = node("span");
      t.append(
        node("b", s.code + " · " + s.unit),
        node("span", labelOf(s), "signal-uk"),
        node("span", s.label, "signal-en"),
      );
      l.title = s.label;
      l.append(c, t);
      $("signals").append(l);
    }
  }

  return { renderSignals };
}
