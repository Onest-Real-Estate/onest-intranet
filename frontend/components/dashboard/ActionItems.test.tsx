import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { ActionItems } from "@/components/dashboard/ActionItems";
import type { DashboardActionItem, DashboardActionItems } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Link: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    className?: string;
    "aria-label"?: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function item(overrides: Partial<DashboardActionItem> = {}): DashboardActionItem {
  return {
    id: "profile:incomplete:1",
    dedupeKey: "profile:incomplete:1",
    title: "Complete your profile",
    type: "profile",
    priority: "normal",
    priorityLabel: "Normal",
    dueAt: null,
    dueLabel: "No due date",
    overdue: false,
    state: "open",
    source: { module: "profile", recordType: "user", recordId: "1" },
    context: "Profile photo, Biography",
    ctaLabel: "Update profile",
    ctaHref: "/profile",
    assigneeId: 1,
    ...overrides,
  };
}

function queue(overrides: Partial<DashboardActionItems> = {}): DashboardActionItems {
  return {
    total: 1,
    items: [item()],
    viewAllHref: "/dashboard/action-items",
    ...overrides,
  };
}

describe("ActionItems", () => {
  it("reports open count and links each row to its CTA", () => {
    render(<ActionItems data={queue()} />);

    expect(screen.getByText("1 open")).toBeVisible();
    expect(screen.getByRole("link", { name: /Complete your profile/ })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.getByText("Update profile")).toBeVisible();
  });

  it("pairs overdue colour with the word Overdue", () => {
    render(
      <ActionItems
        data={queue({
          items: [
            item({
              id: "licence",
              title: "Real-estate license expired",
              priority: "critical",
              priorityLabel: "Critical",
              overdue: true,
              dueLabel: "Overdue · Aug 1, 2026",
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText("Overdue")).toBeVisible();
    expect(screen.getByText("Overdue · Aug 1, 2026")).toBeVisible();
  });

  it("pairs high priority colour with priority words when not overdue", () => {
    render(
      <ActionItems
        data={queue({
          items: [
            item({
              priority: "high",
              priorityLabel: "High priority",
              overdue: false,
              dueLabel: "Due Sep 1, 2026",
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText("High priority")).toBeVisible();
  });

  it("offers View all when the server truncated the feed", () => {
    render(
      <ActionItems
        data={queue({ total: 7, items: [item(), item({ id: "2" })] })}
        truncated
      />,
    );

    expect(screen.getByText("2 of 7 open")).toBeVisible();
    expect(screen.getByRole("link", { name: /View all/ })).toHaveAttribute(
      "href",
      "/dashboard/action-items",
    );
  });

  it("does not offer a completion checkbox — source records own completion", () => {
    render(<ActionItems data={queue()} />);

    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(
      <ActionItems
        data={queue({
          items: [
            item({ overdue: true, priority: "critical", priorityLabel: "Critical" }),
            item({
              id: "high",
              priority: "high",
              priorityLabel: "High priority",
              overdue: false,
            }),
          ],
        })}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
