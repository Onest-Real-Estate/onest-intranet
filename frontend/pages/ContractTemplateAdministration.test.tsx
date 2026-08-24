import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ContractTemplateAdministration from "@/pages/ContractTemplateAdministration";
import ContractTemplateWorkspace from "@/pages/ContractTemplateWorkspace";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ href, children }: { href: string; children?: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
  usePage: vi.fn(),
}));

vi.mock("@/components/HubLayout", () => ({
  HubLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="hub-layout">{children}</div>
  ),
}));

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { usePage } from "@inertiajs/react";

describe("ContractTemplateAdministration", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    vi.mocked(usePage).mockReturnValue({
      props: {
        csrfToken: "token",
        user: {
          id: 1,
          email: "admin@example.com",
          permissions: [
            "contract.manage_contract_templates",
            "contract.approve_contract_templates",
          ],
        },
        templates: {
          items: [
            {
              publicId: "pub-1",
              stableKey: "ica-standard",
              name: "ICA Standard",
              description: "Main agreement",
              status: "active",
              jurisdictionStateCodes: ["VA"],
              companyWide: false,
              effectiveFrom: "",
              effectiveUntil: "",
              activeVersionPk: 9,
              activeVersionId: "ver-1",
            },
          ],
          pagination: {
            page: 1,
            pageSize: 20,
            totalItems: 1,
            totalPages: 1,
            hasNext: false,
            hasPrevious: false,
          },
          filters: { q: "", status: "", jurisdiction: "" },
          sort: null,
        },
        capabilities: { canManage: true, canApprove: true },
        createSheet: null,
        errors: { fields: {}, form: [] },
      },
    } as never);
  });

  it("lists template families and links into the workspace", () => {
    render(<ContractTemplateAdministration />);
    expect(screen.getByText("ICA Standard")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open/i })).toHaveAttribute(
      "href",
      "/operations/contract-templates/templates/9",
    );
  });

  it("drives search through Inertia", async () => {
    const user = userEvent.setup();
    render(<ContractTemplateAdministration />);
    await user.type(screen.getByLabelText(/search templates/i), "ica");
    await user.keyboard("{Enter}");
    expect(getMock).toHaveBeenCalled();
  });
});

describe("ContractTemplateWorkspace", () => {
  beforeEach(() => {
    vi.mocked(usePage).mockReturnValue({
      props: {
        csrfToken: "token",
        user: {
          id: 1,
          email: "admin@example.com",
          permissions: ["contract.approve_contract_templates"],
        },
        capabilities: { canManage: false, canApprove: true },
        errors: { fields: {}, form: [] },
        posted: null,
        versionDetail: {
          id: 9,
          publicId: "ver-1",
          templatePublicId: "tpl-1",
          versionLabel: "1.0.0",
          displayName: "ICA Standard",
          description: "Draft",
          status: "draft",
          sourceFormat: "docx",
          sourceMediaType:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          sourceChecksum: "a".repeat(64),
          placeholderKeys: ["party.legalFirstName"],
          mergeSchema: [],
          mergeSchemaJson: "[]",
          previewChecksum: "",
          previewGeneratedAt: null,
          previewUrl: null,
          validationErrors: [],
          publishedAt: null,
          retiredAt: null,
          contractsUsingVersion: 0,
          version: "2026-08-24T12:00:00+00:00",
          template: {
            publicId: "tpl-1",
            stableKey: "ica-standard",
            name: "ICA Standard",
            description: "Main agreement",
            status: "draft",
            jurisdictionStateCodes: ["VA"],
            companyWide: false,
            effectiveFrom: "",
            effectiveUntil: "",
            activeVersionPk: null,
            activeVersionId: null,
          },
        },
      },
    } as never);
  });

  it("shows the approver review note when draft editing is withheld", () => {
    render(<ContractTemplateWorkspace />);
    expect(
      screen.getByText(/review, preview, publish, and activate/i),
    ).toBeInTheDocument();
  });
});
