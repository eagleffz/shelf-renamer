export function toggleVisibleSelection(
  selected: Set<string>,
  visible: string[],
): Set<string> {
  const next = new Set(selected)
  const allVisible =
    visible.length > 0 && visible.every((id) => selected.has(id))
  for (const id of visible) {
    if (allVisible) next.delete(id)
    else next.add(id)
  }
  return next
}

export function readPreference(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

export function savePreference(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* Storage may be disabled. */
  }
}
