import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MyContract from "@/pages/MyContract";
import type { MyContractPageProps } from "@/types";

const routerGet = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
}));

let pageProps: MyContractPageProps;

const activeContract = {
  publicId: "11111111-1111-1111-1111-111111111111",
  familyId: "22222222-2222-2222-2222-222222222222",
  versionNumber: 2,
  status: "active",
  statusLabel: "Active",
  statusTone: "success",
  effectiveOn: "2026-01-01",
  expiresOn: "2027-01-01",
  officeName: "Fairfax VA",
  partyDisplayName: "Avery Agent",
  sentAt: "2026-01-01T12:00:00Z",
  viewedAt: "2026-01-02T12:00:00Z",
  signedAt: "2026-01-03T12:00:00Z",
  activatedAt: "2026-01-04T12:00:00Z",
  supersededAt: null,
  expiredAt: null,
  terminatedAt: null,
  updatedAt: "2026-01-04T12:00:00Z",
  expectedVersion: "2026-01-04T12:00:00.000000",
  generatedPdf: {
    publicId: "33333333-3333-3333-3333-333333333333",
    kind: "generated_pdf",
    displayName: "agreement.pdf",
    mediaType: "application/pdf",
    byteSize: 1024,
    checksum: "abc",
  },
  signedPdf: null,
  previewUrl:
    "/my-contract/11111111-1111-1111-1111-111111111111/artifacts/33333333-3333-3333-3333-333333333333/preview",
  downloadUrl:
    "/operations/agent-contracts/11111111-1111-1111-1111-111111111111/artifacts/33333333-3333-3333-3333-333333333333/download",
  artifactKind: "generated_pdf",
  isCurrentFocus: true,
  amendsPublicId: null,
  supersedesPublicId: null,
  commission: {
    agentSplitPercent: "70.000",
    officeSplitPercent: "30.000",
    transactionFeeAmount: "100.00",
    transactionFeePercent: null,
    annualCapAmount: null,
    mentor: {
      percent: "5.000",
      fixedAmount: null,
      capAmount: null,
      basis: "gross_commission",
      notes: "",
    },
    referral: {
      percent: null,
      fixedAmount: null,
      capAmount: null,
      basis: "",
      notes: "",
    },
  },
  summaryLines: [
    "Agent/office split: 70.000/30.000%.",
    "Mentor deduction — basis Gross commission income; 5.000%.",
  ],
  specialArrangements: "",
  addendaReferences: [],
};

const baseProps = {
  state: "active",
  nextAction: {
    title: "Your agreement is active",
    description: "These terms govern your current relationship.",
    ctaLabel: "",
    ctaKind: "",
    ctaHref: "",
  },
  contract: activeContract,
  history: [
    {
      publicId: activeContract.publicId,
      versionNumber: 2,
      changeKind: "original",
      changeKindLabel: "Original agreement",
      role: "base",
      governing: "current",
      status: "active",
      statusLabel: "Active",
      statusTone: "success",
      effectiveOn: "2026-01-01",
      expiresOn: "2027-01-01",
      isFocus: true,
      hasArtifact: true,
      href: "/my-contract",
      amendsPublicId: null,
      supersedesPublicId: null,
    },
    {
      publicId: "44444444-4444-4444-4444-444444444444",
      versionNumber: 1,
      changeKind: "original",
      changeKindLabel: "Original agreement",
      role: "base",
      governing: "historical",
      status: "superseded",
      statusLabel: "Superseded",
      statusTone: "neutral",
      effectiveOn: "2025-01-01",
      expiresOn: null,
      isFocus: false,
      hasArtifact: true,
      href: "/my-contract?v=44444444-4444-4444-4444-444444444444",
      amendsPublicId: null,
      supersedesPublicId: null,
    },
  ],
  capabilities: {
    canViewCommission: true,
    canSign: false,
    signingReady: false,
  },
  disclaimer:
    "Summary values are informational. If anything disagrees with the PDF agreement, the PDF controls.",
  empty: null,
  user: null,
  csrfToken: "test",
  requestId: "req",
  features: {},
  primaryOffice: null,
  shell: {
    authorizationVersion: "1",
    capabilitySchemaVersion: "1",
    help: { url: null },
    session: { authenticated: true },
  },
  notifications: null,
} as unknown as MyContractPageProps;

