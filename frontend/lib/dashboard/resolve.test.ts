import { beforeEach, describe, expect, it } from "vitest";

import {
  DASHBOARD_PROFILES,
  type DashboardProfileId,
  fallbackProfile,
  getDashboardProfile,
  profileForRoleCode,
} from "@/lib/dashboard/profiles";
import {
  authorizedProfiles,
  DASHBOARD_PROFILE_STORAGE_KEY,
  readRememberedProfile,
  rememberProfile,
  resolveDashboard,
  resolveWidgets,
} from "@/lib/dashboard/resolve";
import { DASHBOARD_WIDGETS, getDashboardWidget } from "@/lib/dashboard/widget-registry";
import { ROLE_CATALOG } from "@/lib/roles";
import type { User } from "@/types";

function reader(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: "reader@onest.realestate",
    name: "Reader",
    headshotUrl: null,
    permissions: [],
    roles: [],
    roleLabel: "Realtor",
    isStaff: false,
    isSuperuser: false,
    ...overrides,
  };
}

/** The full permission set, so widget filtering never masks a layout bug. */
const ALL_PERMISSIONS = DASHBOARD_WIDGETS.flatMap((widget) => [
  ...(widget.permissions.all ?? []),
  ...(widget.permissions.any ?? []),
]);

describe("dashboard registry integrity", () => {
  it("gives every catalogued role a profile", () => {
    for (const role of ROLE_CATALOG) {
      expect(
        profileForRoleCode(role.code),
        `role ${role.code} has no dashboard profile`,
      ).toBeDefined();
    }
  });

  it("maps a role code to exactly one profile", () => {
    const owners = new Map<string, DashboardProfileId[]>();
    for (const profile of DASHBOARD_PROFILES) {
      for (const code of profile.roleCodes) {
        owners.set(code, [...(owners.get(code) ?? []), profile.id]);
      }
    }
    for (const [code, ids] of owners) {
      expect(ids, `role ${code} is claimed by ${ids.join(", ")}`).toHaveLength(1);
    }
  });

  it("only composes profiles from registered widget ids", () => {
    for (const profile of DASHBOARD_PROFILES) {
      for (const id of profile.widgets) {
        expect(getDashboardWidget(id), `${profile.id} lists ${id}`).toBeDefined();
      }
    }
  });

  it("gives every profile the reader's own day", () => {
    // My Day is personal: it shows the signed-in user's own obligations, not
    // the brokerage's. No role should hide somebody's deadlines from them —
    // and `systemAdmin` once did, so a colleague with no catalogued role saw
    // their day while an administrator did not.
    for (const profile of DASHBOARD_PROFILES) {
      expect(profile.widgets, `${profile.id} omits myDay`).toContain("myDay");
    }
  });

  it("never lists a widget twice in one profile", () => {
    for (const profile of DASHBOARD_PROFILES) {
      expect(new Set(profile.widgets).size).toBe(profile.widgets.length);
    }
  });

  it("keeps the top band's two widgets adjacent so the row closes", () => {
    // `announcements` and `quickAccess` share one twelve-column row. A widget
    // between them wraps the band into three rows. They sit behind the
    // metrics row, which leads every profile as its own full-width band.
    for (const profile of DASHBOARD_PROFILES) {
      expect(profile.widgets.slice(1, 3), `${profile.id} splits the top band`).toEqual([
        "announcements",
        "quickAccess",
      ]);
    }
  });

  it("leads every profile with the metrics row", () => {
    // The four-figure stat band is the first thing after the greeting, in
    // every role — before news, launchers, and every workflow panel.
    for (const profile of DASHBOARD_PROFILES) {
      expect(profile.widgets[0], `${profile.id} does not lead with figures`).toBe(
        "performance",
      );
    }
  });

  it("still registers brokerage news at the top of the wide band", () => {
    expect(getDashboardWidget("announcements")?.column).toBe("wide");
    expect(getDashboardWidget("performance")?.column).toBe("wide");
  });

  it("gives every profile something to show", () => {
    for (const profile of DASHBOARD_PROFILES) {
      expect(profile.widgets.length, `${profile.id} is empty`).toBeGreaterThan(0);
    }
  });

  it("keeps the fallback last so it never wins a priority comparison", () => {
    const fallback = fallbackProfile();
    for (const profile of DASHBOARD_PROFILES) {
      if (profile.id !== fallback.id) {
        expect(profile.priority).toBeLessThan(fallback.priority);
      }
    }
    expect(fallback.roleCodes).toHaveLength(0);
  });

  it("registers a distinct prop for every widget", () => {
    const props = DASHBOARD_WIDGETS.map((widget) => widget.prop);
    expect(new Set(props).size).toBe(props.length);
  });
});

