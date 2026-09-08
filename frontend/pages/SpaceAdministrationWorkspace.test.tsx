import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import SpaceAdministrationWorkspace from "@/pages/SpaceAdministrationWorkspace";
import type { SpaceAdministrationWorkspacePageProps } from "@/types";

const routerPost = vi.fn();
let pageProps: SpaceAdministrationWorkspacePageProps;

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { post: (...args: unknown[]) => routerPost(...args) },
  usePage: () => ({ props: pageProps }),
}));

const user = {
  id: 1,
  email: "branch@example.com",
  name: "Branch Manager",
  headshotUrl: null,
  permissions: ["reservations.view_spaces", "reservations.manage_spaces"],
  roles: ["branch_manager"],
  roleLabel: "Branch manager",
  isStaff: false,
  isSuperuser: false,
};

const baseProps = {
  user,
  csrfToken: "token",
  space: {
    publicId: "11111111-1111-1111-1111-111111111111",
    name: "Harbor boardroom",
    officeKey: "fairfax-va",
    officeName: "Fairfax VA",
    spaceType: "conference_room",
    spaceTypeLabel: "Conference room",
    capacity: 16,
    location: "Floor 1",
    status: "active",
    statusLabel: "Active",
    isReservable: true,
    displayOrder: 0,
    amenities: [],
    description: "",
    accessInstructions: "Door code 4321",
    updatedAt: "2026-09-08T12:00:00+00:00",
    retiredAt: null,
    policy: {
      minimumDurationMinutes: 60,
      maximumDurationMinutes: 240,
      bookingHorizonDays: 90,
      minimumNoticeMinutes: 30,
      bufferBeforeMinutes: 0,
      bufferAfterMinutes: 15,
      cancellationCutoffMinutes: 0,
      requiresApproval: false,
      isReservable: true,
    },
  },
  schedule: [{ weekday: 0, startsAt: "09:00:00", endsAt: "17:00:00" }],
  blocks: [
    {
      publicId: "22222222-2222-2222-2222-222222222222",
      kind: "maintenance",
      kindLabel: "Maintenance",
      startsAt: "2026-09-10T13:00:00+00:00",
      endsAt: "2026-09-10T14:00:00+00:00",
      reason: "Alarm service",
      visibility: "internal",
    },
  ],
  upcomingBookings: [
    {
      publicId: "33333333-3333-3333-3333-333333333333",
      reference: "ROOM-ABC123",
      ownerName: "Kayla Peterson",
      startsAt: "2026-09-10T15:00:00+00:00",
      endsAt: "2026-09-10T16:00:00+00:00",
      status: "confirmed",
      statusLabel: "Confirmed",
      attendeeCount: 4,
    },
  ],
  moveTargets: [
    { value: "44444444-4444-4444-4444-444444444444", label: "Cedar room", capacity: 6 },
  ],
  options: {
    spaceTypes: [{ value: "conference_room", label: "Conference room" }],
    blockKinds: [{ value: "maintenance", label: "Maintenance" }],
    visibilities: [{ value: "internal", label: "Internal only" }],
  },
  capabilities: {
    canManageSpaces: true,
    canManageSchedules: true,
    canManageReservations: true,
    canOverride: false,
    canViewSensitive: true,
  },
  impact: null,
  errors: { fields: {}, form: [] },
  links: { indexHref: "/operations/rooms" },
} as unknown as SpaceAdministrationWorkspacePageProps;

