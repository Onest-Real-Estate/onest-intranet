import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TransactionSignatureCeremony from "@/pages/TransactionSignatureCeremony";
import type { TransactionSignatureCeremonyPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as TransactionSignatureCeremonyPageProps,
}));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current }),
  Head: () => null,
  router: { post: routerPost, visit: vi.fn() },
}));

/** The pad needs a canvas 2d context, which jsdom does not provide. */
vi.mock("@/components/ContractSignaturePad", () => ({
  ContractSignaturePad: () => <div data-testid="signature-pad" />,
}));

function props(
  overrides: Partial<TransactionSignatureCeremonyPageProps> = {},
): TransactionSignatureCeremonyPageProps {
  return {
    canSign: true,
    signingReady: true,
    recovery: null,
    disclosure: {
      version: "v1",
      title: "Electronic signature disclosure",
      body: "You agree to sign electronically.",
      acknowledgementLabel: "I agree to sign electronically",
    },
    package: {
      publicId: "pkg-1",
      title: "Purchase agreement signatures",
      status: "in_progress",
      routingMode: "ordered",
      disclosureVersion: "v1",
      expiresAt: null,
      expectedVersion: "pkg-token",
    },
    signer: {
      publicId: "signer-2",
      roleLabel: "Seller",
      displayName: "Sam Seller",
      email: "sam@example.com",
      status: "invited",
      statusLabel: "Invited",
      routingOrder: 2,
      signedAt: null,
    },
    documents: [
      {
        publicId: "pkgdoc-1",
        displayName: "offer.pdf",
        pageCount: 3,
        sortOrder: 0,
        previewUrl: "/transactions/sign/pkg-1/documents/pkgdoc-1/",
        fields: [
          {
            publicId: "fld-1",
            name: "SellerSignature",
            type: "signature",
            typeLabel: "Signature",
            signerKey: "signer-2",
            documentKey: "pkgdoc-1",
            page: 2,
            x: 72,
            y: 600,
            w: 200,
            h: 56,
            required: true,
          },
          {
            publicId: "fld-2",
            name: "SellerSignedOn",
            type: "date",
            typeLabel: "Date",
            signerKey: "signer-2",
            documentKey: "pkgdoc-1",
            page: 2,
            x: 288,
            y: 600,
            w: 140,
            h: 28,
            required: true,
          },
        ],
      },
    ],
    ceremony: null,
    errors: { fields: {}, form: [] },
    endpoints: {
      mode: "hub",
      startUrl: "/transactions/sign/pkg-1/",
      completeUrl: "/transactions/sign/pkg-1/complete",
      declineUrl: "/transactions/sign/pkg-1/decline",
      previewTokenParam: "",
      previewToken: "",
    },
    ...overrides,
  } as TransactionSignatureCeremonyPageProps;
}

describe("TransactionSignatureCeremony", () => {
  beforeEach(() => {
    routerPost.mockClear();
    pageProps.current = props();
  });

  it("holds the ceremony behind the disclosure until it is acknowledged", async () => {
    const user = userEvent.setup();
    render(<TransactionSignatureCeremony />);

    const proceed = screen.getByRole("button", {
      name: /Continue to electronic signature/,
    });
    expect(proceed).toBeDisabled();

    await user.click(screen.getByLabelText("I agree to sign electronically"));
    expect(proceed).toBeEnabled();

    await user.click(proceed);
    const [url, payload] = routerPost.mock.calls[0] ?? [];
    expect(url).toBe("/transactions/sign/pkg-1/");
    expect(payload).toMatchObject({
      consentAccepted: true,
      disclosureVersion: "v1",
      expectedVersion: "pkg-token",
    });
  });

  it("refuses to start when the server says this signer cannot sign", () => {
    pageProps.current = props({ canSign: false, signingReady: false });
    render(<TransactionSignatureCeremony />);

    expect(
      screen.getByRole("button", { name: /Continue to electronic signature/ }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /Decline to sign/ })).toBeDisabled();
  });

  it("replaces the ceremony with the recovery message when one is set", () => {
    pageProps.current = props({
      recovery: { code: "not_your_turn", message: "Another party signs before you." },
    });
    render(<TransactionSignatureCeremony />);

    expect(screen.getByText("Another party signs before you.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Continue to electronic signature/ }),
    ).toBeNull();
  });

  it("renders only the fields the server addressed to this signer", () => {
    pageProps.current = props({
      ceremony: { intentPublicId: "intent-1", expiresAt: "2026-09-22T10:00:00Z" },
    });
    render(<TransactionSignatureCeremony />);

    // The date field this signer owns is fillable; nothing belonging to the
    // buyer is in the payload, so no control exists for it.
    expect(screen.getByLabelText("SellerSignedOn")).toBeInTheDocument();
    expect(screen.queryByLabelText("BuyerSignedOn")).toBeNull();
    expect(screen.queryByText(/BuyerSignature/)).toBeNull();
    expect(screen.getByTestId("signature-pad")).toBeInTheDocument();
  });

  it("blocks the finish button until every required field is filled", async () => {
    pageProps.current = props({
      ceremony: { intentPublicId: "intent-1", expiresAt: "2026-09-22T10:00:00Z" },
    });
    render(<TransactionSignatureCeremony />);

    expect(
      screen.getByRole("button", { name: /Apply signature and finish/ }),
    ).toBeDisabled();
    expect(screen.getByText("Add your signature to finish.")).toBeInTheDocument();
  });
});
