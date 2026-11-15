import { $ } from "../../shared/dom.js";
import { createTimeSeries } from "../../shared/time-series.js";
export function createChart(options) {
  const plot = createTimeSeries({
    ...options,
    canvas: $("chart"),
    hover: $("hover"),
    windowSeconds: () => Number($("window").value),
    comparison: () => $("view").value === "compare",
    isCurrentMode: () => options.getState().mode === $("mode").value,
  });
  return {
    draw() {
      $("chart").style.minHeight =
        ($("view").value === "compare"
          ? 180
          : Math.max(180, options.graphed().length * 90 + 50)) + "px";
      $("chartnote").textContent =
        $("view").value === "compare"
          ? "Кожна серія нормована до власного min–max. Порівнюється форма, не абсолютні величини."
          : "Окремі шкали для кожного параметра. Стани показані ступінчасто.";
      plot.draw();
    },
  };
}
