import { describe, expect, it } from "vitest";

import {
  HUB_ADMIN_NAV,
  HUB_FEATURE_KEYS,
  HUB_NAV_GROUPS,
  HUB_NAV_REGISTRY,
  HUB_NAV_SECTIONS,
  HUB_NAV_VERSION,
  type HubNavItem,
  isHubNavItemActive,
  parseHubNavExpansion,
  resolveHubNav,
  resolveHubNavSections,
  validateHubNavRegistry,
} from "@/lib/hub-nav";
import { routes } from "@/lib/routes";
import type { HubFeatures, PrimaryOffice, User } from "@/types";

function user(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: "agent@onest.realestate",
    name: "Avery Johnson",
    headshotUrl: null,
    permissions: [],
    roles: ["realtor"],
    roleLabel: "Realtor",
    isStaff: false,
    isSuperuser: false,
    ...overrides,
  };
}

const office: PrimaryOffice = {
  id: 7,
  name: "Cedar Ridge branch",
  regionName: "Midwest",
};

function features(enabled: string[] = HUB_FEATURE_KEYS): HubFeatures {
  return Object.fromEntries(enabled.map((key) => [key, true]));
}

function labels(permissions: string[], enabled = HUB_FEATURE_KEYS): string[] {
  return resolveHubNav(user({ permissions }), features(enabled), office).flatMap(
    (group) => group.items.map((item) => item.label),
  );
}

function adminPermissions(): string[] {
  return HUB_ADMIN_NAV.flatMap((item) => [
    ...(item.permissions.all ?? []),
    ...(item.permissions.any ?? []),
  ]);
}

function registryItem(key: string): HubNavItem {
  const item = HUB_NAV_REGISTRY.find((candidate) => candidate.key === key);
  if (!item) {
    throw new Error(`missing registry item: ${key}`);
  }
  return item;
}

describe("navigation registry contract", () => {
  it("is versioned and validates without errors", () => {
    expect(HUB_NAV_VERSION).toBe(1);
    expect(validateHubNavRegistry()).toEqual([]);
  });

  it("declares stable group and item ordering", () => {
    expect(
      HUB_NAV_GROUPS.map(({ key, label, order }) => ({ key, label, order })),
    ).toEqual([
      { key: "general", label: "General", order: 10 },
      { key: "tools", label: "Tools", order: 20 },
      { key: "my-office", label: "My office", order: 30 },
      { key: "directory", label: "Directory", order: 40 },
      { key: "administration", label: "Administration", order: 50 },
    ]);
    for (const item of HUB_NAV_REGISTRY) {
      expect(item.label).not.toBe("");
      expect(item.route.name).not.toBe("");
      expect(item.route.href).toMatch(/^\/[\w/-]+$/);
      expect(item.order).toBeGreaterThan(0);
      expect(item.activeMatch.prefixes.length).toBeGreaterThan(0);
    }
  });

  it("declares permissions for every permission-protected destination", () => {
    const protectedItems = HUB_NAV_REGISTRY.filter(
      (item) => item.access === "permission-protected",
    );
    expect(protectedItems).toHaveLength(23);
    for (const item of protectedItems) {
      expect([
        ...(item.permissions.all ?? []),
        ...(item.permissions.any ?? []),
      ]).not.toHaveLength(0);
    }
  });

  it("matches the reviewed protected route and permission contract", () => {
    expect(
      Object.fromEntries(
        HUB_ADMIN_NAV.map((item) => [item.route.name, item.permissions.all?.[0]]),
      ),
    ).toEqual({
      admin_users: "web.view_users",
      admin_new_agents: "web.view_new_agents",
      admin_add_user: "web.add_users",
      admin_assign_roles: "web.assign_user_roles",
      admin_agent_contracts: "web.view_agent_contracts",
      admin_contract_templates: "contract.manage_contract_templates",
      admin_transactions: "web.view_transactions",
      admin_inventory: "web.view_inventory",
      admin_reservations: "web.view_reservations",
      admin_announcements: "web.manage_announcements",
      admin_training: "web.manage_training",
      admin_marketing_resources: "web.manage_marketing_resources",
      admin_documents: "web.manage_documents",
      admin_compliance: "web.view_compliance",
      admin_feedback: "web.view_feedback",
      admin_platform_tasks: "web.view_platform_tasks",
      admin_offices: "web.manage_offices",
      admin_it_support: "web.view_it_support",
      admin_office_resources: "web.view_office_resources_admin",
      onboarding_tool_catalog: "web.manage_onboarding_tools",
      report_catalog: "web.view_reports",
      space_administration: "reservations.view_spaces",
    });
  });

  it("rejects a role list that doubles as authorization or names an unknown role", () => {
    const contract = registryItem("my-contract");
    const users = registryItem("admin-users");

    expect(validateHubNavRegistry([{ ...contract, roles: ["not_a_role"] }])).toContain(
      "unknown role for my-contract: not_a_role",
    );
    expect(validateHubNavRegistry([{ ...contract, roles: [] }])).toContain(
      "item declares an empty role list: my-contract",
    );
    // Where a permission already decides relevance, a role filter on top can
    // only hide something somebody was deliberately granted.
    expect(validateHubNavRegistry([{ ...users, roles: ["system_admin"] }])).toContain(
      "permission-protected item declares roles: admin-users",
    );
  });

  it("declares role relevance only on destinations that ask for no permission", () => {
    for (const item of HUB_NAV_REGISTRY) {
      if (item.roles) {
        expect(item.permissions, `${item.key} mixes roles with permissions`).toEqual(
          {},
        );
      }
    }
  });

  it("detects malformed entries and duplicate destinations", () => {
    const dashboard = registryItem("dashboard");
    const invalid = {
      ...dashboard,
      key: "dashboard-copy",
      access: "permission-protected" as const,
      permissions: {},
      order: -1,
      activeMatch: { prefixes: [] },
    };
    expect(validateHubNavRegistry([dashboard, invalid])).toEqual(
      expect.arrayContaining([
        "duplicate destination: /dashboard",
        "invalid order for dashboard-copy: -1",
        "protected item lacks permissions: dashboard-copy",
        "item lacks active match prefixes: dashboard-copy",
      ]),
    );
  });

  it("keeps the reviewed nested administrative structure", () => {
    const resolved = resolveHubNav(
      user({ permissions: adminPermissions() }),
      features(),
      office,
    );
    const administration = resolved.find((group) => group.key === "administration");
    expect(administration).toBeDefined();
    if (!administration) {
      return;
    }
    expect(
      resolveHubNavSections(administration).map((section) => section.label),
    ).toEqual(["People", "Reporting", "Operations", "Content", "Governance & support"]);
  });
});

