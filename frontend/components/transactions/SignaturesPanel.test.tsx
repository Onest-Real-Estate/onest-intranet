import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SignaturePackageRow, SignatureSchema } from "@/types";
import { SignaturesPanel } from "./SignaturesPanel";

const routerPost = vi.fn();

vi.mock("@inertiajs/react", () => ({
  router: { post: (...args: unknown[]) => routerPost(...args) },
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const schema: SignatureSchema = {
  packageStatuses: [{ value: "draft", label: "Draft" }],
  routingModes: [
    { value: "ordered", label: "Ordered" },
    { value: "parallel", label: "Parallel" },
  ],
  deliveryMethods: [
    { value: "email", label: "Email magic link" },
    { value: "hub", label: "Hub user" },
  ],
  signerStatuses: [{ value: "pending", label: "Pending" }],
  fieldTypes: [{ value: "signature", label: "Signature" }],
  disclosure: {
    version: "v1",
    title: "Electronic signature disclosure",
    body: "Body",
    acknowledgementLabel: "I agree",
  },
};

const sentPackage: SignaturePackageRow = {
  publicId: "pkg-1",
  title: "Purchase agreement signatures",
  status: "in_progress",
  statusLabel: "In progress",
  routingMode: "ordered",
  routingModeLabel: "Ordered",
  disclosureVersion: "v1",
  isDraft: false,
  isTerminal: false,
  expiresAt: null,
  sentAt: "2026-09-20T00:00:00Z",
  completedAt: null,
  cancelledAt: null,
  createdAt: "2026-09-19T00:00:00Z",
  updatedAt: "2026-09-20T00:00:00Z",
  progress: { signed: 1, total: 2 },
  documents: [
    {
      publicId: "pkgdoc-1",
      versionPublicId: "ver-1",
      displayName: "offer.pdf",
      pageCount: 3,
      sortOrder: 0,
      sourceChecksum: "abc",
      previewUrl: "/transactions/sign/pkg-1/documents/pkgdoc-1/",
    },
  ],
  signers: [
    {
      publicId: "signer-1",
      signerKey: "signer-1",
      roleLabel: "Buyer",
      displayName: "Rae Buyer",
      email: "rae@example.com",
      deliveryMethod: "email",
      deliveryMethodLabel: "Email magic link",
      routingOrder: 1,
      status: "signed",
      statusLabel: "Signed",
      isHubUser: false,
      partyPublicId: null,
      invitedAt: null,
      viewedAt: null,
      signedAt: "2026-09-20T01:00:00Z",
      declinedAt: null,
      declineReason: "",
    },
    {
      publicId: "signer-2",
      signerKey: "signer-2",
      roleLabel: "Seller",
      displayName: "Sam Seller",
      email: "sam@example.com",
      deliveryMethod: "hub",
      deliveryMethodLabel: "Hub user",
      routingOrder: 2,
      status: "invited",
      statusLabel: "Invited",
      isHubUser: true,
      partyPublicId: null,
      invitedAt: "2026-09-20T00:05:00Z",
      viewedAt: null,
      signedAt: null,
      declinedAt: null,
      declineReason: "",
    },
  ],
  artifacts: [
    {
      publicId: "art-1",
      kind: "signed_pdf",
      kindLabel: "Signed PDF",
      displayName: "offer-signed.pdf",
      packageDocumentPublicId: "pkgdoc-1",
      mediaType: "application/pdf",
      byteSize: 4096,
      checksum: "def",
      createdAt: "2026-09-20T02:00:00Z",
      downloadUrl: "/transactions/signatures/artifacts/art-1/",
    },
  ],
  ceremonyUrl: "/transactions/sign/pkg-1/",
};

type PanelProps = React.ComponentProps<typeof SignaturesPanel>;

function renderPanel(overrides: Partial<PanelProps> = {}) {
  return render(
    <SignaturesPanel
      signaturePackages={[]}
      signatureSchema={schema}
      documents={[]}
      parties={[]}
      expectedVersion="v1"
      publicId="txn-1"
      canEdit={false}
      {...overrides}
    />,
  );
}

describe("SignaturesPanel", () => {
  beforeEach(() => {
    routerPost.mockReset();
  });

  it("shows the empty state and hides authoring when read-only", () => {
    renderPanel();

    expect(screen.getByText("No signature packages yet")).toBeInTheDocument();
    expect(screen.queryByText("New signature package")).not.toBeInTheDocument();
  });

  it("offers the create form when the reader can manage the deal", () => {
    renderPanel({ canEdit: true });

    expect(screen.getByText("New signature package")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
  });

  it("waits for the schema before rendering any control", () => {
    renderPanel({ signatureSchema: null });

    expect(screen.getByText("Signatures loading")).toBeInTheDocument();
    expect(screen.queryByText("No signature packages yet")).not.toBeInTheDocument();
  });

  it("reports progress, signer state, and the artifact download", () => {
    renderPanel({ signaturePackages: [sentPackage] });

    expect(screen.getByText(/1 of 2 signed/)).toBeInTheDocument();
    expect(screen.getByText("Signed")).toBeInTheDocument();
    expect(screen.getByText("Invited")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Signed PDF/ })).toHaveAttribute(
      "href",
      "/transactions/signatures/artifacts/art-1/",
    );
  });

  it("keeps remind and cancel out of reach for a read-only reader", () => {
    renderPanel({ signaturePackages: [sentPackage] });

    expect(screen.queryByRole("button", { name: /Remind/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Cancel package/ })).toBeNull();
  });

  it("nudges only the signer who is actually holding the package up", async () => {
    const user = userEvent.setup();
    renderPanel({ signaturePackages: [sentPackage], canEdit: true });

    // Rae has signed; only Sam can be reminded.
    const remind = screen.getAllByRole("button", { name: /Remind/ });
    expect(remind).toHaveLength(1);

    await user.click(remind[0] as HTMLElement);

    expect(routerPost).toHaveBeenCalledTimes(1);
    const [url, payload] = routerPost.mock.calls[0] ?? [];
    expect(url).toBe("/transactions/txn-1/signatures/pkg-1/signers/signer-2/remind");
    expect(payload).toMatchObject({ expectedVersion: "v1" });
  });

  it("creates a draft from the title and routing mode", async () => {
    const user = userEvent.setup();
    renderPanel({ canEdit: true });

    await user.type(screen.getByLabelText("Title"), "Disclosure package");
    await user.click(screen.getByRole("button", { name: /Create draft/ }));

    const [url, payload] = routerPost.mock.calls[0] ?? [];
    expect(String(url)).toContain("/signatures");
    expect(payload).toMatchObject({
      title: "Disclosure package",
      routingMode: "ordered",
      expectedVersion: "v1",
    });
  });
});
