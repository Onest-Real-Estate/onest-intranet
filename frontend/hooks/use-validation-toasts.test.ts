import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useValidationToasts } from "./use-validation-toasts";

const toastError = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
  },
}));

describe("useValidationToasts", () => {
  beforeEach(() => {
    toastError.mockReset();
  });

  it("toasts form and field messages once per error fingerprint", async () => {
    const errors = {
      form: [],
      fields: { mentor_percent: ["Enter a valid percentage."] },
    };
    const { rerender } = renderHook(({ value }) => useValidationToasts(value), {
      initialProps: { value: errors },
    });

    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError).toHaveBeenCalledWith(
      "Check the highlighted fields",
      expect.objectContaining({
        description: "mentor percent: Enter a valid percentage.",
      }),
    );

    rerender({ value: errors });
    expect(toastError).toHaveBeenCalledTimes(1);
  });

  it("does not toast when there are no errors", () => {
    renderHook(() => useValidationToasts({ form: [], fields: {} }));
    expect(toastError).not.toHaveBeenCalled();
  });
});

it("toasts a form-only refusal as the message itself", async () => {
  renderHook(() =>
    useValidationToasts({
      form: ["That is not a contract action."],
      fields: {},
    }),
  );
  await waitFor(() =>
    expect(toastError).toHaveBeenCalledWith("That is not a contract action.", {
      duration: 8_000,
    }),
  );
});
