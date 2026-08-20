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
 *
 * Frontend checks are presentation guidance only. The backend remains
 * authoritative; never trust a forged or stale client payload.
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

/**
 * Compare opaque `shell.authorizationVersion` values from successive Inertia
 * responses. A mismatch means roles, permissions, or scope changed — refresh
 * navigation and avoid acting on stale deferred props.
 */
export function isAuthorizationStale(
  clientVersion: string | null | undefined,
  serverVersion: string | null | undefined,
): boolean {
  if (!clientVersion || !serverVersion) {
    return false;
  }
  return clientVersion !== serverVersion;
}

/**
 * True when the session still looks authenticated but effective permissions
 * no longer satisfy a check (revoked mid-session after a shell refresh).
 */
export function isAccessRevoked(user: User | null, required: PermissionCheck): boolean {
  if (!user) {
    return true;
  }
  return !hasPermission(user, required);
}
