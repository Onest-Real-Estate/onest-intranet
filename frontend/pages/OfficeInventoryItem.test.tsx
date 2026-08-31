import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OfficeInventoryItem from "@/pages/OfficeInventoryItem";
import type { OfficeInventoryItemPageProps } from "@/types";

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

let pageProps: OfficeInventoryItemPageProps;

const baseProps = {
  item: {
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
    hasPhoto: true,
    photoHref: "/office-inventory/11111111-1111-1111-1111-111111111111/photo",
    detailHref: "/office-inventory/11111111-1111-1111-1111-111111111111",
    storageLocation: "Front closet",
    notes: "Return clean",
    availability: null,
    myReservation: null,
    reserveHref:
      "/hub/my-reservations?item=11111111-1111-1111-1111-111111111111&quantity=1",
  },
  office: { id: 1, name: "Fairfax VA" },
  filters: {
    q: "",
    category: "",
    condition: "",
    pickup: "",
    return: "",
    quantity: "1",
    view: "grid",
    available_only: "",
  },
  filterOptions: {
    categories: [{ value: "signage", label: "Signage" }],
    conditions: [{ value: "good", label: "Good" }],
  },
  capabilities: { canViewSensitive: false },
  dateErrors: [],
  serviceError: null,
  errors: {},
  flash: {},
  auth: { user: null },
  permissions: [],
  csrfToken: "test",
} as unknown as OfficeInventoryItemPageProps;

describe("OfficeInventoryItem", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("shows photo, guidance, and reservation CTA", () => {
    render(<OfficeInventoryItem />);
    expect(screen.getByRole("heading", { name: /yard sign kit/i })).toBeInTheDocument();
    expect(screen.getByText("Front closet")).toBeInTheDocument();
    expect(screen.getByText("Return clean")).toBeInTheDocument();
    expect(document.querySelector("img")).toHaveAttribute(
      "src",
      expect.stringContaining("/photo"),
    );
    expect(screen.getByRole("link", { name: /start reservation/i })).toHaveAttribute(
      "href",
      expect.stringContaining("item="),
    );
  });

  it("reloads availability for selected dates", async () => {
    const user = userEvent.setup();
    render(<OfficeInventoryItem />);
    await user.type(screen.getByLabelText(/pickup date/i), "2026-04-01");
    await user.type(screen.getByLabelText(/return date/i), "2026-04-03");
    await user.click(screen.getByRole("button", { name: /check dates/i }));
    expect(routerGet).toHaveBeenCalled();
    const url = String(routerGet.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("pickup=");
    expect(url).toContain("return=");
  });

  it("surfaces unavailable range without booking identities", () => {
    pageProps.item.availability = {
      start: "2026-04-01T00:00:00+00:00",
      end: "2026-04-03T00:00:00+00:00",
      requestedQuantity: 1,
      availableQuantity: 0,
      totalQuantity: 4,
      isAvailable: false,
      reason: "unavailable_range",
      reasonLabel: "Not available for the selected dates.",
    };
    render(<OfficeInventoryItem />);
    expect(
      screen.getByText(/not available for the selected dates/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/reserved by/i)).not.toBeInTheDocument();
  });
});
