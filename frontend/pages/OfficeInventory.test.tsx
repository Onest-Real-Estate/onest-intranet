import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OfficeInventory from "@/pages/OfficeInventory";
import type { OfficeInventoryPageProps } from "@/types";

const routerGet = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({
    children,
    href,
    className,
    "aria-disabled": ariaDisabled,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
    "aria-disabled"?: boolean;
  }) => (
    <a href={href} className={className} aria-disabled={ariaDisabled}>
      {children}
    </a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: OfficeInventoryPageProps;

const baseItem = {
  publicId: "11111111-1111-1111-1111-111111111111",
  name: "Yard sign kit",
  category: "signage",
  categoryLabel: "Signage",
  trackingMode: "pooled",
  trackingModeLabel: "Pooled quantity",
  totalQuantity: 4,
  condition: "good",
  conditionLabel: "Good",
  ownerOffice: { id: 1, name: "Fairfax VA" },
  hasPhoto: false,
  photoHref: null,
  detailHref: "/office-inventory/11111111-1111-1111-1111-111111111111",
  storageLocation: "Front closet",
  notes: "Return clean",
  availability: {
    start: "2026-03-01T00:00:00+00:00",
    end: "2026-03-03T00:00:00+00:00",
    requestedQuantity: 1,
    availableQuantity: 4,
    totalQuantity: 4,
    isAvailable: true,
    reason: "",
    reasonLabel: "",
  },
  myReservation: null,
  reserveHref:
    "/hub/inventory-reservations/new?item=11111111-1111-1111-1111-111111111111&quantity=1",
};

const baseProps = {
  items: {
    items: [baseItem],
    pagination: {
      page: 1,
      pageSize: 24,
      totalItems: 1,
      totalPages: 1,
      hasNext: false,
      hasPrevious: false,
    },
    filters: {
      q: "",
      category: "",
      condition: "",
      pickup: "2026-03-01",
      return: "2026-03-02",
      quantity: "1",
      view: "grid",
      available_only: "",
    },
    sort: null,
  },
  office: { id: 1, name: "Fairfax VA" },
  filterOptions: {
    categories: [{ value: "signage", label: "Signage" }],
    conditions: [{ value: "good", label: "Good" }],
  },
  capabilities: { canViewSensitive: false },
  dateErrors: [],
  serviceError: null,
  empty: null,
  errors: {},
  flash: {},
  auth: { user: null },
  permissions: [],
  csrfToken: "test",
} as unknown as OfficeInventoryPageProps;

describe("OfficeInventory", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("renders item cards with pickup guidance and reserve CTA", () => {
    render(<OfficeInventory />);
    expect(
      screen.getByRole("heading", { name: /office inventory/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Yard sign kit")).toBeInTheDocument();
    expect(screen.getByText(/pickup: front closet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^reserve$/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/hub/inventory-reservations/new"),
    );
  });

  it("shows image fallback when photo is missing", () => {
    render(<OfficeInventory />);
    expect(screen.getByText("Yard sign kit").closest("li")).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });

  it("renders no-office empty state with profile link", () => {
    pageProps.empty = {
      kind: "no-office",
      title: "No office assigned",
      description: "Assign an office.",
    };
    pageProps.office = null;
    pageProps.items.items = [];
    render(<OfficeInventory />);
    expect(screen.getByText("No office assigned")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open profile/i })).toBeInTheDocument();
  });

  it("renders unavailable-range empty state", () => {
    pageProps.empty = {
      kind: "unavailable-range",
      title: "Nothing available for those dates",
      description: "Try different dates.",
    };
    pageProps.items.items = [];
    render(<OfficeInventory />);
    expect(screen.getByText(/nothing available for those dates/i)).toBeInTheDocument();
  });

  it("toggles list view via URL filters", async () => {
    const user = userEvent.setup();
    render(<OfficeInventory />);
    await user.click(screen.getByRole("button", { name: /list view/i }));
    expect(routerGet).toHaveBeenCalled();
    const url = String(routerGet.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("view=list");
  });

  it("shows date validation errors accessibly", () => {
    pageProps.dateErrors = ["Return date must be on or after the pickup date."];
    render(<OfficeInventory />);
    expect(screen.getByRole("alert")).toHaveTextContent(/return date/i);
  });

  it("disables reserve when the range is unavailable", () => {
    pageProps.items.items[0] = {
      ...baseItem,
      availability: {
        start: "2026-03-01T00:00:00+00:00",
        end: "2026-03-03T00:00:00+00:00",
        requestedQuantity: 1,
        availableQuantity: 0,
        totalQuantity: 4,
        isAvailable: false,
        reason: "unavailable_range",
        reasonLabel: "Not available for the selected dates.",
      },
    };
    render(<OfficeInventory />);
    expect(
      screen.getByText(/not available for the selected dates/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^reserve$/i })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});
