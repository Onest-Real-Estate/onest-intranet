import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@inertiajs/react", () => ({
  Head: ({ title }: { title?: string }) => <title>{title}</title>,
  router: { post: vi.fn() },
  usePage: () => ({
    props: {
      user: {
        permissions: ["web.create_own_transactions"],
      },
      schema: {
        stage: "draft",
        sections: [],
        requiredFields: ["transactionType", "representationType", "officeKey"],
        lockedFields: ["officeKey", "primaryAgentId"],
        transactionTypes: [
          { value: "buy", label: "Buy" },
          { value: "sell", label: "Sell" },
        ],
        representationTypes: [{ value: "buyer", label: "Buyer agency" }],
        jurisdiction: "VA",
      },
      draft: {},
      errors: { fields: {}, form: [] },
      duplicates: [],
      offices: [{ stableKey: "fairfax", name: "Fairfax", state: "VA" }],
      capabilities: {
        manage: false,
        createOwn: true,
        lockOffice: true,
        lockPrimaryAgent: true,
      },
      selfPerson: {
        id: 1,
        name: "Ada Agent",
        email: "ada@example.com",
        officeId: 1,
        officeName: "Fairfax",
        officeKey: "fairfax",
        licenseState: "VA",
        agentIdentifier: "",
      },
      flash: null,
      csrfToken: "test",
    },
  }),
}));

vi.mock("@/components/HubLayout", () => ({
  HubLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/administration/PersonCombobox", () => ({
  PersonCombobox: ({ label }: { label: string }) => <div>{label}</div>,
}));

vi.mock("@/components/administration/AccessChangeDialog", () => ({
  AccessChangeDialog: () => null,
}));

import TransactionNew from "./TransactionNew";

describe("TransactionNew", () => {
  it("renders the guided create sections and actions", () => {
    render(<TransactionNew />);
    expect(screen.getByRole("heading", { name: "New transaction" })).toBeTruthy();
    expect(screen.getByText("Property street")).toBeTruthy();
    expect(screen.getByText("Primary client name")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create / prepare" })).toBeTruthy();
  });
});
