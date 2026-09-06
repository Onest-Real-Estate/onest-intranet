import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InventoryAdministration from "@/pages/InventoryAdministration";
import type { InventoryAdministrationPageProps } from "@/types";

const routerGet = vi.fn();

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: InventoryAdministrationPageProps;

const baseProps: InventoryAdministrationPageProps = {
  items: {
    items: [
      {
        publicId: "11111111-1111-4111-8111-111111111111",
        name: "Branch laptop",
        category: "electronics",
        categoryLabel: "Electronics",
        trackingMode: "serialized",
        trackingModeLabel: "Serialized",
        totalQuantity: 1,
        availabilityState: "active",
        availabilityStateLabel: "Active",
        ownerOffice: { stableKey: "fairfax-va", name: "Fairfax VA" },
        version: "2026-08-22T00:00:00Z",
        detailHref: "/operations/inventory/11111111-1111-4111-8111-111111111111",
      },
      {
        publicId: "22222222-2222-4222-8222-222222222222",
        name: "Conference chairs",
        category: "furniture",
        categoryLabel: "Furniture",
        trackingMode: "pooled",
        trackingModeLabel: "Pooled",
        totalQuantity: 8,
        availabilityState: "damaged",
        availabilityStateLabel: "Damaged",
        ownerOffice: { stableKey: "fairfax-va", name: "Fairfax VA" },
        version: "2026-08-22T00:00:00Z",
        detailHref: "/operations/inventory/22222222-2222-4222-8222-222222222222",
      },
    ],
    pagination: {
      page: 1,
      pageSize: 50,
      totalItems: 2,
      totalPages: 1,
      hasNext: false,
      hasPrevious: false,
    },
    filters: {
      q: "",
      category: "",
      tracking_mode: "",
      condition: "",
      state: "",
      owner: "",
      include_retired: "",
    },
    sort: null,
  },
  filterOptions: {
    categories: [{ value: "electronics", label: "Electronics" }],
    trackingModes: [{ value: "serialized", label: "Serialized" }],
    conditions: [{ value: "good", label: "Good" }],
    states: [{ value: "active", label: "Active" }],
    owners: [{ value: "fairfax-va", label: "Fairfax VA" }],
  },
  writableOffices: [{ id: 3, label: "Fairfax VA", kind: "branch" }],
  capabilities: { canManage: true, canViewSensitive: true },
  scope: { level: "office", label: "Office scope" },
  csrfToken: "test-csrf-token",
  validation: { fields: {}, form: [] },
  createSheet: null,
  user: {
    id: 1,
    permissions: ["web.view_inventory", "inventory.manage_inventory"],
  },
} as unknown as InventoryAdministrationPageProps;

describe("InventoryAdministration", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("lists scoped inventory with state badges", () => {
    render(<InventoryAdministration />);
    expect(screen.getByText("Branch laptop")).toBeInTheDocument();
    expect(screen.getByText("Conference chairs")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Damaged")).toBeInTheDocument();
  });

  it("links each row into its workspace", () => {
    render(<InventoryAdministration />);
    const link = screen.getAllByRole("link", { name: /branch laptop/i })[0];
    expect(link).toHaveAttribute(
      "href",
      "/operations/inventory/11111111-1111-4111-8111-111111111111",
    );
  });

  it("opens the create sheet from the New item action", async () => {
    const user = userEvent.setup();
    render(<InventoryAdministration />);
    await user.click(screen.getByRole("button", { name: /new item/i }));
    expect(
      screen.getByRole("heading", { name: /new inventory item/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/owning office/i)).toBeInTheDocument();
    const form = document.getElementById("inventory-create-form");
    expect(form).toHaveAttribute("action", "/operations/inventory/create");
    const context = form?.querySelector('input[name="context"]');
    expect(context).toHaveValue("sheet");
  });

  it("does not render the create sheet for read-only viewers", () => {
    pageProps = {
      ...baseProps,
      capabilities: { canManage: false, canViewSensitive: false },
    };
    render(<InventoryAdministration />);
    expect(screen.queryByRole("button", { name: /new item/i })).toBeNull();
  });

  it("requests sort changes through the list URL", async () => {
    const user = userEvent.setup();
    render(<InventoryAdministration />);
    const sortButton = screen.getByRole("button", { name: /^item$/i });
    await user.click(sortButton);
    expect(routerGet).toHaveBeenCalledWith(
      expect.stringContaining("sort=name"),
      {},
      expect.objectContaining({ preserveState: true, replace: true }),
    );
  });
});