describe("profile resolution per role", () => {
  const cases: { roles: string[]; expected: DashboardProfileId }[] = [
    { roles: ["realtor"], expected: "agent" },
    { roles: ["branch_admin"], expected: "branchAdmin" },
    { roles: ["branch_manager"], expected: "branchManager" },
    { roles: ["regional_manager"], expected: "regional" },
    { roles: ["regional_admin"], expected: "regional" },
    { roles: ["regional_transaction_coordinator"], expected: "transactionCoordinator" },
    { roles: ["transaction_coordinator"], expected: "transactionCoordinator" },
    { roles: ["principal_broker"], expected: "broker" },
    { roles: ["broker_admin"], expected: "broker" },
    { roles: ["compliance"], expected: "compliance" },
    { roles: ["marketing_team"], expected: "marketing" },
    { roles: ["accountant"], expected: "accounting" },
    { roles: ["it_support"], expected: "itSupport" },
    { roles: ["system_admin"], expected: "systemAdmin" },
  ];

  it.each(cases)("resolves $roles to $expected", ({ roles, expected }) => {
    const resolved = resolveDashboard(reader({ roles }));
    expect(resolved.profile.id).toBe(expected);
    expect(resolved.source).toBe("effective-role");
  });

  it("falls back to the authenticated profile for an uncatalogued role", () => {
    const resolved = resolveDashboard(reader({ roles: ["not_a_role"] }));
    expect(resolved.profile.id).toBe("authenticated");
    expect(resolved.source).toBe("fallback");
    expect(resolved.profile.widgets.length).toBeGreaterThan(0);
  });

  it("gives an unauthenticated visitor the fallback and no switcher", () => {
    const resolved = resolveDashboard(null);
    expect(resolved.profile.id).toBe("authenticated");
    expect(resolved.available).toHaveLength(0);
  });

  it("offers no alternative when the fallback is the only dashboard", () => {
    // A control with one option is not a control.
    expect(authorizedProfiles(reader({ roles: ["not_a_role"] }))).toHaveLength(1);
  });
});

describe("multi-role precedence", () => {
  const multi = reader({ roles: ["branch_manager", "realtor"] });

  it("takes the most senior effective role", () => {
    expect(resolveDashboard(multi).profile.id).toBe("branchManager");
  });

  it("is order-independent — the catalog priority decides, not the array", () => {
    const reversed = reader({ roles: ["realtor", "branch_manager"] });
    expect(resolveDashboard(reversed).profile.id).toBe(
      resolveDashboard(multi).profile.id,
    );
  });

  it("prefers an explicit user assignment over every role rule", () => {
    const resolved = resolveDashboard(multi, {
      assignedProfileId: "agent",
      primaryRoleCode: "branch_manager",
      scopeProfileId: null,
    });
    expect(resolved.profile.id).toBe("agent");
    expect(resolved.source).toBe("user-assignment");
  });

  it("prefers the designated primary role over the senior one", () => {
    const resolved = resolveDashboard(multi, {
      assignedProfileId: null,
      primaryRoleCode: "realtor",
      scopeProfileId: null,
    });
    expect(resolved.profile.id).toBe("agent");
    expect(resolved.source).toBe("primary-role");
  });

  it("uses an office assignment only when no role rule applies", () => {
    const resolved = resolveDashboard(reader({ roles: ["not_a_role"] }), {
      assignedProfileId: null,
      primaryRoleCode: null,
      scopeProfileId: "branchAdmin",
    });
    // The reader holds no role the office assignment could present, so the
    // assignment is ignored rather than granting a dashboard it has no basis for.
    expect(resolved.profile.id).toBe("authenticated");
  });

  it("offers every held profile, most senior first", () => {
    const available = authorizedProfiles(multi).map((profile) => profile.id);
    expect(available).toEqual(["branchManager", "agent"]);
  });

  it("resolves the same result for the same input every time", () => {
    const first = resolveDashboard(multi);
    const second = resolveDashboard(multi);
    expect(second.profile.id).toBe(first.profile.id);
    expect(second.available.map((p) => p.id)).toEqual(first.available.map((p) => p.id));
  });
});

describe("expired and revoked assignments", () => {
  it("ignores an assignment naming a profile the reader no longer holds", () => {
    // The server sends only currently-valid assignments, but a revoked role
    // and a cached assignment can still meet in one response.
    const resolved = resolveDashboard(reader({ roles: ["realtor"] }), {
      assignedProfileId: "systemAdmin",
      primaryRoleCode: null,
      scopeProfileId: null,
    });
    expect(resolved.profile.id).toBe("agent");
    expect(resolved.source).toBe("effective-role");
  });

  it("ignores an assignment naming a profile that does not exist", () => {
    const resolved = resolveDashboard(reader({ roles: ["realtor"] }), {
      assignedProfileId: "deletedProfile",
      primaryRoleCode: null,
      scopeProfileId: null,
    });
    expect(resolved.profile.id).toBe("agent");
  });

  it("drops a remembered selection once the role behind it is revoked", () => {
    const promoted = resolveDashboard(
      reader({ roles: ["branch_manager", "realtor"] }),
      undefined,
      "agent",
    );
    expect(promoted.profile.id).toBe("agent");
    expect(promoted.source).toBe("reader-selection");

    const demoted = resolveDashboard(
      reader({ roles: ["realtor"] }),
      undefined,
      "branchManager",
    );
    expect(demoted.profile.id).toBe("agent");
    expect(demoted.source).toBe("effective-role");
  });

  it("reports the assigned profile alongside a reader's override", () => {
    const resolved = resolveDashboard(
      reader({ roles: ["branch_manager", "realtor"] }),
      undefined,
      "agent",
    );
    expect(resolved.assigned.id).toBe("branchManager");
  });
});

