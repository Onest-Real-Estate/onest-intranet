import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OfficeResources from "@/pages/OfficeResources";
import type { OfficeResourcesPageProps } from "@/types";

const routerGet = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: OfficeResourcesPageProps;

const baseProps = {
  groups: [
    {
      key: "printer_wifi",
      label: "Printer / Wi-Fi / copier",
      items: [
        {
          slug: "wifi-password",
          title: "Branch Wi-Fi",
          summary: "Ask the front desk.",
          category: "printer_wifi",
          categoryLabel: "Printer / Wi-Fi / copier",
          resourceType: "content",
          sourceLabel: "Company",
          sourceLevel: "company",
          body: "Network: onest-guest",
        },
      ],
    },
    {
      key: "local_forms",
      label: "Local forms",
      items: [
        {
          slug: "packet",
          title: "Local forms packet",
          summary: "",
          category: "local_forms",
          categoryLabel: "Local forms",
          resourceType: "file",
          sourceLabel: "Fairfax VA",
          sourceLevel: "office",
          downloadUrl: "/office-resources/packet/download",
          fileName: "packet.pdf",
        },
        {
          slug: "vendor-site",
          title: "Approved vendors",
          summary: "Ordering portal.",
          category: "local_forms",
          categoryLabel: "Local forms",
          resourceType: "link",
          sourceLabel: "Region",
          sourceLevel: "region",
          url: "https://vendors.example.com",
        },
      ],
    },
  ],
  filters: { q: "", category: "" },
  categories: [
    { value: "printer_wifi", label: "Printer / Wi-Fi / copier" },
    { value: "local_forms", label: "Local forms" },
  ],
  empty: null,
} as unknown as OfficeResourcesPageProps;

describe("OfficeResources", () => {
  beforeEach(() => {
    pageProps = structuredClone(baseProps);
    routerGet.mockClear();
  });

  it("groups resources by category with source labels", () => {
    render(<OfficeResources />);
    expect(screen.getByText("Printer / Wi-Fi / copier")).toBeInTheDocument();
    expect(screen.getByText("Local forms")).toBeInTheDocument();
    expect(screen.getByText("Branch Wi-Fi")).toBeInTheDocument();
    expect(screen.getAllByText("Company")).toHaveLength(1);
    expect(screen.getByText("Fairfax VA")).toBeInTheDocument();
  });

  it("renders content bodies and safe external links", () => {
    render(<OfficeResources />);
    expect(screen.getByText(/onest-guest/)).toBeInTheDocument();
    const external = screen.getByRole("link", { name: /open link/i });
    expect(external).toHaveAttribute("href", "https://vendors.example.com");
    expect(external).toHaveAttribute("target", "_blank");
    expect(external).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("routes file downloads through the authorized endpoint", () => {
    render(<OfficeResources />);
    const download = screen.getByRole("link", { name: /download/i });
    expect(download).toHaveAttribute("href", "/office-resources/packet/download");
    expect(download).toHaveAttribute("download");
  });

  it("pushes search state into the URL", async () => {
    const user = userEvent.setup();
    render(<OfficeResources />);
    await user.type(screen.getByLabelText(/search resources/i), "wifi{Enter}");
    await user.tab();
    expect(routerGet).toHaveBeenCalledWith(
      "/office-resources",
      { q: "wifi" },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  });

  it("shows the no-office empty state with a profile action", () => {
    pageProps = {
      ...baseProps,
      groups: [],
      empty: {
        title: "No office assigned",
        description: "Your profile does not have a primary office yet.",
        kind: "no-office",
      },
    };
    render(<OfficeResources />);
    expect(screen.getByText("No office assigned")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open profile/i })).toHaveAttribute(
      "href",
      "/profile",
    );
  });

  it("shows a no-results empty state", () => {
    pageProps = {
      ...baseProps,
      groups: [],
      filters: { q: "zebra", category: "" },
      empty: {
        title: "No resources found",
        description: "Nothing matches your search.",
        kind: "no-results",
      },
    };
    render(<OfficeResources />);
    expect(screen.getByText("No resources found")).toBeInTheDocument();
  });

  it("shows an empty state when an office has no resources", () => {
    pageProps = {
      ...baseProps,
      groups: [],
      empty: {
        title: "No resources yet",
        description: "Your office has no published resources yet.",
        kind: "empty",
      },
    };
    render(<OfficeResources />);
    expect(screen.getByText("No resources yet")).toBeInTheDocument();
  });
});
