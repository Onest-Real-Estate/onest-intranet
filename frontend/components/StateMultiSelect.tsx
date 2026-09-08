import { Check, ChevronsUpDown, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { StateOption } from "@/types";

type StateMultiSelectProps = {
  name: string;
  options: StateOption[];
  defaultValue?: string[];
  label?: string;
  placeholder?: string;
  hint?: string;
  id?: string;
  className?: string;
};

/**
 * Native-form-friendly US state multi-select with typeahead filter.
 *
 * Selected codes are submitted as repeated fields with the same ``name``
 * (Django ``MultipleChoiceField`` / ``request.POST.getlist``).
 */
export function StateMultiSelect({
  name,
  options,
  defaultValue = [],
  label,
  placeholder = "Select states",
  hint,
  id,
  className,
}: StateMultiSelectProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>(() =>
    defaultValue.map((code) => code.toUpperCase()).filter(Boolean),
  );

  const byCode = useMemo(() => {
    const map = new Map<string, string>();
    for (const option of options) {
      map.set(option.code.toUpperCase(), option.name);
    }
    return map;
  }, [options]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) => {
      const code = option.code.toLowerCase();
      const optionName = option.name.toLowerCase();
      return code.includes(needle) || optionName.includes(needle);
    });
  }, [options, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      searchRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  function toggle(code: string) {
    const next = code.toUpperCase();
    setSelected((current) =>
      current.includes(next)
        ? current.filter((item) => item !== next)
        : [...current, next].sort(),
    );
  }

  function clear() {
    setSelected([]);
  }

  function selectAllShown() {
    const codes = filtered.map((option) => option.code.toUpperCase());
    setSelected((current) => {
      const next = new Set(current);
      for (const code of codes) {
        next.add(code);
      }
      return [...next].sort();
    });
  }

  const allShownSelected =
    filtered.length > 0 &&
    filtered.every((option) => selected.includes(option.code.toUpperCase()));

  const summary =
    selected.length === 0
      ? placeholder
      : selected.length <= 3
        ? selected.map((code) => byCode.get(code) ?? code).join(", ")
        : `${selected.length} states selected`;

  return (
    <div className={cn("grid gap-2", className)}>
      {label ? <Label htmlFor={fieldId}>{label}</Label> : null}
      {selected.map((code) => (
        <input key={code} type="hidden" name={name} value={code} />
      ))}
      <Popover open={open} onOpenChange={setOpen} modal>
        <PopoverTrigger asChild>
          <Button
            id={fieldId}
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="h-auto min-h-9 w-full justify-between px-3 py-2 font-normal"
          >
            <span
              className={cn(
                "truncate text-left",
                selected.length === 0 && "text-muted-foreground",
              )}
            >
              {summary}
            </span>
            <ChevronsUpDown className="size-4 shrink-0 opacity-50" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[var(--radix-popover-trigger-width)] p-0"
          align="start"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            searchRef.current?.focus();
          }}
          onWheel={(event) => {
            // Keep wheel scrolling inside the list; CreateSheet's body otherwise
            // steals the gesture and the options pane never scrolls.
            event.stopPropagation();
          }}
        >
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search
                className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
                aria-hidden
              />
              <Input
                ref={searchRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search states…"
                aria-label="Search states"
                className="h-9 pl-8"
                autoComplete="off"
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.stopPropagation();
                    setOpen(false);
                  }
                }}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
            <span className="text-muted-foreground text-xs font-medium">
              {selected.length} selected
              {query.trim() ? ` · ${filtered.length} shown` : ""}
            </span>
            <div className="flex shrink-0 items-center gap-0.5">
              {!allShownSelected ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={selectAllShown}
                >
                  {query.trim() ? "Select shown" : "Select all"}
                </Button>
              ) : null}
              {selected.length > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={clear}
                >
                  Clear
                </Button>
              ) : null}
            </div>
          </div>
          <div
            className="max-h-64 overflow-y-auto overscroll-contain p-2"
            onWheel={(event) => event.stopPropagation()}
          >
            {filtered.length === 0 ? (
              <p className="text-muted-foreground px-2 py-6 text-center text-sm">
                No states match “{query.trim()}”.
              </p>
            ) : (
              <div className="grid gap-1">
                {filtered.map((option) => {
                  const code = option.code.toUpperCase();
                  const checked = selected.includes(code);
                  const optionId = `${fieldId}-${code}`;
                  return (
                    <label
                      key={code}
                      htmlFor={optionId}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                        "hover:bg-muted",
                        checked && "bg-muted/70",
                      )}
                    >
                      <Checkbox
                        id={optionId}
                        checked={checked}
                        onCheckedChange={() => toggle(code)}
                      />
                      <span className="min-w-8 font-medium tabular-nums">{code}</span>
                      <span className="text-muted-foreground truncate">
                        {option.name}
                      </span>
                      {checked ? (
                        <Check className="ml-auto size-3.5 shrink-0" aria-hidden />
                      ) : null}
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((code) => (
            <Badge key={code} variant="secondary" className="gap-1 pr-1">
              {code}
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-muted"
                aria-label={`Remove ${code}`}
                onClick={() => toggle(code)}
              >
                <X className="size-3" aria-hidden />
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}
