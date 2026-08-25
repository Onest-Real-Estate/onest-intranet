import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
      agreementPreview: null,
      generatedPdfUrl: null,
      errors: { fields: {}, form: [] },
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
    agent_contract_validate: (publicId: string) =>
      `/operations/agent-contracts/${publicId}/validate`,
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

  afterEach(() => vi.unstubAllGlobals());

  it("reprices from the server when the gross changes, and never in the browser", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        summaryLines: ["70% agent / 30% office"],
        breakdown: {
          ruleVersion: "1.0.0",
          currency: "USD",
          grossCommission: "20000",
          agentNet: "14000.00",
          officeNet: "6000.00",
          transactionFee: "395.00",
          mentorAmount: null,
          referralAmount: null,
          explanation: ["Gross commission 20000.00", "Agent side 70% = 14000.00"],
        },
        units: {},
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentContractWorkspace />);

    const input = screen.getByLabelText(/gross commission/i);
    await user.clear(input);
    await user.type(input, "20000");

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(url).toContain("/validate");
    expect(url).toContain("gross_commission=20000");

    // The figure comes back from the engine; nothing is multiplied client-side.
    expect(await screen.findByText("$14,000.00")).toBeInTheDocument();
    expect(screen.getByText("$395.00")).toBeInTheDocument();
    expect(screen.getByText(/Agent side 70% = 14000\.00/)).toBeInTheDocument();
  });

  it("surfaces a refused calculation instead of showing a stale figure as current", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ error: "Gross commission must be positive." }),
      }),
    );
    render(<AgentContractWorkspace />);

    const input = screen.getByLabelText(/gross commission/i);
    await user.clear(input);
    await user.type(input, "-5");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Gross commission must be positive.",
    );
  });

  it("prices the agreement from the server's own figures", () => {
    render(<AgentContractWorkspace />);
    expect(screen.getByText(/70% agent \/ 30% office/i)).toBeInTheDocument();
    expect(screen.getByText(/Agent net/i)).toBeInTheDocument();
    // Formatted as currency rather than echoed as a raw decimal string.
    expect(screen.getByText("$7,000.00")).toBeInTheDocument();
    expect(screen.getByText("$3,000.00")).toBeInTheDocument();
    // The gross is editable: this panel prices a deal, it does not just report.
    expect(screen.getByLabelText(/gross commission/i)).toHaveValue("10000");
  });
});