describe("resolveHubNav", () => {
  it("filters any/all permission requirements without reading role names", () => {
    const dashboard = registryItem("dashboard");
    const standIn: HubNavItem[] = [
      {
        ...dashboard,
        key: "all-item",
        label: "All item",
        route: { ...dashboard.route, href: "/all-item" },
        permissions: { all: ["web.alpha", "web.beta"] },
        order: 10,
        activeMatch: { prefixes: ["/all-item"] },
      },
      {
        ...dashboard,
        key: "any-item",
        label: "Any item",
        route: { ...dashboard.route, href: "/any-item" },
        permissions: { any: ["web.gamma", "web.delta"] },
        order: 20,
        activeMatch: { prefixes: ["/any-item"] },
      },
    ];
    const visible = resolveHubNav(
      user({
        roles: ["Completely Unknown Role"],
        permissions: ["web.alpha", "web.beta", "web.delta"],
      }),
      {},
      office,
      standIn,
    );
    expect(visible[0].items.map((item) => item.key)).toEqual(["all-item", "any-item"]);
    expect(
      resolveHubNav(user({ permissions: ["web.alpha"] }), {}, office, standIn),
    ).toEqual([]);
  });

  it("fails closed for signed-out or incomplete permission context", () => {
    expect(resolveHubNav(null, features(), office)).toEqual([]);
    expect(
      resolveHubNav(
        { ...user(), permissions: undefined } as unknown as User,
        features(),
        office,
      ),
    ).toEqual([]);
  });

  it("hides missing feature keys and exposes an enabled module", () => {
    expect(labels([], [])).toEqual(["Dashboard", "Agent profile"]);
    expect(labels([], ["my-contract"])).toEqual([
      "Dashboard",
      "Agent profile",
      "My contract",
    ]);
  });

  it("labels the profile by role without changing its destination", () => {
    const profileOf = (overrides: Partial<User>) => {
      const item = resolveHubNav(user(overrides), features(), office)
        .flatMap((group) => group.items)
        .find((entry) => entry.key === "agent-profile");
      return { label: item?.label, href: item?.route.href };
    };

    expect(profileOf({ roles: ["realtor"] })).toEqual({
      label: "Agent profile",
      href: routes.profile(),
    });
    expect(profileOf({ roles: ["transaction_coordinator"] })).toEqual({
      label: "Your profile",
      href: routes.profile(),
    });
    expect(
      profileOf({ roles: ["transaction_coordinator"], isSuperuser: true }).label,
    ).toBe("Your profile");
    expect(
      profileOf({ roles: ["transaction_coordinator", "branch_manager"] }).label,
    ).toBe("Agent profile");
  });

  it("routes My contract to the live destination when the feature is on", () => {
    const contract = resolveHubNav(user(), features(["my-contract"]), office)
      .flatMap((group) => group.items)
      .find((item) => item.key === "my-contract");
    expect(contract).toMatchObject({
      label: "My contract",
      availability: "available",
      route: { name: "my_contract", href: routes.my_contract() },
    });
  });

  it("keeps an explicitly registered disabled module as a Soon destination", () => {
    const groups = resolveHubNav(user(), { "my-contract": false }, office);
    const contract = groups
      .flatMap((group) => group.items)
      .find((item) => item.key === "my-contract");
    expect(contract).toMatchObject({
      label: "My contract",
      availability: "coming-soon",
    });
  });

  it("hides agent-only destinations from roles that have no book of business", () => {
    const accountant = resolveHubNav(
      user({ roles: ["accountant"], permissions: [] }),
      features(),
      office,
    ).flatMap((group) => group.items.map((item) => item.key));

    expect(accountant).not.toContain("my-contract");
    expect(accountant).not.toContain("agent-transactions");
    expect(accountant).not.toContain("marketing-resources");
    // Everything a non-producing colleague still needs stays put.
    expect(accountant).toContain("my-reservations");
    expect(accountant).toContain("policies-compliance");
    expect(accountant).toContain("documents-forms");
    expect(accountant).toContain("agent-directory");
  });

  it("keeps them for a manager who also carries listings", () => {
    const keys = resolveHubNav(
      user({ roles: ["branch_manager", "realtor"] }),
      features(),
      office,
    ).flatMap((group) => group.items.map((item) => item.key));

    expect(keys).toContain("my-contract");
    expect(keys).toContain("agent-transactions");
  });

  it("keeps marketing collateral for the team that produces it", () => {
    const keys = resolveHubNav(
      user({ roles: ["marketing_team"] }),
      features(),
      office,
    ).flatMap((group) => group.items.map((item) => item.key));

    expect(keys).toContain("marketing-resources");
    expect(keys).not.toContain("my-contract");
  });

  it("never filters a superuser by role relevance", () => {
    const keys = resolveHubNav(
      user({ roles: ["it_support"], isSuperuser: true }),
      features(),
      office,
    ).flatMap((group) => group.items.map((item) => item.key));

    expect(keys).toContain("my-contract");
  });

  it("treats role relevance as presentation, never as a grant", () => {
    // A role list can only ever remove an entry. It cannot add one the
    // reader's permissions do not already allow.
    const withRoles = resolveHubNav(
      user({ roles: ["realtor"], permissions: [] }),
      features(),
      office,
    ).flatMap((group) => group.items.map((item) => item.key));

    expect(withRoles).not.toContain("admin-users");
    expect(withRoles).not.toContain("admin-compliance");
  });

  it("hides an office module when the required context is absent", () => {
    const groups = resolveHubNav(user(), features(["office-info"]), null);
    expect(
      groups.flatMap((group) => group.items.map((item) => item.key)),
    ).not.toContain("office-info");
    expect(groups.some((group) => group.key === "my-office")).toBe(false);
  });

  it("deduplicates overlapping multi-role results by key and destination", () => {
    const dashboard = registryItem("dashboard");
    const duplicateKey = { ...dashboard, label: "Duplicate key", order: 20 };
    const duplicateDestination = {
      ...dashboard,
      key: "dashboard-alias",
      label: "Duplicate destination",
      order: 30,
    };
    const groups = resolveHubNav(
      user({
        roles: ["Branch Manager", "Realtor"],
        permissions: adminPermissions(),
      }),
      features(),
      office,
      [dashboard, duplicateKey, duplicateDestination, ...HUB_ADMIN_NAV],
    );
    const destinations = groups.flatMap((group) =>
      group.items.map((item) => item.route.href),
    );
    expect(destinations.filter((href) => href === routes.dashboard())).toHaveLength(1);
    expect(new Set(destinations).size).toBe(destinations.length);
  });

  it("sorts groups and items from explicit order rather than source position", () => {
    const groups = resolveHubNav(
      user(),
      {},
      office,
      [registryItem("agent-profile"), registryItem("dashboard")],
      [...HUB_NAV_GROUPS].reverse(),
    );
    expect(groups.map((group) => group.key)).toEqual(["general"]);
    expect(groups[0].items.map((item) => item.key)).toEqual([
      "dashboard",
      "agent-profile",
    ]);
  });

  it("drops empty groups and unauthorized confidential labels", () => {
    const groups = resolveHubNav(
      user({ permissions: ["web.view_users"] }),
      features(["admin-compliance"]),
      office,
    );
    expect(groups.some((group) => group.key === "administration")).toBe(false);
    expect(
      groups.flatMap((group) => group.items.map((item) => item.label)),
    ).not.toContain("Compliance");
  });
});

