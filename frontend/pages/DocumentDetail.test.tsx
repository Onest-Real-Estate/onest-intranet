import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const { pageProps } = vi.hoisted(() => {
  return {
    pageProps: {
      document: {
        id: 2,
        key: "exclusive-buyer",
        name: "Exclusive buyer agreement",
        description: "Use this form for exclusive buyer representation.",
        status: {
          code: "published",
          label: "Published",
          tone: "success",
          known: true,
        },
        category: {
          code: "buyer",
          label: "Buyer",
          tone: "neutral",
          known: true,
        },
        scope: {
          level: "company",
          label: "Brokerage-wide",
          officeName: "oNEST",
          officeId: "1",
        },
        jurisdictionStateCodes: ["VA"],
        versionNumber: 2,
        versionLabel: "v2",
        effectiveAt: "2026-01-01T00:00:00Z",
        expiresAt: null as string | null,
        publishedAt: "2026-01-01T00:00:00Z",
        fileCount: 1,
        detailUrl: "/documents-forms/2",
        files: [
          {
            id: 9,
            displayName: "buyer-agreement.pdf",
            mediaType: "application/pdf",
            byteSize: 2048,
            checksum: "abc",
            url: "/documents-forms/files/9",
            isReadable: true,
          },
        ],
        superseded: false,
      },
    },
  };
});

vi.mock("@inertiajs/react", async () => {
  const actual =
    await vi.importActual<typeof import("@inertiajs/react")>("@inertiajs/react");
  return {
    ...actual,
    Head: ({ title }: { title: string }) => <title>{title}</title>,
    Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    usePage: () => ({ props: pageProps }),
  };
});

import DocumentDetail from "@/pages/DocumentDetail";

describe("DocumentDetail", () => {
  beforeEach(() => {
    pageProps.document.superseded = false;
  });

  it("renders version, effective date, and a download link", () => {
    render(<DocumentDetail />);
    expect(
      screen.getByRole("heading", { name: "Exclusive buyer agreement" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/v2/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download/ })).toHaveAttribute(
      "href",
      "/documents-forms/files/9",
    );
  });

  it("warns when the bookmarked version was superseded", () => {
    pageProps.document.superseded = true;
    render(<DocumentDetail />);
    expect(
      screen.getByText(/bookmark pointed at a superseded version/i),
    ).toBeInTheDocument();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<DocumentDetail />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
