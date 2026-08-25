/**
 * Theme resolution for the hub.
 *
 * The dark token set in `app.css` is switched by a single `dark` class on the
 * document element. Nothing else in the app writes that class, so this module
 * is the only path to the dark theme — keep it that way rather than toggling
 * the class from a component.
 *
 * The default is the reader's operating system, because the use scene is
 * people at a desk for a full day whose OS already knows whether they are in a
 * bright room. An explicit choice overrides it and is remembered.
 */

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "onest-theme";

const PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];

export function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && PREFERENCES.includes(value as ThemePreference);
}

/** The stored choice, or `system` when nothing was chosen or storage is unavailable. */
export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

/** What `system` currently means. Defaults to light where the query is unsupported. */
export function systemTheme(): ResolvedTheme {
  return typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? systemTheme() : preference;
}

/**
 * Put the resolved theme on the document. `color-scheme` goes with it so form
 * controls, scrollbars, and the caret — surfaces the design system does not
 * draw — follow the theme instead of staying light on a dark page.
 */
export function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

export function storeThemePreference(preference: ThemePreference): void {
  try {
    if (preference === "system") {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    }
  } catch {
    // A reader with storage disabled still gets the theme for this page view.
  }
}

/** The next step in the System → Light → Dark cycle. */
export function nextThemePreference(current: ThemePreference): ThemePreference {
  return (
    PREFERENCES[(PREFERENCES.indexOf(current) + 1) % PREFERENCES.length] ?? "system"
  );
}

/**
 * Watch the OS preference so a reader on `system` follows it while the tab is
 * open. Returns a cleanup function; a no-op where `matchMedia` is unavailable.
 */
export function watchSystemTheme(onChange: (theme: ResolvedTheme) => void): () => void {
  if (typeof window.matchMedia !== "function") {
    return () => {};
  }
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = (event: MediaQueryListEvent) => {
    onChange(event.matches ? "dark" : "light");
  };
  query.addEventListener("change", handler);
  return () => query.removeEventListener("change", handler);
}
