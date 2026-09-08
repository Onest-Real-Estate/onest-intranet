import { describe, expect, it, vi } from "vitest";

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastWarning = vi.fn();
const toastInfo = vi.fn();
const toastMessage = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    warning: (...args: unknown[]) => toastWarning(...args),
    info: (...args: unknown[]) => toastInfo(...args),
    message: (...args: unknown[]) => toastMessage(...args),
  },
}));

import { FLASH_LEVELS, showFlashToast } from "./flash-toast";

describe("showFlashToast", () => {
  it("covers every Django-aligned flash level", () => {
    expect([...FLASH_LEVELS]).toEqual(["debug", "info", "success", "warning", "error"]);
  });

  it("maps levels onto the matching Sonner helpers", () => {
    showFlashToast("success", "Saved");
    showFlashToast("error", "Failed");
    showFlashToast("warning", "Careful");
    showFlashToast("info", "Note");
    showFlashToast("debug", "Trace");
    showFlashToast("unknown", "Fallback");

    expect(toastSuccess).toHaveBeenCalledWith("Saved");
    expect(toastError).toHaveBeenCalledWith("Failed");
    expect(toastWarning).toHaveBeenCalledWith("Careful");
    expect(toastInfo).toHaveBeenCalledWith("Note");
    expect(toastMessage).toHaveBeenCalledWith("Trace");
    expect(toastMessage).toHaveBeenCalledWith("Fallback");
  });
});
