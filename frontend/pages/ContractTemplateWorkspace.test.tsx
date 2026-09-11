import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ContractTemplateWorkspace from "@/pages/ContractTemplateWorkspace";
import type { ContractTemplateWorkspacePageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as ContractTemplateWorkspacePageProps,
}));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current }),
  Head: () => null,
  router: { post: routerPost },
}));

/** pdf.js needs a worker and a canvas; neither exists under jsdom. */
vi.mock("@/components/ContractTemplateFieldPlacer", () => ({
  ContractTemplateFieldPlacer: ({ dirty }: { dirty?: boolean }) => (
    <div data-testid="field-placer">{dirty ? "dirty" : "clean"}</div>
  ),
}));

function props(
  overrides: Partial<ContractTemplateWorkspacePageProps["versionDetail"]> = {},
): ContractTemplateWorkspacePageProps {
  return {
    user: {
      id: 1,
      email: "avery@onest.realestate",
      name: "Avery Johnson",
      headshotUrl: null,
      permissions: [
        "contract.manage_contract_templates",
        "contract.approve_contract_templates",
      ],
      roles: ["system_admin"],
      roleLabel: "System Admin",
    },
    capabilities: { canManage: true, canApprove: true },
    errors: { fields: {}, form: [] },
    posted: null,
    versionDetail: {
      id: 7,
      publicId: "ctv_7",
      templatePublicId: "ct_2",
      versionLabel: "1.0.0",
      displayName: "Contractor Agreement Form",
      description: "Independent contractor agreement.",
      status: "draft",
      statusLabel: "Draft",
      statusTone: "neutral",
      sourceFormat: "pdf",
      sourceMediaType: "application/pdf",
      sourceChecksum: "abc123",
      sourcePdfUrl: "/media/templates/7.pdf",
      fieldLayout: [
        {
          id: "f1",
          name: "PrefillText",
          type: "text",
          role: "Prefill",
          page: 1,
          x: 10,
          y: 20,
          w: 180,
          h: 28,
        },
        {
          id: "f2",
          name: "CompanySignature",
          type: "signature",
          role: "Company",
          page: 1,
          x: 10,
          y: 60,
          w: 180,
          h: 48,
        },
        {
          id: "f3",
          name: "CompanySignedOn",
          type: "date",
          role: "Company",
          page: 1,
          x: 200,
          y: 60,
          w: 120,
          h: 28,
        },
        {
          id: "f4",
          name: "AgentSignature",
          type: "signature",
          role: "Agent",
          page: 1,
          x: 10,
          y: 120,
          w: 180,
          h: 48,
        },
        {
          id: "f5",
          name: "AgentSignedOn",
          type: "date",
          role: "Agent",
          page: 1,
          x: 200,
          y: 120,
          w: 120,
          h: 28,
        },
      ],
      fieldAiConfigured: false,
      mergeSourceOptions: ["party.legalFirstName", "office.name"],
      placeholderKeys: ["PrefillText"],
      mergeSchema: [{ key: "PrefillText", label: "First name", type: "text" }],
      mergeSchemaJson: "[]",
      previewChecksum: "",
      previewGeneratedAt: null,
      previewUrl: null,
      validationErrors: [],
      publishedAt: null,
      retiredAt: null,
      contractsUsingVersion: 0,
      version: "v-token",
      template: {
        publicId: "ct_2",
        name: "Contractor Agreement",
      } as ContractTemplateWorkspacePageProps["versionDetail"]["template"],
      ...overrides,
    },
    // Only the props this page reads; the shared PageProps shell is irrelevant
    // here and mocking all of it would test the mock.
  } as unknown as ContractTemplateWorkspacePageProps;
}

describe("ContractTemplateWorkspace", () => {
  beforeEach(() => {
    routerPost.mockClear();
    pageProps.current = props();
  });

  it("names the stalled pipeline stage and points the primary action at it", () => {
    render(<ContractTemplateWorkspace />);

    const strip = screen.getByRole("list");
    expect(within(strip).getByText("Data mapped")).toBeInTheDocument();
    expect(within(strip).getByText("1 of 1 still unmapped")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Map hub data/ })).toBeInTheDocument();
    expect(
      screen.getByText(/Publishing is blocked until this is cleared/),
    ).toBeInTheDocument();
  });

  it("opens on the document when a source PDF exists", () => {
    render(<ContractTemplateWorkspace />);

    expect(screen.getByRole("tab", { name: /Document/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByTestId("field-placer")).toBeInTheDocument();
  });

  it("opens on the details tab when there is no source PDF", () => {
    pageProps.current = props({ sourcePdfUrl: "" });
    render(<ContractTemplateWorkspace />);

    expect(screen.getByRole("tab", { name: /Template details/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("moves between views with the arrow keys", async () => {
    const user = userEvent.setup();
    render(<ContractTemplateWorkspace />);

    await user.click(screen.getByRole("tab", { name: /Document/ }));
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("tab", { name: /Data mapping/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Prefill fields to hub data")).toBeInTheDocument();
  });

  it("saves name, description, and mapping through one draft post", async () => {
    const user = userEvent.setup();
    render(<ContractTemplateWorkspace />);

    await user.click(screen.getByRole("tab", { name: /Template details/ }));
    await user.type(screen.getByLabelText("Display name"), "!");
    // The panel's own closing bar, not the header's next-action button.
    const [, panelSave] = screen.getAllByRole("button", { name: "Save draft" });
    await user.click(panelSave as HTMLElement);

    expect(routerPost).toHaveBeenCalledTimes(1);
    const [, payload] = routerPost.mock.calls[0] ?? [];
    expect(payload).toMatchObject({
      display_name: "Contractor Agreement Form!",
      expected_version: "v-token",
    });
    expect(
      JSON.parse((payload as { merge_schema_json: string }).merge_schema_json),
    ).toHaveLength(1);
  });

  it("keeps draft edits out of reach for a reviewer who cannot manage", () => {
    pageProps.current = {
      ...props(),
      capabilities: { canManage: false, canApprove: true },
    };
    render(<ContractTemplateWorkspace />);

    expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();
  });
});
