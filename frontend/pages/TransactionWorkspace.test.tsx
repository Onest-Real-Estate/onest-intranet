import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const routerGet = vi.fn();
const routerPost = vi.fn();

const page = {
  user: { permissions: ["web.manage_transactions"] },
  flash: null,
  csrfToken: "test",
  errors: { fields: {}, form: [] as string[] },
  transaction: {
    publicId: "11111111-1111-1111-1111-111111111111",
    reference: "TXN-000001",
    transactionType: "buy",
    representationType: "buyer",
    status: "draft",
    statusLabel: "Draft",
    office: { stableKey: "fairfax", name: "Fairfax" },
    primaryAgent: { id: "1", displayName: "Ada", email: "ada@example.com" },
    coordinator: null,
    property: { line1: "100 Main", city: "Fairfax", state: "VA" },
    mlsNumber: "MLS-1",
    acceptanceDate: null,
    closingDate: null,
    lenderRef: "",
    titleRef: "",
    referralRef: "",
    assignments: [],
    createdAt: null,
    updatedAt: null,
  },
  expectedVersion: "2026-09-21T00:00:00.000000",
  section: "overview",
  sections: [
    { id: "overview", label: "Overview", live: true, stub: false, writable: false },
    { id: "parties", label: "Parties", live: true, stub: false, writable: true },
    { id: "notes", label: "Notes", live: true, stub: false, writable: true },
    { id: "documents", label: "Documents", live: false, stub: true, writable: false },
  ],
  capabilities: {
    manage: true,
    view: true,
    transition: true,
    viewBrokerNotes: true,
    viewClients: true,
  },
  allowedLifecycleActions: [],
  parties: [],
  propertyHistory: [],
  keyDates: [],
  notes: [
    {
      publicId: "22222222-2222-2222-2222-222222222222",
      body: "Team visible",
      visibility: "team",
      visibilityLabel: "Team",
      author: { id: "1", displayName: "Ada" },
      createdAt: "2026-09-21T00:00:00Z",
      updatedAt: null,
      mine: true,
    },
  ],
  activity: null,
  activityTeaser: null,
};

vi.mock("@inertiajs/react", () => ({
  Head: ({ title }: { title?: string }) => <title>{title}</title>,
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    get: (...args: unknown[]) => routerGet(...args),
    post: (...args: unknown[]) => routerPost(...args),
  },
  usePage: () => ({ props: page }),
}));

vi.mock("@/components/HubLayout", () => ({
  HubLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/hooks/use-validation-toasts", () => ({
  useValidationToasts: () => undefined,
}));

vi.mock("@/components/activity/ActivityTimeline", () => ({
  ActivityTimeline: ({ title }: { title: string }) => <div>{title}</div>,
}));

import TransactionWorkspace from "./TransactionWorkspace";

describe("TransactionWorkspace", () => {
  beforeEach(() => {
    routerGet.mockReset();
    routerPost.mockReset();
    page.section = "overview";
    page.errors = { fields: {}, form: [] };
  });

  it("renders section tablist and deep-links on tab click", async () => {
    const user = userEvent.setup();
    render(<TransactionWorkspace />);
    expect(
      screen.getByRole("tablist", { name: "Transaction workspace sections" }),
    ).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Parties" }));
    expect(routerGet).toHaveBeenCalled();
    expect(String(routerGet.mock.calls[0][0])).toContain("section=parties");
  });

  it("only shows notes returned by the server", () => {
    page.section = "notes";
    render(<TransactionWorkspace />);
    expect(screen.getByText("Team visible")).toBeTruthy();
    expect(screen.queryByText("Hidden note")).toBeNull();
  });

  it("shows note visibility select for editors", () => {
    page.section = "notes";
    render(<TransactionWorkspace />);
    expect(screen.getByLabelText("Visibility")).toBeTruthy();
  });

  it("preserves form errors on the parties panel", () => {
    page.section = "parties";
    page.errors = {
      fields: { displayName: ["A display name is required."] },
      form: [],
    };
    render(<TransactionWorkspace />);
    expect(screen.getByRole("alert").textContent).toContain(
      "A display name is required.",
    );
  });
});
