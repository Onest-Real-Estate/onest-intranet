import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import SpaceAdministration from "@/pages/SpaceAdministration";
import type { SpaceAdministrationPageProps } from "@/types";

const routerGet = vi.fn();
let pageProps: SpaceAdministrationPageProps;

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
  email: "branch@example.com",
  name: "Branch Manager",
  headshotUrl: null,
  permissions: ["reservations.view_spaces", "reservations.manage_spaces"],
  roles: ["branch_manager"],
  roleLabel: "Branch manager",
  isStaff: false,
  isSuperuser: false,
};

const room = {
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
  amenities: [{ code: "screen", name: "Presentation screen" }],
};

const baseProps = {
  user,
  csrfToken: "token",
  spaces: [room],
  pagination: {
    page: 1,
    pageSize: 20,
    totalItems: 1,
    totalPages: 1,
    hasNext: false,
    hasPrevious: false,
  },
  filters: {
    q: "",
    office: "",
    type: "",
    status: "",
    capacity: "",
    amenities: [],
  },
  filterOptions: {
    offices: [{ value: "fairfax-va", label: "Fairfax VA" }],
    spaceTypes: [{ value: "conference_room", label: "Conference room" }],
    statuses: [{ value: "active", label: "Active" }],
    amenities: [{ value: "screen", label: "Presentation screen" }],
  },
  capabilities: {
    canManageSpaces: true,
    canManageSchedules: true,
    canManageReservations: true,
    canOverride: false,
    canViewSensitive: true,
  },
  errors: { fields: {}, form: [] },
} as unknown as SpaceAdministrationPageProps;

describe("SpaceAdministration", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("lists a room with its office, capacity, and state", () => {
    render(<SpaceAdministration />);

    expect(screen.getByRole("link", { name: "Harbor boardroom" })).toHaveAttribute(
      "href",
      expect.stringContaining("/operations/rooms/"),
    );
    // "Fairfax VA" is also an option in the office filter, so scope to the row.
    const row = screen.getByRole("row", { name: /Harbor boardroom/ });
    expect(within(row).getByText("Fairfax VA")).toBeVisible();
    expect(within(row).getByText("Active")).toBeVisible();
  });

  it("keeps every filter in the visited URL", async () => {
    const actor = userEvent.setup();
    render(<SpaceAdministration />);

    await actor.click(screen.getByRole("button", { name: /filters/i }));
    await actor.selectOptions(screen.getByLabelText("Room type"), "conference_room");

    expect(String(routerGet.mock.calls[0]?.[0])).toContain("type=conference_room");
  });

  it("hides the create action from a reader who cannot manage rooms", () => {
    pageProps.capabilities.canManageSpaces = false;
    render(<SpaceAdministration />);

    expect(screen.queryByRole("button", { name: /new room/i })).not.toBeInTheDocument();
  });

  it("offers a filter reset when a search returns nothing", () => {
    pageProps.spaces = [];
    pageProps.filters.q = "nothing";
    pageProps.pagination.totalItems = 0;
    render(<SpaceAdministration />);

    expect(screen.getByRole("heading", { name: /no rooms match/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /clear filters/i })).toBeVisible();
  });

  it("distinguishes an unbookable room from an active one", () => {
    pageProps.spaces[0].isReservable = false;
    render(<SpaceAdministration />);

    expect(screen.getByText("Not bookable")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<SpaceAdministration />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
