import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import DocumentsAdministration from "@/pages/DocumentsAdministration";
import type { DocumentsAdministrationPageProps, DocumentsAdminRow } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as DocumentsAdministrationPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/documents" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

function row(overrides: Partial<DocumentsAdminRow> = {}): DocumentsAdminRow {
  return {
    id: 1,
    key: "exclusive-buyer",
    name: "Exclusive buyer agreement",
    description: "Current approved buyer form",
    lifecycle: { code: "live", label: "Live", tone: "success" },
    status: {
      code: "published",
      label: "Published",
      tone: "success",
      known: true,
    },
    category: {
      code: "buyer",
      label: "Buyer",
      tone: "neutral",
      known: true,
    },
    versionNumber: 2,
    versionLabel: "v2",
    ownerOffice: { id: 4, name: "Fairfax VA" },
    scope: {
      level: "office",
      label: "Office",
      officeName: "Fairfax VA",
      officeId: "4",
    },
    audience: [
      {
        kind: "office",
        label: "Fairfax VA",
        code: "",
        officeId: 4,
        userId: null,
      },
    ],
    jurisdictionStateCodes: ["VA"],
    effectiveAt: "2026-01-01T00:00:00Z",
    expiresAt: null,
    publishedAt: "2026-01-01T12:00:00Z",
    updatedAt: "2026-08-02T09:00:00Z",
    updatedBy: "Ada Admin",
    createdBy: "Ada Admin",
    version: "2026-08-02T09:00:00+00:00",
    ...overrides,
  };
}

function setPage(overrides: Partial<DocumentsAdministrationPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: [
        "web.manage_documents",
        "web.publish_documents",
        "web.retire_documents",
      ],
      roles: ["branch_manager"],
      roleLabel: "Branch Manager",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "req-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p1-document-version-admin-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    notifications: null,
    documents: {
      items: [row()],
      pagination: {
        page: 1,
        pageSize: 20,
        totalItems: 1,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: {
        q: "",
        lifecycle: "",
        category: "",
        audience: "",
        author: "",
        office: "",
        publishedFrom: "",
        publishedTo: "",
      },
      sort: { key: "updatedAt", direction: "desc" },
    },
    filterOptions: {
      categories: [{ value: "buyer", label: "Buyer" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
    },
    createOptions: {
      offices: [{ value: 4, label: "Fairfax VA" }],
      categories: [{ value: "buyer", label: "Buyer" }],
      audience: {
        canTargetCompany: false,
        regions: [{ value: 2, label: "Mid-Atlantic" }],
        offices: [{ value: 4, label: "Fairfax VA" }],
        roles: [{ value: "realtor", label: "Realtor" }],
      },
    },
    createSheet: null,
    capabilities: { canAuthor: true, canPublish: true, canRetire: true },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as DocumentsAdministrationPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  routerPost.mockClear();
  setPage();
});

describe("DocumentsAdministration", () => {
  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<DocumentsAdministration />);

    expect(screen.queryByText("Exclusive buyer agreement")).not.toBeInTheDocument();
  });

  it("lists versions in scope", () => {
    render(<DocumentsAdministration />);

    expect(screen.getByText("Exclusive buyer agreement")).toBeInTheDocument();
    expect(screen.getByText(/v2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New document/ })).toBeInTheDocument();
  });

  it("posts the drawer natively to the create route with the sheet marker", async () => {
    render(<DocumentsAdministration />);
    await userEvent.click(screen.getByRole("button", { name: /New document/ }));

    const drawer = await screen.findByRole("dialog");
    const form = drawer.querySelector("form");
    expect(form).toHaveAttribute("action", "/operations/documents/create");
    expect(form).toHaveAttribute("method", "post");
    expect(form?.querySelector('input[name="context"]')).toHaveValue("sheet");
    expect(form?.querySelector('input[name="csrfmiddlewaretoken"]')).toHaveValue(
      "token",
    );
    expect(routerPost).not.toHaveBeenCalled();
  });

  it("offers no create drawer without the authoring grant", () => {
    setPage({
      capabilities: { canAuthor: false, canPublish: true, canRetire: true },
    });
    render(<DocumentsAdministration />);

    expect(
      screen.queryByRole("button", { name: /New document/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<DocumentsAdministration />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
