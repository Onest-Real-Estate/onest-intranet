import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import {
  NotificationBell,
  POLL_INTERVAL_MS,
} from "@/components/notifications/NotificationBell";

vi.mock("@inertiajs/react", () => ({
  Link: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    "aria-label"?: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function summary(unreadCount = 3, mandatoryCount = 0) {
  return { unreadCount, mandatoryCount, href: "/notifications" };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("NotificationBell", () => {
  it("names the count in the control label rather than in colour alone", () => {
    render(<NotificationBell summary={summary(3)} />);

    const link = screen.getByRole("link", { name: "3 unread notifications" });
    expect(link).toHaveAttribute("href", "/notifications");
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("says so when nothing is unread, and shows no badge", () => {
    render(<NotificationBell summary={summary(0)} />);

    expect(screen.getByRole("link", { name: "No unread notifications" })).toBeVisible();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("caps the badge but keeps the exact figure in the label", () => {
    render(<NotificationBell summary={summary(240)} />);

    expect(screen.getByText("99+")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "240 unread notifications" }),
    ).toBeVisible();
  });

  it("calls out acknowledgements that cannot be swept away", () => {
    render(<NotificationBell summary={summary(4, 1)} />);

    expect(
      screen.getByRole("link", {
        name: "4 unread notifications, 1 requiring acknowledgement",
      }),
    ).toBeVisible();
  });

  it("renders nothing at all when the reader is signed out", () => {
    const { container } = render(<NotificationBell summary={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("polls for a fresh count and announces the change politely", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ unreadCount: 5, mandatoryCount: 0 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NotificationBell summary={summary(3)} />);
    expect(fetchMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    await vi.waitFor(() => expect(screen.getByText("5")).toBeVisible());
    expect(fetchMock).toHaveBeenCalledWith(
      "/notifications/summary",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent("5 unread notifications");
  });

  it("keeps the last known count when a poll fails", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<NotificationBell summary={summary(3)} />);
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);

    await vi.waitFor(() =>
      expect(screen.getByRole("link", { name: /3 unread/ })).toHaveAttribute(
        "data-stale",
        "true",
      ),
    );
    expect(screen.getByText("3")).toBeVisible();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<NotificationBell summary={summary(2)} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
