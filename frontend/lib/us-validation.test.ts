import { describe, expect, it } from "vitest";

import {
  US_PHONE_ERROR,
  US_ZIP_ERROR,
  validateUsPhone,
  validateUsZip,
} from "./us-validation";

describe("validateUsZip", () => {
  it("accepts 5-digit and ZIP+4", () => {
    expect(validateUsZip("12345")).toBeUndefined();
    expect(validateUsZip("12345-6789")).toBeUndefined();
  });

  it("rejects partial zip codes", () => {
    expect(validateUsZip("1")).toBe(US_ZIP_ERROR);
    expect(validateUsZip("1234")).toBe(US_ZIP_ERROR);
  });
});

describe("validateUsPhone", () => {
  it("accepts common formats", () => {
    expect(validateUsPhone("(202) 555-0100")).toBeUndefined();
    expect(validateUsPhone("2025550100")).toBeUndefined();
  });

  it("rejects invalid numbers", () => {
    expect(validateUsPhone("123")).toBe(US_PHONE_ERROR);
  });
});
