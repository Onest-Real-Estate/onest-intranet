import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RoleBadge } from "./role-badge";

describe("RoleBadge", () => {
  it("renders code-backed label and optional scope", () => {
    render(<RoleBadge code="realtor" scopeLabel="Company" />);
    expect(screen.getByText("Realtor")).toBeInTheDocument();
    expect(screen.getByText(/Company/)).toBeInTheDocument();
  });

  it("prefers an explicit server label", () => {
    render(<RoleBadge code="realtor" label="Custom label" />);
    expect(screen.getByText("Custom label")).toBeInTheDocument();
  });
});
