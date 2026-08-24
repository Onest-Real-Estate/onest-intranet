import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentContractWorkspace from "./AgentContractWorkspace";

const post = vi.fn();
const get = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    post: (...args: unknown[]) => post(...args),
    get: (...args: unknown[]) => get(...args),
  },
  usePage: () => ({
    props: {
      csrfToken: "test-csrf",
      contract: {
        publicId: "11111111-1111-1111-1111-111111111111",
        status: "ready_for_review",
        statusLabel: "Ready for review",
        statusTone: "warning",
        effectiveOn: "2026-08-24",
        expiresOn: null,
        templateVersionId: 1,
        commission: {
          agentSplitPercent: "70.000",
          officeSplitPercent: "30.000",
          mentor: {},
          referral: {},
        },
      },
      expectedVersion: "2026-08-24T00:00:00.000000",
      capabilities: {
        canView: true,
        canManage: true,
        canViewCommission: true,
        canViewNotes: true,
      },
      allowedActions: ["issue", "reopen"],
      recipient: {
        id: 1,
        name: "Ada Agent",
        email: "ada@example.com",
        officeId: 2,
        officeName: "Fairfax VA",
        licenseState: "VA",
        agentIdentifier: "A1",
      },
      office: { officeId: 2, name: "Fairfax VA" },
      templateOptions: [
        {
          id: 1,
          publicId: "t1",
          versionLabel: "1.0.0",
          displayName: "ICA",
          templateName: "ICA",
          templateStableKey: "ica",
          jurisdictionStateCodes: ["VA"],
        },
      ],
      commercialPreview: {
        summaryLines: ["70% agent / 30% office"],
        breakdown: {
          ruleVersion: "1.0.0",
          currency: "USD",
          grossCommission: "10000",
          agentNet: "7000.00",
          officeNet: "3000.00",
          transactionFee: "0.00",
          mentorAmount: null,
          referralAmount: null,
          explanation: [],
        },
        units: {},
      },
      statusOptions: [],
      errors: { fields: {}, form: [] },
      agreementPreview: null,
    },
  }),
}));

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/HubLayout", () => ({
  HubLayout: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
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

vi.mock("@/lib/routes", () => ({
  routes: {
    admin_agent_contracts: () => "/operations/agent-contracts",
    agent_contract_update: () => "/save",
    agent_contract_lifecycle: () => "/lifecycle",
    agent_contract_preview: () => "/preview",
  },
}));

describe("AgentContractWorkspace", () => {
  beforeEach(() => {
    post.mockReset();
    get.mockReset();
  });

  it("requires confirmation before issue", async () => {
    const user = userEvent.setup();
    render(<AgentContractWorkspace />);
    await user.click(screen.getByRole("button", { name: /issue \/ send/i }));
    expect(
      screen.getByRole("heading", { name: /issue this contract/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /confirm issue/i }));
    expect(post).toHaveBeenCalled();
    const body = post.mock.calls[0][1];
    expect(body.action).toBe("issue");
    expect(body.confirmed).toBe("1");
  });

  it("shows commercial breakdown for permitted actors", () => {
    render(<AgentContractWorkspace />);
    expect(screen.getByText(/70% agent \/ 30% office/i)).toBeInTheDocument();
    expect(screen.getByText(/Agent net/i)).toBeInTheDocument();
    expect(screen.getByText(/7000\.00/)).toBeInTheDocument();
  });
});
