import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnnouncementSourceArticlePanel } from "@/components/announcements/AnnouncementSourceArticlePanel";
import type { AnnouncementArticleSuggestions } from "@/types";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

function suggestions(
  overrides: Partial<AnnouncementArticleSuggestions> = {},
): AnnouncementArticleSuggestions {
  return {
    sourceUrl: "https://news.example/rates",
    publisher: "Market Desk",
    title: "Rates hold steady this week",
    description: "Mortgage averages were unchanged Friday.",
    imageUrl: "https://cdn.example/hero.jpg",
    hasExtractableText: true,
    extractToken: "tok123",
    textBasis: "extract",
    retrievedAt: "2026-09-17T12:00:00Z",
    limitations: ["Metadata and extracted text are unverified suggestions."],
    aiConfigured: true,
    ...overrides,
  };
}

describe("AnnouncementSourceArticlePanel", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    document.cookie = "XSRF-TOKEN=test-token";
  });

  it("fetches suggestions and applies title only when asked", async () => {
    const onChange = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ suggestions: suggestions() }),
    });

    render(
      <AnnouncementSourceArticlePanel
        announcementId={1}
        draft={{
          sourceUrl: "https://news.example/rates",
          sourcePublisher: "",
          sourceRetrievedAt: "",
          title: "My existing title",
          summary: "Mine",
          body: "Body",
          ctaLabel: "",
          ctaUrl: "",
          aiAssistedSummary: false,
          aiAssistedBody: false,
        }}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /fetch article details/i }));

    await waitFor(() => {
      expect(screen.getByText("Rates hold steady this week")).toBeInTheDocument();
    });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceUrl: "https://news.example/rates",
        sourcePublisher: "Market Desk",
      }),
    );
    // Title must not change until Use as title.
    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: "Rates hold steady this week" }),
    );

    fireEvent.click(screen.getByRole("button", { name: /use as title/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Rates hold steady this week" }),
    );
  });

  it("disables generate summary when extract text is missing", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        suggestions: suggestions({
          hasExtractableText: false,
          textBasis: "metadata",
        }),
      }),
    });

    render(
      <AnnouncementSourceArticlePanel
        announcementId={null}
        draft={{
          sourceUrl: "https://news.example/thin",
          sourcePublisher: "",
          sourceRetrievedAt: "",
          title: "",
          summary: "",
          body: "",
          ctaLabel: "",
          ctaUrl: "",
          aiAssistedSummary: false,
          aiAssistedBody: false,
        }}
        onChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /fetch article details/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate summary/i })).toBeDisabled();
    });
    expect(screen.getByText(/not enough readable text for ai/i)).toBeInTheDocument();
    expect(screen.getByText(/save the draft first/i)).toBeInTheDocument();
  });

  it("surfaces fetch errors accessibly", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        validation: { form: ["That page is blocked or requires a login."], fields: {} },
      }),
    });

    render(
      <AnnouncementSourceArticlePanel
        announcementId={1}
        draft={{
          sourceUrl: "https://news.example/paywall",
          sourcePublisher: "",
          sourceRetrievedAt: "",
          title: "",
          summary: "",
          body: "",
          ctaLabel: "",
          ctaUrl: "",
          aiAssistedSummary: false,
          aiAssistedBody: false,
        }}
        onChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /fetch article details/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /blocked or requires a login/i,
      );
    });
  });
});
