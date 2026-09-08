import {
  ArrowRight,
  ChevronDown,
  SquareArrowOutUpRight,
  TriangleAlert,
  Unplug,
} from "lucide-react";
import { useId, useState } from "react";
import { brandMark } from "@/components/BrandMarks";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { IconWell } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  QUICK_ACCESS_COLLAPSED_LIMIT,
  type QuickAppStatus,
  quickAppStatus,
  reportQuickAppClick,
} from "@/lib/quick-access";
import { quickAccessIcon } from "@/lib/quick-access-icons";
import type { DashboardQuickApp } from "@/types";

/**
 * Vendor launchers, as a panel beside the news band.
 *
 * The rows are administered data (`P1-025`): an administrator decides what
 * appears here, in what order, and for which offices and roles, and the server
 * has already resolved all of that by the time this component runs. Nothing
 * about the audience is decided in the browser — a link this reader may not
 * see never arrives, rather than arriving and being hidden with CSS.
 *
 * The mark comes from the link's approved icon key rather than from a guess at
 * the vendor's name, so the row is scannable by shape before anyone reads a
 * label. Microsoft is the one vendor whose real mark the app ships, so it uses
 * that rather than an impression of it.
 */
export function QuickApps({
  apps,
  csrfToken = "",
  truncated = false,
}: {
  apps: DashboardQuickApp[];
  /** Passed down rather than read from the page, so the panel stays pure. */
  csrfToken?: string;
  /** The server's own cap bit. See the registry's `feed_limit`. */
  truncated?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();

  const collapsible = apps.length > QUICK_ACCESS_COLLAPSED_LIMIT;
  const visible =
    collapsible && !expanded ? apps.slice(0, QUICK_ACCESS_COLLAPSED_LIMIT) : apps;

  return (
    <SurfaceCard className="arrive h-full">
      <PanelHeader title="Quick access" />
      <SurfaceCardContent className="flex flex-1 flex-col gap-3">
        {/* One column: the launchers sit in the narrow third of the top band,
            where two labels side by side would both truncate. */}
        <ul id={listId} className="grid flex-1 auto-rows-fr grid-cols-1 gap-3">
          {visible.map((app) => (
            <li key={app.id} className="min-w-0">
              <QuickAppRow app={app} csrfToken={csrfToken} />
            </li>
          ))}
        </ul>
        {collapsible ? (
          <Button
            variant="ghost"
            size="sm"
            className="self-start"
            aria-expanded={expanded}
            aria-controls={listId}
            onClick={() => setExpanded((open) => !open)}
          >
            <ChevronDown
              className={
                expanded ? "rotate-180 transition-transform" : "transition-transform"
              }
              aria-hidden
            />
            {expanded ? "Show fewer tools" : `View all ${apps.length} tools`}
          </Button>
        ) : null}
        {truncated ? (
          // The server capped the payload. Saying so beats a panel that
          // quietly omits a tool the reader was told they had.
          <p className="text-muted-foreground text-xs">
            Showing the first {apps.length} tools. Ask an administrator if one is
            missing.
          </p>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

/** The shared inside of a row, whether or not that row is a link. */
function QuickAppBody({
  app,
  status,
}: {
  app: DashboardQuickApp;
  status: QuickAppStatus;
}) {
  // A vendor whose official artwork ships draws that; everyone else draws the
  // approved category glyph.
  const brand = brandMark(app.icon);
  const Icon = brand ? undefined : quickAccessIcon(app.icon);
  const secondLine = status.state === "ready" ? app.description : status.label;

  return (
    <>
      {brand?.bleed ? (
        // The mark carries its own background, so it *is* the tile. Nesting it
        // in the tinted well would put two squares inside each other.
        <brand.Component className="size-9 shrink-0 rounded-md object-contain" />
      ) : (
        <IconWell
          icon={Icon}
          tone={status.state === "unavailable" ? "muted" : "brand"}
          className="size-9 shrink-0"
        >
          {brand ? <brand.Component className="size-[1.125rem]" /> : null}
        </IconWell>
      )}
      {/* Two short lines beat "Micros…" in a half-width tile. A long name
          wraps to two lines and then clips, so one verbose tool cannot push
          the rest of the panel out of shape. */}
      <span className="min-w-0 flex-1 text-sm leading-tight font-medium">
        <span className="line-clamp-2 break-words">{app.name}</span>
        {secondLine ? (
          <span
            className={
              status.state === "degraded" || status.state === "unavailable"
                ? "text-warning-ink mt-0.5 block truncate text-xs font-normal"
                : "text-muted-foreground mt-0.5 block truncate text-xs font-normal"
            }
          >
            {secondLine}
          </span>
        ) : null}
        {status.announcement ? (
          <span className="sr-only"> {status.announcement}</span>
        ) : null}
      </span>
    </>
  );
}

const ROW_CLASS =
  "flex h-full items-center gap-3 rounded-lg border px-3 py-2 transition-colors duration-(--motion-fast)";

function QuickAppRow({
  app,
  csrfToken,
}: {
  app: DashboardQuickApp;
  csrfToken: string;
}) {
  const status = quickAppStatus(app);

  // An offline integration is not a launcher. Rendering it as a link that
  // lands on an error page would be worse than saying so here, and a disabled
  // link is not a thing HTML has — so the row simply stops being one, and
  // keyboard users tab past it instead of into a dead end.
  if (status.state === "unavailable") {
    return (
      <div className={`${ROW_CLASS} border-dashed opacity-80`} data-state="unavailable">
        <QuickAppBody app={app} status={status} />
        <Unplug
          className="text-muted-foreground size-4 shrink-0"
          strokeWidth={1.5}
          aria-hidden
        />
      </div>
    );
  }

  // Product rule: an external tool opens in a new tab so the hub session is
  // not navigated away from, an internal destination navigates in place.
  // `noopener noreferrer` on every new tab — the opener reference and the
  // referrer are both things a third-party tool has no business receiving.
  const external = app.external;

  return (
    <a
      href={app.href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      onClick={() => reportQuickAppClick(app, csrfToken)}
      data-state={status.state}
      className={`${ROW_CLASS} hover:border-primary/30 hover:bg-muted/40 focus-visible:ring-ring focus-visible:ring-offset-background group focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none`}
    >
      <QuickAppBody app={app} status={status} />
      {status.state === "degraded" ? (
        <TriangleAlert
          className="text-warning-ink size-4 shrink-0"
          strokeWidth={1.5}
          aria-hidden
        />
      ) : null}
      {external ? (
        <SquareArrowOutUpRight
          className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors duration-(--motion-fast)"
          strokeWidth={1.5}
          aria-hidden
        />
      ) : (
        <ArrowRight
          className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors duration-(--motion-fast)"
          strokeWidth={1.5}
          aria-hidden
        />
      )}
      {external ? <span className="sr-only"> (opens in a new tab)</span> : null}
    </a>
  );
}

export function QuickAppsSkeleton() {
  return (
    <SurfaceCard state="loading" className="h-full">
      <PanelHeader title="Quick access" />
      <SurfaceCardContent className="flex flex-1 flex-col">
        <div className="grid flex-1 auto-rows-fr grid-cols-1 gap-3">
          {["a1", "a2", "a3", "a4"].map((id) => (
            <Skeleton key={id} className="h-13 rounded-lg" />
          ))}
        </div>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
