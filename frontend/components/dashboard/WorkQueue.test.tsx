import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { WorkQueue } from "@/components/dashboard/WorkQueue";
import type { DashboardQueue } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Link: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    className?: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function queue(overrides: Partial<DashboardQueue> = {}): DashboardQueue {
  return {
    total: 7,
    rows: [
      {
        id: "ON-1048",
        title: "1428 Grove Avenue",
        subtitle: "Listing agreement",
        meta: "Sent 3 days ago",
        badge: "Awaiting seller",
        tone: "warning",
        href: "/operations/agent-contracts",
      },
      {
        id: "ON-1039",
        title: "26 Kestrel Lane",
        meta: "Sent 9 days ago",
        badge: "Overdue",
        tone: "destructive",
      },
    ],
    ...overrides,
  };
}

describe("WorkQueue", () => {
  it("says how much of the scope it is showing when the list is capped", () => {
    render(<WorkQueue title="Awaiting signature" data={queue()} />);

    expect(screen.getByText("2 of 7")).toBeVisible();
  });

  it("reports the plain total when nothing was left out", () => {
    render(<WorkQueue title="Awaiting signature" data={queue({ total: 2 })} />);

    expect(screen.getByText("2 open")).toBeVisible();
  });

  it("pairs every status colour with words", () => {
    render(<WorkQueue title="Awaiting signature" data={queue()} />);

    expect(screen.getByText("Overdue")).toBeVisible();
    expect(screen.getByText("Awaiting seller")).toBeVisible();
  });

  it("links only the rows the provider gave a destination", () => {
    render(<WorkQueue title="Awaiting signature" data={queue()} />);

    expect(screen.getByRole("link", { name: /1428 Grove Avenue/ })).toHaveAttribute(
      "href",
      "/operations/agent-contracts",
    );
    expect(screen.queryByRole("link", { name: /Kestrel/ })).toBeNull();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(
      <WorkQueue title="Awaiting signature" data={queue()} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
