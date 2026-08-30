import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sonnerProps = vi.fn();

vi.mock("sonner", () => ({
  Toaster: (props: Record<string, unknown>) => {
    sonnerProps(props);
    return <div data-testid="sonner-toaster" data-theme={String(props.theme)} />;
  },
}));

import { Toaster } from "./sonner";

describe("Toaster", () => {
  beforeEach(() => {
    sonnerProps.mockClear();
    document.documentElement.classList.remove("dark");
  });

  it("passes the document theme into Sonner", async () => {
    render(<Toaster />);
    await waitFor(() => {
      expect(sonnerProps).toHaveBeenCalled();
    });
    const latest = sonnerProps.mock.calls.at(-1)?.[0] as { theme: string };
    expect(latest.theme).toBe("light");
  });

  it("tracks the document dark class when the theme cycles", async () => {
    render(<Toaster />);
    await waitFor(() => expect(sonnerProps).toHaveBeenCalled());

    act(() => {
      document.documentElement.classList.add("dark");
    });

    await waitFor(() => {
      const latest = sonnerProps.mock.calls.at(-1)?.[0] as { theme: string };
      expect(latest.theme).toBe("dark");
    });
  });
});
