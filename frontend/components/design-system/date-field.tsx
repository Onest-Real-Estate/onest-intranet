import { CalendarIcon } from "lucide-react";
import { type ReactNode, useState } from "react";

import {
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
} from "@/components/design-system/form";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatFormDate, parseFormDate, toFormDate } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { firstFieldError } from "@/lib/validation";
import type { ValidationErrors } from "@/types/design-system";

function keepPopoverOpenForSelect(event: Event) {
  const target = event.target as HTMLElement;
  if (
    target.closest('[data-slot="select-content"]') ||
    target.closest('[data-slot="select-trigger"]')
  ) {
    event.preventDefault();
  }
}
const RANGE_START = new Date(new Date().getFullYear() - 100, 0);
const RANGE_END = new Date(new Date().getFullYear() + 20, 11);

export function DatePicker({
  id,
  value,
  onChange,
  disabled = false,
  placeholder = "Pick a date",
  includeTime = false,
  required = false,
  invalid,
  describedBy,
  className,
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  placeholder?: string;
  includeTime?: boolean;
  required?: boolean;
  invalid?: boolean;
  describedBy?: string;
  className?: string;
  "aria-label"?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = parseFormDate(value);
  const display = formatFormDate(value, includeTime);
  const timeValue =
    selected && includeTime ? toFormDate(selected, true).slice(11, 16) : "";

  function commitDate(next: Date | undefined) {
    if (!next) {
      onChange("");
      return;
    }
    if (includeTime && selected) {
      next.setHours(selected.getHours(), selected.getMinutes());
    } else if (includeTime) {
      const now = new Date();
      next.setHours(now.getHours(), now.getMinutes(), 0, 0);
    }
    onChange(toFormDate(next, includeTime));
    if (!includeTime) {
      setOpen(false);
    }
  }

  function commitTime(nextTime: string) {
    const base = selected ?? new Date();
    if (!nextTime) {
      onChange(toFormDate(base, false));
      return;
    }
    const [hours, minutes] = nextTime.split(":").map(Number);
    base.setHours(hours, minutes, 0, 0);
    onChange(toFormDate(base, true));
  }

  return (
    <Popover open={open} onOpenChange={setOpen} modal={false}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          disabled={disabled}
          data-empty={!display}
          aria-required={required || undefined}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          aria-label={ariaLabel}
          className={cn(
            "w-full justify-start font-normal data-[empty=true]:text-muted-foreground",
            className,
          )}
        >
          <CalendarIcon className="size-4" aria-hidden />
          {display || placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-auto p-0"
        align="start"
        onInteractOutside={keepPopoverOpenForSelect}
        onPointerDownOutside={keepPopoverOpenForSelect}
      >
        <Calendar
          mode="single"
          selected={selected}
          onSelect={commitDate}
          captionLayout="dropdown"
          startMonth={RANGE_START}
          endMonth={RANGE_END}
          defaultMonth={selected}
          disabled={disabled}
        />
        {includeTime ? (
          <div className="border-border grid gap-2 border-t p-3">
            <label
              className="text-muted-foreground text-xs font-semibold"
              htmlFor={`${id}-time`}
            >
              Time
            </label>
            <Input
              id={`${id}-time`}
              type="time"
              step={60}
              value={timeValue}
              disabled={disabled || !selected}
              onChange={(event) => commitTime(event.target.value)}
            />
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

export function DateField({
  name,
  label,
  value: controlledValue,
  defaultValue = "",
  onChange,
  validation,
  description,
  optional,
  required,
  disabled,
  includeTime = false,
  placeholder = "Pick a date",
}: {
  name: string;
  label: string;
  value?: string;
  defaultValue?: string;
  onChange?: (next: string) => void;
  validation?: ValidationErrors;
  description?: ReactNode;
  optional?: boolean;
  required?: boolean;
  disabled?: boolean;
  includeTime?: boolean;
  placeholder?: string;
}) {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const value = controlledValue ?? uncontrolled;
  const help = description ? `${name}_description` : undefined;
  const a11y = fieldA11yProps(name, validation, help);

  function setValue(next: string) {
    if (controlledValue === undefined) {
      setUncontrolled(next);
    }
    onChange?.(next);
  }

  return (
    <FormField>
      <FormLabel htmlFor={name} required={required} optional={optional}>
        {label}
      </FormLabel>
      <input type="hidden" name={name} value={value} />
      <DatePicker
        id={name}
        value={value}
        onChange={setValue}
        disabled={disabled}
        placeholder={placeholder}
        includeTime={includeTime}
        required={required}
        invalid={Boolean(a11y["aria-invalid"])}
        describedBy={a11y["aria-describedby"]}
      />
      {description ? <FormDescription id={help}>{description}</FormDescription> : null}
      <FormFieldError
        id={`${name}_error`}
        message={validation ? firstFieldError(validation, name) : undefined}
      />
    </FormField>
  );
}
