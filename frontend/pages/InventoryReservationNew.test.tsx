import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InventoryReservationNew from "@/pages/InventoryReservationNew";
import type { InventoryReservationNewPageProps } from "@/types";

const routerGet = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  Form: ({
    children,
    action,
  }: {
    children: React.ReactNode | ((state: { processing: boolean }) => React.ReactNode);
    action: string;
  }) => (
    <form action={action}>
      {typeof children === "function" ? children({ processing: false }) : children}
    </form>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

vi.mock("@/hooks/use-validation-toasts", () => ({
  useValidationToasts: () => undefined,
}));

let pageProps: InventoryReservationNewPageProps;

const baseProps = {
  item: {
    publicId: "11111111-1111-1111-1111-111111111111",
    name: "Yard sign kit",
    category: "signage",
    categoryLabel: "Signage",
    trackingMode: "pooled",
    trackingModeLabel: "Pooled quantity",
    totalQuantity: 3,
    condition: "good",
    conditionLabel: "Good",
    ownerOffice: { id: 1, name: "Fairfax VA" },
    hasPhoto: false,
    photoHref: null,
    detailHref: "/office-inventory/11111111-1111-1111-1111-111111111111",
    availability: null,
    myReservation: null,
    reserveHref: "/hub/inventory-reservations/new",
  },
  draft: {
    item: "11111111-1111-1111-1111-111111111111",
    pickup: "2026-09-10",
    return: "2026-09-11",
    quantity: "1",
    purpose: "",
  },
  review: false,
  summary: null,
  office: { id: 1, name: "Fairfax VA" },
  links: {
    inventoryHref: "/office-inventory",
    myReservationsHref: "/hub/inventory-reservations",
    dashboardHref: "/dashboard",
  },
  errors: { fields: {}, form: [] },
  flash: {},
  auth: { user: null },
  permissions: [],
  csrfToken: "test",
} as unknown as InventoryReservationNewPageProps;

describe("InventoryReservationNew", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("renders the draft form and requests a server review", async () => {
    const user = userEvent.setup();
    render(<InventoryReservationNew />);
    expect(screen.getByRole("heading", { name: /reserve inventory/i })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /review availability/i }));
    expect(routerGet).toHaveBeenCalled();
    const url = String(routerGet.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("review=1");
    expect(url).toContain("item=11111111-1111-1111-1111-111111111111");
  });

  it("shows summary terms and confirm when reviewing", () => {
    pageProps = {
      ...baseProps,
      review: true,
      summary: {
        item: {
          publicId: "11111111-1111-1111-1111-111111111111",
          name: "Yard sign kit",
          trackingMode: "pooled",
          requiresApproval: false,
          totalQuantity: 3,
          storageLocation: "Closet",
          notes: "Bring back clean",
        },
        office: { id: 1, name: "Fairfax VA" },
        pickup: "2026-09-10",
        return: "2026-09-11",
        startsAt: "2026-09-10T00:00:00Z",
        endsAt: "2026-09-12T00:00:00Z",
        quantity: 1,
        purpose: "Open house",
        availableQuantity: 2,
        isAvailable: true,
        status: "confirmed",
        statusLabel: "Confirmed",
        terms: {
          requiresApproval: false,
          autoConfirm: true,
          maxHorizonDays: 90,
          maxDurationDays: 14,
          cancelCutoffHours: 24,
          approvalLabel: "This item confirms automatically when available.",
          cancelPolicyLabel: "You can cancel until 24 hours before pickup.",
        },
        instructions: {
          storageLocation: "Closet",
          notes: "Bring back clean",
        },
      },
    } as InventoryReservationNewPageProps;

    render(<InventoryReservationNew />);
    expect(screen.getByRole("heading", { name: /review reservation/i })).toBeTruthy();
    expect(screen.getByText(/bring back clean/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /confirm reservation/i })).toBeEnabled();
    expect(
      screen.getByDisplayValue(/11111111-1111-1111-1111-111111111111/),
    ).toBeTruthy();
  });

  it("disables confirm when the summary is unavailable", () => {
    pageProps = {
      ...baseProps,
      review: true,
      summary: {
        item: {
          publicId: "11111111-1111-1111-1111-111111111111",
          name: "Yard sign kit",
          trackingMode: "pooled",
          requiresApproval: false,
          totalQuantity: 3,
          storageLocation: "",
          notes: "",
        },
        office: { id: 1, name: "Fairfax VA" },
        pickup: "2026-09-10",
        return: "2026-09-11",
        startsAt: "2026-09-10T00:00:00Z",
        endsAt: "2026-09-12T00:00:00Z",
        quantity: 1,
        purpose: "",
        availableQuantity: 0,
        isAvailable: false,
        status: "confirmed",
        statusLabel: "Confirmed",
        terms: {
          requiresApproval: false,
          autoConfirm: true,
          maxHorizonDays: 90,
          maxDurationDays: 14,
          cancelCutoffHours: 24,
          approvalLabel: "Auto",
          cancelPolicyLabel: "Cancel policy",
        },
        instructions: { storageLocation: "", notes: "" },
      },
      errors: {
        fields: {},
        form: ["Not enough quantity is available for those dates."],
      },
    } as InventoryReservationNewPageProps;

    render(<InventoryReservationNew />);
    expect(screen.getByRole("button", { name: /confirm reservation/i })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/not enough quantity/i);
  });
});
