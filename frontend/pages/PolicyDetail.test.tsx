import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const { pageProps, routerPost } = vi.hoisted(() => {
  return {
    routerPost: vi.fn(),
    pageProps: {
      policy: {
        id: 1,
        title: "Code of conduct",
        summary: "How we work",
        status: {
          code: "published",
          label: "Published",
          tone: "success",
          known: true,
        },
        category: {
          code: "conduct",
          label: "Conduct",
          tone: "neutral",
          known: true,
        },
        scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
        jurisdictionStateCodes: [] as string[],
        versionNumber: 1,
        versionLabel: "v1",
        isMandatory: true,
        publishedAt: "2026-01-01T00:00:00Z",
        detailUrl: "/policies-compliance/1",
        acknowledged: false,
        required: true,
        dueAt: "2026-01-15T00:00:00Z",
        canAcknowledge: true,
        body: "Be professional.",
        documents: [] as {
          id: number;
          role: string;
          displayName: string;
          mediaType: string;
          byteSize: number;
          url: string;
          isReadable: boolean;
        }[],
        contentChecksum: "abc123",
        acknowledgementDisclosure: "I have read and understand this policy.",
        disclosureVersion: 1,
        effectiveAt: null as string | null,
        expiresAt: null as string | null,
        waived: false,
        acknowledgedAt: null as string | null,
        mustOpenDocument: false,
        documentAccessed: true,
      },
      errors: { fields: {}, form: [] as string[] },
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
    router: { post: routerPost, get: vi.fn(), reload: vi.fn() },
    usePage: () => ({ props: pageProps }),
  };
});

import PolicyDetail from "@/pages/PolicyDetail";

describe("PolicyDetail", () => {
  beforeEach(() => {
    pageProps.policy.canAcknowledge = true;
    pageProps.policy.acknowledged = false;
    pageProps.policy.mustOpenDocument = false;
    pageProps.policy.documentAccessed = true;
    pageProps.policy.documents = [];
    routerPost.mockClear();
  });

  it("renders the policy body and acknowledgement disclosure", () => {
    render(<PolicyDetail />);
    expect(
      screen.getByRole("heading", { name: "Code of conduct", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Be professional.")).toBeInTheDocument();
    expect(
      screen.getByText("I have read and understand this policy."),
    ).toBeInTheDocument();
  });

  it("keeps acknowledgement disabled until the reader confirms", async () => {
    const user = userEvent.setup();
    render(<PolicyDetail />);
    const button = screen.getByRole("button", {
      name: "I acknowledge this policy",
    });
    expect(button).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: /I have read this version and confirm the disclosure/i,
      }),
    );
    expect(button).toBeEnabled();
    await user.click(button);
    expect(routerPost).toHaveBeenCalled();
  });

  it("asks the reader to open the document before acknowledging", () => {
    pageProps.policy.mustOpenDocument = true;
    pageProps.policy.documentAccessed = false;
    pageProps.policy.documents = [
      {
        id: 9,
        role: "document",
        displayName: "Handbook.pdf",
        mediaType: "application/pdf",
        byteSize: 1024,
        url: "/policies-compliance/files/9",
        isReadable: true,
      },
    ];
    render(<PolicyDetail />);
    expect(
      screen.getByText(
        "Download the current policy document before acknowledging this version.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "I acknowledge this policy" }),
    ).toBeDisabled();
  });

  it("hides the acknowledge button when canAcknowledge is false", () => {
    pageProps.policy.canAcknowledge = false;
    pageProps.policy.acknowledged = true;
    pageProps.policy.acknowledgedAt = "2026-01-02T00:00:00Z";
    render(<PolicyDetail />);
    expect(
      screen.queryByRole("button", { name: "I acknowledge this policy" }),
    ).not.toBeInTheDocument();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<PolicyDetail />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
