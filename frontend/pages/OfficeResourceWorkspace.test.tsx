import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OfficeResourceWorkspace from "@/pages/OfficeResourceWorkspace";
import type { OfficeResourceWorkspacePageProps } from "@/types";

const routerPost = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { post: (...args: unknown[]) => routerPost(...args) },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: OfficeResourceWorkspacePageProps;

const baseProps = {
  resource: {
    id: 7,
    slug: "wifi-password",
    title: "Branch Wi-Fi",
    summary: "",
    category: "printer_wifi",
    resourceType: "content",
    body: "Network: onest-guest",
    url: "",
    ownerId: 3,
    ownerPathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
    isActive: true,
    isArchived: false,
    archivedAt: "",
    processingState: "ready",
    fileName: "",
    downloadUrl: "",
    sortOrder: 10,
    startsAt: "",
    endsAt: "",
    createdAt: "2026-08-01T00:00:00Z",
    updatedAt: "2026-08-22T00:00:00Z",
  },
  version: "7:2026-08-22T00:00:00.000000+00:00",
  preview: {
    officeId: 3,
    officeLabel: "Fairfax VA",
    items: [
      {
        slug: "company-handbook",
        title: "Company handbook",
        summary: "",
        categoryLabel: "General",
        resourceType: "content",
        sourceLabel: "Company",
        origin: "inherited",
      },
      {
        slug: "wifi-password",
        title: "Branch Wi-Fi",
        summary: "",
        categoryLabel: "Printer / Wi-Fi / copier",
        resourceType: "content",
        sourceLabel: "Fairfax VA",
        origin: "local",
      },
    ],
    localCount: 1,
    inheritedCount: 1,
  },
  writableOffices: [{ id: 3, label: "Fairfax VA", kind: "branch" }],
  capabilities: { canManage: true, canPublishCompany: false },
  categories: [{ value: "printer_wifi", label: "Printer / Wi-Fi / copier" }],
  types: [
    { value: "content", label: "Content" },
    { value: "link", label: "Link" },
    { value: "file", label: "File" },
  ],
  scope: { level: "office", label: "Office scope" },
  validation: { fields: {}, form: [] },
  user: {
    id: 1,
    permissions: ["web.view_office_resources_admin", "web.manage_office_resources"],
  },
  csrfToken: "test-csrf-token",
} as unknown as OfficeResourceWorkspacePageProps;

describe("OfficeResourceWorkspace", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerPost.mockClear();
  });

  it("renders the edit form with concurrency and CSRF tokens", () => {
    const { container } = render(<OfficeResourceWorkspace />);
    expect(screen.getByLabelText(/title/i)).toHaveValue("Branch Wi-Fi");
    const versions = container.querySelectorAll('input[name="expected_version"]');
    expect(versions.length).toBeGreaterThan(0);
    expect(versions[0]).toHaveValue(baseProps.version);
    expect(container.querySelector('input[name="csrfmiddlewaretoken"]')).toBeTruthy();
    const form = versions[0]?.closest("form");
    expect(form).toHaveAttribute("action", "/operations/office-resources/7/submit");
  });

  it("shows inherited versus local origin badges in the preview", () => {
    render(<OfficeResourceWorkspace />);
    expect(screen.getByText(/Library preview · Fairfax VA/i)).toBeInTheDocument();
    expect(screen.getByText("Inherited · Company")).toBeInTheDocument();
    expect(screen.getByText("Local · Fairfax VA")).toBeInTheDocument();
    expect(screen.getByText(/1 local · 1 inherited/)).toBeInTheDocument();
  });

  it("offers activate/deactivate/archive per lifecycle state", () => {
    render(<OfficeResourceWorkspace />);
    expect(screen.getByRole("button", { name: /^deactivate$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^archive$/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^activate$/i }),
    ).not.toBeInTheDocument();
  });

  it("exposes file replacement for file resources", () => {
    pageProps = {
      ...pageProps,
      resource: {
        ...baseProps.resource,
        resourceType: "file",
        fileName: "packet.pdf",
        downloadUrl: "/office-resources/packet/download",
      } as OfficeResourceWorkspacePageProps["resource"],
    };
    render(<OfficeResourceWorkspace />);
    const link = screen.getByText(/packet\.pdf/i);
    expect(link).toHaveAttribute("download");
    expect(screen.getByLabelText(/replace file/i)).toBeInTheDocument();
  });

  it("marks the workspace read-only without manage rights", () => {
    pageProps = {
      ...pageProps,
      capabilities: { canManage: false, canPublishCompany: false },
    };
    render(<OfficeResourceWorkspace />);
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save changes/i })).toBeNull();
  });

  it("renders a create form for new resources", () => {
    pageProps = {
      ...baseProps,
      resource: null,
      version: "",
      preview: null,
      user: {
        id: 1,
        permissions: ["web.view_office_resources_admin", "web.manage_office_resources"],
      },
      csrfToken: "test-csrf-token",
    } as unknown as OfficeResourceWorkspacePageProps;
    const { container } = render(<OfficeResourceWorkspace />);
    const form = screen
      .getByRole("button", { name: /create resource/i })
      .closest("form");
    expect(form).toHaveAttribute("action", "/operations/office-resources/create");
    expect(container.querySelector('input[name="csrfmiddlewaretoken"]')).toBeTruthy();
  });
});
