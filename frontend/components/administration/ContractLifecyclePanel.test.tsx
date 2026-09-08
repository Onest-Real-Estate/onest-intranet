import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ContractLifecyclePanel } from "./ContractLifecyclePanel";
import { LIFECYCLE_ACTION_ORDER, LIFECYCLE_ACTIONS } from "./contract-lifecycle";

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof ContractLifecyclePanel>> = {},
) {
  const onRun = vi.fn();
  render(
    <ContractLifecyclePanel
      status="draft"
      statusLabel="Draft"
      stamps={{ createdAt: "2026-03-01T10:00:00Z" }}
      allowedActions={["submit_for_review", "terminate"]}
      onRun={onRun}
      {...overrides}
    />,
  );
  return { onRun };
}

describe("ContractLifecyclePanel", () => {
  it("renders a button for every action the server allows", () => {
    // `sent` is the status that used to dead-end: the server allows
    // mark_viewed and mark_signed there, and the old sidebar drew neither.
    renderPanel({
      status: "sent",
      statusLabel: "Sent to agent",
      stamps: { createdAt: "2026-03-01T10:00:00Z", sentAt: "2026-03-02T10:00:00Z" },
      allowedActions: ["mark_viewed", "mark_signed", "supersede", "terminate"],
    });

    expect(screen.getByRole("button", { name: /mark as viewed/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /mark as signed/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /supersede/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /terminate/i })).toBeVisible();
  });

  it("ignores an action code it has no button for", () => {
    renderPanel({ allowedActions: ["submit_for_review", "not_a_real_action"] });

    expect(screen.getByRole("button", { name: /submit for review/i })).toBeVisible();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("gives exactly one forward move the primary treatment", () => {
    renderPanel({
      status: "sent",
      statusLabel: "Sent to agent",
      allowedActions: ["mark_viewed", "mark_signed", "supersede", "terminate"],
    });

    // The earliest forward move leads; the skip-ahead stays available but
    // quiet, so the region keeps one "press this" signal.
    const advance = screen.getByRole("button", { name: /mark as viewed/i });
    const skipAhead = screen.getByRole("button", { name: /mark as signed/i });
    expect(advance.className).toContain("bg-brand-gold");
    expect(skipAhead.className).not.toContain("bg-brand-gold");
  });

  it("separates the moves that end the agreement", () => {
    renderPanel({
      status: "active",
      statusLabel: "Active",
      allowedActions: ["supersede", "expire", "terminate"],
    });

    // The hints say "end this version" too, so match the group label exactly.
    const heading = screen.getByText("End this version");
    const group = heading.parentElement;
    expect(group).not.toBeNull();
    const ending = within(group as HTMLElement);
    expect(ending.getByRole("button", { name: /supersede/i })).toBeVisible();
    expect(ending.getByRole("button", { name: /expire/i })).toBeVisible();
    expect(ending.getByRole("button", { name: /terminate/i })).toBeVisible();
    // The advance move is not swept into the destructive group.
    expect(ending.queryByRole("button", { name: /activate/i })).toBeNull();
  });

  it("reports the action code to the caller", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPanel();

    await user.click(screen.getByRole("button", { name: /submit for review/i }));

    expect(onRun).toHaveBeenCalledWith("submit_for_review");
  });

  it("marks the current step and the ones already behind it", () => {
    renderPanel({
      status: "signed",
      statusLabel: "Signed",
      stamps: {
        createdAt: "2026-03-01T10:00:00Z",
        sentAt: "2026-03-02T10:00:00Z",
        viewedAt: "2026-03-03T10:00:00Z",
        signedAt: "2026-03-04T10:00:00Z",
      },
      allowedActions: ["activate"],
    });

    const steps = screen.getAllByRole("listitem");
    // Draft, Ready for review, Sent, Viewed, Signed, Active.
    expect(steps).toHaveLength(6);
    expect(steps[4]).toHaveAttribute("aria-current", "step");
    expect(steps[3]).not.toHaveAttribute("aria-current");
  });

  it("stops the pipeline where a terminated contract actually left it", () => {
    renderPanel({
      status: "terminated",
      statusLabel: "Terminated",
      stamps: {
        createdAt: "2026-03-01T10:00:00Z",
        sentAt: "2026-03-02T10:00:00Z",
        terminatedAt: "2026-03-05T10:00:00Z",
      },
      allowedActions: [],
    });

    const steps = screen.getAllByRole("listitem");
    // Draft, Ready for review, Sent, then Terminated — not the unreached
    // Viewed / Signed / Active steps it will never take.
    expect(steps).toHaveLength(4);
    expect(within(steps[3]).getByText("Terminated")).toBeVisible();
    expect(screen.queryByText("Active")).toBeNull();
  });

  it("places a generation failure after the contract was sent", () => {
    renderPanel({
      status: "generation_error",
      statusLabel: "Generation error",
      stamps: { createdAt: "2026-03-01T10:00:00Z" },
      allowedActions: ["retry_generation", "terminate"],
    });

    const steps = screen.getAllByRole("listitem");
    expect(within(steps[2]).getByText("Sent to agent")).toBeVisible();
    expect(within(steps[3]).getByText("Generation error")).toBeVisible();
  });

  it("says so rather than showing an empty box when nothing is available", () => {
    renderPanel({
      status: "superseded",
      statusLabel: "Superseded",
      stamps: { createdAt: "2026-03-01T10:00:00Z" },
      allowedActions: [],
    });

    expect(screen.getByText(/no lifecycle moves are available/i)).toBeVisible();
  });

  it("keeps every registered action orderable and described", () => {
    for (const code of LIFECYCLE_ACTION_ORDER) {
      expect(LIFECYCLE_ACTIONS[code]).toBeDefined();
      expect(LIFECYCLE_ACTIONS[code].label).not.toBe("");
    }
    expect(new Set(LIFECYCLE_ACTION_ORDER).size).toBe(
      Object.keys(LIFECYCLE_ACTIONS).length,
    );
  });
});
