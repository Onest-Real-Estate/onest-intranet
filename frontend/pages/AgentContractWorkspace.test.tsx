import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AgentContractWorkspace from "./AgentContractWorkspace";

const post = vi.fn();
const get = vi.fn();

let pageProps: Record<string, unknown>;

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    post: (...args: unknown[]) => post(...args),
    get: (...args: unknown[]) => get(...args),
  },
  usePage: () => ({ props: pageProps }),
}));

function buildPageProps(overrides: Record<string, unknown> = {}) {
  return {
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
      canCreateAmendment: false,
      canCreateReplacement: false,
    },
    allowedActions: ["issue", "reopen"],
    familyHistory: [],
    termComparison: null,
    governingTerms: null,
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
    commissionBasisOptions: [
      { value: "agent_side_before_fees", label: "Agent side before fees" },
      { value: "gross_commission", label: "Gross commission income" },
      { value: "fixed_only", label: "Fixed amount only" },
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
    ...overrides,
  };
}

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
    agent_contract_recipient_search: () => "/recipients",
    agent_contract_create_amendment: (publicId: string) =>
      `/operations/agent-contracts/${publicId}/amend`,
    agent_contract_create_replacement: (publicId: string) =>
      `/operations/agent-contracts/${publicId}/replace`,
    agent_contract_validate: (publicId: string) =>
      `/operations/agent-contracts/${publicId}/validate`,
  },
}));

