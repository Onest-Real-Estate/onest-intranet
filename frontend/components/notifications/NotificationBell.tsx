import { Link } from "@inertiajs/react";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { unreadAnnouncement, unreadBadgeLabel } from "@/lib/notifications";
import { routes } from "@/lib/routes";
import type { NotificationShell } from "@/types";

/** How often the header re-asks for its own count, in milliseconds. */
export const POLL_INTERVAL_MS = 60_000;

/**
 * The header's unread badge and the way into the notification centre.
 *
 * The count arrives with the page as a shared prop, so the first paint is
 * already correct and never flashes a zero. After that the bell re-asks the
 * server on an interval — the same shape a websocket would slot into later,
 * with the same accessible announcement: the number is exposed as text in the
 * control's label and mirrored into a polite live region, so a screen-reader
 * user hears "3 unread notifications" rather than nothing at all.
 *
 * Polling pauses while the tab is hidden, and a failed poll keeps the last
 * known figure rather than blanking the badge: a stale count is useful, and a
 * count that disappears when the network hiccups is not.
 */
export function NotificationBell({ summary }: { summary: NotificationShell | null }) {
  const [counts, setCounts] = useState({
    unread: summary?.unreadCount ?? 0,
    mandatory: summary?.mandatoryCount ?? 0,
  });
  const [stale, setStale] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const lastAnnounced = useRef(summary?.unreadCount ?? 0);

  const serverUnread = summary?.unreadCount ?? 0;
  const serverMandatory = summary?.mandatoryCount ?? 0;

  // A completed Inertia visit carries a fresh count with it; trust it over
  // whatever the last poll produced.
  useEffect(() => {
    setCounts({ unread: serverUnread, mandatory: serverMandatory });
    setStale(false);
  }, [serverUnread, serverMandatory]);

  useEffect(() => {
    if (!summary) {
      return;
    }
    let cancelled = false;

    async function poll() {
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      try {
        const response = await fetch(routes.notification_summary(), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Unexpected status ${response.status}`);
        }
        const payload = (await response.json()) as {
          unreadCount?: number;
          mandatoryCount?: number;
        };
        if (cancelled) {
          return;
        }
        setCounts({
          unread: Number(payload.unreadCount ?? 0),
          mandatory: Number(payload.mandatoryCount ?? 0),
        });
        setStale(false);
      } catch {
        if (!cancelled) {
          setStale(true);
        }
      }
    }

    const timer = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [summary]);

  useEffect(() => {
    if (counts.unread === lastAnnounced.current) {
      return;
    }
    lastAnnounced.current = counts.unread;
    setAnnouncement(unreadAnnouncement(counts.unread, counts.mandatory));
  }, [counts]);

  if (!summary) {
    return null;
  }

  const badge = unreadBadgeLabel(counts.unread);
  const label = unreadAnnouncement(counts.unread, counts.mandatory);
  const tooltip = stale ? "Notifications — count may be out of date" : "Notifications";

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-foreground relative size-9"
          >
            <Link
              href={summary.href}
              aria-label={label}
              data-stale={stale || undefined}
            >
              <Bell className="size-5" strokeWidth={1.5} aria-hidden />
              {badge ? (
                <span
                  aria-hidden
                  className="bg-destructive text-destructive-foreground absolute top-1 right-0.5 grid min-w-4 place-items-center rounded-full px-1 text-[0.625rem] leading-4 font-semibold tabular-nums"
                >
                  {badge}
                </span>
              ) : null}
            </Link>
          </Button>
        </TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </>
  );
}
