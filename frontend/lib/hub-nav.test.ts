import { describe, expect, it } from "vitest";

import {
  HUB_NAV_GROUPS,
  type HubNavGroup,
  type HubNavItem,
  type ResolvedHubNavGroup,
  type ResolvedHubNavItem,
  resolveHubNav,
  unavailableDescription,
  unavailableLabel,
} from "@/lib/hub-nav";
import { routes } from "@/lib/routes";
import type { HubFeatures, PrimaryOffice, User } from "@/types";

function user(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: "agent@onest.realestate",
    name: "Avery Johnson",
    permissions: [],
    roles: ["Users"],
    roleLabel: "Agent",
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

/** Every hub section is unbuilt today; tests that need one live flip it here. */
function features(overrides: HubFeatures = {}): HubFeatures {
  const base: HubFeatures = {};
  for (const group of HUB_NAV_GROUPS) {
    for (const item of group.items) {
      if (item.feature) {
        base[item.feature] = false;
      }
    }
  }
  return { ...base, ...overrides };
}

function allItems(): HubNavItem[] {
  return HUB_NAV_GROUPS.flatMap((group) => group.items);
}

/**
 * A registry-shaped stand-in. The shipped registry needs no permission gates
 * yet — every approved agent destination is open to any signed-in user — so
 * the filtering and empty-group rules are exercised against this instead of
 * being asserted vacuously against the real one.
 */
const STAND_IN: HubNavGroup[] = [
  {
    label: "Open",
    items: [
      {
        key: "open",
        title: "Open item",
        href: routes.dashboard(),
        icon: HUB_NAV_GROUPS[0].items[0].icon,
        permission: { any: ["web.view_open"] },
      },
      {
        key: "no-guard",
        title: "Ungated item",
        href: routes.profile(),
        icon: HUB_NAV_GROUPS[0].items[1].icon,
      },
    ],
  },
  {
    label: "Restricted",
    items: [
      {
        key: "restricted",
        title: "Restricted item",
        href: routes.coming_soon("restricted"),
        icon: HUB_NAV_GROUPS[0].items[2].icon,
        permission: { all: ["web.view_restricted"] },
      },
    ],
  },
];

/** Locate a resolved item by key, failing the test if the resolver dropped it. */
function itemByKey(groups: ResolvedHubNavGroup[], key: string): ResolvedHubNavItem {
  const found = groups.flatMap((group) => group.items).find((it) => it.key === key);
  if (!found) {
    throw new Error(`expected the resolved nav to contain "${key}"`);
  }
  return found;
}

describe("HUB_NAV_GROUPS structure", () => {
  it("carries the approved groups in the approved order", () => {
    expect(HUB_NAV_GROUPS.map((group) => group.label)).toEqual([
      "General",
      "Tools",
      "My office",
      "Directory",
    ]);
  });

  it("carries the approved items in the approved order", () => {
    const byGroup = Object.fromEntries(
      HUB_NAV_GROUPS.map((group) => [
        group.label,
        group.items.map((item) => item.title),
      ]),
    );
    expect(byGroup).toEqual({
      General: [
        "Dashboard",
        "Agent profile",
        "My contract",
        "Agent transactions",
        "My reservations",
      ],
      Tools: [
        "Training & learning",
        "Documents & forms",
        "Marketing resources",
        "Policies & compliance",
      ],
      "My office": ["Office info", "Office resources", "Office inventory"],
      Directory: ["Agent directory"],
    });
  });

  it("gives every item a unique key and a unique destination", () => {
    const items = allItems();
    expect(new Set(items.map((item) => item.key)).size).toBe(items.length);
    expect(new Set(items.map((item) => item.href)).size).toBe(items.length);
  });

  it("maps every item to a generated route, never a string literal", () => {
    const known = new Set([
      routes.dashboard(),
      routes.profile(),
      ...Object.keys(features()).map((section) => routes.coming_soon(section)),
    ]);
    for (const item of allItems()) {
      expect(known).toContain(item.href);
    }
  });

  it("routes every unbuilt item through the coming_soon page, never a 404", () => {
    for (const item of allItems()) {
      if (item.feature) {
        expect(item.href).toBe(routes.coming_soon(item.feature));
      }
    }
  });

  it("marks exactly the office destinations as office-scoped", () => {
    const scoped = allItems()
      .filter((item) => item.requiresOffice)
      .map((item) => item.key);
    expect(scoped).toEqual(["office-info", "office-resources", "office-inventory"]);
  });

  it("keeps the live destinations free of a feature gate", () => {
    const live = allItems()
      .filter((item) => item.feature === undefined)
      .map((item) => item.key);
    expect(live).toEqual(["dashboard", "agent-profile"]);
  });
});

describe("resolveHubNav", () => {
  it("gives a Realtor the full approved structure in order", () => {
    const groups = resolveHubNav(user(), features(), office);
    expect(groups.map((group) => group.label)).toEqual([
      "General",
      "Tools",
      "My office",
      "Directory",
    ]);
    expect(groups.flatMap((group) => group.items).map((item) => item.title)).toEqual(
      allItems().map((item) => item.title),
    );
  });

  it("shows nothing to a signed-out visitor", () => {
    expect(resolveHubNav(null, features(), office)).toEqual([]);
  });

  it("returns each item once for a user holding manager and agent roles", () => {
    const groups = resolveHubNav(
      user({
        roles: ["Branch Managers", "Users"],
        permissions: ["user.view_user", "user.change_user"],
      }),
      features(),
      office,
    );
    const keys = groups.flatMap((group) => group.items).map((item) => item.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).toEqual(allItems().map((item) => item.key));
  });

  it("hides items the user lacks permission for", () => {
    const groups = resolveHubNav(
      user({ permissions: ["web.view_open"] }),
      {},
      office,
      STAND_IN,
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].items.map((item) => item.key)).toEqual(["open", "no-guard"]);
  });

  it("keeps an item once the user holds its permission", () => {
    const groups = resolveHubNav(
      user({ permissions: ["web.view_open", "web.view_restricted"] }),
      {},
      office,
      STAND_IN,
    );
    expect(groups.map((group) => group.label)).toEqual(["Open", "Restricted"]);
    expect(groups[1].items.map((item) => item.key)).toEqual(["restricted"]);
  });

  it("drops a group once every item in it is filtered out", () => {
    const groups = resolveHubNav(user(), {}, office, STAND_IN);
    expect(groups.map((group) => group.label)).toEqual(["Open"]);
    expect(groups.every((group) => group.items.length > 0)).toBe(true);
  });

  it("keeps the first occurrence when a key repeats across groups", () => {
    const groups = resolveHubNav(
      user({ permissions: ["web.view_open", "web.view_restricted"] }),
      {},
      office,
      [
        ...STAND_IN,
        { label: "Duplicate", items: [{ ...STAND_IN[0].items[0], title: "Copy" }] },
      ],
    );
    expect(groups.map((group) => group.label)).toEqual(["Open", "Restricted"]);
    expect(groups[0].items[0].title).toBe("Open item");
  });
});

