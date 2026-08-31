import { LoaderCircle, Search, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function SearchControl({
  value,
  defaultValue = "",
  onValueChange,
  onSearch,
  onClear,
  label = "Search",
  placeholder = "Search",
  loading = false,
  disabled = false,
  error,
  tone = "outline",
  size = "default",
  className,
}: {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  onSearch?: (value: string) => void;
  onClear?: () => void;
  label?: string;
  placeholder?: string;
  loading?: boolean;
  disabled?: boolean;
  error?: string;
  /**
   * `outline` is the search that owns its region. `subtle` recedes into a
   * toolbar or app header, where a bordered field would out-weigh the controls
   * beside it.
   */
  tone?: "outline" | "subtle";
  size?: "default" | "sm";
  className?: string;
}) {
  const [internalValue, setInternalValue] = useState(defaultValue);
  const currentValue = value ?? internalValue;
  const errorId = error
    ? `${label.toLowerCase().replaceAll(" ", "-")}-error`
    : undefined;

  function update(nextValue: string) {
    if (value === undefined) {
      setInternalValue(nextValue);
    }
    onValueChange?.(nextValue);
  }

  return (
    // biome-ignore lint/a11y/useSemanticElements: jsdom does not recognise <search> yet
    <div role="search" className={cn("block", className)}>
      <form
        className="grid gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch?.(currentValue.trim());
        }}
      >
        <div className="relative">
          {loading ? (
            <LoaderCircle
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 animate-spin"
              aria-hidden
            />
          ) : (
            <Search
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
              aria-hidden
            />
          )}
          <Input
            type="search"
            value={currentValue}
            onChange={(event) => update(event.target.value)}
            placeholder={placeholder}
            aria-label={label}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={errorId}
            disabled={disabled}
            className={cn(
              "pr-10 pl-9 [&::-webkit-search-cancel-button]:hidden",
              size === "sm" ? "h-8" : "h-9",
              tone === "subtle" && "bg-muted/60 border-transparent shadow-none",
            )}
          />
          {currentValue && !disabled ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-1/2 right-1 size-8 -translate-y-1/2"
              aria-label={`Clear ${label.toLowerCase()}`}
              onClick={() => {
                update("");
                onClear?.();
              }}
            >
              <X className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
        {error ? (
          <p id={errorId} role="alert" className="text-destructive text-xs">
            {error}
          </p>
        ) : null}
      </form>
    </div>
  );
}
