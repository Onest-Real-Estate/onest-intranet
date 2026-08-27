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

vi.mock("@/components/DocusealBuilderEmbed", () => ({
  DocusealBuilderEmbed: ({ token }: { token: string }) => (
    <div data-testid="docuseal-builder">{token}</div>
  ),
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
              workspaceVersionPk: 9,
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

  it("links draft families into their draft workspace", () => {
    vi.mocked(usePage).mockReturnValue({
      props: {
        csrfToken: "token",
        user: {
          id: 1,
          email: "admin@example.com",
          permissions: ["contract.manage_contract_templates"],
        },
        templates: {
          items: [
            {
              publicId: "pub-2",
              stableKey: "agent-contract",
              name: "Agent Contract",
              description: "",
              status: "draft",
              jurisdictionStateCodes: ["VA"],
              companyWide: true,
              effectiveFrom: "",
              effectiveUntil: "",
              activeVersionPk: null,
              activeVersionId: null,
              workspaceVersionPk: 42,
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
        capabilities: { canManage: true, canApprove: false },
        createSheet: null,
        errors: { fields: {}, form: [] },
      },
    } as never);
    render(<ContractTemplateAdministration />);
    expect(screen.getByRole("link", { name: /edit draft/i })).toHaveAttribute(
      "href",
      "/operations/contract-templates/templates/42",
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
          sourceFormat: "pdf",
          sourceMediaType: "application/pdf",
          sourceChecksum: "a".repeat(64),
          docusealTemplateId: null,
          docusealExternalId: "",
          docusealHost: "",
          docusealOrigin: "",
          docusealAdminUrl: "",
          docusealEmbedsAvailable: false,
          builder: null,
          builderReady: false,
          mergeSourceOptions: ["party.legalFirstName", "office.state"],
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
            workspaceVersionPk: 9,
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

  it("embeds the DocuSeal builder when a token is present", () => {
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
        capabilities: { canManage: true, canApprove: true },
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
          sourceFormat: "pdf",
          sourceMediaType: "application/pdf",
          sourceChecksum: "a".repeat(64),
          docusealTemplateId: 55,
          docusealExternalId: "ext-55",
          docusealHost: "localhost:3000",
          docusealOrigin: "http://localhost:3000",
          docusealAdminUrl: "http://localhost:3000/templates/55",
          docusealEmbedsAvailable: true,
          builder: {
            token: "builder-jwt",
            host: "localhost:3000",
            protocol: "http",
            templateId: "55",
          },
          builderReady: true,
          mergeSourceOptions: ["party.legalFirstName"],
          placeholderKeys: ["party.legalFirstName"],
          mergeSchema: [
            {
              key: "party.legalFirstName",
              label: "First name",
              type: "text",
              source: "party.legalFirstName",
            },
          ],
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
            workspaceVersionPk: 9,
          },
        },
      },
    } as never);
    render(<ContractTemplateWorkspace />);
    expect(screen.getByTestId("docuseal-builder")).toHaveTextContent("builder-jwt");
    expect(screen.getByText(/merge field mapping/i)).toBeInTheDocument();
  });
});
