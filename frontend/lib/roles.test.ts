import { describe, expect, it } from "vitest";

import {
  getRoleCatalogEntry,
  protectedRoleBlockReason,
  ROLE_CATALOG,
  roleLabel,
} from "@/lib/roles";

describe("role catalog", () => {
  it("lists all fourteen brokerage roles with stable codes", () => {
    expect(ROLE_CATALOG).toHaveLength(14);
    expect(new Set(ROLE_CATALOG.map((entry) => entry.code)).size).toBe(14);
  });

  it("keeps labels independent of codes", () => {
    expect(roleLabel("realtor")).toBe("Realtor");
    expect(getRoleCatalogEntry("system_admin")?.protected).toBe(true);
    expect(protectedRoleBlockReason("system_admin")).toMatch(/protected/i);
    expect(protectedRoleBlockReason("realtor")).toBeNull();
  });
});
