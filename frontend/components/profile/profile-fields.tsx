import type * as React from "react";

import {
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
} from "@/components/design-system";
import { Input } from "@/components/ui/input";
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
import type { OfficeGroup } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

/**
 * The three field shapes this page repeats. Each one keeps the Django field
 * name as the DOM id so `FormErrorSummary` links land on the control that
 * failed, and wires `aria-invalid`/`aria-describedby` from the same payload.
 */

export function descriptionId(name: string): string {
  return `${name}_description`;
}

export function TextField({
  name,
  label,
  validation,
  description,
  optional,
  required,
  leading,
  ...props
}: Omit<React.ComponentProps<typeof Input>, "id" | "name"> & {
  name: string;
  label: string;
  validation: ValidationErrors;
  description?: React.ReactNode;
  optional?: boolean;
  required?: boolean;
  /** Decorative icon set inside the control's left edge. */
  leading?: React.ReactNode;
}) {
  const help = description ? descriptionId(name) : undefined;
  return (
    <FormField>
      <FormLabel htmlFor={name} required={required} optional={optional}>
        {label}
      </FormLabel>
      {leading ? (
        <div className="relative">
          <span
            aria-hidden
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 [&_svg]:size-4"
          >
            {leading}
          </span>
          <Input
            id={name}
            name={name}
            required={required}
            className="pl-10"
            {...fieldA11yProps(name, validation, help)}
            {...props}
          />
        </div>
      ) : (
        <Input
          id={name}
          name={name}
          required={required}
          {...fieldA11yProps(name, validation, help)}
          {...props}
        />
      )}
      {description ? <FormDescription id={help}>{description}</FormDescription> : null}
      <FormFieldError
        id={`${name}_error`}
        message={firstFieldError(validation, name)}
      />
    </FormField>
  );
}

/**
 * shadcn's Select is not a native form control, so the submitted value rides
 * in a mirrored hidden input. `value` is owned by the caller because several
 * of these also drive the unsaved-changes guard.
 */
export function SelectField({
  name,
  label,
  value,
  onChange,
  placeholder,
  options,
  groups,
  validation,
  description,
  optional,
  required,
  disabled,
  className,
  controlClassName,
  controlId = name,
}: {
  name: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder: string;
  options?: { value: string; label: string }[];
  groups?: OfficeGroup[];
  validation: ValidationErrors;
  description?: React.ReactNode;
  optional?: boolean;
  required?: boolean;
  disabled?: boolean;
  /** Placement of the whole field — a grid span, typically. */
  className?: string;
  /** Visual treatment for the trigger; the field wrapper remains unchanged. */
  controlClassName?: string;
  /** Unique DOM id when several controls submit the same field name. */
  controlId?: string;
}) {
  const help = description ? descriptionId(controlId) : undefined;
  return (
    <FormField className={className}>
      <FormLabel htmlFor={controlId} required={required} optional={optional}>
        {label}
      </FormLabel>
      <input type="hidden" name={name} value={value} />
      <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger
          id={controlId}
          className={controlClassName}
          {...fieldA11yProps(name, validation, help, controlId)}
        >
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {options?.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
          {groups?.map((group) => (
            <SelectGroup key={group.label}>
              <SelectLabel>{group.label}</SelectLabel>
              {group.offices.map((office) => (
                <SelectItem key={office.id} value={String(office.id)}>
                  {office.name}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      {description ? <FormDescription id={help}>{description}</FormDescription> : null}
      <FormFieldError
        id={`${controlId}_error`}
        message={firstFieldError(validation, name)}
      />
    </FormField>
  );
}
