import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsPanel } from "./DocumentsPanel";

const routerGet = vi.fn();
const routerPost = vi.fn();

vi.mock("@inertiajs/react", () => ({
  router: {
    get: (...args: unknown[]) => routerGet(...args),
    post: (...args: unknown[]) => routerPost(...args),
  },
}));

const schema = {
  categories: [
    { value: "other", label: "Other" },
    { value: "disclosure", label: "Disclosure" },
  ],
  requirements: [
    { value: "optional", label: "Optional" },
    { value: "required", label: "Required" },
  ],
  retentionPolicies: [{ value: "indefinite", label: "Indefinite" }],
  signatureStatuses: [{ value: "none", label: "None" }],
  complianceStatuses: [{ value: "none", label: "None" }],
  matrix: {
    extensions: [".pdf", ".png"],
    maxBytes: 20 * 1024 * 1024,
    maxCount: 40,
    maxBatch: 10,
  },
};

const readyVersion = {
  publicId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  versionNumber: 1,
  originalName: "offer.pdf",
  displayName: "offer.pdf",
  mediaType: "application/pdf",
  byteSize: 1200,
  checksum: "",
  processingState: "ready",
  processingNote: "",
  isReadable: true,
  isCurrent: true,
  isLocked: false,
  signatureStatus: "none",
  signatureStatusLabel: "None",
  complianceStatus: "none",
  complianceStatusLabel: "None",
  lockedAt: null,
  lockReason: "",
  uploadedBy: { id: "1", displayName: "Ada" },
  createdAt: "2026-09-21T00:00:00Z",
  downloadUrl:
    "/transactions/documents/versions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/file",
  previewUrl:
    "/transactions/documents/versions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/preview",
  reviewComments: [],
};

const lockedVersion = {
  ...readyVersion,
  publicId: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  isLocked: true,
  complianceStatus: "approved",
  complianceStatusLabel: "Approved",
  lockReason: "approved",
  lockedAt: "2026-09-21T01:00:00Z",
};

describe("DocumentsPanel", () => {
  beforeEach(() => {
    routerGet.mockReset();
    routerPost.mockReset();
  });

  it("shows empty state and hides uploader when read-only", () => {
    render(
      <DocumentsPanel
        documents={[]}
        documentSchema={schema}
        expectedVersion="v1"
        publicId="11111111-1111-1111-1111-111111111111"
        canEdit={false}
        canLock={false}
      />,
    );
    expect(screen.getByText("No documents yet")).toBeTruthy();
    expect(screen.queryByText("Upload document")).toBeNull();
  });

  it("shows upload controls when editable", () => {
    render(
      <DocumentsPanel
        documents={[]}
        documentSchema={schema}
        expectedVersion="v1"
        publicId="11111111-1111-1111-1111-111111111111"
        canEdit
        canLock
      />,
    );
    expect(screen.getByText("Upload document")).toBeTruthy();
    expect(screen.getByText("Choose files")).toBeTruthy();
  });

  it("disables retire for locked current versions and shows lock badge", () => {
    render(
      <DocumentsPanel
        documents={[
          {
            publicId: "cccccccc-cccc-cccc-cccc-cccccccccccc",
            title: "Purchase agreement",
            category: "purchase_agreement",
            categoryLabel: "Purchase agreement",
            requirement: "required",
            requirementLabel: "Required",
            retentionPolicy: "indefinite",
            retentionPolicyLabel: "Indefinite",
            retainUntil: null,
            createdBy: null,
            createdAt: null,
            updatedAt: null,
            currentVersion: lockedVersion,
            versions: [lockedVersion],
          },
        ]}
        documentSchema={schema}
        expectedVersion="v1"
        publicId="11111111-1111-1111-1111-111111111111"
        canEdit
        canLock
      />,
    );
    expect(screen.getByText("Locked")).toBeTruthy();
    expect(screen.queryByText("Retire")).toBeNull();
    expect(screen.queryByText("Mark approved")).toBeNull();
  });

  it("posts a review comment", async () => {
    const user = userEvent.setup();
    render(
      <DocumentsPanel
        documents={[
          {
            publicId: "cccccccc-cccc-cccc-cccc-cccccccccccc",
            title: "Disclosure",
            category: "disclosure",
            categoryLabel: "Disclosure",
            requirement: "optional",
            requirementLabel: "Optional",
            retentionPolicy: "indefinite",
            retentionPolicyLabel: "Indefinite",
            retainUntil: null,
            createdBy: null,
            createdAt: null,
            updatedAt: null,
            currentVersion: readyVersion,
            versions: [readyVersion],
          },
        ]}
        documentSchema={schema}
        expectedVersion="v1"
        publicId="11111111-1111-1111-1111-111111111111"
        canEdit
        canLock
      />,
    );
    await user.type(screen.getByLabelText("Review comment"), "Looks good");
    await user.click(screen.getByRole("button", { name: /Add comment/i }));
    expect(routerPost).toHaveBeenCalled();
    expect(String(routerPost.mock.calls[0][0])).toContain("/comments");
  });
});
