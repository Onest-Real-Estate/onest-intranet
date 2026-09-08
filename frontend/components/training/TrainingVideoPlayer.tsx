import { useMemo, useState } from "react";

import { SearchControl } from "@/components/design-system";
import type { TrainingEmbed, TrainingTranscription } from "@/types";

/**
 * Build a provider embed URL. YouTube Error 153 ("Video player configuration
 * error") appears when the player request lacks a usable Referer; the iframe
 * also needs enablejsapi + origin for transcript seek postMessages.
 */
function providerEmbedUrl(embed: TrainingEmbed, pageOrigin: string): string {
  if (embed.provider === "youtube") {
    const match = embed.url.match(/(?:v=|youtu\.be\/)([\w-]+)/);
    const id = match?.[1];
    if (id) {
      const params = new URLSearchParams({ enablejsapi: "1" });
      if (pageOrigin.startsWith("http")) {
        params.set("origin", pageOrigin);
      }
      return `https://www.youtube.com/embed/${id}?${params.toString()}`;
    }
  }
  if (embed.provider === "vimeo") {
    const match = embed.url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
    const id = match?.[1];
    if (id) {
      return `https://player.vimeo.com/video/${id}`;
    }
  }
  return embed.url;
}

export function TrainingVideoPlayer({
  embed,
  transcription,
}: {
  embed: TrainingEmbed;
  transcription: TrainingTranscription | null;
}) {
  const [query, setQuery] = useState("");
  const segments = transcription?.segments ?? [];
  const pageOrigin = typeof window !== "undefined" ? window.location.origin : "";
  const embedSrc = useMemo(
    () => providerEmbedUrl(embed, pageOrigin),
    [embed, pageOrigin],
  );

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) {
      return segments;
    }
    return segments.filter((segment) => segment.text.toLowerCase().includes(term));
  }, [query, segments]);

  function seekTo(startMs: number) {
    const iframe = document.getElementById(
      "training-video-embed",
    ) as HTMLIFrameElement | null;
    if (!iframe?.contentWindow) {
      return;
    }
    const seconds = Math.floor(startMs / 1000);
    if (embed.provider === "youtube") {
      iframe.contentWindow.postMessage(
        JSON.stringify({ event: "command", func: "seekTo", args: [seconds, true] }),
        "*",
      );
      return;
    }
    if (embed.provider === "vimeo") {
      iframe.contentWindow.postMessage(
        JSON.stringify({ method: "setCurrentTime", value: seconds }),
        "*",
      );
    }
  }

  return (
    <div className="grid gap-4">
      <div className="aspect-video overflow-hidden rounded-lg border bg-muted">
        <iframe
          id="training-video-embed"
          title="Training video"
          src={embedSrc}
          className="size-full"
          referrerPolicy="strict-origin-when-cross-origin"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
      {segments.length > 0 || transcription?.hasSearchableText ? (
        <section aria-labelledby="training-transcript" className="grid gap-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="training-transcript" className="text-base font-semibold">
              Transcript
            </h2>
            <SearchControl
              value={query}
              onValueChange={setQuery}
              label="Search transcript"
              placeholder="Search transcript"
              className="max-w-sm"
            />
          </div>
          <ol className="grid max-h-80 gap-2 overflow-y-auto rounded-lg border p-3 text-sm">
            {matches.length === 0 ? (
              <li className="text-muted-foreground">
                {segments.length === 0
                  ? "Transcript text is not available yet."
                  : "No transcript matches."}
              </li>
            ) : (
              matches.map((segment) => (
                <li key={`${segment.startMs}-${segment.endMs}`}>
                  <button
                    type="button"
                    className="hover:bg-muted focus-visible:ring-ring w-full rounded-md px-2 py-1.5 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
                    onClick={() => seekTo(segment.startMs)}
                  >
                    <span className="text-muted-foreground mr-2 tabular-nums">
                      {formatTimestamp(segment.startMs)}
                    </span>
                    {segment.text}
                  </button>
                </li>
              ))
            )}
          </ol>
          <p className="text-muted-foreground text-xs" role="note">
            Click a line to jump to that moment when the provider allows seeking.
          </p>
        </section>
      ) : null}
    </div>
  );
}

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
