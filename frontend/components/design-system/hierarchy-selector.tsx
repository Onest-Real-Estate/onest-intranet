import { type ReactNode, useMemo, useState } from "react";

import {
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
} from "@/components/design-system/form";
import { SearchControl } from "@/components/design-system/search-control";
import { StatusBadge } from "@/components/design-system/status-badge";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { firstFieldError } from "@/lib/validation";
import type { ValidationErrors } from "@/types/design-system";

export type HierarchySelectorOffice = {
  id: number | string;
  name: string;
  pathLabel?: string;
  isActive?: boolean;
  isAssignable?: boolean;
};

export type HierarchySelectorGroup = {
  label: string;
  offices: HierarchySelectorOffice[];
};

const EMPTY_VALIDATION: ValidationErrors = { fields: {}, form: [] };

/**
 * Searchable, keyboard-accessible hierarchy office picker for large trees.
 * Client filtering is a convenience; the server remains authoritative.
 */
export function HierarchySelector({
  name,
  label,
  value,
  onChange,
  placeholder = "Select an office",
  groups,
  validation = EMPTY_VALIDATION,
  description,
  optional,
  required,
  disabled,
  controlId = name,
}: {
  name: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  groups: HierarchySelectorGroup[];
  validation?: ValidationErrors;
  description?: ReactNode;
  optional?: boolean;
  required?: boolean;
  disabled?: boolean;
  controlId?: string;
}) {
  const [query, setQuery] = useState("");
  const help = description ? `${controlId}_description` : undefined;
  const errors = validation ?? EMPTY_VALIDATION;

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return groups;
    }
    return groups
      .map((group) => ({
        ...group,
        offices: group.offices.filter((office) => {
          const haystack = `${office.name} ${office.pathLabel ?? ""} ${group.label}`;
          return haystack.toLowerCase().includes(needle);
        }),
      }))
      .filter((group) => group.offices.length > 0);
  }, [groups, query]);

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
          placeholder="Search offices or regions"
          label="Search offices or regions"
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
          <SelectContent>
            {filtered.length === 0 ? (
              <div className="text-muted-foreground px-2 py-3 text-sm">
                No offices match “{query.trim()}”.
              </div>
            ) : (
              filtered.map((group) => (
                <SelectGroup key={group.label}>
                  <SelectLabel>{group.label}</SelectLabel>
                  {group.offices.map((office) => {
                    const inactive = office.isActive === false;
                    const unassignable = office.isAssignable === false;
                    return (
                      <SelectItem
                        key={String(office.id)}
                        value={String(office.id)}
                        disabled={inactive || unassignable}
                      >
                        <span className="flex items-center gap-2">
                          <span>{office.pathLabel ?? office.name}</span>
                          {inactive ? (
                            <StatusBadge
                              status={{ label: "Inactive", tone: "neutral" }}
                            />
                          ) : null}
                        </span>
                      </SelectItem>
                    );
                  })}
                </SelectGroup>
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
