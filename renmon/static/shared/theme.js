import { $ } from "./dom.js";
export function setupTheme(redraw) {
  let light = true;
  try {
    light = localStorage.getItem("renmon-theme") !== "dark";
  } catch {}
  function apply() {
    document.documentElement.dataset.theme = light ? "light" : "dark";
    const label = light ? "Увімкнути темну тему" : "Увімкнути світлу тему";
    $("theme-toggle").textContent = light ? "☾" : "☀";
    $("theme-toggle").title = label;
    $("theme-toggle").setAttribute("aria-label", label);
    $("theme-toggle").setAttribute("aria-pressed", String(light));
  }
  apply();
  $("theme-toggle").onclick = () => {
    light = !light;
    apply();
    try {
      localStorage.setItem("renmon-theme", light ? "light" : "dark");
    } catch {}
    redraw();
  };
}
