import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import TrainingDetail from "@/pages/TrainingDetail";

vi.mock("@inertiajs/react", async () => {
  const actual =
    await vi.importActual<typeof import("@inertiajs/react")>("@inertiajs/react");
  return {
    ...actual,
    Head: ({ title }: { title: string }) => <title>{title}</title>,
    Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    usePage: () => ({
      props: {
        content: {
          id: 1,
          slug: "ethics",
          title: "Ethics overview",
          summary: "Annual ethics training",
          body: "Training body",
          bodyBlocks: [
            {
              type: "paragraph",
              spans: [{ type: "text", value: "Training body" }],
            },
          ],
          contentType: {
            code: "article",
            label: "Article",
            tone: "neutral",
            known: true,
          },
          category: {
            code: "ethics",
            label: "Ethics",
            tone: "neutral",
            known: true,
          },
          scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
          isRequired: true,
          estimatedMinutes: 15,
          toolCode: null,
          completion: { status: "not_started", label: "Not started" },
          publishedAt: "2026-01-01T00:00:00Z",
          detailUrl: "/training-learning/1",
          externalUrl: {
            url: "https://example.com/resource",
            label: "Open resource",
          },
          embed: null,
          primaryMedia: null,
          attachments: [],
          transcription: null,
          modules: [],
          interactivity: "available",
        },
      },
    }),
  };
});

describe("TrainingDetail", () => {
  it("renders the article body and external link", () => {
    render(<TrainingDetail />);
    expect(
      screen.getByRole("heading", { name: "Ethics overview", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Training body")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open resource" })).toHaveAttribute(
      "href",
      "https://example.com/resource",
    );
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<TrainingDetail />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
