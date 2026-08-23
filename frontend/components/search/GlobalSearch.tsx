import { router } from "@inertiajs/react";
import {
  Building,
  Folder,
  type LucideIcon,
  Megaphone,
  Search as SearchIcon,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  CommandPalette,
  CommandPaletteFooter,
  CommandPaletteGroupLabel,
  CommandPaletteInput,
  CommandPaletteKey,
  CommandPaletteList,
  CommandPaletteOption,
  CommandPaletteTab,
  CommandPaletteTabs,
} from "@/components/design-system";
import { routes } from "@/lib/routes";
import type { SearchGroup, SearchHit, SearchResults } from "@/types";

const ICONS: Record<string, LucideIcon> = {
  users: Users,
  megaphone: Megaphone,
  folder: Folder,
  building: Building,
};

/** Debounce window. Long enough that a burst of typing is one request. */
const DEBOUNCE_MS = 220;

/**
 * Split plain text around every case-insensitive occurrence of the query.
 *
 * This is why the server sends text rather than markup: highlighting is a
 * render-time decision over a string React escapes, so a record whose body
 * contains `<script>` is highlighted like any other text and there is nothing
 * to sanitize on arrival.
 */
export function highlightParts(text: string, query: string): string[] {
  const needle = query.trim();
  if (!needle || !text) {
    return [text];
  }
  const parts: string[] = [];
  const lowered = text.toLowerCase();
  const target = needle.toLowerCase();
  let index = 0;
  while (index < text.length) {
    const found = lowered.indexOf(target, index);
    if (found === -1) {
      parts.push(text.slice(index));
      break;
    }
    if (found > index) {
      parts.push(text.slice(index, found));
    }
    parts.push(text.slice(found, found + target.length));
    index = found + target.length;
  }
  return parts.filter((part) => part !== "");
}

function Highlighted({ text, query }: { text: string; query: string }) {
  const parts = highlightParts(text, query);
  const target = query.trim().toLowerCase();
  return (
    <>
      {parts.map((part, index) => {
        const matched = Boolean(target) && part.toLowerCase() === target;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: parts are a pure function of one string, rebuilt wholesale and never reordered
          <Part key={index} part={part} matched={matched} />
        );
      })}
    </>
  );
}

/** One run of the split, marked or not. Split out so the key is set once. */
function Part({ part, matched }: { part: string; matched: boolean }) {
  if (matched) {
    return <mark className="bg-warning/40 text-foreground rounded-sm">{part}</mark>;
  }
  return <span>{part}</span>;
}

const EMPTY: SearchResults = {
  query: "",
  groups: [],
  total: 0,
  tooShort: false,
  minLength: 2,
  partial: false,
};

interface FlatEntry {
  hit: SearchHit;
  group: SearchGroup;
}

/**
 * Global search, as a command palette.
 *
 * Everything rendered here was authorized and scoped server-side before it was
 * serialized. A source the reader may not use is absent from the payload, not
 * an empty group in the markup, so this component never decides what anybody
 * may see — it only decides how it looks.
 *
 * Two behaviours worth naming:
 *
 * * **Stale answers are dropped.** Every keystroke aborts the request before
 *   it, so a slow response for "fai" can never overwrite a fast one for
 *   "fairfax".
 * * **Selection roves, focus does not.** The arrow keys move a highlight while
 *   the caret stays in the input, which is what lets somebody keep typing
 *   without first tabbing back — the behaviour Spotlight has trained everyone
 *   to expect. It is exposed with `aria-activedescendant`.
 */
