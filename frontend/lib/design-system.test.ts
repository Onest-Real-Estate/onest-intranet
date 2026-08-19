import { describe, expect, it } from "vitest";

import { buildListUrl } from "@/lib/list-query";
import { CONTRACT_STATUS, presentStatus } from "@/lib/status";
import {
  firstFieldError,
  hasValidationErrors,
  validationEntries,
} from "@/lib/validation";

describe("design-system adapters", () => {
  it("maps unknown statuses to a safe neutral presentation", () => {
    expect(presentStatus("backend_added_value", CONTRACT_STATUS)).toMatchObject({
      label: "Unknown status",
      tone: "neutral",
    });
  });

  it("normalizes field and form validation access", () => {
    const errors = {
      fields: { email: ["Enter a valid email.", "Email is already in use."] },
      form: ["Save failed."],
    };
    expect(firstFieldError(errors, "email")).toBe("Enter a valid email.");
    expect(hasValidationErrors(errors)).toBe(true);
    expect(validationEntries(errors, { email: "Email address" })).toHaveLength(3);
  });

  it("resets pagination when list shape changes and preserves other query state", () => {
    expect(
      buildListUrl("/contracts", "page=8&status=active", {
        q: "  Grove Avenue  ",
      }),
    ).toBe("/contracts?status=active&q=Grove+Avenue&page=1");
  });
});
