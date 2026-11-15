import { fmt, displayValue } from "./display.js";
export function createTimeSeries({
  getState,
  graphed,
  colorOf,
  canvas,
  hover,
  compact = false,
  windowSeconds,
  comparison,
  isCurrentMode,
}) {
  let plotted = [];
  let contextKey = "";
  let plottedEnd = 0;
  function draw() {
    const w = canvas.clientWidth,
      h = canvas.clientHeight,
      dpr = window.devicePixelRatio || 1;
    if (!w || !h) return;
    const theme = getComputedStyle(document.documentElement);
    const gridColor = theme.getPropertyValue("--line").trim();
    const mutedColor = theme.getPropertyValue("--muted").trim();
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const c = canvas.getContext("2d");
    c.scale(dpr, dpr);
    const state = getState();
    const sig = graphed();
    const duration = windowSeconds();
    const compare = comparison();
    const currentMode = isCurrentMode();
    const nextKey = JSON.stringify([
      state.mode,
      state.started,
      currentMode,
      sig.map((s) => s.code),
      duration,
      compare,
    ]);
    const history = currentMode ? state.samples : [];
    const latest = history.findLast((p) =>
      sig.some((s) => Number.isFinite(p.values[s.code])),
    );
    const end =
      latest?.at ?? (nextKey === contextKey ? plottedEnd : Date.now() / 1000);
    const start = end - duration;
    const samples = latest
      ? history.filter((p) => p.at >= start && p.at <= end)
      : [];
    plotted = samples;
    plottedEnd = end;
    if (nextKey !== contextKey) {
      contextKey = nextKey;
      hover.textContent =
        "Торкніться графіка або наведіть курсор, щоб побачити значення.";
    }
    const left = compact ? 44 : 64,
      right = w - 14,
      top = 20,
      bottom = h - 30;
    c.font = "10px monospace";
    c.lineWidth = 1;
    const ticks = w < 260 ? 1 : 4;
    for (let k = 0; k <= ticks; k++) {
      const x = left + ((right - left) * k) / ticks;
      c.strokeStyle = gridColor;
      c.beginPath();
      c.moveTo(x, top);
      c.lineTo(x, bottom);
      c.stroke();
      c.fillStyle = mutedColor;
      c.textAlign = "center";
      c.fillText(
        new Date(
          (start + ((end - start) * k) / ticks) * 1000,
        ).toLocaleTimeString("uk-UA"),
        Math.max(30, Math.min(w - 30, x)),
        h - 9,
      );
    }
    sig.forEach((s, i) => {
      const vals = samples.map((p) => p.values[s.code]).filter(Number.isFinite);
      const hi = vals.length ? Math.max(...vals) : 1;
      let lo = vals.length ? Math.min(...vals) : 0;
      if (lo === hi) lo -= 1;
      const lane = compare
          ? bottom - top
          : (bottom - top) / Math.max(sig.length, 1),
        y0 = compare ? top : top + i * lane,
        y1 = y0 + lane - 18;
      c.textAlign = "left";
      c.fillStyle = colorOf(s);
      if (!compare) {
        c.fillText(s.code, 0, y0 + 9);
        c.fillText(fmt(hi), 0, y0 + 22);
        c.fillText(fmt(lo), 0, y1);
        c.strokeStyle = gridColor;
        c.beginPath();
        c.moveTo(left, y1);
        c.lineTo(right, y1);
        c.stroke();
      }
      c.strokeStyle = colorOf(s);
      c.lineWidth = 1.8;
      c.beginPath();
      let pen = false,
        previousY = 0;
      for (const p of samples) {
        const v = p.values[s.code];
        if (!Number.isFinite(v)) {
          if (p.errors[s.code]) pen = false;
          continue;
        }
        const x = left + ((p.at - start) / (end - start)) * (right - left),
          y = y1 - ((v - lo) / (hi - lo)) * (y1 - y0);
        if (pen) {
          if (s.kind === "state") c.lineTo(x, previousY);
          c.lineTo(x, y);
        } else c.moveTo(x, y);
        previousY = y;
        pen = true;
      }
      c.stroke();
    });
    if (compare) {
      c.fillStyle = mutedColor;
      c.fillText("100%", 0, top + 8);
      c.fillText("0%", 0, bottom - 18);
    }
    if (!samples.length || !sig.length) {
      c.fillStyle = mutedColor;
      c.textAlign = "center";
      c.font = "13px sans-serif";
      c.fillText(
        !sig.length
          ? "Оберіть параметри над графіком"
          : "Очікування вимірювань",
        w / 2,
        h / 2,
        Math.max(1, w - 24),
      );
    }
  }
  function inspectPoint(e) {
    if (!plotted.length || !graphed().length) return;
    const r = e.target.getBoundingClientRect(),
      ratio = Math.max(
        0,
        Math.min(
          1,
          (e.clientX - r.left - (compact ? 44 : 64)) /
            Math.max(1, r.width - (compact ? 58 : 78)),
        ),
      ),
      end = plottedEnd,
      t = end - windowSeconds() * (1 - ratio);
    hover.textContent = graphed()
      .map((s) => {
        const points = plotted.filter(
          (p) => Object.hasOwn(p.values, s.code) || p.errors[s.code],
        );
        if (!points.length) return s.code + ": —";
        const p = points.reduce((a, b) =>
          Math.abs(a.at - t) < Math.abs(b.at - t) ? a : b,
        );
        return (
          new Date(p.at * 1000).toLocaleTimeString("uk-UA") +
          " · " +
          s.code +
          ": " +
          displayValue(s, p.values[s.code]) +
          " " +
          s.unit +
          (p.errors[s.code] ? " (помилка)" : "")
        );
      })
      .join(" / ");
  }

  canvas.onpointermove = inspectPoint;
  canvas.onpointerdown = inspectPoint;
  return { draw };
}
