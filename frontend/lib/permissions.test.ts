import { describe, expect, it } from "vitest";

import { hasPermission } from "@/lib/permissions";
import type { User } from "@/types";

function user(permissions: string[]): User {
  return {
    id: 1,
    email: "alice@example.com",
    name: "Alice",
    permissions,
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
