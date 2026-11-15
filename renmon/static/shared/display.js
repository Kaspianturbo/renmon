export const labelOf = (s) => s.label_uk || s.label;
export const fmt = (n) =>
  Number.isFinite(n)
    ? n.toLocaleString("uk-UA", { maximumFractionDigits: 2 })
    : "—";
export function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
export function interpretation(s, value) {
  return s.interpretations?.[String(value)];
}
export function displayValue(s, value) {
  if (!Number.isFinite(value)) return "—";
  if (s.kind !== "state") return fmt(value);
  const item = interpretation(s, value);
  return item ? item.label_uk || item.label : `Невідомий стан (${fmt(value)})`;
}
