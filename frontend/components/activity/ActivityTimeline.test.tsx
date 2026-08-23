import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { ActivityTimeline } from "@/components/activity/ActivityTimeline";
import type { ActivityTimelinePage } from "@/types";

const page: ActivityTimelinePage = {
  entries: [
    {
      id: "1",
      eventType: "user.administration.updated",
      summary: "Administrative record updated",
      occurredAt: "2026-08-01T10:00:00+00:00",
      occurredAtDisplay: "Aug. 1, 2026, 6:00 AM",
      actorLabel: "Ada Admin",
      actorKind: "user",
      target: { type: "user", id: "9", label: "Agent Nine" },
      related: [],
      source: "app",
      visibility: "full",
      outcome: "success",
      reason: "Office move",
      metadata: {},
      typedAction: null,
      files: [],
      changeSummary: ["office"],
    },
    {
      id: "2",
      eventType: "user.headshot.updated",
      summary: "Headshot updated",
      occurredAt: "2026-08-01T09:00:00+00:00",
      occurredAtDisplay: "Aug. 1, 2026, 5:00 AM",
      actorLabel: "System",
      actorKind: "system",
      target: { type: "user", id: "9", label: "Agent Nine" },
      related: [],
      source: "app",
      visibility: "summary",
      outcome: "success",
      reason: "",
      metadata: {},
      typedAction: "file.upload",
      files: [{ id: "f1", name: "headshot.jpg", contentType: "image/jpeg" }],
      changeSummary: ["headshot"],
    },
  ],
  nextCursor: "abc",
  hasMore: true,
  timezone: "America/New_York",
};

describe("ActivityTimeline", () => {
  it("renders chronological entries with system actors and files", () => {
    render(<ActivityTimeline page={page} />);
    expect(screen.getByText("Administrative record updated")).toBeVisible();
    expect(screen.getByText(/Ada Admin/)).toBeVisible();
    expect(screen.getByText("Headshot updated")).toBeVisible();
    expect(screen.getByText(/System/)).toBeVisible();
    expect(screen.getByText(/headshot.jpg/)).toBeVisible();
    expect(screen.getByText("America/New_York")).toBeVisible();
  });

  it("shows empty and error states", () => {
    const { rerender } = render(
      <ActivityTimeline
        page={{ entries: [], nextCursor: null, hasMore: false, timezone: "UTC" }}
      />,
    );
    expect(screen.getByText("No activity yet")).toBeVisible();

    rerender(<ActivityTimeline state="error" errorMessage="Boom" />);
    expect(screen.getByText("Activity unavailable")).toBeVisible();
    expect(screen.getByText("Boom")).toBeVisible();
  });

  it("loads older activity when asked", async () => {
    const onLoadMore = vi.fn();
    const user = userEvent.setup();
    render(<ActivityTimeline page={page} onLoadMore={onLoadMore} />);
    await user.click(screen.getByRole("button", { name: "Load older activity" }));
    expect(onLoadMore).toHaveBeenCalledOnce();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<ActivityTimeline page={page} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
