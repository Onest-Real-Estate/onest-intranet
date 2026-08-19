import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import {
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
} from "@/components/design-system/form";
import { Input } from "@/components/ui/input";

describe("form components", () => {
  it("renders untrusted server text without creating HTML", async () => {
    const unsafe = '<img src=x onerror="alert(1)">';
    const errors = { fields: { name: [unsafe] }, form: [] };
    const { container } = render(
      <form>
        <FormErrorSummary errors={errors} />
        <FormField>
          <FormLabel htmlFor="name" required>
            Name
          </FormLabel>
          <Input id="name" aria-invalid aria-describedby="name_error" />
          <FormFieldError id="name_error" message={unsafe} />
        </FormField>
      </form>,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByText(unsafe)).toHaveLength(2);
    expect(await axe(container)).toHaveNoViolations();
  });
});