export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<SearchResults>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [active, setActive] = useState(0);
  // Which source the results are narrowed to. Client-side over what the server
  // already returned — the filter never widens the set, so it cannot reach a
  // source this reader was not served.
  const [source, setSource] = useState("all");
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const visibleGroups = useMemo(
    () =>
      source === "all"
        ? results.groups
        : results.groups.filter((group) => group.key === source),
    [results, source],
  );
  const entries = useMemo<FlatEntry[]>(
    () => visibleGroups.flatMap((group) => group.hits.map((hit) => ({ hit, group }))),
    [visibleGroups],
  );
  // A response of only failed groups has no hits but is not "no results":
  // saying so would report an outage as an answer.
  const hasFailure = useMemo(
    () => visibleGroups.some((group) => group.failed),
    [visibleGroups],
  );
  const query = term.trim();
  const searchable = query.length >= results.minLength;

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!searchable) {
      abortRef.current?.abort();
      setResults((current) => ({
        ...EMPTY,
        minLength: current.minLength,
        tooShort: query.length > 0,
      }));
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    setLoading(true);
    const timer = setTimeout(() => {
      fetch(`${routes.search_suggestions()}?q=${encodeURIComponent(query)}`, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      })
        .then(async (response) => {
          if (response.status === 429) {
            setRateLimited(true);
            return null;
          }
          setRateLimited(false);
          return response.ok ? ((await response.json()) as SearchResults) : null;
        })
        .then((payload) => {
          if (payload) {
            setResults(payload);
            setActive(0);
            // A tab for a source the new query did not return would filter to
            // nothing and read as "no results" for a query that has some.
            setSource((current) =>
              payload.groups.some((group) => group.key === current) ? current : "all",
            );
          }
        })
        // Aborting is the expected case while typing, and a failed request
        // leaves the last good list in place rather than blanking it.
        .catch(() => undefined)
        .finally(() => setLoading(false));
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, searchable, open]);

  const openPalette = useCallback(() => {
    setTerm("");
    setResults(EMPTY);
    setRateLimited(false);
    setActive(0);
    setSource("all");
    setOpen(true);
  }, []);

  // Cmd-K / Ctrl-K — the shortcut people try before looking for a button.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        openPalette();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openPalette]);

  function go(href: string) {
    setOpen(false);
    router.visit(href);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (entries.length === 0) {
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + step + entries.length) % entries.length);
      return;
    }
    if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && tabs.length > 1) {
      event.preventDefault();
      const step = event.key === "ArrowRight" ? 1 : -1;
      const current = tabs.findIndex((tab) => tab.key === source);
      const next = tabs[(current + step + tabs.length) % tabs.length];
      setSource(next.key);
      setActive(0);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const chosen = entries[active];
      if (chosen) {
        go(chosen.hit.href);
      } else if (searchable) {
        // Nothing highlighted: Enter means "show me everything".
        setOpen(false);
        router.get(routes.search(), { q: query });
      }
    }
  }

  const tabs = useMemo(
    () => [
      { key: "all", label: "All", count: results.total },
      ...results.groups
        .filter((group) => group.hits.length > 0)
        .map((group) => ({
          key: group.key,
          label: group.label,
          count: group.hits.length,
        })),
    ],
    [results],
  );

  const activeId = entries[active]
    ? `search-option-${entries[active].group.key}-${entries[active].hit.id}`
    : undefined;

  return (
    <>
      <button
        type="button"
        onClick={openPalette}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="text-muted-foreground border-border/60 bg-muted/40 hover:bg-muted focus-visible:ring-ring hidden w-full max-w-sm items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none xl:flex"
      >
        <SearchIcon className="size-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-left">Search ONEST</span>
        <kbd className="border-border/60 rounded border px-1.5 py-0.5 text-[10px] font-medium">
          &#8984;K
        </kbd>
      </button>

      <button
        type="button"
        onClick={openPalette}
        aria-label="Search ONEST"
        aria-haspopup="dialog"
        className="text-muted-foreground hover:bg-muted focus-visible:ring-ring grid size-9 shrink-0 place-items-center rounded-lg transition-colors focus-visible:ring-2 focus-visible:outline-none xl:hidden"
      >
        <SearchIcon className="size-5" strokeWidth={1.5} aria-hidden />
      </button>

      <CommandPalette
        open={open}
        onOpenChange={setOpen}
        label="Search ONEST"
        description="People, announcements, resources, and offices you have access to."
      >
        <CommandPaletteInput
          ref={inputRef}
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search people, announcements, resources…"
          aria-label="Search query"
          aria-describedby="search-status"
          aria-controls="search-results"
          aria-activedescendant={activeId}
          role="combobox"
          aria-expanded={entries.length > 0}
          aria-autocomplete="list"
        />

        <p id="search-status" aria-live="polite" className="sr-only">
          {loading
            ? "Searching"
            : `${entries.length} results across ${visibleGroups.length} sources`}
        </p>

        {searchable && !rateLimited && tabs.length > 2 ? (
          <CommandPaletteTabs aria-label="Filter results by source">
            {tabs.map((tab) => (
              <CommandPaletteTab
                key={tab.key}
                active={source === tab.key}
                count={tab.count}
                onClick={() => {
                  setSource(tab.key);
                  setActive(0);
                  inputRef.current?.focus();
                }}
              >
                {tab.label}
              </CommandPaletteTab>
            ))}
          </CommandPaletteTabs>
        ) : null}

        {rateLimited ? (
          <Message
            icon={TriangleAlert}
            title="Too many searches"
            body="Wait a moment and try again."
          />
        ) : !searchable ? (
          <Message
            icon={SearchIcon}
            title={query ? "Keep typing" : "Start typing"}
            body={
              query
                ? `Search needs at least ${results.minLength} characters.`
                : "People, announcements, resources, and offices."
            }
          />
        ) : loading && entries.length === 0 ? (
          <CommandPaletteList aria-hidden>
            {[0, 1, 2].map((row) => (
              <div key={row} className="bg-muted mb-1 h-12 animate-pulse rounded-lg" />
            ))}
          </CommandPaletteList>
        ) : entries.length === 0 && !hasFailure ? (
          <Message
            icon={SearchIcon}
            title="No results"
            body={`Nothing you can access matches "${query}".`}
          />
        ) : (
          <CommandPaletteList
            id="search-results"
            role="listbox"
            aria-label="Search results"
          >
            {results.partial ? (
              <p className="text-warning-ink flex items-start gap-2 px-3 py-2 text-xs">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Some sources did not answer, so these results are incomplete.
              </p>
            ) : null}
            {visibleGroups.map((group) => (
              <Group
                key={group.key}
                group={group}
                query={results.query}
                entries={entries}
                active={active}
                onHover={setActive}
                onChoose={go}
              />
            ))}
          </CommandPaletteList>
        )}

        <CommandPaletteFooter>
          <span className="flex items-center gap-1">
            <CommandPaletteKey>&#8593;</CommandPaletteKey>
            <CommandPaletteKey>&#8595;</CommandPaletteKey> to move
          </span>
          <span className="flex items-center gap-1">
            <CommandPaletteKey>&#8629;</CommandPaletteKey> to open
          </span>
          <span className="flex items-center gap-1">
            <CommandPaletteKey>esc</CommandPaletteKey> to close
          </span>
        </CommandPaletteFooter>
      </CommandPalette>
    </>
  );
}

