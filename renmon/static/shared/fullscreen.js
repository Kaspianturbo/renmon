// A viewport overlay works consistently in desktop and Android WebViews.
export function createFullscreen(redraw) {
  const entries = new Map(),
    stack = [];
  let inert = [];
  function sync() {
    for (const [element, previous] of inert) element.inert = previous;
    inert = [];
    const top = stack.at(-1);
    if (top) {
      let child = top;
      while (child.parentElement && child !== document.body) {
        for (const sibling of child.parentElement.children) {
          if (sibling !== child) {
            inert.push([sibling, sibling.inert]);
            sibling.inert = true;
          }
        }
        child = child.parentElement;
      }
    }
    document.body.classList.toggle("panel-expanded", !!top);
    for (const [panel, entry] of entries) {
      const expanded = stack.includes(panel);
      panel.classList.toggle("expanded", expanded);
      panel.style.zIndex = expanded ? String(1000 + stack.indexOf(panel)) : "";
      entry.button.setAttribute("aria-expanded", String(expanded));
      entry.button.title = expanded ? "Згорнути" : "На весь екран";
      entry.button.setAttribute(
        "aria-label",
        `${expanded ? "Згорнути" : "Розгорнути"} ${entry.label}`,
      );
      if (!entry.icon)
        entry.button.textContent = expanded ? "Згорнути" : "На весь екран";
    }
    requestAnimationFrame(redraw);
  }
  function close(panel) {
    const index = stack.indexOf(panel);
    if (index < 0) return;
    stack.splice(index);
    sync();
    entries.get(panel)?.button.focus();
  }
  function register(panel, button, label, icon = false) {
    entries.set(panel, { button, label, icon });
    button.setAttribute("aria-expanded", "false");
    button.onclick = () => {
      if (stack.includes(panel)) close(panel);
      else {
        if (stack.length && !stack.at(-1).contains(panel)) stack.length = 0;
        stack.push(panel);
        sync();
        button.focus();
      }
    };
    return () => {
      close(panel);
      entries.delete(panel);
    };
  }
  document.addEventListener("keydown", (event) => {
    const top = stack.at(-1);
    if (!top) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close(top);
    }
    if (event.key !== "Tab") return;
    const controls = [
      ...top.querySelectorAll("button, select, input, summary"),
    ].filter((element) => !element.disabled && element.getClientRects().length);
    const first = controls[0],
      last = controls.at(-1);
    if (
      event.shiftKey &&
      (document.activeElement === first ||
        !top.contains(document.activeElement))
    ) {
      event.preventDefault();
      last?.focus();
    } else if (
      !event.shiftKey &&
      (document.activeElement === last || !top.contains(document.activeElement))
    ) {
      event.preventDefault();
      first?.focus();
    }
  });
  return { register, close };
}
