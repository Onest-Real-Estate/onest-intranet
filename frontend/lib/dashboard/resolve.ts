/**
 * Deterministic dashboard profile resolution.
 *
 * The same reader, the same effective access, and the same remembered choice
 * always produce the same profile and the same ordered widget list. Nothing
 * here reads a clock, a random value, or an unordered collection.
 *
 * **Resolution never grants anything.** It picks a layout. Widgets the reader
 * has no permission for are dropped from that layout regardless of which
 * profile selected them, so switching profiles can only ever narrow what is on
 * screen — and even then, the server remains the authority for every figure.
 */

import {
  DASHBOARD_PROFILES,
  type DashboardProfile,
  type DashboardProfileId,
  fallbackProfile,
  getDashboardProfile,
  profileForRoleCode,
} from "@/lib/dashboard/profiles";
import {
  type DashboardWidgetDefinition,
  type DashboardWidgetId,
  getDashboardWidget,
} from "@/lib/dashboard/widget-registry";
import { hasPermission } from "@/lib/permissions";
import type { DashboardAssignment, MetricScopeLevel, User } from "@/types";

/** Bump when the remembered-selection contract changes. */
export const DASHBOARD_PROFILE_VERSION = 1;
export const DASHBOARD_PROFILE_STORAGE_KEY = `onest-dashboard-profile:v${DASHBOARD_PROFILE_VERSION}`;

/**
 * Which rule produced the active profile. Surfaced in the switcher so a reader
 * can tell a remembered choice from an administrator's assignment, and carried
 * into the audit trail once assignment lands server-side.
 */
export type DashboardProfileSource =
  | "reader-selection"
  | "user-assignment"
  | "primary-role"
  | "effective-role"
  | "scope-assignment"
  | "fallback";

export interface ResolvedDashboardWidget {
  definition: DashboardWidgetDefinition;
  /**
   * True when the profile lists the widget but the reader's permissions do not
   * cover it, and the registry asked for the gap to be shown rather than
   * hidden. Widgets denied with `omit` never reach this list at all.
   */
  withheld: boolean;
}

export interface ResolvedDashboard {
  profile: DashboardProfile;
  source: DashboardProfileSource;
  /** Profiles the reader may switch to, most senior first. */
  available: DashboardProfile[];
  /** The profile resolution would pick with no remembered choice. */
  assigned: DashboardProfile;
}

/**
 * Profiles this reader is authorized to look at.
 *
 * Authorization to *view* a profile follows from holding one of its roles.
 * That is a presentation entitlement only — see the module note.
 */
export function authorizedProfiles(user: User | null): DashboardProfile[] {
  const fallback = fallbackProfile();
  if (!user) {
    return [];
  }
  const seen = new Set<DashboardProfileId>();
  const profiles: DashboardProfile[] = [];
  for (const code of user.roles) {
    const profile = profileForRoleCode(code);
    if (profile && !seen.has(profile.id)) {
      seen.add(profile.id);
      profiles.push(profile);
    }
  }
  // A superuser may inspect every presentation; it changes no permission and
  // no query, and it is how an admin reproduces what a role sees.
  if (user.isSuperuser) {
    for (const profile of DASHBOARD_PROFILES) {
      if (!seen.has(profile.id)) {
        seen.add(profile.id);
        profiles.push(profile);
      }
    }
  }
  // The fallback sorts last by construction, so a superuser sees it after every
  // role presentation rather than among them.
  profiles.sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id));
  if (profiles.length === 0) {
    // Nothing catalogued applies. The fallback is not an alternative here — it
    // is the only dashboard, so offering it as a choice would be a control
    // with one option.
    profiles.push(fallback);
  }
  return profiles;
}

function pick(
  candidates: DashboardProfile[],
  id: string | null | undefined,
): DashboardProfile | undefined {
  if (!id) {
    return undefined;
  }
  const profile = getDashboardProfile(id);
  if (!profile) {
    return undefined;
  }
  // A server-side assignment still has to name a profile the reader holds.
  // A stale or over-broad assignment falls through to the next rule rather
  // than handing out a presentation the reader's roles do not cover.
  return candidates.find((candidate) => candidate.id === profile.id);
}

