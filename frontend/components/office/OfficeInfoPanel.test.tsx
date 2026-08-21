import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OfficeInfoPanel } from "@/components/office/OfficeInfoPanel";
import type { OfficeInfoPayload } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  usePage: () => ({ props: {} }),
}));

const baseInfo: OfficeInfoPayload = {
  id: 1,
  name: "Fairfax VA",
  slug: "fairfax-va",
  stableKey: "fairfax-va",
  kind: "branch",
  pathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
  regionName: "Mid-Atlantic",
  isActive: true,
  streetAddress: "1 Main St",
  city: "Fairfax",
  state: "VA",
  zipCode: "22030",
  mainPhone: "(703) 555-0100",
  publicEmail: "fairfax@example.com",
  internalEmail: "secret@example.com",
  officeHours: ["Mon–Fri 9–5"],
  parkingInstructions: "Lot B",
  accessInstructions: "Door code 9999",
  accessInstructionsInternal: true,
  includeInternal: false,
  updatedAt: "2026-08-22T00:00:00Z",
  version: "1:2026-08-22T00:00:00Z",
  contacts: {
    branchManager: null,
    branchAdmin: null,
    brokers: [],
    transactionCoordinator: null,
    itSupport: null,
  },
};

describe("OfficeInfoPanel", () => {
  it("hides internal access instructions when includeInternal is false", () => {
    render(<OfficeInfoPanel info={baseInfo} />);
    expect(screen.getByText("Fairfax VA")).toBeInTheDocument();
    expect(screen.queryByText("Door code 9999")).not.toBeInTheDocument();
    expect(screen.queryByText("secret@example.com")).not.toBeInTheDocument();
  });

  it("shows internal fields when includeInternal is true", () => {
    render(
      <OfficeInfoPanel
        info={{
          ...baseInfo,
          includeInternal: true,
        }}
      />,
    );
    expect(screen.getByText("Door code 9999")).toBeInTheDocument();
    expect(screen.getByText(/secret@example.com/)).toBeInTheDocument();
  });

  it("renders empty contact fallbacks", () => {
    render(<OfficeInfoPanel info={baseInfo} />);
    expect(screen.getByText("No branch manager assigned.")).toBeInTheDocument();
    expect(screen.getByText("No IT support contact assigned.")).toBeInTheDocument();
  });
});
