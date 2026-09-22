/** Common brokerage zones floated to the top of long IANA lists. */
const PREFERRED = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "UTC",
] as const;

const FALLBACK = [
  ...PREFERRED,
  "America/Anchorage",
  "America/Puerto_Rico",
  "Pacific/Honolulu",
  "Europe/London",
  "Asia/Kathmandu",
] as const;

function supportedZones(): string[] {
  try {
    const intl = Intl as typeof Intl & {
      supportedValuesOf?: (key: string) => string[];
    };
    if (typeof intl.supportedValuesOf === "function") {
      return intl.supportedValuesOf("timeZone");
    }
  } catch {
    // Older runtimes — fall through to the curated list.
  }
  return [...FALLBACK];
}

/**
 * IANA timezone ids for pickers. Preferred US/brokerage zones lead; the rest
 * follow alphabetically so search stays predictable. Always merges a small
 * curated fallback so stripped ICU builds (and older runtimes) still expose
 * common brokerage zones such as UTC and Asia/Kathmandu.
 */
export function listIanaTimezones(): string[] {
  const all = new Set([...supportedZones(), ...FALLBACK, "UTC"]);
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const zone of PREFERRED) {
    if (all.has(zone) && !seen.has(zone)) {
      seen.add(zone);
      ordered.push(zone);
    }
  }
  for (const zone of [...all].sort((a, b) => a.localeCompare(b))) {
    if (!seen.has(zone)) {
      seen.add(zone);
      ordered.push(zone);
    }
  }
  return ordered;
}

export function filterIanaTimezones(zones: string[], query: string): string[] {
  const needle = query.trim().toLowerCase().replaceAll("_", " ");
  if (!needle) return zones;
  return zones.filter((zone) => {
    const haystack = zone.toLowerCase().replaceAll("_", " ");
    return haystack.includes(needle) || haystack.replaceAll("/", " ").includes(needle);
  });
}