describe("AgentContractWorkspace", () => {
  beforeEach(() => {
    pageProps = buildPageProps();
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
    const body = post.mock.calls[0][1] as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("action")).toBe("issue");
    expect(body.get("confirmed")).toBe("1");
  });

  it("requires confirmation before activate", async () => {
    pageProps = buildPageProps({
      contract: {
        ...(pageProps.contract as object),
        status: "signed",
        statusLabel: "Signed",
        statusTone: "info",
      },
      allowedActions: ["activate", "supersede", "terminate"],
    });
    const user = userEvent.setup();
    render(<AgentContractWorkspace />);
    expect(screen.getByRole("button", { name: /^activate$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^supersede$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^terminate$/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^activate$/i }));
    expect(
      screen.getByRole("heading", { name: /activate this contract/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /confirm activate/i }));
    expect(post).toHaveBeenCalled();
    const body = post.mock.calls[0][1] as FormData;
    expect(body.get("action")).toBe("activate");
    expect(body.get("confirmed")).toBe("1");
  });

  it("exposes create amendment and replacement when capable", async () => {
    pageProps = buildPageProps({
      contract: {
        ...(pageProps.contract as object),
        status: "active",
        statusLabel: "Active",
        statusTone: "success",
        versionNumber: 1,
        changeKind: "original",
        changeKindLabel: "Original agreement",
      },
      capabilities: {
        canView: true,
        canManage: true,
        canViewCommission: true,
        canViewNotes: true,
        canCreateAmendment: true,
        canCreateReplacement: true,
      },
      allowedActions: ["supersede", "terminate"],
      termComparison: null,
      familyHistory: [
        {
          publicId: "11111111-1111-1111-1111-111111111111",
          versionNumber: 1,
          changeKind: "original",
          changeKindLabel: "Original agreement",
          role: "base",
          governing: "current",
          status: "active",
          statusLabel: "Active",
          statusTone: "success",
          effectiveOn: "2026-08-24",
          expiresOn: null,
          isFocus: true,
          amendsPublicId: null,
          supersedesPublicId: null,
          hasArtifact: true,
          href: "/operations/agent-contracts/11111111-1111-1111-1111-111111111111",
        },
      ],
    });
    const user = userEvent.setup();
    render(<AgentContractWorkspace />);
    expect(
      screen.getByRole("button", { name: /create amendment/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create replacement/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/family history/i)).toBeInTheDocument();
    expect(screen.getByText(/currently governing/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /create amendment/i }));
    expect(post).toHaveBeenCalled();
    expect(String(post.mock.calls[0][0])).toContain("/amend");
  });

  it("renders accessible before/after term comparison", () => {
    pageProps = buildPageProps({
      contract: {
        ...(pageProps.contract as object),
        status: "draft",
        statusLabel: "Draft",
        changeKind: "amendment",
        changeKindLabel: "Amendment",
        changeSummary: "Lower agent split.",
        versionNumber: 2,
      },
      termComparison: {
        basePublicId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        baseVersionNumber: 1,
        baseStatus: "active",
        baseStatusLabel: "Active",
        baseEffectiveOn: "2026-01-01",
        baseExpiresOn: null,
        draftEffectiveOn: "2026-08-24",
        draftExpiresOn: null,
        changeKind: "amendment",
        changeKindLabel: "Amendment",
        changeSummary: "Lower agent split.",
        effectiveDateNote: "Effective date moves from 2026-01-01 to 2026-08-24.",
        rows: [
          {
            key: "agentSplitPercent",
            label: "Agent split %",
            before: "70.000",
            after: "65.000",
            changed: true,
          },
        ],
      },
    });
    render(<AgentContractWorkspace />);
    expect(
      screen.getByRole("table", {
        name: /term changes between base version 1 and this draft/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Agent split %")).toBeInTheDocument();
    expect(screen.getByText("70.000")).toBeInTheDocument();
    expect(screen.getByText("65.000")).toBeInTheDocument();
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

it("hides percent when mentor basis is fixed-only", async () => {
  pageProps = buildPageProps({
    contract: {
      ...(pageProps.contract as object),
      status: "draft",
      statusLabel: "Draft",
      statusTone: "neutral",
      commission: {
        agentSplitPercent: "70.000",
        officeSplitPercent: "30.000",
        mentor: { percent: "10", basis: "agent_side_before_fees" },
        referral: {},
      },
    },
  });
  const user = userEvent.setup();
  render(<AgentContractWorkspace />);
  expect(screen.getByLabelText(/mentor percent/i)).toBeInTheDocument();
  await user.click(screen.getByRole("combobox", { name: /mentor basis/i }));
  await user.click(await screen.findByRole("option", { name: /fixed amount only/i }));
  expect(screen.queryByLabelText(/mentor percent/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/mentor fixed \(usd\)/i)).toBeInTheDocument();
});

it("hides mentor payee when basis is none", async () => {
  pageProps = buildPageProps({
    contract: {
      ...(pageProps.contract as object),
      status: "draft",
      statusLabel: "Draft",
      statusTone: "neutral",
      commission: {
        agentSplitPercent: "70.000",
        officeSplitPercent: "30.000",
        mentor: {
          percent: "10",
          basis: "",
          payee: {
            id: 9,
            name: "Sid",
            email: "sid@example.com",
            officeName: "Harrisburg",
          },
        },
        referral: {},
      },
    },
  });
  const user = userEvent.setup();
  render(<AgentContractWorkspace />);
  expect(screen.queryByLabelText(/mentor payee/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/sid@example.com/i)).not.toBeInTheDocument();

  await user.click(screen.getByRole("combobox", { name: /mentor basis/i }));
  await user.click(
    await screen.findByRole("option", { name: /agent side before fees/i }),
  );
  // Amount already present from props — payee appears once basis is chosen.
  expect(screen.getByLabelText(/mentor payee/i)).toBeInTheDocument();
});

it("hides referral payee until basis and an amount are set", async () => {
  pageProps = buildPageProps({
    contract: {
      ...(pageProps.contract as object),
      status: "draft",
      statusLabel: "Draft",
      statusTone: "neutral",
      commission: {
        agentSplitPercent: "70.000",
        officeSplitPercent: "30.000",
        mentor: {},
        referral: { basis: "", percent: "", fixedAmount: "" },
      },
    },
  });
  const user = userEvent.setup();
  render(<AgentContractWorkspace />);
  expect(screen.queryByLabelText(/referral payee/i)).not.toBeInTheDocument();

  await user.click(screen.getByRole("combobox", { name: /referral basis/i }));
  await user.click(
    await screen.findByRole("option", { name: /agent side before fees/i }),
  );
  expect(screen.queryByLabelText(/referral payee/i)).not.toBeInTheDocument();
  expect(
    screen.getByText(/enter a percent or fixed amount to choose a referral payee/i),
  ).toBeInTheDocument();

  await user.type(screen.getByLabelText(/referral percent/i), "5");
  expect(screen.getByLabelText(/referral payee/i)).toBeInTheDocument();
});

it("saves the draft through Inertia instead of a full document post", async () => {
  pageProps = buildPageProps({
    contract: {
      ...(pageProps.contract as object),
      status: "draft",
      statusLabel: "Draft",
      statusTone: "neutral",
    },
  });
  const user = userEvent.setup();
  render(<AgentContractWorkspace />);
  await user.click(screen.getByRole("button", { name: /save draft/i }));
  expect(post).toHaveBeenCalled();
  const [url, body, options] = post.mock.calls.at(-1) as [
    string,
    FormData,
    { preserveScroll?: boolean; onSuccess?: () => void },
  ];
  expect(typeof url).toBe("string");
  expect(body).toBeInstanceOf(FormData);
  expect(options).toEqual(expect.objectContaining({ preserveScroll: true }));
});
