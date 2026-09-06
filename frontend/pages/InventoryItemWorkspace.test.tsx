import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InventoryItemWorkspace from "@/pages/InventoryItemWorkspace";
import type { InventoryItemWorkspacePageProps } from "@/types";

const routerGet = vi.fn();
const routerPost = vi.fn();

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/administration/AccessChangeDialog", () => ({
  AccessChangeDialog: ({
    open,
    title,
    confirmLabel,
    onConfirm,
  }: {
    open: boolean;
    title: string;
    confirmLabel: string;
    onConfirm: () => void;
  }) =>
    open ? (
      <div>
        <h2>{title}</h2>
        <button type="button" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    ) : null,
}));

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

let pageProps: InventoryItemWorkspacePageProps;

const baseProps: InventoryItemWorkspacePageProps = {
  item: {
    publicId: "11111111-1111-4111-8111-111111111111",
    name: "Branch laptop",
    category: "electronics",
    categoryLabel: "Electronics",
    trackingMode: "pooled",
    trackingModeLabel: "Pooled",
    totalQuantity: 4,
    effectiveQuantity: 4,
    condition: "good",
    conditionLabel: "Good",
    availabilityState: "active",
    availabilityStateLabel: "Active",
    isReservable: true,
    storageLocation: "Supply closet",
    notes: "Shared laptops",
    photoIsPublic: false,
    hasPhoto: false,
    ownerOffice: { id: 3, stableKey: "fairfax-va", name: "Fairfax VA" },
    createdAt: "2026-08-22T00:00:00Z",
    updatedAt: "2026-08-22T00:00:00Z",
    assetId: "LAP-100",
    internalNotes: "Handle with care",
    replacementValue: "1200.00",
    replacementCurrency: "USD",
  },
  version: "2026-08-22T00:00:00Z",
  writableOffices: [
    { id: 3, label: "Fairfax VA", kind: "branch" },
    { id: 4, label: "Charlottesville VA", kind: "branch" },
  ],
  capabilities: { canManage: true, canViewSensitive: true },
  filterOptions: {
    categories: [{ value: "electronics", label: "Electronics" }],
    trackingModes: [{ value: "pooled", label: "Pooled" }],
    conditions: [{ value: "good", label: "Good" }],
  },
  transfers: [
    {
      publicId: "33333333-3333-4333-8333-333333333333",
      fromOffice: "Harrisburg",
      toOffice: "Fairfax VA",
      performedAt: "2026-08-20T00:00:00Z",
      reason: "Branch consolidation",
    },
  ],
  reservations: [],
  committedQuantity: 0,
  availabilityPreview: {
    start: "2026-09-01T09:00:00Z",
    end: "2026-09-01T17:00:00Z",
    availableQuantity: 4,
    totalQuantity: 4,
    physicalState: "active",
    physicalStateLabel: "Active",
    isReservableCatalogState: true,
  },
  scope: { level: "office", label: "Office scope" },
  csrfToken: "test-csrf-token",
  validation: { fields: {}, form: [] },
  user: {
    id: 1,
    permissions: ["web.view_inventory", "inventory.manage_inventory"],
  },
} as unknown as InventoryItemWorkspacePageProps;

describe("InventoryItemWorkspace", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
    routerPost.mockClear();
  });

  it("shows edit form, availability preview, reservations, and lifecycle actions", () => {
    render(<InventoryItemWorkspace />);
    expect(screen.getByRole("heading", { name: /branch laptop/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /edit item/i })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /availability preview/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /reservations/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /lifecycle/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /item photo/i })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /transfer office/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/4 of 4 available/i)).toBeInTheDocument();
    expect(screen.getByText(/Harrisburg → Fairfax VA/i)).toBeInTheDocument();
  });

  it("requires confirmation before lifecycle transitions", async () => {
    const user = userEvent.setup();
    render(<InventoryItemWorkspace />);
    await user.click(screen.getByRole("button", { name: /^mark damaged$/i }));
    expect(
      screen.getByRole("heading", { name: /mark damaged\?/i }),
    ).toBeInTheDocument();
    expect(routerPost).not.toHaveBeenCalled();
    await user.click(screen.getAllByRole("button", { name: /^mark damaged$/i })[1]);
    expect(routerPost).toHaveBeenCalledWith(
      "/operations/inventory/11111111-1111-4111-8111-111111111111/transition",
      {
        action: "mark_damaged",
        expected_version: "2026-08-22T00:00:00Z",
        reason: "",
      },
      expect.any(Object),
    );
  });

  it("opens transfer confirmation after reviewing a destination", async () => {
    const user = userEvent.setup();
    render(<InventoryItemWorkspace />);
    await user.selectOptions(screen.getByLabelText(/destination office/i), "4");
    await user.click(screen.getByRole("button", { name: /review transfer/i }));
    expect(
      screen.getByRole("heading", { name: /transfer this item\?/i }),
    ).toBeInTheDocument();
    expect(routerPost).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /^transfer item$/i }));
    expect(routerPost).toHaveBeenCalled();
  });

  it("reloads availability preview for the selected range", async () => {
    const user = userEvent.setup();
    render(<InventoryItemWorkspace />);
    await user.click(screen.getByRole("button", { name: /calculate availability/i }));
    expect(routerGet).toHaveBeenCalledWith(
      "/operations/inventory/11111111-1111-4111-8111-111111111111",
      expect.objectContaining({
        availability_start: expect.any(String),
        availability_end: expect.any(String),
      }),
      expect.objectContaining({ preserveState: true, replace: true }),
    );
  });

  it("hides mutation controls for read-only viewers", () => {
    pageProps = {
      ...baseProps,
      capabilities: { canManage: false, canViewSensitive: false },
    };
    render(<InventoryItemWorkspace />);
    expect(screen.queryByRole("heading", { name: /edit item/i })).toBeNull();
    expect(screen.queryByRole("heading", { name: /lifecycle/i })).toBeNull();
    expect(
      screen.getByRole("heading", { name: /availability preview/i }),
    ).toBeInTheDocument();
  });
});