/**
 * Apply the documented precedence.
 *
 * 1. Explicit, currently-valid user assignment.
 * 2. The reader's designated primary role.
 * 3. The highest-priority effective role — `user.roles` arrives ranked, and
 *    `authorizedProfiles` re-sorts by catalog priority, so ties are broken the
 *    same way on every request.
 * 4. An office- or region-targeted assignment.
 * 5. The authenticated fallback.
 *
 * A remembered reader selection sits above all of it, but only while it still
 * names an authorized profile.
 */
export function resolveDashboard(
  user: User | null,
  assignment?: DashboardAssignment,
  remembered?: string | null,
): ResolvedDashboard {
  const available = authorizedProfiles(user);
  const fallback = fallbackProfile();

  if (available.length === 0) {
    return { profile: fallback, source: "fallback", available: [], assigned: fallback };
  }

  const byUser = pick(available, assignment?.assignedProfileId);
  const byPrimaryRole = assignment?.primaryRoleCode
    ? pick(available, profileForRoleCode(assignment.primaryRoleCode)?.id)
    : undefined;
  const byEffectiveRole = available.find((profile) => profile.id !== fallback.id);
  const byScope = pick(available, assignment?.scopeProfileId);

  let assigned: DashboardProfile = fallback;
  let source: DashboardProfileSource = "fallback";
  if (byUser) {
    assigned = byUser;
    source = "user-assignment";
  } else if (byPrimaryRole) {
    assigned = byPrimaryRole;
    source = "primary-role";
  } else if (byEffectiveRole) {
    assigned = byEffectiveRole;
    source = "effective-role";
  } else if (byScope) {
    assigned = byScope;
    source = "scope-assignment";
  }

  const readerChoice = pick(available, remembered);
  if (readerChoice && readerChoice.id !== assigned.id) {
    return { profile: readerChoice, source: "reader-selection", available, assigned };
  }
  return { profile: assigned, source, available, assigned };
}

/**
 * The widgets a profile actually renders for this reader.
 *
 * Deduplicated by id, so a profile that lists a widget twice — or a future
 * merge of two profiles — cannot put the same aggregate on the page twice.
 * Order is the profile's, which is the reviewed reading order.
 */
export function resolveWidgets(
  profile: DashboardProfile,
  user: User | null,
  /**
   * The breadth the server says this reader's team figures cover. Null means
   * the server has not said yet — the client does not guess a scope, so no
   * scope filtering is applied and the profile's reviewed list stands.
   */
  scopeLevel: MetricScopeLevel | null = null,
): ResolvedDashboardWidget[] {
  const seen = new Set<DashboardWidgetId>();
  const widgets: ResolvedDashboardWidget[] = [];
  for (const id of profile.widgets) {
    if (seen.has(id)) {
      continue;
    }
    seen.add(id);
    const definition = getDashboardWidget(id);
    // A profile naming an unregistered id renders nothing — the allowlist is
    // the whole point of storing ids rather than component names.
    if (!definition) {
      continue;
    }
    if (scopeLevel !== null && !definition.scopes.includes(scopeLevel)) {
      continue;
    }
    if (hasPermission(user, definition.permissions)) {
      widgets.push({ definition, withheld: false });
      continue;
    }
    if (definition.deniedBehavior === "withhold") {
      widgets.push({ definition, withheld: true });
    }
  }
  return widgets;
}

/** Read the remembered selection. Never trusted — always revalidated. */
export function readRememberedProfile(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(DASHBOARD_PROFILE_STORAGE_KEY);
  } catch {
    // Private browsing and blocked storage are not errors worth surfacing;
    // the reader simply gets their assigned profile.
    return null;
  }
}

/**
 * Remember a selection, or clear it when the reader returns to their assigned
 * profile — storing "the default" would silently pin a dashboard that an
 * administrator later reassigns.
 */
export function rememberProfile(id: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (id === null) {
      window.localStorage.removeItem(DASHBOARD_PROFILE_STORAGE_KEY);
    } else {
      window.localStorage.setItem(DASHBOARD_PROFILE_STORAGE_KEY, id);
    }
  } catch {
    // Same as above: a dashboard that renders beats a remembered preference.
  }
}
