import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OfficeResourcesAdministration from "@/pages/OfficeResourcesAdministration";
import type { OfficeResourcesAdministrationPageProps } from "@/types";

const routerGet = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: OfficeResourcesAdministrationPageProps;

const baseProps: OfficeResourcesAdministrationPageProps = {
  resources: {
    items: [
      {
        id: 1,
        slug: "wifi-password",
        title: "Branch Wi-Fi",
        summary: "Front desk knows the password.",
        category: "printer_wifi",
        categoryLabel: "Printer / Wi-Fi / copier",
        resourceType: "content",
        typeLabel: "Content",
        ownerPathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
        ownerStableKey: "fairfax-va",
        sourceLabel: "Fairfax VA",
        state: "active",
        isActive: true,
        isArchived: false,
        processingState: "ready",
        fileName: "",
        startsAt: "",
        endsAt: "",
        updatedAt: "2026-08-22T00:00:00Z",
      },
      {
        id: 2,
        slug: "forms-packet",
        title: "Forms packet",
        summary: "",
        category: "local_forms",
        categoryLabel: "Local forms",
        resourceType: "file",
        typeLabel: "File",
        ownerPathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
        ownerStableKey: "fairfax-va",
        sourceLabel: "Fairfax VA",
        state: "archived",
        isActive: false,
        isArchived: true,
        processingState: "quarantined",
        fileName: "packet.pdf",
        startsAt: "",
        endsAt: "",
        updatedAt: "2026-08-22T00:00:00Z",
      },
    ],
    pagination: {
      page: 1,
      pageSize: 50,
      totalItems: 2,
      totalPages: 1,
      hasNext: false,
      hasPrevious: false,
    },
    filters: {
      q: "",
      category: "",
      resource_type: "",
      status: "",
      owner: "",
      region: "",
    },
    sort: null,
  },
  filterOptions: {
    categories: [{ value: "printer_wifi", label: "Printer / Wi-Fi / copier" }],
    types: [
      { value: "content", label: "Content" },
      { value: "link", label: "Link" },
      { value: "file", label: "File" },
    ],
    statuses: [{ value: "archived", label: "Archived" }],
    owners: [{ value: "fairfax-va", label: "Fairfax VA" }],
  },
  writableOffices: [{ id: 3, label: "Fairfax VA", kind: "branch" }],
  capabilities: { canManage: true, canPublishCompany: false },
  scope: { level: "office", label: "Office scope" },
  csrfToken: "test-csrf-token",
  validation: { fields: {}, form: [] },
  user: {
    id: 1,
    permissions: ["web.view_office_resources_admin"],
  },
} as unknown as OfficeResourcesAdministrationPageProps;

describe("OfficeResourcesAdministration", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("lists scoped resources with state and quarantine badges", () => {
    render(<OfficeResourcesAdministration />);
    expect(screen.getByText("Branch Wi-Fi")).toBeInTheDocument();
    expect(screen.getByText("Forms packet")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.getByText("File quarantined")).toBeInTheDocument();
  });

  it("links each row into its workspace", () => {
    render(<OfficeResourcesAdministration />);
    const link = screen.getAllByRole("link", { name: /branch wi-fi/i })[0];
    expect(link).toHaveAttribute("href", "/operations/office-resources/1");
  });

  it("opens the create sheet from the New resource action", async () => {
    const user = userEvent.setup();
    render(<OfficeResourcesAdministration />);
    await user.click(screen.getByRole("button", { name: /new resource/i }));
    expect(screen.getByRole("heading", { name: /new resource/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/owning office/i)).toBeInTheDocument();
    // The form posts to the create endpoint with the sheet marker.
    const form = document.getElementById("office-resource-create-form");
    expect(form).toHaveAttribute("action", "/operations/office-resources/create");
    expect(form).toHaveAttribute("enctype", "multipart/form-data");
    const context = form?.querySelector('input[name="context"]');
    expect(context).toHaveValue("sheet");
  });

  it("re-opens the create sheet with a draft after a failed submit", () => {
    pageProps = {
      ...baseProps,
      validation: { fields: { title: ["This field is required."] }, form: [] },
      createSheet: { open: true, draft: { title: "Draft title" } },
    };
    render(<OfficeResourcesAdministration />);
    expect(
      screen.getAllByRole("heading", { name: /new resource/i }).length,
    ).toBeGreaterThan(0);
    expect(screen.getByLabelText(/title/i)).toHaveValue("Draft title");
  });

  it("does not render the create sheet for read-only viewers", () => {
    pageProps = {
      ...baseProps,
      capabilities: { canManage: false, canPublishCompany: false },
    };
    render(<OfficeResourcesAdministration />);
    expect(screen.queryByRole("button", { name: /new resource/i })).toBeNull();
    expect(screen.queryByText(/publish an instruction/i)).not.toBeInTheDocument();
  });
});