describe("representative effective-permission matrix", () => {
  const branch = [
    "web.view_users",
    "web.view_new_agents",
    "web.view_inventory",
    "web.view_reservations",
    "web.manage_training",
    "web.manage_documents",
    "web.view_feedback",
    "web.manage_offices",
  ];
  const regional = [...branch, "web.view_transactions"];

  it.each([
    ["Realtor", [], []],
    [
      "Branch",
      branch,
      [
        "Users",
        "New Agent List",
        "Inventory",
        "Reservations",
        "Training",
        "Documents",
        "Feedback",
        "Offices",
      ],
    ],
    [
      "Regional",
      regional,
      [
        "Users",
        "New Agent List",
        "Transactions",
        "Inventory",
        "Reservations",
        "Training",
        "Documents",
        "Feedback",
        "Offices",
      ],
    ],
    ["Brokerage", adminPermissions(), HUB_ADMIN_NAV.map((item) => item.label)],
  ])("shows the %s permission union", (_persona, permissions, expected) => {
    const administration = resolveHubNav(
      user({ permissions }),
      features(),
      office,
    ).find((group) => group.key === "administration");
    expect(administration?.items.map((item) => item.label) ?? []).toEqual(expected);
  });

  it.each([
    ["Realtor", [], 0],
    ["Branch", branch, branch.length],
    ["Regional", regional, regional.length],
    ["Brokerage", adminPermissions(), HUB_ADMIN_NAV.length],
  ])(
    "shows registered Soon tabs for the %s permission union",
    (_persona, permissions, adminCount) => {
      const explicitDisabled = Object.fromEntries(
        HUB_FEATURE_KEYS.map((key) => [key, false]),
      );
      const groups = resolveHubNav(user({ permissions }), explicitDisabled, office);
      const items = groups.flatMap((group) => group.items);
      expect(items.filter((item) => item.group === "administration")).toHaveLength(
        adminCount,
      );
      expect(
        items
          .filter((item) => item.feature !== undefined)
          .every((item) => item.availability === "coming-soon"),
      ).toBe(true);
    },
  );
});