describe("feature and office availability", () => {
  it("marks an unbuilt module unavailable", () => {
    const contract = itemByKey(
      resolveHubNav(user(), features(), office),
      "my-contract",
    );
    expect(contract.unavailable).toBe("feature");
    expect(unavailableLabel(contract.unavailable)).toBe("Soon");
  });

  it("clears the marker once the backend enables the module", () => {
    const contract = itemByKey(
      resolveHubNav(user(), features({ "my-contract": true }), office),
      "my-contract",
    );
    expect(contract.unavailable).toBeNull();
    expect(unavailableLabel(contract.unavailable)).toBeNull();
  });

  it("treats a missing feature entry as unbuilt rather than as live", () => {
    const groups = resolveHubNav(user(), {}, office);
    const gated = groups
      .flatMap((group) => group.items)
      .filter((item) => item.feature !== undefined);
    expect(gated.every((item) => item.unavailable === "feature")).toBe(true);
  });

  it("keeps Dashboard and Agent profile usable regardless of feature state", () => {
    const groups = resolveHubNav(user(), {}, null);
    const general = groups[0].items;
    expect(general[0]).toMatchObject({ key: "dashboard", unavailable: null });
    expect(general[1]).toMatchObject({ key: "agent-profile", unavailable: null });
  });

  it("explains office destinations when the user has no primary office", () => {
    const groups = resolveHubNav(
      user(),
      features({
        "office-info": true,
        "office-resources": true,
        "office-inventory": true,
      }),
      null,
    );
    const myOffice = groups.find((group) => group.label === "My office");
    expect(myOffice?.items.map((item) => item.unavailable)).toEqual([
      "no-office",
      "no-office",
      "no-office",
    ]);
    expect(unavailableLabel("no-office")).toBe("No office");
  });

  it("reports the module gate ahead of the office gate", () => {
    const groups = resolveHubNav(user(), features(), null);
    const myOffice = groups.find((group) => group.label === "My office");
    expect(myOffice?.items.every((item) => item.unavailable === "feature")).toBe(true);
  });

  it("keeps the office group visible so navigation does not shift", () => {
    const groups = resolveHubNav(user(), features(), null);
    expect(groups.map((group) => group.label)).toEqual([
      "General",
      "Tools",
      "My office",
      "Directory",
    ]);
  });

  it("describes each unavailable state in a full sentence", () => {
    const groups = resolveHubNav(user(), features(), null);
    expect(unavailableDescription(itemByKey(groups, "my-contract"))).toBe(
      "My contract is not available yet",
    );

    const officeGroups = resolveHubNav(user(), features({ "office-info": true }), null);
    expect(unavailableDescription(itemByKey(officeGroups, "office-info"))).toBe(
      "Office info needs an office on your profile",
    );

    const dashboard = groups[0].items[0];
    expect(unavailableDescription(dashboard)).toBeNull();
  });
});
