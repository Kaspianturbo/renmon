import { $ } from "./dom.js";
export function setupLayout(draw) {
  const mobile = window.matchMedia("(max-width: 700px)");
  let desktopCollapsed = false;
  try {
    desktopCollapsed =
      localStorage.getItem("renmon-sidebar-collapsed") === "true";
  } catch {}
  function setSidebar(collapsed, focus = false) {
    const sidebar = $("sidebar");
    sidebar.hidden = collapsed;
    $("layout").classList.toggle("sidebar-collapsed", collapsed);
    $("sidebar-toggle").setAttribute("aria-expanded", String(!collapsed));
    $("sidebar-toggle").title = collapsed
      ? "Розгорнути бічну панель"
      : "Згорнути бічну панель";
    const modal = mobile.matches && !collapsed;
    $("sidebar-backdrop").hidden = !modal;
    document.body.classList.toggle("sidebar-open", modal);
    document.querySelector(".workspace").inert = modal;
    if (modal) {
      sidebar.setAttribute("role", "dialog");
      sidebar.setAttribute("aria-modal", "true");
    } else {
      sidebar.removeAttribute("role");
      sidebar.removeAttribute("aria-modal");
    }
    if (!mobile.matches) {
      desktopCollapsed = collapsed;
      try {
        localStorage.setItem("renmon-sidebar-collapsed", String(collapsed));
      } catch {}
    }
    if (focus) (modal ? $("sidebar-close") : $("sidebar-toggle")).focus();
    requestAnimationFrame(draw);
  }
  $("sidebar-toggle").onclick = () =>
    setSidebar(!$("sidebar").hidden, mobile.matches);
  $("sidebar-close").onclick = () => setSidebar(true, true);
  $("sidebar-backdrop").onclick = () => setSidebar(true, true);
  mobile.addEventListener("change", () =>
    setSidebar(mobile.matches || desktopCollapsed),
  );
  setSidebar(mobile.matches || desktopCollapsed);
  document.addEventListener("keydown", (event) => {
    if (!mobile.matches || $("sidebar").hidden) return;
    if (event.key === "Escape") {
      setSidebar(true, true);
      return;
    }
    if (event.key !== "Tab") return;
    const controls = [
      ...$("sidebar").querySelectorAll("button, input, select, [tabindex='0']"),
    ].filter((element) => !element.disabled && element.getClientRects().length);
    const first = controls[0],
      last = controls.at(-1);
    if (
      event.shiftKey &&
      (document.activeElement === first ||
        !$("sidebar").contains(document.activeElement))
    ) {
      event.preventDefault();
      last?.focus();
    } else if (
      !event.shiftKey &&
      (document.activeElement === last ||
        !$("sidebar").contains(document.activeElement))
    ) {
      event.preventDefault();
      first?.focus();
    }
  });
}
