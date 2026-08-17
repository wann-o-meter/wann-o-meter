// Plan state lives in the fragment, never in the query. The server and every
// crawler see one address per plan page, while the visitor can still copy their
// own date, Ort and filters out of the address bar.
//
// Browser only: touches window.

export function readPlanState(): URLSearchParams {
  if (typeof window === "undefined") return new URLSearchParams();
  const state = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  // Links shared while the state was still in the query keep working.
  for (const [key, value] of new URLSearchParams(window.location.search)) {
    if (!state.has(key)) state.set(key, value);
  }
  return state;
}

// Only the keys the caller owns, so two writers do not erase each other.
export function writePlanState(
  path: string,
  values: Record<string, string | null>,
): void {
  if (typeof window === "undefined") return;
  // Seeded from the old query too, so the first write migrates a shared link
  // whole instead of dropping the keys this caller does not own.
  const state = readPlanState();
  for (const [key, value] of Object.entries(values)) {
    if (value === null) state.delete(key);
    else state.set(key, value);
  }
  const fragment = state.toString();
  history.replaceState(null, "", fragment ? `${path}#${fragment}` : path);
}
