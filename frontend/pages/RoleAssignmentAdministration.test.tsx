import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoleAssignmentAdministration from "@/pages/RoleAssignmentAdministration";
import RoleAssignmentWorkspace from "@/pages/RoleAssignmentWorkspace";

const visitMock = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ href, children }: { href: string; children?: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    get: (...args: unknown[]) => visitMock(...args),
    post: vi.fn(),
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

const baseUser = {
  id: 1,
  email: "admin@example.com",
  permissions: ["web.assign_user_roles"],
};

describe("RoleAssignmentAdministration", () => {
  beforeEach(() => {
    visitMock.mockReset();
    vi.mocked(usePage).mockReturnValue({
      props: {
        csrfToken: "token",
        user: baseUser,
        users: {
          items: [
            {
              id: 9,
              email: "agent@example.com",
              displayName: "Alex Agent",
              isActive: true,
              isSelf: false,
              office: { id: 1, name: "Cedar", pathLabel: "North / Cedar" },
              liveRoles: [
                {
                  role: "realtor",
                  roleLabel: "Realtor",
                  scopeLabel: "North / Cedar",
                  status: "active",
                },
              ],
              counts: { active: 1, scheduled: 0, expired: 0, revoked: 0 },
            },
          ],
          pagination: {
            page: 1,
            pageSize: 25,
            totalItems: 1,
            totalPages: 1,
            hasNext: false,
            hasPrevious: false,
          },
          filters: { q: "", role: "", status: "", office: "", region: "" },
          sort: null,
        },
        filterOptions: {
          roles: [{ value: "realtor", label: "Realtor" }],
          statuses: [{ value: "active", label: "Active" }],
          offices: [
            { id: 1, name: "Cedar", pathLabel: "North / Cedar", kind: "branch" },
          ],
        },
        scope: { level: "brokerage", label: "Brokerage-wide" },
      },
    } as never);
  });

  it("exposes the shared hub layout on the Inertia page export", () => {
    const [ResolvedLayout] =
      RoleAssignmentAdministration.layout() as unknown as readonly [
        (props: { children?: React.ReactNode }) => React.ReactNode,
      ];
    render(<ResolvedLayout>Page content</ResolvedLayout>);

    expect(screen.getByTestId("hub-layout")).toHaveTextContent("Page content");
  });

  it("lists people and links into the workspace", () => {
    render(<RoleAssignmentAdministration />);
    expect(screen.getByText("Alex Agent")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /manage/i })).toHaveAttribute(
      "href",
      "/operations/role-assignments/9",
    );
  });

  it("shows an empty state when nobody matches", () => {
    vi.mocked(usePage).mockReturnValue({
      props: {
        csrfToken: "token",
        user: baseUser,
        users: {
          items: [],
          pagination: {
            page: 1,
            pageSize: 25,
            totalItems: 0,
            totalPages: 1,
            hasNext: false,
            hasPrevious: false,
          },
          filters: { q: "zzz", role: "", status: "", office: "", region: "" },
          sort: null,
        },
        filterOptions: { roles: [], statuses: [], offices: [] },
        scope: { level: "brokerage", label: "Brokerage-wide" },
      },
    } as never);
    render(<RoleAssignmentAdministration />);
    expect(screen.getByText(/no people in scope/i)).toBeInTheDocument();
  });
});

