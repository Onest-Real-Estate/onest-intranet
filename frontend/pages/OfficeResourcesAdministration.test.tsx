import { render, screen } from "@testing-library/react";
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
  capabilities: { canManage: true, canPublishCompany: false },
  scope: { level: "office", label: "Office scope" },
  validation: { fields: {}, form: [] },
  user: {
    id: 1,
    permissions: ["web.view_office_resources_admin"],
  },
  csrfToken: "test-csrf-token",
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

  it("shows the new-resource action for managers", () => {
    render(<OfficeResourcesAdministration />);
    expect(screen.getByRole("link", { name: /new resource/i })).toHaveAttribute(
      "href",
      "/operations/office-resources/new",
    );
  });

  it("hides the new-resource action without manage rights", () => {
    pageProps = {
      ...pageProps,
      capabilities: { canManage: false, canPublishCompany: false },
    };
    render(<OfficeResourcesAdministration />);
    expect(
      screen.queryByRole("link", { name: /new resource/i }),
    ).not.toBeInTheDocument();
  });
});
