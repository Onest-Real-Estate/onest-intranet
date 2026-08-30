import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MyContractSign from "@/pages/MyContractSign";
import type { MyContractSignPageProps } from "@/types";

const routerPost = vi.fn();
const routerVisit = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    post: (...args: unknown[]) => routerPost(...args),
    visit: (...args: unknown[]) => routerVisit(...args),
  },
  usePage: () => ({ props: pageProps }),
}));

vi.mock("@/components/ContractSignaturePad", () => ({
  ContractSignaturePad: ({ onChange }: { onChange: (dataUrl: string) => void }) => (
    <button
      type="button"
      data-testid="signature-pad"
      onClick={() => onChange("data:image/png;base64,aa")}
    >
      Draw signature
    </button>
  ),
}));

let pageProps: MyContractSignPageProps;

const baseProps = {
  canSign: true,
  signingReady: true,
  recovery: null,
  disclosure: {
    version: "2026-08-29.1",
    title: "Electronic signature disclosure (ESIGN / UETA)",
    body: "You will sign electronically in the Hub.",
    acknowledgementLabel: "I acknowledge the disclosure.",
  },
  contract: {
    publicId: "11111111-1111-1111-1111-111111111111",
    versionNumber: 1,
    status: "viewed",
    statusLabel: "Viewed",
    effectiveOn: "2026-01-01",
    expectedVersion: "2026-01-01T00:00:00.000000",
    artifactChecksum: "a".repeat(64),
    partyDisplayName: "Avery Agent",
    signerEmail: "avery@example.com",
  },
  ceremony: null,
  errors: { fields: {}, form: [] },
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
} as unknown as MyContractSignPageProps;

describe("MyContractSign", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerPost.mockReset();
    routerVisit.mockReset();
  });

  it("requires acknowledgement before starting the ceremony", async () => {
    const user = userEvent.setup();
    render(<MyContractSign />);
    const start = screen.getByRole("button", {
      name: /Continue to electronic signature/i,
    });
    expect(start).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(start).toBeEnabled();
    await user.click(start);
    expect(routerPost).toHaveBeenCalledTimes(1);
    const [url, body] = routerPost.mock.calls[0];
    expect(url).toContain("/my-contract/sign");
    expect(body).toMatchObject({
      consentAccepted: true,
      disclosureVersion: "2026-08-29.1",
      contractPublicId: pageProps.contract?.publicId,
    });
  });

  it("blocks duplicate start while submitting", async () => {
    const user = userEvent.setup();
    routerPost.mockImplementation(() => {
      // Intentionally omit onFinish so the button stays disabled mid-request.
    });
    render(<MyContractSign />);
    await user.click(screen.getByRole("checkbox"));
    const start = screen.getByRole("button", {
      name: /Continue to electronic signature/i,
    });
    await user.click(start);
    expect(start).toBeDisabled();
    await user.click(start);
    expect(routerPost).toHaveBeenCalledTimes(1);
  });

  it("shows recovery copy when the contract is not signable", () => {
    pageProps = {
      ...pageProps,
      canSign: false,
      recovery: {
        code: "not_signable",
        message: "This agreement cannot be signed right now.",
      },
      contract: null,
    };
    render(<MyContractSign />);
    expect(screen.getByText(/cannot be signed right now/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Continue to electronic signature/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the Hub signature pad after an intent exists", () => {
    pageProps = {
      ...pageProps,
      ceremony: {
        intentPublicId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        expiresAt: "2026-01-01T01:00:00Z",
        reviewPdfUrl: "/my-contract/artifact-preview",
        agentFields: [
          {
            id: "f2",
            name: "AgentSignature",
            type: "signature",
            role: "Agent",
            page: 1,
            x: 72,
            y: 600,
            w: 200,
            h: 48,
          },
        ],
      },
    };
    render(<MyContractSign />);
    expect(screen.getByTestId("signature-pad")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Continue to electronic signature/i }),
    ).not.toBeInTheDocument();
  });
});
