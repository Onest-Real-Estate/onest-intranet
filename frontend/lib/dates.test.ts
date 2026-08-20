import { format } from "date-fns";
import { describe, expect, it } from "vitest";

import { formatFormDate, parseFormDate, toFormDate } from "./dates";

describe("form dates", () => {
  it("round-trips a calendar date in local time", () => {
    const date = parseFormDate("2030-06-30");
    expect(date).toBeInstanceOf(Date);
    if (!(date instanceof Date)) {
      return;
    }
    expect(toFormDate(date)).toBe("2030-06-30");
    expect(formatFormDate("2030-06-30")).toBe(format(date, "PPP"));
  });

  it("keeps hours when the posted value includes time", () => {
    const date = parseFormDate("2024-02-01T09:15");
    expect(date).toBeInstanceOf(Date);
    if (!(date instanceof Date)) {
      return;
    }
    expect(date.getHours()).toBe(9);
    expect(date.getMinutes()).toBe(15);
    expect(toFormDate(date, true)).toBe("2024-02-01T09:15");
  });

  it("rejects malformed values", () => {
    expect(parseFormDate("")).toBeUndefined();
    expect(parseFormDate("not-a-date")).toBeUndefined();
    expect(formatFormDate("")).toBe("");
  });
});