describe("RoleAssignmentWorkspace", () => {
  beforeEach(() => {
    vi.mocked(usePage).mockReturnValue({
      props: {
        csrfToken: "token",
        user: baseUser,
        validation: { fields: {}, form: [] },
        preview: null,
        scope: { level: "brokerage", label: "Brokerage-wide" },
        workspace: {
          subject: {
            id: 9,
            email: "agent@example.com",
            displayName: "Alex Agent",
            isActive: true,
            isSelf: false,
            office: { id: 1, name: "Cedar", pathLabel: "North / Cedar" },
            agentStatus: "active",
          },
          assignments: [
            {
              id: 3,
              role: "realtor",
              roleLabel: "Realtor",
              roleDescription: "Licensed agent",
              scopeType: "office",
              scopeLabel: "North / Cedar",
              scopeOfficeId: 1,
              status: "active",
              startsAt: null,
              endsAt: null,
              assignedBy: "Admin",
              revokedBy: null,
              revokedAt: null,
              businessReason: "Seed",
              version: "2026-01-01T00:00:00",
              canEdit: true,
              canRevoke: true,
              access: {
                roleLabel: "Realtor",
                scopeLabel: "North / Cedar",
                permissions: ["web.view_own_leads"],
                orgReach: "North / Cedar",
              },
              isLastLive: true,
              isManagement: false,
            },
          ],
          effectiveAccess: {
            roles: ["Realtor"],
            roleKeys: ["realtor"],
            permissions: ["web.view_own_leads"],
            scopeLabel: "North / Cedar",
            companyWide: false,
            assignedRecord: false,
            liveAssignments: 1,
          },
          grantVersion: "2026-01-01T00:00:00",
          options: {
            roles: [
              {
                value: "realtor",
                label: "Realtor",
                description: "Licensed agent",
                available: true,
                unavailableReason: null,
                scopes: [
                  {
                    value: "office",
                    label: "Office",
                    available: true,
                    unavailableReason: null,
                  },
                  {
                    value: "assigned_record",
                    label: "Assigned records",
                    available: true,
                    unavailableReason: null,
                  },
                ],
              },
              {
                value: "system_admin",
                label: "System Admin",
                available: false,
                unavailableReason: "Protected system role.",
                scopes: [],
              },
            ],
            offices: [
              {
                id: 1,
                name: "Cedar",
                pathLabel: "North / Cedar",
                regionName: "North",
              },
            ],
          },
          editable: true,
          administrationHref: "/operations/users/9/administration",
        },
      },
    } as never);
  });

  it("exposes the shared hub layout on the Inertia page export", () => {
    const [ResolvedLayout] = RoleAssignmentWorkspace.layout() as unknown as readonly [
      (props: { children?: React.ReactNode }) => React.ReactNode,
    ];
    render(<ResolvedLayout>Page content</ResolvedLayout>);

    expect(screen.getByTestId("hub-layout")).toHaveTextContent("Page content");
  });

  it("renders assignments and explains unavailable roles", () => {
    render(<RoleAssignmentWorkspace />);
    expect(screen.getByText("Alex Agent")).toBeInTheDocument();
    expect(screen.getByText(/assigned records/i)).toBeInTheDocument();
    expect(screen.getByText(/system admin unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /revoke/i })).toBeInTheDocument();
  });

  it("opens the revoke dialog", async () => {
    const user = userEvent.setup();
    render(<RoleAssignmentWorkspace />);
    // Preview fetch is async; stub it so the dialog can open.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          preview: {
            before: {
              roles: ["Realtor"],
              roleKeys: ["realtor"],
              permissions: [],
              scopeLabel: "North / Cedar",
              companyWide: false,
              assignedRecord: false,
              liveAssignments: 1,
            },
            after: {
              roles: [],
              roleKeys: [],
              permissions: [],
              scopeLabel: "No administrative scope",
              companyWide: false,
              assignedRecord: false,
              liveAssignments: 0,
            },
            permissionDelta: { added: [], removed: [] },
            navigationDelta: { added: [], removed: [] },
            highImpact: [
              {
                label: "Last live role",
                from: "North / Cedar",
                to: "No live assignments",
                impact: "Would strip access.",
              },
            ],
            requiresConfirmation: true,
            warnings: ["Only live role"],
          },
        }),
      }),
    );
    await user.click(screen.getByRole("button", { name: /revoke/i }));
    expect(
      await screen.findByRole("heading", { name: /revoke realtor/i }),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
