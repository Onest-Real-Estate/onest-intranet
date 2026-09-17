/**
 * Optional source-article URL fetch, reviewable suggestions, AI digest, and
 * hero import controls for the announcement workspace.
 *
 * Suggestions never overwrite draft fields silently — each accept is explicit.
 * Fetch and AI are deliberate actions; save/publish never trigger them.
 */

import { Link } from "@inertiajs/react";
import { Images, Newspaper, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { routes } from "@/lib/routes";
import type {
  AnnouncementArticleAiSummary,
  AnnouncementArticleSuggestions,
} from "@/types";

function readCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function postJson<T>(
  url: string,
  body: Record<string, string>,
): Promise<{ ok: true; data: T } | { ok: false; message: string }> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": readCsrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(body),
  });
  let payload: {
    suggestions?: AnnouncementArticleSuggestions;
    summary?: AnnouncementArticleAiSummary;
    media?: unknown;
    validation?: { form?: string[]; fields?: Record<string, string[]> };
  } = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    const fieldMessages = Object.values(payload.validation?.fields ?? {}).flat();
    const message =
      payload.validation?.form?.[0] ||
      fieldMessages[0] ||
      "That request could not be completed.";
    return { ok: false, message };
  }
  return { ok: true, data: payload as T };
}

export interface SourceArticleDraftSlice {
  sourceUrl: string;
  sourcePublisher: string;
  sourceRetrievedAt: string;
  title: string;
  summary: string;
  body: string;
  ctaLabel: string;
  ctaUrl: string;
  aiAssistedSummary: boolean;
  aiAssistedBody: boolean;
}