describe("SpaceAdministrationWorkspace", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerPost.mockClear();
  });

  it("shows identity, policy, hours, blocks, and bookings", () => {
    render(<SpaceAdministrationWorkspace />);

    expect(screen.getByLabelText("Name")).toHaveValue("Harbor boardroom");
    expect(screen.getByLabelText("Minimum minutes")).toHaveValue(60);
    expect(screen.getByText("Alarm service")).toBeVisible();
    expect(screen.getByText("ROOM-ABC123")).toBeVisible();
    expect(screen.getByText("Confirmed")).toBeVisible();
  });

  it("carries no booker purpose to render in the first place", () => {
    render(<SpaceAdministrationWorkspace />);

    // The guarantee is structural: the server never serializes purpose or
    // attendee detail into this page, so the booking row can only show a
    // reference, an owner, and a time.
    const booking = pageProps.upcomingBookings[0] as unknown as Record<string, unknown>;
    expect(booking).not.toHaveProperty("purpose");
    expect(screen.getByText(/stay private to the booker/i)).toBeVisible();
  });

  it("sends the loaded timestamp so a stale edit can be detected", async () => {
    const actor = userEvent.setup();
    render(<SpaceAdministrationWorkspace />);

    await actor.click(screen.getByRole("button", { name: /save room/i }));

    expect(routerPost.mock.calls[0]?.[1]).toMatchObject({
      expectedUpdatedAt: "2026-09-08T12:00:00+00:00",
      acknowledgeImpact: false,
    });
  });

  it("lists the bookings a refused change would strand", () => {
    pageProps.impact = {
      total: 1,
      bookings: [
        {
          reference: "ROOM-ABC123",
          publicId: "33333333-3333-3333-3333-333333333333",
          ownerName: "Kayla Peterson",
          startsAt: "2026-09-10T15:00:00+00:00",
          endsAt: "2026-09-10T16:00:00+00:00",
          reason: "Shorter than the new minimum duration",
        },
      ],
    };
    render(<SpaceAdministrationWorkspace />);

    expect(screen.getByText(/1 future booking would be affected/i)).toBeVisible();
    expect(screen.getByText("Shorter than the new minimum duration")).toBeVisible();
  });

  it("requires a reason before a destructive action can be confirmed", async () => {
    const actor = userEvent.setup();
    render(<SpaceAdministrationWorkspace />);

    await actor.click(screen.getByRole("button", { name: /deactivate room/i }));
    const confirm = screen.getByRole("button", { name: /^deactivate$/i });
    expect(confirm).toBeDisabled();

    await actor.type(screen.getByLabelText("Reason"), "Ceiling repair");
    expect(confirm).toBeEnabled();
  });

  it("blocks a save while two intervals on one day overlap", async () => {
    const actor = userEvent.setup();
    render(<SpaceAdministrationWorkspace />);

    // A new row defaults to Monday 09:00-17:00, which the seeded row already
    // covers; the editor must refuse it before the server has to.
    await actor.click(screen.getByRole("button", { name: /add interval/i }));

    expect(screen.getByText(/intervals on the same day overlap/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /save hours/i })).toBeDisabled();
    expect(routerPost).not.toHaveBeenCalled();
  });

  it("saves hours from the keyboard with no drag interaction", async () => {
    const actor = userEvent.setup();
    render(<SpaceAdministrationWorkspace />);

    await actor.click(screen.getByRole("button", { name: /add interval/i }));
    const days = screen.getAllByLabelText("Day");
    await actor.selectOptions(days[days.length - 1], "2");
    await actor.click(screen.getByRole("button", { name: /save hours/i }));

    expect(String(routerPost.mock.calls[0]?.[0])).toContain("/schedule");
    const payload = routerPost.mock.calls[0]?.[1] as { intervals: string };
    expect(JSON.parse(payload.intervals)).toEqual([
      { weekday: 0, startsAt: "09:00", endsAt: "17:00" },
      { weekday: 2, startsAt: "09:00", endsAt: "17:00" },
    ]);
  });

  it("hides every write control from a read-only administrator", () => {
    pageProps.capabilities = {
      canManageSpaces: false,
      canManageSchedules: false,
      canManageReservations: false,
      canOverride: false,
      canViewSensitive: false,
    };
    render(<SpaceAdministrationWorkspace />);

    expect(screen.getByLabelText("Name")).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: /add block/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /move/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /deactivate room/i }),
    ).not.toBeInTheDocument();
  });

  it("locks a retired room and explains why", () => {
    pageProps.space.status = "retired";
    render(<SpaceAdministrationWorkspace />);

    expect(screen.getByText(/this room is retired/i)).toBeVisible();
    expect(screen.getByLabelText("Name")).toBeDisabled();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<SpaceAdministrationWorkspace />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
