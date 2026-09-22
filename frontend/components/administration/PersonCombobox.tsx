import { Building2, Loader2, Search, TriangleAlert, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { AgentContractRecipientResult } from "@/types";

const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

export type PersonOption = AgentContractRecipientResult;

/** Up to two letters, so a long name does not stretch the tile. */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/**
 * The part of the label the reader actually typed, marked so the row answers
 * "why is this here" without them re-reading it. Plain string matching — the
 * term goes nowhere near a regex.
 */
function Highlight({ text, term }: { text: string; term: string }) {
  const needle = term.trim().toLowerCase();
  if (!needle) return <>{text}</>;
  const at = text.toLowerCase().indexOf(needle);
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="bg-chip-primary text-foreground rounded-[2px] px-px">
        {text.slice(at, at + needle.length)}
      </mark>
      {text.slice(at + needle.length)}
    </>
  );
}

function metaLine(person: PersonOption): string {
  return [person.officeName, person.officeState].filter(Boolean).join(" · ");
}

/**
 * The person already chosen, shown as a record rather than as text in a field.
 *
 * The field this replaced put `Name <email>` into the input, which reads as a
 * mailbox header and gives the reader nothing to check against — the office
 * that decides which templates apply was one line further down, unlinked to
 * the name above it. Selection is a resolved fact, so it gets a resolved
 * presentation and the input steps aside until someone wants to change it.
 */
function SelectedPerson({
  person,
  disabled,
  onClear,
}: {
  person: PersonOption;
  disabled: boolean;
  onClear: () => void;
}) {
  return (
    <div className="border-input bg-card flex items-center gap-3 rounded-md border p-2.5">
      <span
        className="bg-muted text-muted-foreground grid size-9 shrink-0 place-items-center rounded-md text-xs font-semibold"
        aria-hidden
      >
        {initials(person.name)}
      </span>
      <span className="grid min-w-0 flex-1 gap-0.5">
        <span className="truncate text-sm font-semibold">{person.name}</span>
        <span className="text-muted-foreground truncate text-xs">
          {person.email}
          {metaLine(person) ? ` · ${metaLine(person)}` : ""}
        </span>
      </span>
      {!disabled ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClear}
          aria-label={`Clear ${person.name}`}
        >
          <X className="size-3.5" aria-hidden />
          Change
        </Button>
      ) : null}
    </div>
  );
}

