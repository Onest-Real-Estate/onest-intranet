import { describe, expect, it } from "vitest";

import {
  hasPermission,
  isAccessRevoked,
  isAuthorizationStale,
} from "@/lib/permissions";
import type { User } from "@/types";

function user(permissions: string[]): User {
  return {
    id: 1,
    email: "alice@example.com",
    name: "Alice",
    headshotUrl: null,
    permissions,
    roles: [],
    roleLabel: "Realtor",
    isStaff: false,
    isSuperuser: false,
  };
}

describe("hasPermission", () => {
  it("allows when no requirements are given", () => {
    expect(hasPermission(user([]), {})).toBe(true);
  });

  it("denies unauthenticated users", () => {
    expect(hasPermission(null, { any: ["user.view_user"] })).toBe(false);
  });

  it("requires every permission listed in `all`", () => {
    const u = user(["user.view_user", "user.change_user"]);
    expect(hasPermission(u, { all: ["user.view_user", "user.change_user"] })).toBe(
      true,
    );
    expect(hasPermission(u, { all: ["user.view_user", "user.delete_user"] })).toBe(
      false,
    );
  });

  it("requires at least one permission listed in `any`", () => {
    const u = user(["user.view_user"]);
    expect(hasPermission(u, { any: ["user.delete_user", "user.view_user"] })).toBe(
      true,
    );
    expect(hasPermission(u, { any: ["user.delete_user", "user.change_user"] })).toBe(
      false,
    );
  });

  it("combines `any` and `all`", () => {
    const u = user(["user.view_user", "user.change_user"]);
    expect(
      hasPermission(u, { all: ["user.view_user"], any: ["user.change_user"] }),
    ).toBe(true);
    expect(
      hasPermission(u, { all: ["user.view_user"], any: ["user.delete_user"] }),
    ).toBe(false);
    expect(
      hasPermission(u, { all: ["user.delete_user"], any: ["user.view_user"] }),
    ).toBe(false);
  });

  it("ignores empty `any`/`all` lists", () => {
    expect(hasPermission(user([]), { any: [], all: [] })).toBe(true);
  });
});

describe("isAuthorizationStale", () => {
  it("detects version mismatches", () => {
    expect(isAuthorizationStale("a", "b")).toBe(true);
    expect(isAuthorizationStale("a", "a")).toBe(false);
    expect(isAuthorizationStale("", "a")).toBe(false);
  });
});

describe("isAccessRevoked", () => {
  it("flags missing permissions after refresh", () => {
    expect(isAccessRevoked(user([]), { all: ["web.view_users"] })).toBe(true);
    expect(isAccessRevoked(user(["web.view_users"]), { all: ["web.view_users"] })).toBe(
      false,
    );
  });
});