describe("MyContract", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockReset();
  });

  it("renders active status, mentor separately from referral, and disclaimer", () => {
    render(<MyContract />);
    expect(screen.getByRole("heading", { name: "My contract" })).toBeInTheDocument();
    expect(screen.getByText("Your agreement is active")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mentor" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Referral" })).toBeInTheDocument();
    expect(screen.getByText(/No referral terms/i)).toBeInTheDocument();
    expect(screen.getByText(/PDF controls/i)).toBeInTheDocument();
  });

  it("exposes download and open-in-new-tab for the PDF", () => {
    render(<MyContract />);
    const download = screen.getAllByRole("link", { name: /Download PDF/i })[0];
    expect(download).toHaveAttribute("href", activeContract.downloadUrl);
    expect(screen.getByRole("link", { name: /Open in new tab/i })).toHaveAttribute(
      "href",
      activeContract.previewUrl,
    );
  });

  it("lists historical versions as keyboard-reachable links", () => {
    render(<MyContract />);
    const prior = screen.getByRole("link", { name: /Version 1/i });
    expect(prior).toHaveAttribute(
      "href",
      "/my-contract?v=44444444-4444-4444-4444-444444444444",
    );
  });

  it("shows no-contract empty state with profile CTA", () => {
    pageProps = {
      ...pageProps,
      state: "no_contract",
      contract: null,
      history: [],
      empty: {
        kind: "no_contract",
        title: "No contract on file",
        description: "Not issued yet.",
      },
      nextAction: {
        title: "No contract on file",
        description: "Not issued yet.",
        ctaLabel: "Open profile",
        ctaKind: "profile",
        ctaHref: "/profile",
      },
    };
    render(<MyContract />);
    expect(
      screen.getByRole("heading", { name: "No contract on file" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open profile/i })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.queryByRole("heading", { name: "Mentor" })).not.toBeInTheDocument();
  });

  it("explains on the page why signing is unavailable, rather than in a tooltip", () => {
    pageProps = {
      ...pageProps,
      state: "awaiting_signature",
      capabilities: {
        canViewCommission: true,
        canSign: true,
        signingReady: false,
      },
      nextAction: {
        title: "Signature required",
        description: "Review and sign.",
        ctaLabel: "Sign contract",
        ctaKind: "sign",
        ctaHref: "",
      },
      contract: {
        ...activeContract,
        status: "viewed",
        statusLabel: "Viewed",
        statusTone: "info",
      },
    };
    render(<MyContract />);

    // A tooltip on a disabled button is unreachable by touch and by keyboard,
    // so the reason is stated in the open and the dead control is gone.
    expect(screen.getByText(/signing is temporarily unavailable/i)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Sign contract/i }),
    ).not.toBeInTheDocument();
  });

  it("links to the signing ceremony when signable and ready", () => {
    pageProps = {
      ...pageProps,
      state: "awaiting_signature",
      capabilities: {
        canViewCommission: true,
        canSign: true,
        signingReady: true,
      },
      nextAction: {
        title: "Signature required",
        description: "Review and sign.",
        ctaLabel: "Sign contract",
        ctaKind: "sign",
        ctaHref: "",
      },
      contract: {
        ...activeContract,
        status: "viewed",
        statusLabel: "Viewed",
        statusTone: "info",
      },
    };
    render(<MyContract />);
    expect(screen.getByRole("link", { name: /Sign contract/i })).toHaveAttribute(
      "href",
      "/my-contract/sign",
    );
  });

  it("hides sign when the version is not signable", () => {
    render(<MyContract />);
    expect(
      screen.queryByRole("button", { name: /Sign contract/i }),
    ).not.toBeInTheDocument();
  });

  it("refreshes when generation is in progress", async () => {
    const user = userEvent.setup();
    pageProps = {
      ...pageProps,
      state: "generating",
      nextAction: {
        title: "Preparing your agreement",
        description: "PDF is generating.",
        ctaLabel: "Refresh",
        ctaKind: "refresh",
        ctaHref: "/my-contract",
      },
      contract: {
        ...activeContract,
        status: "sent",
        previewUrl: null,
        downloadUrl: null,
        generatedPdf: null,
      },
    };
    render(<MyContract />);
    await user.click(screen.getByRole("button", { name: /Refresh/i }));
    expect(routerGet).toHaveBeenCalled();
  });

  it("surfaces generation failure guidance", () => {
    pageProps = {
      ...pageProps,
      state: "generation_failed",
      nextAction: {
        title: "Document generation failed",
        description: "Contact support.",
        ctaLabel: "Open profile",
        ctaKind: "profile",
        ctaHref: "/profile",
      },
      contract: {
        ...activeContract,
        status: "generation_error",
        statusLabel: "Generation error",
        statusTone: "danger",
        previewUrl: null,
        downloadUrl: null,
        generatedPdf: null,
      },
    };
    render(<MyContract />);
    expect(screen.getByText(/could not be generated/i)).toBeInTheDocument();
  });

  it("shows the agreement's progress in the agent's own terms", () => {
    render(<MyContract />);

    const steps = within(
      screen.getByRole("list", { name: /agreement progress/i }),
    ).getAllByRole("listitem");
    // The brokerage-internal `draft` and `ready_for_review` stages are not the
    // agent's business; these four are what they can act on or wait for.
    expect(steps).toHaveLength(4);
    // "Active" also appears in the header status badge, so read the labels off
    // the timeline itself.
    for (const [index, label] of [
      "Sent to you",
      "Opened",
      "Signed",
      "Active",
    ].entries()) {
      expect(within(steps[index]).getByText(label)).toBeVisible();
    }
  });

  it("stops the progress where a replaced agreement actually stopped", () => {
    pageProps = {
      ...pageProps,
      state: "superseded",
      contract: {
        ...activeContract,
        status: "superseded",
        statusLabel: "Superseded",
        statusTone: "neutral",
        signedAt: null,
        activatedAt: null,
        supersededAt: "2026-02-01T12:00:00Z",
      },
    };
    render(<MyContract />);

    const steps = within(
      screen.getByRole("list", { name: /agreement progress/i }),
    ).getAllByRole("listitem");
    // Sent, Opened, Replaced — not the Signed and Active steps it never reached.
    expect(steps).toHaveLength(3);
    expect(screen.getByText("Replaced")).toBeVisible();
    expect(screen.queryByText("Active")).toBeNull();
  });

  it("keeps the contract id available without ranking it as a headline fact", () => {
    render(<MyContract />);

    expect(screen.getByText("Contract id")).toBeVisible();
    expect(screen.getByText(activeContract.publicId)).toBeVisible();
  });

  it("says an open-ended agreement has no end date", () => {
    pageProps = {
      ...pageProps,
      contract: { ...activeContract, expiresOn: null },
    };
    render(<MyContract />);

    expect(screen.getByText("No end date")).toBeVisible();
  });
});
