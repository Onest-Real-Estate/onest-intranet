import { type ReactNode, useMemo, useState } from "react";

import {
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
} from "@/components/design-system/form";
import { SearchControl } from "@/components/design-system/search-control";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { filterIanaTimezones, listIanaTimezones } from "@/lib/timezones";
import { firstFieldError } from "@/lib/validation";
import type { ValidationErrors } from "@/types/design-system";

const EMPTY_VALIDATION: ValidationErrors = { fields: {}, form: [] };

/**
 * Searchable IANA timezone picker. Mirrors HierarchySelector: a SearchControl
 * narrows the Select list client-side; the server still validates the value.
 */
export function TimezoneField({
  name,
  label = "Timezone",
  value,
  onChange,
  placeholder = "Select a timezone",
  validation = EMPTY_VALIDATION,
  description,
  optional,
  required,
  disabled,
  controlId = name,
  zones,
}: {
  name: string;
  label?: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  validation?: ValidationErrors;
  description?: ReactNode;
  optional?: boolean;
  required?: boolean;
  disabled?: boolean;
  controlId?: string;
  /** Override the IANA list (tests). Defaults to Intl.supportedValuesOf. */
  zones?: string[];
}) {
  const [query, setQuery] = useState("");
  const help = description ? `${controlId}_description` : undefined;
  const errors = validation ?? EMPTY_VALIDATION;
  const catalog = useMemo(() => zones ?? listIanaTimezones(), [zones]);
  const filtered = useMemo(() => filterIanaTimezones(catalog, query), [catalog, query]);

  // Keep the current value selectable even when the search hides it.
  const options = value && !filtered.includes(value) ? [value, ...filtered] : filtered;

  return (
    <FormField>
      <FormLabel htmlFor={controlId} required={required} optional={optional}>
        {label}
      </FormLabel>
      <input type="hidden" name={name} value={value} />
      <div className="space-y-2">
        <SearchControl
          value={query}
          onValueChange={setQuery}
          placeholder="Search timezones"
          label="Search timezones"
          disabled={disabled}
          tone="subtle"
          size="sm"
        />
        <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger
            id={controlId}
            {...fieldA11yProps(name, errors, help, controlId)}
          >
            <SelectValue placeholder={placeholder} />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            {options.length === 0 ? (
              <div className="text-muted-foreground px-2 py-3 text-sm">
                No timezones match “{query.trim()}”.
              </div>
            ) : (
              options.map((zone) => (
                <SelectItem key={zone} value={zone}>
                  {zone.replaceAll("_", " ")}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
      </div>
      {description ? <FormDescription id={help}>{description}</FormDescription> : null}
      <FormFieldError
        id={`${controlId}_error`}
        message={firstFieldError(errors, name)}
      />
    </FormField>
  );
}

/** Controlled picker without the surrounding FormField chrome. */
export function TimezonePicker({
  id,
  value,
  onChange,
  disabled = false,
  invalid = false,
  placeholder = "Select a timezone",
  zones,
}: {
  id?: string;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  invalid?: boolean;
  placeholder?: string;
  zones?: string[];
}) {
  const [query, setQuery] = useState("");
  const catalog = useMemo(() => zones ?? listIanaTimezones(), [zones]);
  const filtered = useMemo(() => filterIanaTimezones(catalog, query), [catalog, query]);
  const options = value && !filtered.includes(value) ? [value, ...filtered] : filtered;

  return (
    <div className="space-y-2">
      <SearchControl
        value={query}
        onValueChange={setQuery}
        placeholder="Search timezones"
        label="Search timezones"
        disabled={disabled}
        tone="subtle"
        size="sm"
      />
      <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} aria-invalid={invalid || undefined}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent className="max-h-72">
          {options.length === 0 ? (
            <div className="text-muted-foreground px-2 py-3 text-sm">
              No timezones match “{query.trim()}”.
            </div>
          ) : (
            options.map((zone) => (
              <SelectItem key={zone} value={zone}>
                {zone.replaceAll("_", " ")}
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
    </div>
  );
}