export function AnnouncementSourceArticlePanel({
  announcementId,
  draft,
  onChange,
}: {
  announcementId: number | null;
  draft: SourceArticleDraftSlice;
  onChange: (patch: Partial<SourceArticleDraftSlice>) => void;
}) {
  const [fetching, setFetching] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<AnnouncementArticleSuggestions | null>(
    null,
  );
  const [aiSummary, setAiSummary] = useState<AnnouncementArticleAiSummary | null>(null);
  const [undo, setUndo] = useState<SourceArticleDraftSlice | null>(null);

  function snapshot(): SourceArticleDraftSlice {
    return { ...draft };
  }

  async function fetchDetails() {
    setNotice(null);
    setAiSummary(null);
    setFetching(true);
    const result = await postJson<{ suggestions: AnnouncementArticleSuggestions }>(
      routes.announcement_article_fetch(),
      { url: draft.sourceUrl },
    );
    setFetching(false);
    if (!result.ok) {
      setSuggestions(null);
      setNotice(result.message);
      return;
    }
    setSuggestions(result.data.suggestions);
    onChange({
      sourceUrl: result.data.suggestions.sourceUrl,
      sourcePublisher: result.data.suggestions.publisher,
      sourceRetrievedAt: result.data.suggestions.retrievedAt,
    });
  }

  async function generateSummary() {
    if (!suggestions?.extractToken) {
      return;
    }
    setNotice(null);
    setSummarizing(true);
    const result = await postJson<{ summary: AnnouncementArticleAiSummary }>(
      routes.announcement_article_summarize(),
      { extract_token: suggestions.extractToken },
    );
    setSummarizing(false);
    if (!result.ok) {
      setAiSummary(null);
      setNotice(result.message);
      return;
    }
    setAiSummary(result.data.summary);
  }

  async function importHero() {
    if (!announcementId || !suggestions?.imageUrl) {
      return;
    }
    setNotice(null);
    setImporting(true);
    const result = await postJson<{ media: unknown }>(
      routes.announcement_article_import_hero(announcementId),
      { image_url: suggestions.imageUrl },
    );
    setImporting(false);
    if (!result.ok) {
      setNotice(result.message);
      return;
    }
    setNotice(
      "Hero import queued. Open Hero & files to confirm processing finished before publishing.",
    );
  }

  function applyField(
    field: "title" | "summary" | "descriptionAsSummary" | "cta" | "source",
  ) {
    if (!suggestions) {
      return;
    }
    if (!undo) {
      setUndo(snapshot());
    }
    if (field === "title" && suggestions.title) {
      onChange({ title: suggestions.title });
    }
    if (field === "summary" && suggestions.description) {
      onChange({ summary: suggestions.description.slice(0, 280) });
    }
    if (field === "descriptionAsSummary" && suggestions.description) {
      onChange({ summary: suggestions.description.slice(0, 280) });
    }
    if (field === "cta") {
      onChange({
        ctaLabel: draft.ctaLabel || "Read original article",
        ctaUrl: draft.ctaUrl || suggestions.sourceUrl,
      });
    }
    if (field === "source") {
      onChange({
        sourceUrl: suggestions.sourceUrl,
        sourcePublisher: suggestions.publisher,
        sourceRetrievedAt: suggestions.retrievedAt,
      });
    }
  }

  function applyAi(kind: "teaser" | "digest" | "both") {
    if (!aiSummary) {
      return;
    }
    if (!undo) {
      setUndo(snapshot());
    }
    const patch: Partial<SourceArticleDraftSlice> = {};
    if (kind === "teaser" || kind === "both") {
      patch.summary = aiSummary.teaser.slice(0, 280);
      patch.aiAssistedSummary = true;
    }
    if (kind === "digest" || kind === "both") {
      patch.body = aiSummary.digest;
      patch.aiAssistedBody = true;
    }
    onChange(patch);
  }

  function restoreUndo() {
    if (!undo) {
      return;
    }
    onChange(undo);
    setUndo(null);
  }

  return (
    <SurfaceCard>
      <PanelHeader
        divided
        title="Source article"
        description="Optional. Fetch public HTTPS metadata for review — nothing is published until you save and publish deliberately."
      />
      <SurfaceCardContent className="grid gap-5">
        <FormField>
          <FormLabel htmlFor="source_url" optional>
            Source article URL
          </FormLabel>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="source_url"
              type="url"
              inputMode="url"
              value={draft.sourceUrl}
              onChange={(event) =>
                onChange({
                  sourceUrl: event.target.value,
                  sourcePublisher: event.target.value ? draft.sourcePublisher : "",
                  sourceRetrievedAt: event.target.value ? draft.sourceRetrievedAt : "",
                })
              }
              placeholder="https://"
              className="flex-1"
            />
            <Button
              type="button"
              variant="secondary"
              disabled={fetching || !draft.sourceUrl.trim()}
              aria-busy={fetching || undefined}
              onClick={() => void fetchDetails()}
            >
              <Newspaper className="size-4" aria-hidden />
              {fetching ? "Fetching…" : "Fetch article details"}
            </Button>
          </div>
          <FormDescription>
            Keep this separate from the call-to-action button. Publisher attribution
            uses this URL for readers.
          </FormDescription>
          {draft.sourcePublisher ? (
            <p className="text-muted-foreground text-sm">
              Publisher: {draft.sourcePublisher}
            </p>
          ) : null}
        </FormField>

        {notice ? (
          <p role="alert" className="text-destructive text-sm">
            {notice}
          </p>
        ) : null}

        {suggestions ? (
          <div className="border-border/60 grid gap-4 rounded-lg border p-4">
            <div className="grid gap-1">
              <p className="text-sm font-semibold">Fetched suggestions</p>
              <p className="text-muted-foreground text-xs">
                Metadata is unverified. Applying a value never happens silently — use
                the buttons below, or Undo last apply.
              </p>
            </div>
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="text-muted-foreground text-xs uppercase">Publisher</dt>
                <dd>{suggestions.publisher || "Not found"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs uppercase">Headline</dt>
                <dd>{suggestions.title || "Not found"}</dd>
                {suggestions.title ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-1"
                    onClick={() => applyField("title")}
                  >
                    Use as title
                  </Button>
                ) : null}
              </div>
              <div>
                <dt className="text-muted-foreground text-xs uppercase">Description</dt>
                <dd>{suggestions.description || "Not found"}</dd>
                {suggestions.description ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-1"
                    onClick={() => applyField("summary")}
                  >
                    Use as summary
                  </Button>
                ) : null}
              </div>
              <div>
                <dt className="text-muted-foreground text-xs uppercase">Image</dt>
                <dd className="break-all">
                  {suggestions.imageUrl ? (
                    <span className="text-muted-foreground">
                      Candidate URL on {new URL(suggestions.imageUrl).hostname} —
                      confirm licensing before importing. Not shown as a hotlink.
                    </span>
                  ) : (
                    "Not found"
                  )}
                </dd>
                {suggestions.imageUrl ? (
                  announcementId ? (
                    <div className="mt-1 flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={importing}
                        aria-busy={importing || undefined}
                        onClick={() => void importHero()}
                      >
                        <Images className="size-3.5" aria-hidden />
                        {importing ? "Importing…" : "Import as hero"}
                      </Button>
                      <Button type="button" size="sm" variant="ghost" asChild>
                        <Link href={routes.announcement_media_manager(announcementId)}>
                          Open Hero &amp; files
                        </Link>
                      </Button>
                    </div>
                  ) : (
                    <FormDescription className="mt-1">
                      Save the draft first, then import the candidate as a hero.
                    </FormDescription>
                  )
                ) : null}
              </div>
            </dl>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => applyField("cta")}
              >
                Set CTA “Read original article”
              </Button>
              {undo ? (
                <Button type="button" size="sm" variant="ghost" onClick={restoreUndo}>
                  Undo last apply
                </Button>
              ) : null}
            </div>
            {suggestions.limitations.length > 0 ? (
              <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-xs">
                {suggestions.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}

            <div className="border-border/40 grid gap-2 border-t pt-4">
              <p className="text-sm font-semibold">AI summary</p>
              <FormDescription>
                Opt-in only. Uses extracted article text when enough was retrieved —
                never metadata alone, and never on save or publish.
              </FormDescription>
              <Button
                type="button"
                variant="secondary"
                disabled={
                  summarizing ||
                  !suggestions.hasExtractableText ||
                  !suggestions.aiConfigured
                }
                aria-busy={summarizing || undefined}
                onClick={() => void generateSummary()}
              >
                <Sparkles className="size-4" aria-hidden />
                {summarizing ? "Generating…" : "Generate summary"}
              </Button>
              {!suggestions.hasExtractableText ? (
                <FormFieldError message="Not enough readable text for AI. Write the teaser and body manually." />
              ) : null}
              {suggestions.hasExtractableText && !suggestions.aiConfigured ? (
                <FormFieldError message="AI summaries are not configured on this environment." />
              ) : null}
              {aiSummary ? (
                <div className="grid gap-3 rounded-md border p-3 text-sm">
                  <p className="text-muted-foreground text-xs">{aiSummary.label}</p>
                  <div>
                    <p className="font-medium">
                      Teaser ({aiSummary.guides.teaserChars} chars)
                    </p>
                    <p>{aiSummary.teaser}</p>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="mt-1"
                      onClick={() => applyAi("teaser")}
                    >
                      Use as summary
                    </Button>
                  </div>
                  <div>
                    <p className="font-medium">
                      Digest ({aiSummary.guides.digestWords} words)
                    </p>
                    <p>{aiSummary.digest}</p>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="mt-1"
                      onClick={() => applyAi("digest")}
                    >
                      Use as body
                    </Button>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => applyAi("both")}
                  >
                    Use teaser and digest
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
