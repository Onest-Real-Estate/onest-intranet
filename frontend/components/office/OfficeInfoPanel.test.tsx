import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OfficeInfoPanel } from "@/components/office/OfficeInfoPanel";
import type { OfficeInfoPayload } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  usePage: () => ({ props: {} }),
}));

const clipboardMock = vi.fn();
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: clipboardMock },
  configurable: true,
});
afterEach(() => {
  clipboardMock.mockClear();
});

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
  directionsUrl: "https://www.google.com/maps/search/?api=1&query=1+Main+St%2C+Fairfax",
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
  corporateContacts: [],
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

  it("links directions to the approved external map destination", () => {
    render(<OfficeInfoPanel info={baseInfo} />);
    const link = screen.getByRole("link", { name: /directions/i });
    expect(link).toHaveAttribute(
      "href",
      "https://www.google.com/maps/search/?api=1&query=1+Main+St%2C+Fairfax",
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("omits the directions action without a URL and shows address fallback", () => {
    render(
      <OfficeInfoPanel
        info={{
          ...baseInfo,
          directionsUrl: "",
          streetAddress: "",
          city: "",
          state: "",
          zipCode: "",
        }}
      />,
    );
    expect(screen.queryByRole("link", { name: /directions/i })).not.toBeInTheDocument();
    expect(screen.getByText("Not listed yet.")).toBeInTheDocument();
  });

  it("copies the single-line address to the clipboard", async () => {
    clipboardMock.mockResolvedValue(undefined);
    render(<OfficeInfoPanel info={baseInfo} />);
    fireEvent.click(screen.getByRole("button", { name: /copy address/i }));
    expect(clipboardMock).toHaveBeenCalledWith("1 Main St, Fairfax, VA, 22030");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /address copied/i }),
      ).toBeInTheDocument(),
    );
  });

  it("renders structured hours with closed days and timezone caption", () => {
    render(
      <OfficeInfoPanel
        info={{
          ...baseInfo,
          officeHours: [
            { day: "monday", open: "09:00", close: "17:00" },
            { day: "friday", open: "09:00", close: "17:00" },
          ],
        }}
      />,
    );
    // The week is a definition list now, so the day and its hours are separate
    // elements: today's row can be called out without reformatting the string.
    expect(screen.getByText("Monday")).toBeInTheDocument();
    // Monday and Friday both open at nine, so this is a pair, not a single.
    expect(screen.getAllByText("09:00–17:00", { selector: "dd" })).toHaveLength(2);
    expect(screen.getByText("Sunday")).toBeInTheDocument();
    expect(screen.getAllByText("Closed").length).toBeGreaterThan(0);
    expect(screen.getByText("Times shown in Eastern Time.")).toBeInTheDocument();
  });

  it("renders free-text hours without a timezone caption", () => {
    render(<OfficeInfoPanel info={baseInfo} />);
    expect(screen.getByText("Mon–Fri 9–5")).toBeInTheDocument();
    expect(screen.queryByText("Times shown in Eastern Time.")).not.toBeInTheDocument();
  });

  it("shows an empty-state hours fallback", () => {
    render(<OfficeInfoPanel info={{ ...baseInfo, officeHours: [] }} />);
    expect(screen.getByText("Hours not listed.")).toBeInTheDocument();
  });

  it("renders companywide support contacts with their role labels", () => {
    render(
      <OfficeInfoPanel
        info={{
          ...baseInfo,
          corporateContacts: [
            {
              id: 9,
              displayName: "Anjana Budhathoki",
              email: "info@onest.realestate",
              phoneNumber: "(703) 509-1167",
              isPrimary: true,
              assignmentType: "principal_broker",
              assignmentTypeLabel: "Principal broker",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Companywide support")).toBeInTheDocument();
    expect(screen.getByText("Anjana Budhathoki")).toBeInTheDocument();
    expect(screen.getByText("Principal broker")).toBeInTheDocument();
    // The address is the control's destination now rather than wrapped text.
    expect(screen.getByRole("link", { name: /email/i })).toHaveAttribute(
      "href",
      "mailto:info@onest.realestate",
    );
  });

  it("omits the corporate section when there are no corporate contacts", () => {
    render(<OfficeInfoPanel info={baseInfo} />);
    expect(screen.queryByText("Companywide support")).not.toBeInTheDocument();
  });

  it("exposes tel: links with sanitized numbers", () => {
    render(
      <OfficeInfoPanel
        info={{
          ...baseInfo,
          contacts: {
            ...baseInfo.contacts,
            branchManager: {
              id: 2,
              displayName: "Suman Mahara",
              email: "suman@onest.realestate",
              phoneNumber: "(857) 869-2765",
              isPrimary: true,
              assignmentType: "manager",
              assignmentTypeLabel: "Branch manager",
            },
          },
        }}
      />,
    );
    const phoneLink = screen.getByRole("link", { name: /\(857\) 869-2765/ });
    expect(phoneLink).toHaveAttribute("href", "tel:8578692765");
  });
});
