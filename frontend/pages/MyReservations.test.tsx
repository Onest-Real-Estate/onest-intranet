import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import MyReservations from "@/pages/MyReservations";
import type { MyReservationsPageProps } from "@/types";

const routerGet = vi.fn();
const routerPost = vi.fn();
let pageProps: MyReservationsPageProps;

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    get: (...args: unknown[]) => routerGet(...args),
    post: (...args: unknown[]) => routerPost(...args),
  },
  usePage: () => ({ props: pageProps }),
}));

const user = {
  id: 1,
  email: "agent@example.com",
  name: "Agent",
  headshotUrl: null,
  permissions: [],
  roles: ["realtor"],
  roleLabel: "Agent",
  isStaff: false,
  isSuperuser: false,
};

const roomRow = {
  sourceId: "room:11111111-1111-1111-1111-111111111111",
  source: "room",
  sourceLabel: "Room",
  publicId: "11111111-1111-1111-1111-111111111111",
  reference: "ROOM-ABC123",
  title: "Harbor boardroom",
  subtitle: "Conference room",
  officeName: "Fairfax VA",
  timezone: "America/New_York",
  startsAt: "2026-09-10T14:00:00+00:00",
  endsAt: "2026-09-10T15:00:00+00:00",
  allDay: false,
  localDate: null,
  displayStatus: "confirmed",
  displayStatusLabel: "Confirmed",
  tone: "success",
  sourceStatus: "confirmed",
  statusLabel: "Confirmed",
  purpose: "Buyer consultation",
  quantity: null,
  instructions: "",
  contact: "",
  detailHref: "/hub/my-reservations/11111111-1111-1111-1111-111111111111",
  actions: [
    {
      key: "cancel",
      label: "Cancel booking",
      href: "/hub/my-reservations/11111111-1111-1111-1111-111111111111/cancel",
      method: "post",
      destructive: true,
      expectedStatus: "confirmed",
    },
  ],
};

const inventoryRow = {
  ...roomRow,
  sourceId: "inventory:22222222-2222-2222-2222-222222222222",
  source: "inventory",
  sourceLabel: "Equipment",
  publicId: "22222222-2222-2222-2222-222222222222",
  reference: "INV-XYZ789",
  title: "Projector",
  subtitle: "Quantity 2",
  allDay: true,
  localDate: "2026-09-11",
  displayStatus: "overdue",
  displayStatusLabel: "Overdue",
  tone: "destructive",
  sourceStatus: "overdue",
  statusLabel: "Overdue",
  purpose: "",
  quantity: 2,
  instructions: "Collect from the storage cupboard.",
  contact: "Second floor store",
  detailHref: "/hub/my-reservations/22222222-2222-2222-2222-222222222222",
  actions: [],
};

const baseProps = {
  user,
  csrfToken: "token",
  reservations: [roomRow, inventoryRow],
  counts: { upcoming: 2, past: 0, cancelled: 0 },
  filters: { tab: "upcoming", source: "", status: "" },
  filterOptions: {
    sources: [
      { value: "room", label: "Room" },
      { value: "inventory", label: "Equipment" },
    ],
    statuses: [
      { value: "confirmed", label: "Confirmed" },
      { value: "overdue", label: "Overdue" },
    ],
  },
  degraded: null,
  errors: { fields: {}, form: [] },
} as unknown as MyReservationsPageProps;

describe("MyReservations", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
    routerPost.mockClear();
  });

  it("shows both sources with their own labels and domain status", () => {
    render(<MyReservations />);

    expect(screen.getByRole("link", { name: "Harbor boardroom" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Projector" })).toBeVisible();
    // "Room" is also a filter option, so scope the source chip to its card.
    const roomCard = screen
      .getByRole("link", { name: "Harbor boardroom" })
      .closest("article");
    expect(within(roomCard as HTMLElement).getByText("Room")).toBeVisible();
    expect(
      within(roomCard as HTMLElement).getByText("Buyer consultation", {
        exact: false,
      }),
    ).toBeVisible();
  });

  it("renders an inventory window as a date rather than a clock time", () => {
    render(<MyReservations />);

    const card = screen.getByRole("link", { name: "Projector" }).closest("article");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText("All day")).toBeVisible();
  });

  it("keeps the tab and filters in the visited URL", async () => {
    const actor = userEvent.setup();
    render(<MyReservations />);

    await actor.click(screen.getByRole("button", { name: /cancelled/i }));
    expect(String(routerGet.mock.calls[0]?.[0])).toContain("tab=cancelled");

    await actor.selectOptions(screen.getByLabelText("Type"), "inventory");
    expect(String(routerGet.mock.calls[1]?.[0])).toContain("source=inventory");
  });

  it("names the source that failed instead of showing a short list as complete", () => {
    pageProps.degraded = { failedSources: ["Equipment"] };
    render(<MyReservations />);

    expect(screen.getByText(/Equipment could not be loaded/i)).toBeVisible();
  });

  it("confirms before cancelling and sends the expected status", async () => {
    const actor = userEvent.setup();
    render(<MyReservations />);

    await actor.click(screen.getByRole("button", { name: /cancel booking/i }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toBeVisible();
    expect(routerPost).not.toHaveBeenCalled();

    await actor.click(within(dialog).getByRole("button", { name: /cancel booking/i }));
    expect(routerPost.mock.calls[0]?.[0]).toContain("/cancel");
    expect(routerPost.mock.calls[0]?.[1]).toEqual({ expectedStatus: "confirmed" });
  });

  it("lets the reader back out of a cancellation", async () => {
    const actor = userEvent.setup();
    render(<MyReservations />);

    await actor.click(screen.getByRole("button", { name: /cancel booking/i }));
    await actor.click(screen.getByRole("button", { name: /keep it/i }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(routerPost).not.toHaveBeenCalled();
  });

  it("offers no cancel control when the domain permitted none", () => {
    render(<MyReservations />);

    // The inventory row arrived with an empty `actions` list, so the page must
    // not invent an action the owning domain refused to allow.
    const projector = screen
      .getByRole("link", { name: "Projector" })
      .closest("article");
    expect(
      within(projector as HTMLElement).queryByRole("button", { name: /cancel/i }),
    ).not.toBeInTheDocument();
  });

  it("points an empty upcoming tab at both ways to book", () => {
    pageProps.reservations = [];
    pageProps.counts = { upcoming: 0, past: 0, cancelled: 0 };
    render(<MyReservations />);

    expect(
      screen.getByRole("heading", { name: /no upcoming reservations/i }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: /book a room/i })).toBeVisible();
    expect(screen.getByRole("link", { name: /reserve equipment/i })).toBeVisible();
  });

  it("offers a filter reset when filters hid everything", () => {
    pageProps.reservations = [];
    pageProps.filters.source = "room";
    render(<MyReservations />);

    expect(
      screen.getByRole("heading", { name: /nothing matches these filters/i }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /clear filters/i })).toBeVisible();
  });

  it("groups the calendar tab by day without losing any row", () => {
    pageProps.filters.tab = "calendar";
    render(<MyReservations />);

    expect(screen.getByRole("link", { name: "Harbor boardroom" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Projector" })).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(0);
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<MyReservations />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
