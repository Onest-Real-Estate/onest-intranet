import { useCallback, useEffect, useState } from "react";

import {
  applyTheme,
  nextThemePreference,
  readThemePreference,
  resolveTheme,
  storeThemePreference,
  type ThemePreference,
  watchSystemTheme,
} from "@/lib/theme";

/**
 * The reader's theme choice, kept in sync with the document and the OS.
 *
 * The class is already on the document before React mounts (see the inline
 * script in `templates/layout.html`); this hook owns it from then on.
 */
export function useTheme(): {
  preference: ThemePreference;
  cycle: () => void;
} {
  const [preference, setPreference] = useState<ThemePreference>("system");

  // Read storage after mount rather than during render: the server has no
  // localStorage, and the pre-paint script has already applied the result.
  useEffect(() => {
    setPreference(readThemePreference());
  }, []);

  // Only a reader on `system` follows the OS while the tab is open. An explicit
  // choice is a choice, not a starting point.
  useEffect(() => {
    if (preference !== "system") {
      return;
    }
    return watchSystemTheme(applyTheme);
  }, [preference]);

  const cycle = useCallback(() => {
    setPreference((current) => {
      const next = nextThemePreference(current);
      storeThemePreference(next);
      applyTheme(resolveTheme(next));
      return next;
    });
  }, []);

  return { preference, cycle };
}