describe("active matching", () => {
  it("matches index, detail, query, and trailing-slash routes", () => {
    const users = registryItem("admin-users");
    expect(isHubNavItemActive(users, "/operations/users")).toBe(true);
    expect(isHubNavItemActive(users, "/operations/users/42?tab=roles")).toBe(true);
    expect(isHubNavItemActive(users, "/operations/users/42/#roles")).toBe(true);
  });

  it("does not activate a prefix collision or an excluded sibling", () => {
    const users = registryItem("admin-users");
    expect(isHubNavItemActive(users, "/operations/users-archive")).toBe(false);
    expect(isHubNavItemActive(users, "/operations/users/new/confirm")).toBe(false);
    expect(
      isHubNavItemActive(
        registryItem("admin-add-user"),
        "/operations/users/new/confirm",
      ),
    ).toBe(true);
  });
});

describe("persisted expansion state", () => {
  it("uses reviewed defaults when state is missing or corrupt", () => {
    const defaults = HUB_NAV_SECTIONS.filter((section) => section.defaultExpanded).map(
      (section) => section.key,
    );
    expect([...parseHubNavExpansion(null)]).toEqual(defaults);
    expect([...parseHubNavExpansion("not-json")]).toEqual(defaults);
    expect([...parseHubNavExpansion('{"unexpected":true}')]).toEqual(defaults);
  });

  it("honors only known, non-sensitive section keys", () => {
    expect([...parseHubNavExpansion('["admin-people","secret-module",42]')]).toEqual(
      HUB_NAV_SECTIONS.map((section) => section.key),
    );
    expect([...parseHubNavExpansion('["admin-people","secret-module"]')]).toEqual([
      "admin-people",
    ]);
    expect([...parseHubNavExpansion("[]")]).toEqual([]);
  });
});
