import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InventoryReservationDetail from "@/pages/InventoryReservationDetail";
import type { InventoryReservationDetailPageProps } from "@/types";

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
  usePage: () => ({ props: pageProps }),
}));

vi.mock("@/hooks/use-validation-toasts", () => ({
  useValidationToasts: () => undefined,
}));

let pageProps: InventoryReservationDetailPageProps;

const baseProps = {
  reservation: {
    publicId: "22222222-2222-2222-2222-222222222222",
    reference: "INV-R-000001",
    itemName: "Yard sign kit",
    itemPublicId: "11111111-1111-1111-1111-111111111111",
    office: { id: 1, name: "Fairfax VA" },
    quantity: 1,
    purpose: "Open house",
    status: "confirmed",
    statusLabel: "Confirmed",
    expectedVersion: "2026-08-31T00:00:00.000000",
    startsAt: "2026-09-10T00:00:00Z",
    endsAt: "2026-09-12T00:00:00Z",
    pickupLabel: "2026-09-10",
    returnLabel: "2026-09-11",
    instructions: {
      storageLocation: "Closet A",
      notes: "Return clean",
    },
    terms: {
      requiresApproval: false,
      autoConfirm: true,
      maxHorizonDays: 90,
      maxDurationDays: 14,
      cancelCutoffHours: 24,
      approvalLabel: "Auto",
      cancelPolicyLabel: "You can cancel until 24 hours before pickup.",
    },
    canCancel: true,
    cancelCutoffAt: "2026-09-09T00:00:00Z",
    cancelledAt: null,
    checkedOutAt: null,
    returnedAt: null,
    completedAt: null,
    checkoutQuantity: null,
    returnQuantity: null,
    returnConditionNotes: "",
    createdAt: "2026-08-31T00:00:00Z",
    timeline: [
      {
        id: "1",
        action: "create",
        actionLabel: "Created",
        fromStatus: "",
        toStatus: "confirmed",
        reason: "",
        notes: "",
        occurredAt: "2026-08-31T00:00:00Z",
        actor: { id: 1, name: "Agent" },
        metadata: {},
      },
    ],
    actions: [],
    itemHref: "/office-inventory/11111111-1111-1111-1111-111111111111",
    myReservationsHref: "/hub/inventory-reservations",
    dashboardHref: "/dashboard",
  },
  errors: { fields: {}, form: [] },
  justCreated: true,
  flash: {},
  auth: { user: null },
  permissions: [],
  csrfToken: "test",
} as unknown as InventoryReservationDetailPageProps;

describe("InventoryReservationDetail", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
  });

  it("shows confirmation, instructions, and cancel", () => {
    const { container } = render(<InventoryReservationDetail />);
    expect(container.textContent).toContain("INV-R-000001");
    expect(container.textContent).toMatch(/reservation saved/i);
    expect(container.textContent).toMatch(/closet a/i);
    expect(container.textContent).toMatch(/return clean/i);
    expect(
      container.querySelector('a[href="/hub/inventory-reservations"]'),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /cancel reservation/i })).toBeTruthy();
  });

  it("hides cancel when not allowed", () => {
    pageProps = {
      ...baseProps,
      justCreated: false,
      reservation: { ...baseProps.reservation, canCancel: false },
    } as InventoryReservationDetailPageProps;
    render(<InventoryReservationDetail />);
    expect(
      screen.queryByRole("button", { name: /cancel reservation/i }),
    ).not.toBeInTheDocument();
  });
});
