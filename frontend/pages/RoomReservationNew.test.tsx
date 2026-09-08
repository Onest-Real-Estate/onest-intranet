import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import RoomReservationNew from "@/pages/RoomReservationNew";
import type { RoomReservationNewPageProps } from "@/types";

let pageProps: RoomReservationNewPageProps;

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  Form: ({
    children,
    action,
    method,
    className,
  }: {
    children: (state: { processing: boolean }) => React.ReactNode;
    action: string;
    method: string;
    className?: string;
  }) => (
    <form action={action} method={method} className={className}>
      {children({ processing: false })}
    </form>
  ),
  usePage: () => ({ props: pageProps }),
}));

const baseProps = {
  user: {
    id: 1,
    email: "agent@example.com",
    name: "Agent",
    headshotUrl: null,
    permissions: ["reservations.book_spaces"],
    roles: ["realtor"],
    roleLabel: "Agent",
    isStaff: false,
    isSuperuser: false,
  },
  space: {
    publicId: "11111111-1111-1111-1111-111111111111",
    name: "Blue conference room",
    typeLabel: "Conference room",
    capacity: 8,
    location: "Second floor",
    requiresApproval: false,
    minimumDurationMinutes: 30,
    maximumDurationMinutes: 240,
  },
  draft: {
    startsAt: "2026-03-02T14:00:00+00:00",
    endsAt: "2026-03-02T14:30:00+00:00",
    purpose: "",
    attendeeCount: "",
  },
  office: { name: "Fairfax VA", timezone: "America/New_York" },
  errors: { fields: {}, form: [] },
  links: { calendarHref: "/rooms" },
} as unknown as RoomReservationNewPageProps;

describe("RoomReservationNew", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
  });

  it("posts the selected slot through the Inertia Form contract", () => {
    render(<RoomReservationNew />);

    const form = screen.getByRole("button", { name: /reserve room/i }).closest("form");
    expect(form).toHaveAttribute("action", "/rooms/reservations");
    expect(form).toHaveAttribute("method", "post");
    expect(screen.getAllByText(/monday, march 2/i)).toHaveLength(2);
    expect(screen.getByLabelText(/business purpose/i)).toBeRequired();
  });

  it("explains that submission performs the authoritative check", () => {
    render(<RoomReservationNew />);
    expect(screen.getByText(/calendar is advisory/i)).toBeVisible();
    expect(screen.getByText(/competing reservations/i)).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<RoomReservationNew />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
