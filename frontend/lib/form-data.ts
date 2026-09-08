/**
 * Build a `FormData` body for an Inertia `router.post`.
 *
 * Inertia serializes a plain object as a **JSON** request body, and Django's
 * `request.POST` only parses `application/x-www-form-urlencoded` and
 * `multipart/form-data`. Posting `{ action: "publish" }` therefore reaches the
 * view as an empty `request.POST`, and every field reads as missing — a bug
 * that surfaces as confusing per-field validation errors ("Title: This field is
 * required") rather than as a transport failure.
 *
 * Every view in this project reads `request.POST`, so a router-driven submit
 * sends `FormData`. Native `<form method="post">` submissions — the create
 * drawer, for one — already encode correctly and do not need this.
 *
 * Arrays append repeated keys, which is what Django's `getlist()` expects for
 * multi-valued fields such as an audience. `undefined` and `null` are dropped
 * rather than sent as the strings "undefined"/"null"; an empty string is kept,
 * because clearing a field is a real instruction.
 */
export function toFormData(
  values: Record<string, string | string[] | number | boolean | null | undefined>,
): FormData {
  const body = new FormData();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        body.append(key, item);
      }
      continue;
    }
    body.set(key, String(value));
  }
  return body;
}
