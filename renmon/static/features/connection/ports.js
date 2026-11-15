import { $ } from "../../shared/dom.js";
import { node } from "../../shared/display.js";
export function createPortPicker({
  api,
  isBusy,
  selectAdapter,
  showError,
  isAndroid,
}) {
  function portCaption() {
    $("port-toggle").textContent = $("port").value || "Оберіть ELM…";
  }
  function updatePorts(devices) {
    const previous = $("port").value;
    $("port").replaceChildren();
    const placeholder = node("option", "Оберіть ELM…");
    placeholder.value = "";
    $("port").append(placeholder);
    for (const port of devices) {
      const o = node("option", port);
      o.value = port;
      $("port").append(o);
    }
    if (previous && !devices.includes(previous)) {
      const o = node("option", previous + " · недоступний");
      o.value = previous;
      $("port").append(o);
    }
    $("port").value = previous;
    portCaption();
  }
  function closePorts() {
    $("port-options").hidden = true;
    $("port-toggle").setAttribute("aria-expanded", "false");
  }
  let portsLoading = false;
  $("port-toggle").onclick = async () => {
    if (portsLoading || isBusy()) return;
    if (!$("port-options").hidden) {
      closePorts();
      return;
    }
    portsLoading = true;
    $("port-toggle").setAttribute("aria-busy", "true");
    try {
      const result = await api("ports");
      updatePorts(result.ports);
      if (isBusy() || $("mode").value !== "live") return;
      const list = $("port-options");
      list.replaceChildren();
      for (const port of ["", ...result.ports]) {
        const option = node("button", port || "Не підключати");
        option.type = "button";
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", String(port === $("port").value));
        option.onclick = () => {
          $("port").value = port;
          portCaption();
          closePorts();
          $("port-toggle").focus();
          selectAdapter();
        };
        list.append(option);
      }
      if (!result.ports.length)
        list.append(
          node(
            "p",
            isAndroid()
              ? "Спарте ELM у налаштуваннях Bluetooth і відкрийте список повторно."
              : "Немає доступних портів",
            "hint",
          ),
        );
      list.hidden = false;
      $("port-toggle").setAttribute("aria-expanded", "true");
      list.querySelector("[aria-selected=true]")?.focus();
    } catch (e) {
      showError("Не вдалося оновити підключення: " + e.message);
    } finally {
      portsLoading = false;
      $("port-toggle").removeAttribute("aria-busy");
    }
  };
  $("port-options").onkeydown = (e) => {
    const options = [...$("port-options").querySelectorAll("button")],
      i = options.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      options[
        (i + (e.key === "ArrowDown" ? 1 : options.length - 1)) % options.length
      ]?.focus();
    }
    if (e.key === "Escape") {
      closePorts();
      $("port-toggle").focus();
    }
  };
  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".port-picker")) closePorts();
  });
  return { updatePorts, portCaption, closePorts };
}
