import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

let flash: { level: string; message: string } | null | undefined;

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: { flash } }),
}));

import { FlashToasts } from "./FlashToasts";

describe("FlashToasts", () => {
  beforeEach(() => {
    flash = undefined;
    toastSuccess.mockReset();
    toastError.mockReset();
    toastWarning.mockReset();
    toastInfo.mockReset();
    toastMessage.mockReset();
  });

  it("shows a success toast when flash is present", async () => {
    flash = { level: "success", message: "Draft saved" };
    render(<FlashToasts />);
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Draft saved"));
  });

  it("maps warning and info flashes", async () => {
    flash = { level: "warning", message: "Check the dates" };
    const { rerender } = render(<FlashToasts />);
    await waitFor(() => expect(toastWarning).toHaveBeenCalledWith("Check the dates"));

    flash = { level: "info", message: "Review is optional" };
    rerender(<FlashToasts />);
    await waitFor(() => expect(toastInfo).toHaveBeenCalledWith("Review is optional"));
  });

  it("does nothing when flash is absent", async () => {
    flash = null;
    render(<FlashToasts />);
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
