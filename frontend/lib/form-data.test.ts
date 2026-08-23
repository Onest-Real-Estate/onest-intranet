import { describe, expect, it } from "vitest";

import { toFormData } from "@/lib/form-data";

function entries(body: FormData): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [key, value] of body.entries()) {
    out[key] = [...(out[key] ?? []), String(value)];
  }
  return out;
}

describe("toFormData", () => {
  it("produces a FormData body, not a plain object", () => {
    // The whole point: Inertia sends a plain object as JSON, which never
    // reaches Django's request.POST.
    expect(toFormData({ action: "publish" })).toBeInstanceOf(FormData);
  });

  it("repeats the key for multi-valued fields so getlist() reads them", () => {
    expect(entries(toFormData({ audience_offices: ["4", "9"] }))).toEqual({
      audience_offices: ["4", "9"],
    });
  });

  it("keeps an empty string, because clearing a field is a real instruction", () => {
    expect(entries(toFormData({ summary: "" }))).toEqual({ summary: [""] });
  });

  it("drops undefined and null rather than sending them as words", () => {
    expect(entries(toFormData({ a: undefined, b: null, c: "kept" }))).toEqual({
      c: ["kept"],
    });
  });

  it("stringifies numbers and booleans", () => {
    expect(entries(toFormData({ page: 2, pinned: true }))).toEqual({
      page: ["2"],
      pinned: ["true"],
    });
  });
});
