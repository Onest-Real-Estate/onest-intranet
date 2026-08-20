import { useCallback, useState } from "react";

import { isAuthorizationStale } from "@/lib/permissions";

export interface AuthorizationStaleness {
  /** Effective access changed after the current payloads were computed. */
  stale: boolean;
  /** Adopt the current version as the new baseline, after a full reload. */
  acknowledge: () => void;
}

/**
 * Detect a mid-session change to roles, permissions, or scope.
 *
 * `shell.authorizationVersion` is opaque and changes whenever effective access
 * does. A page that keeps rendering figures computed under the old version is
 * showing something the reader may no longer be entitled to — or, just as
 * misleading, hiding something they now are. The page marks those figures
 * rather than discarding them mid-read, and offers a refresh.
 *
 * The baseline is only advanced explicitly, so a partial reload of one widget
 * cannot quietly clear a warning that still applies to the others.
 */
export function useAuthorizationStaleness(
  version: string | null | undefined,
): AuthorizationStaleness {
  const [baseline, setBaseline] = useState(version);
  const acknowledge = useCallback(() => setBaseline(version), [version]);
  return { stale: isAuthorizationStale(baseline, version), acknowledge };
}
