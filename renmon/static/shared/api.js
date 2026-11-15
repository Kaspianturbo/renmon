// Native bridge readiness precedes all data access. There is no HTTP fallback.
const ready = new Promise((resolve) => {
  if (window.pywebview?.api) resolve();
  else window.addEventListener("pywebviewready", resolve, { once: true });
});
export async function api(action, data) {
  await ready;
  const response = await window.pywebview.api.call(action, data ?? null);
  if (!response.ok) throw Error(response.error);
  return response.result;
}