function Message({
  icon: Icon,
  title,
  body,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
}) {
  return (
    <div className="grid justify-items-center gap-1 px-6 py-10 text-center">
      <Icon className="text-muted-foreground mb-1 size-6" aria-hidden />
      <p className="text-sm font-semibold">{title}</p>
      <p className="text-muted-foreground text-xs">{body}</p>
    </div>
  );
}

function Group({
  group,
  query,
  entries,
  active,
  onHover,
  onChoose,
}: {
  group: SearchGroup;
  query: string;
  entries: FlatEntry[];
  active: number;
  onHover: (index: number) => void;
  onChoose: (href: string) => void;
}) {
  const Icon = ICONS[group.icon] ?? SearchIcon;
  return (
    <section aria-label={group.label}>
      <CommandPaletteGroupLabel>
        <span className="flex items-center gap-1.5">
          <Icon className="size-3.5" aria-hidden />
          {group.label}
        </span>
      </CommandPaletteGroupLabel>
      {group.failed ? (
        <p className="text-muted-foreground px-3 pb-2 text-xs">
          This source did not answer. Its results are missing, not empty.
        </p>
      ) : (
        group.hits.map((hit) => {
          const index = entries.findIndex(
            (entry) => entry.hit === hit && entry.group === group,
          );
          return (
            <CommandPaletteOption
              key={hit.id}
              id={`search-option-${group.key}-${hit.id}`}
              href={hit.href}
              active={index === active}
              onMouseEnter={() => onHover(index)}
              onClick={(event) => {
                event.preventDefault();
                onChoose(hit.href);
              }}
            >
              <span className="text-sm font-semibold">
                <Highlighted text={hit.title} query={query} />
              </span>
              {hit.snippet ? (
                <span className="text-muted-foreground line-clamp-1 text-xs">
                  <Highlighted text={hit.snippet} query={query} />
                </span>
              ) : null}
              {hit.meta ? (
                <span className="text-muted-foreground text-[11px]">{hit.meta}</span>
              ) : null}
            </CommandPaletteOption>
          );
        })
      )}
      {group.truncated && group.allResultsHref ? (
        <button
          type="button"
          onClick={() => onChoose(group.allResultsHref)}
          className="text-primary hover:bg-muted/60 focus-visible:ring-ring w-full rounded-lg px-3 py-1.5 text-left text-xs font-medium focus-visible:ring-2 focus-visible:outline-none"
        >
          See all {group.label.toLowerCase()} results
        </button>
      ) : null}
    </section>
  );
}
