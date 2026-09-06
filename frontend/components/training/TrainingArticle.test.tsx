import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TrainingArticle } from "@/components/training/TrainingArticle";
import type { TrainingDetail } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    post: vi.fn(),
  },
}));

const baseContent: TrainingDetail = {
  id: 1,
  slug: "ethics",
  title: "Ethics overview",
  summary: "Annual ethics training",
  body: "",
  bodyBlocks: [],
  contentType: { code: "article", label: "Article", tone: "neutral", known: true },
  category: { code: "ethics", label: "Ethics", tone: "neutral", known: true },
  scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
  isRequired: true,
  estimatedMinutes: 15,
  toolCode: null,
  completion: { status: "not_started", label: "Not started" },
  publishedAt: "2026-01-01T00:00:00Z",
  detailUrl: "/training-learning/1",
  externalUrl: null,
  embed: null,
  primaryMedia: null,
  attachments: [],
  transcription: null,
  modules: [],
  interactivity: "available",
  canMarkStarted: true,
  canMarkComplete: true,
};

describe("TrainingArticle", () => {
  it("shows an embed-unavailable fallback", () => {
    render(
      <TrainingArticle
        content={{
          ...baseContent,
          embed: {
            url: "https://example.com/bad",
            provider: "other",
            host: "example.com",
            available: false,
          },
        }}
      />,
    );
    expect(screen.getByText("Video unavailable")).toBeInTheDocument();
  });

  it("shows a processing fallback for unreadable primary media", () => {
    render(
      <TrainingArticle
        content={{
          ...baseContent,
          primaryMedia: {
            id: 9,
            role: "primary",
            displayName: "Recording.mp4",
            mediaType: "video/mp4",
            byteSize: 100,
            url: "",
            processingState: "pending",
            isReadable: false,
          },
        }}
      />,
    );
    expect(screen.getByText("Media is still processing")).toBeInTheDocument();
  });

  it("shows progress actions for passive content", () => {
    render(<TrainingArticle content={baseContent} />);
    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark complete" })).toBeInTheDocument();
  });

  it("shows the unconfigured interactive placeholder for quizzes", () => {
    render(
      <TrainingArticle
        content={{
          ...baseContent,
          contentType: { code: "quiz", label: "Quiz", tone: "info", known: true },
          interactivity: "unavailable",
          canMarkComplete: false,
        }}
      />,
    );
    expect(screen.getByText("Interactive content not configured")).toBeInTheDocument();
  });

  it("renders a configured quiz", () => {
    render(
      <TrainingArticle
        content={{
          ...baseContent,
          contentType: { code: "quiz", label: "Quiz", tone: "info", known: true },
          canMarkComplete: false,
          quiz: {
            passThresholdPercent: 80,
            maxAttempts: 3,
            feedbackPolicy: "score_only",
            attemptCount: 0,
            attemptsRemaining: 3,
            canAttempt: true,
            latestAttempt: null,
            questions: [
              {
                id: 10,
                prompt: "What is fair housing?",
                choices: [
                  { id: "a", label: "Correct answer" },
                  { id: "b", label: "Wrong answer" },
                ],
                sortOrder: 0,
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText(/What is fair housing\?/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit answers" })).toBeInTheDocument();
  });
});
