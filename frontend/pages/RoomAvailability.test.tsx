import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import RoomAvailability from "@/pages/RoomAvailability";
import type { RoomAvailabilityPageProps } from "@/types";

const routerGet = vi.fn();
let pageProps: RoomAvailabilityPageProps;

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

const user = {
  id: 1,
  email: "agent@example.com",
  name: "Agent",
  headshotUrl: null,
  permissions: ["reservations.book_spaces"],
  roles: ["realtor"],
  roleLabel: "Agent",
  isStaff: false,
  isSuperuser: false,
};

const room = {
  publicId: "11111111-1111-1111-1111-111111111111",
  name: "Blue conference room",
  type: "conference_room",
  typeLabel: "Conference room",
  capacity: 8,
  location: "Second floor",
  amenities: [{ code: "screen", name: "Presentation screen" }],
  rules: {
    minimumDurationMinutes: 30,
    maximumDurationMinutes: 240,
    minimumNoticeMinutes: 0,
    bookingHorizonDays: 90,
    bufferBeforeMinutes: 0,
    bufferAfterMinutes: 15,
    requiresApproval: false,
  },
  days: [
    {
      date: "2026-03-02",
      isClosed: false,
      openIntervals: [
        {
          startsAt: "2026-03-02T14:00:00+00:00",
          endsAt: "2026-03-02T17:00:00+00:00",
        },
      ],
      busyIntervals: [
        {
          startsAt: "2026-03-02T15:00:00+00:00",
          endsAt: "2026-03-02T16:00:00+00:00",
          kind: "busy",
          label: "Busy",
          isMine: false,
        },
      ],
      availableIntervals: [
        {
          startsAt: "2026-03-02T14:00:00+00:00",
          endsAt: "2026-03-02T15:00:00+00:00",
        },
      ],
      candidateSlots: [
        {
          startsAt: "2026-03-02T14:00:00+00:00",
          endsAt: "2026-03-02T14:30:00+00:00",
          bookingHref: "/rooms/reservations/new?space=111&startsAt=14",
        },
      ],
    },
  ],
};

const baseProps = {
  user,
  calendar: {
    view: "day",
    startDate: "2026-03-02",
    days: [{ date: "2026-03-02" }],
    spaces: [room],
    generatedAt: "2026-03-01T15:00:00+00:00",
    timezone: "America/New_York",
    isTruncated: false,
    advisory: "Availability is advisory and checked again on submit.",
  },
  office: {
    key: "fairfax-va",
    name: "Fairfax VA",
    timezone: "America/New_York",
  },
  officeOptions: [
    {
      key: "fairfax-va",
      name: "Fairfax VA",
      regionName: "Mid-Atlantic",
    },
  ],
  filterOptions: {
    spaceTypes: [{ value: "conference_room", label: "Conference room" }],
    amenities: [{ value: "screen", label: "Presentation screen" }],
    rooms: [
      {
        value: "11111111-1111-1111-1111-111111111111",
        label: "Blue conference room",
      },
    ],
  },
  filters: {
    date: "2026-03-02",
    view: "day",
    office: "",
    type: "",
    capacity: "",
    amenities: [],
    space: "",
  },
  capabilities: { canBook: true, canChangeOffice: false },
  empty: null,
  errors: { fields: {}, form: [] },
} as unknown as RoomAvailabilityPageProps;

describe("RoomAvailability", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("shows open hours, coarse busy periods, and a keyboard-native slot link", () => {
    render(<RoomAvailability />);

    expect(screen.getByRole("heading", { name: "Blue conference room" })).toBeVisible();
    expect(screen.getByText("Busy")).toBeVisible();
    expect(screen.getByRole("link", { name: /9:00 AM–9:30 AM/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/rooms/reservations/new"),
    );
    expect(screen.queryByText(/private purpose/i)).not.toBeInTheDocument();
  });

  it("keeps view and filters in the visited URL", async () => {
    const actor = userEvent.setup();
    render(<RoomAvailability />);

    await actor.click(screen.getByRole("button", { name: /^list$/i }));
    expect(String(routerGet.mock.calls[0]?.[0])).toContain("view=list");

    await actor.click(screen.getByText(/^amenities$/i));
    await actor.click(screen.getByRole("checkbox", { name: /presentation screen/i }));
    expect(String(routerGet.mock.calls[1]?.[0])).toContain("amenities=screen");
  });

  it("renders the list fallback with the same selectable slot", () => {
    pageProps.filters.view = "list";
    if (pageProps.calendar) pageProps.calendar.view = "list";
    render(<RoomAvailability />);

    expect(screen.getByRole("link", { name: /9:00 AM–9:30 AM/i })).toHaveAttribute(
      "href",
      room.days[0].candidateSlots[0].bookingHref,
    );
  });

  it("renders a useful no-office state with the stable empty filter contract", () => {
    pageProps = {
      ...pageProps,
      calendar: null,
      office: null,
      officeOptions: [],
      filterOptions: { spaceTypes: [], amenities: [], rooms: [] },
      capabilities: { canBook: false, canChangeOffice: false },
      empty: {
        kind: "no-office",
        title: "No office assigned",
        description: "Add an office to your profile before reserving a room.",
      },
    };

    render(<RoomAvailability />);

    expect(screen.getByRole("heading", { name: "No office assigned" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open profile" })).toBeVisible();
  });

  it("announces an invalid filter without dropping the calendar", () => {
    pageProps.errors = {
      fields: { date: ["Availability starts today or later."] },
      form: [],
    };
    render(<RoomAvailability />);

    expect(screen.getByRole("alert")).toHaveTextContent(/check the date or filters/i);
    expect(screen.getByRole("heading", { name: "Blue conference room" })).toBeVisible();
  });

  it("shows a closed day with no selectable slots", () => {
    const day = pageProps.calendar?.spaces[0].days[0];
    if (day) {
      day.isClosed = true;
      day.openIntervals = [];
      day.availableIntervals = [];
      day.busyIntervals = [];
      day.candidateSlots = [];
    }
    render(<RoomAvailability />);

    expect(screen.getByText("Closed")).toBeVisible();
    expect(screen.queryByRole("link", { name: /AM|PM/ })).not.toBeInTheDocument();
  });

  it("has no automated accessibility violations in the day view", async () => {
    const { container } = render(<RoomAvailability />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