function Note({
  icon: Icon,
  children,
  tone = "muted",
}: {
  icon: typeof Search;
  children: React.ReactNode;
  tone?: "muted" | "destructive";
}) {
  return (
    <p
      className={cn(
        "flex items-center gap-2 px-3 py-2.5 text-sm",
        tone === "destructive" ? "text-destructive" : "text-muted-foreground",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      {children}
    </p>
  );
}

/**
 * Search for a person in scope and choose exactly one.
 *
 * Replaces two near-identical hand-rolled fields that claimed
 * `role="combobox"` while pointing `aria-controls` at a plain `div` of
 * buttons: no `listbox`, no `option`, no `aria-activedescendant`, and no way
 * to reach a result from the keyboard without tabbing out of the input. Both
 * also painted the popover with `bg-surface`, which is not a token this
 * project defines, so the panel had no fill at all.
 *
 * Two behaviours worth naming, both borrowed from `GlobalSearch`:
 *
 * * **Stale answers are dropped.** Each keystroke aborts the request before
 *   it, so a slow response for "sam" cannot overwrite a fast one for "samuel".
 * * **Selection roves, focus does not.** Arrow keys move a highlight while the
 *   caret stays in the input, exposed with `aria-activedescendant`.
 */
export function PersonCombobox({
  id,
  name,
  label,
  endpoint,
  value,
  onChange,
  disabled = false,
  required = false,
  placeholder = "Search by name or email",
  description,
  invalid = false,
}: {
  id: string;
  /** Hidden field posted with the form; omit for a purely controlled use. */
  name?: string;
  label: string;
  /** Search URL. `?q=` is appended. */
  endpoint: string;
  value: PersonOption | null;
  onChange: (person: PersonOption | null) => void;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  description?: React.ReactNode;
  invalid?: boolean;
}) {
  const listId = useId();
  const statusId = useId();
  const describedId = useId();
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<PersonOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);

  const searchable = term.trim().length >= MIN_QUERY;
  const activeId = open && results.length > 0 ? `${listId}-${active}` : undefined;

  useEffect(() => {
    if (disabled || value || !searchable) {
      abortRef.current?.abort();
      setResults([]);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    const handle = window.setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const separator = endpoint.includes("?") ? "&" : "?";
      fetch(`${endpoint}${separator}q=${encodeURIComponent(term.trim())}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) throw new Error(String(response.status));
          return response.json() as Promise<{ results?: PersonOption[] }>;
        })
        .then((payload) => {
          setResults(payload.results ?? []);
          setActive(0);
          setLoading(false);
        })
        .catch((error: unknown) => {
          // An abort is this component superseding itself, not a failure.
          if (error instanceof DOMException && error.name === "AbortError") return;
          setResults([]);
          setFailed(true);
          setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [disabled, endpoint, searchable, term, value]);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Keep the roving highlight inside the scroll box.
  useEffect(() => {
    listRef.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const status = useMemo(() => {
    if (!open) return "";
    if (!searchable) return `Type at least ${MIN_QUERY} characters to search.`;
    if (loading) return "Searching.";
    if (failed) return "Search failed.";
    return `${results.length} ${results.length === 1 ? "person" : "people"} found.`;
  }, [failed, loading, open, results.length, searchable]);

  function choose(person: PersonOption) {
    onChange(person);
    setTerm("");
    setResults([]);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
      }
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index - 1 + results.length) % results.length);
    } else if (event.key === "Home") {
      event.preventDefault();
      setActive(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setActive(results.length - 1);
    } else if (event.key === "Enter") {
      const person = results[active];
      if (person) {
        event.preventDefault();
        choose(person);
      }
    }
  }

  const showPanel = open && !disabled && !value;

  return (
    <div className="grid gap-2">
      {name ? <input type="hidden" name={name} value={value?.id ?? ""} /> : null}

      {value ? (
        // Once somebody is chosen there is no field left to label, so the name
        // of the group becomes a legend rather than a `<label>` pointing at
        // nothing — an orphan label is announced as a control that is not there.
        <fieldset className="min-w-0">
          <legend className="mb-2 text-sm leading-none font-medium">{label}</legend>
          <SelectedPerson
            person={value}
            disabled={disabled}
            onClear={() => {
              onChange(null);
              setTerm("");
              setOpen(false);
            }}
          />
        </fieldset>
      ) : (
        <>
          <Label htmlFor={id}>{label}</Label>
          {/*
            Portal the panel: SurfaceCard (and other rounded shells) use
            overflow-hidden, which clips an absolutely positioned listbox to a
            sliver. Radix Popover escapes that the same way SelectContent does.
          */}
          <Popover
            open={showPanel}
            onOpenChange={(next) => {
              if (!next) setOpen(false);
            }}
            modal={false}
          >
            <PopoverAnchor asChild>
              <div ref={anchorRef} className="relative">
                <Search
                  className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                  aria-hidden
                />
                <Input
                  id={id}
                  role="combobox"
                  aria-expanded={showPanel}
                  aria-controls={listId}
                  aria-activedescendant={activeId}
                  aria-autocomplete="list"
                  aria-describedby={description ? describedId : undefined}
                  aria-invalid={invalid || undefined}
                  aria-required={required || undefined}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  data-1p-ignore
                  data-lpignore="true"
                  data-form-type="other"
                  disabled={disabled}
                  className="pl-9"
                  value={term}
                  placeholder={placeholder}
                  onChange={(event) => {
                    setTerm(event.target.value);
                    setOpen(true);
                  }}
                  onFocus={() => setOpen(true)}
                  onKeyDown={onKeyDown}
                />
                {loading && showPanel ? (
                  <Loader2
                    className="text-muted-foreground absolute top-1/2 right-3 size-4 -translate-y-1/2 animate-spin"
                    aria-hidden
                  />
                ) : null}
              </div>
            </PopoverAnchor>
            <PopoverContent
              align="start"
              sideOffset={4}
              className="w-[var(--radix-popover-trigger-width)] overflow-hidden p-0"
              onOpenAutoFocus={(event) => event.preventDefault()}
              onCloseAutoFocus={(event) => event.preventDefault()}
              onInteractOutside={(event) => {
                // The input is the anchor, outside the content. Keep the panel
                // open while the caret stays in the field.
                if (
                  event.target instanceof Node &&
                  anchorRef.current?.contains(event.target)
                ) {
                  event.preventDefault();
                }
              }}
            >
              {!searchable ? (
                <Note icon={Search}>
                  {`Type at least ${MIN_QUERY} characters to search.`}
                </Note>
              ) : failed ? (
                <Note icon={TriangleAlert} tone="destructive">
                  Search could not run. Check your connection and try again.
                </Note>
              ) : loading && results.length === 0 ? (
                <div className="grid gap-1 p-1" aria-hidden>
                  {[0, 1, 2].map((row) => (
                    <div key={row} className="bg-muted h-12 animate-pulse rounded-md" />
                  ))}
                </div>
              ) : results.length === 0 ? (
                <Note icon={Search}>Nobody in your scope matches “{term.trim()}”.</Note>
              ) : (
                <div
                  ref={listRef}
                  id={listId}
                  role="listbox"
                  aria-label={label}
                  className="max-h-64 overflow-y-auto p-1"
                >
                  {results.map((person, index) => (
                    // ARIA 1.2 combobox: options are pointed at with
                    // `aria-activedescendant` and must NOT be focusable, so the
                    // caret stays in the input while the arrows move a highlight.
                    // biome-ignore lint/a11y/useFocusableInteractive: roving selection, not focus
                    <div
                      key={person.id}
                      id={`${listId}-${index}`}
                      role="option"
                      aria-selected={index === active}
                      className={cn(
                        "flex scroll-m-1 cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 transition-colors",
                        index === active ? "bg-accent" : "bg-transparent",
                      )}
                      onMouseEnter={() => setActive(index)}
                      onMouseDown={(event) => {
                        // Choose on mousedown so focus stays in the input.
                        event.preventDefault();
                        choose(person);
                      }}
                    >
                      <span
                        className="bg-muted text-muted-foreground grid size-8 shrink-0 place-items-center rounded-md text-xs font-semibold"
                        aria-hidden
                      >
                        {initials(person.name)}
                      </span>
                      <span className="grid min-w-0 flex-1 gap-0.5">
                        <span className="truncate text-sm font-medium">
                          <Highlight text={person.name} term={term} />
                        </span>
                        <span className="text-muted-foreground truncate text-xs">
                          <Highlight text={person.email} term={term} />
                        </span>
                      </span>
                      {person.officeName ? (
                        <span className="text-muted-foreground hidden shrink-0 items-center gap-1 text-xs sm:flex">
                          <Building2 className="size-3.5" aria-hidden />
                          {person.officeName}
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </PopoverContent>
          </Popover>
        </>
      )}

      {description ? (
        <p id={describedId} className="text-muted-foreground text-xs leading-4">
          {description}
        </p>
      ) : null}

      <p id={statusId} aria-live="polite" className="sr-only">
        {status}
      </p>
    </div>
  );
}