describe("superuser inspection", () => {
  const superuser = reader({
    roles: ["system_admin"],
    isSuperuser: true,
    permissions: ALL_PERMISSIONS,
  });

  it("may look at every presentation", () => {
    const available = authorizedProfiles(superuser).map((profile) => profile.id);
    for (const profile of DASHBOARD_PROFILES) {
      expect(available).toContain(profile.id);
    }
  });

  it("still lands on the system admin dashboard by default", () => {
    expect(resolveDashboard(superuser).profile.id).toBe("systemAdmin");
  });
});

describe("widget resolution", () => {
  const admin = reader({ roles: ["system_admin"], permissions: ALL_PERMISSIONS });

  it("never renders the same widget twice", () => {
    for (const profile of DASHBOARD_PROFILES) {
      const ids = resolveWidgets(profile, admin).map((w) => w.definition.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it("keeps the profile's reviewed reading order", () => {
    const profile = getDashboardProfile("branchManager");
    if (!profile) {
      throw new Error("branchManager profile is missing");
    }
    const ids = resolveWidgets(profile, admin).map((w) => w.definition.id);
    expect(ids).toEqual([...profile.widgets]);
  });

  it("drops widgets the reader has no permission for", () => {
    const profile = getDashboardProfile("branchManager");
    if (!profile) {
      throw new Error("branchManager profile is missing");
    }
    const ids = resolveWidgets(profile, reader({ roles: ["branch_manager"] })).map(
      (w) => w.definition.id,
    );
    expect(ids).not.toContain("agentOnboarding");
    expect(ids).not.toContain("teamTasks");
  });

  it("switching profiles cannot show a widget the reader may not see", () => {
    // A realtor inspecting the system admin presentation — the only widgets
    // that survive are the ones their own permissions already allowed.
    const realtor = reader({
      roles: ["realtor"],
      permissions: ["web.view_own_transactions", "web.view_own_tasks"],
    });
    const adminProfile = getDashboardProfile("systemAdmin");
    if (!adminProfile) {
      throw new Error("systemAdmin profile is missing");
    }
    for (const widget of resolveWidgets(adminProfile, realtor)) {
      const required = [
        ...(widget.definition.permissions.all ?? []),
        ...(widget.definition.permissions.any ?? []),
      ];
      if (required.length > 0 && !widget.withheld) {
        expect(required.some((p) => realtor.permissions.includes(p))).toBe(true);
      }
    }
  });

  it("marks a restricted widget rather than hiding it when absence would mislead", () => {
    const profile = getDashboardProfile("compliance");
    if (!profile) {
      throw new Error("compliance profile is missing");
    }
    const withheld = resolveWidgets(profile, reader({ roles: ["compliance"] })).filter(
      (widget) => widget.withheld,
    );
    expect(withheld.map((w) => w.definition.id)).toContain("complianceExceptions");
  });

  it("omits team widgets when the server reports a self-only scope", () => {
    const profile = getDashboardProfile("branchManager");
    if (!profile) {
      throw new Error("branchManager profile is missing");
    }
    const ids = resolveWidgets(profile, admin, "self").map((w) => w.definition.id);
    expect(ids).not.toContain("closingPipeline");
    expect(ids).toContain("performance");
  });

  it("applies no scope filter until the server reports a scope", () => {
    const profile = getDashboardProfile("branchManager");
    if (!profile) {
      throw new Error("branchManager profile is missing");
    }
    expect(resolveWidgets(profile, admin, null).map((w) => w.definition.id)).toContain(
      "closingPipeline",
    );
  });
});

describe("remembered selection storage", () => {
  beforeEach(() => window.localStorage.clear());

  it("round-trips a selection", () => {
    rememberProfile("agent");
    expect(window.localStorage.getItem(DASHBOARD_PROFILE_STORAGE_KEY)).toBe("agent");
    expect(readRememberedProfile()).toBe("agent");
  });

  it("clears rather than pinning when the reader returns to their default", () => {
    rememberProfile("agent");
    rememberProfile(null);
    expect(readRememberedProfile()).toBeNull();
  });
});
