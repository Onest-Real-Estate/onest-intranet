import type { User } from "@/types";

/**
 * Permission requirements, shared by the `PermissionRequired` component and
 * the server-side guards (see apps/web/permissions.py).
 *
 *   { all: [...] } — the user must have every listed permission
 *   { any: [...] } — the user must have at least one listed permission
 *   { any, all }   — both conditions must hold
 *   {}             — no requirements, always allowed
 *
 * Permissions are Django auth codenames (e.g. "user.view_user"), exposed to
 * the client as `user.permissions` by web.middleware.InertiaShareMiddleware.
 */
export interface PermissionCheck {
  all?: string[];
  any?: string[];
}

export function hasPermission(
  user: User | null,
  required: PermissionCheck = {},
): boolean {
  if (!user) {
    return false;
  }
  const permissions = new Set(user.permissions);
  if (
    required.all &&
    required.all.length > 0 &&
    !required.all.every((permission) => permissions.has(permission))
  ) {
    return false;
  }
  if (
    required.any &&
    required.any.length > 0 &&
    !required.any.some((permission) => permissions.has(permission))
  ) {
    return false;
  }
  return true;
}
