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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

  it("contains long select values inside responsive form columns", () => {
    const { container } = render(
      <div className="grid grid-cols-2">
        <FormField data-testid="field">
          <FormLabel htmlFor="office">Office</FormLabel>
          <Select defaultValue="fairfax">
            <SelectTrigger id="office" aria-label="Office">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fairfax">
                Onest Real Estate / Mid-Atlantic / Virginia / Fairfax VA
              </SelectItem>
            </SelectContent>
          </Select>
        </FormField>
      </div>,
    );

    expect(screen.getByTestId("field")).toHaveClass("min-w-0");
    expect(screen.getByRole("combobox", { name: "Office" })).toHaveClass(
      "min-w-0",
      "overflow-hidden",
    );
    expect(
      container.querySelector('[data-slot="select-trigger"]')?.className,
    ).toContain("*:data-[slot=select-value]:truncate");
  });
});
