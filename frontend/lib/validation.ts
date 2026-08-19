import type { ValidationErrors } from "@/types/design-system";

export const EMPTY_VALIDATION_ERRORS: ValidationErrors = {
  fields: {},
  form: [],
};

export function fieldMessages(
  errors: ValidationErrors | undefined,
  field: string,
): string[] {
  return errors?.fields[field] ?? [];
}

export function firstFieldError(
  errors: ValidationErrors | undefined,
  field: string,
): string | undefined {
  return fieldMessages(errors, field)[0];
}

export function hasValidationErrors(errors: ValidationErrors | undefined): boolean {
  return Boolean(
    errors &&
      (errors.form.length > 0 ||
        Object.values(errors.fields).some((messages) => messages.length > 0)),
  );
}

export function validationEntries(
  errors: ValidationErrors | undefined,
  labels: Record<string, string> = {},
): { id: string; field?: string; label: string; message: string }[] {
  if (!errors) {
    return [];
  }
  const formEntries = errors.form.map((message, index) => ({
    id: `form-${index}-${message}`,
    label: "Form",
    message,
  }));
  const fieldEntries = Object.entries(errors.fields).flatMap(([field, messages]) =>
    messages.map((message, index) => ({
      id: `${field}-${index}-${message}`,
      field,
      label: labels[field] ?? field.replaceAll("_", " "),
      message,
    })),
  );
  return [...formEntries, ...fieldEntries];
}
