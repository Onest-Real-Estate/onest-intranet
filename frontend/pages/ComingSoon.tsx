import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Construction } from "lucide-react";

import {
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardDescription,
  SurfaceCardHeader,
  SurfaceCardTitle,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { IconWell } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

interface ComingSoonProps extends PageProps {
  title: string;
  section: string;
  administrative?: boolean;
  scope?: {
    level: string;
    label: string;
  };
}

/**
 * Placeholder for registered modules that do not have a domain backend yet.
 * Copy adapts to agent and permission-protected administrative destinations.
 */
export default function ComingSoon() {
  const { title, administrative = false, scope } = usePage<ComingSoonProps>().props;

  return (
    <div className="flex flex-1 items-center justify-center py-8">
      <Head title={title} />
      <SurfaceCard className="w-full max-w-md">
        <SurfaceCardHeader>
          <SurfaceCardTitle asChild className="flex items-center gap-3">
            <h1>
              <IconWell icon={Construction} />
              {title}
            </h1>
          </SurfaceCardTitle>
          <SurfaceCardDescription>
            {administrative
              ? "This administrative module is registered and protected, but it isn’t enabled yet."
              : "We’re still building this part of the hub. It isn’t available yet, and nothing you need to act on is hiding here."}
          </SurfaceCardDescription>
        </SurfaceCardHeader>
        <SurfaceCardContent className="grid gap-4">
          <p className="text-muted-foreground text-sm">
            {administrative
              ? `Your current administrative access is ${scope?.label ?? "scope-limited"}. No records or counts are exposed while this module is unavailable.`
              : "Your transactions, schedule, and action items are on the dashboard in the meantime."}
          </p>
          <Button asChild variant="outline" className="w-fit">
            <Link href={routes.dashboard()}>
              <ArrowLeft className="size-4" strokeWidth={1.5} aria-hidden />
              Back to dashboard
            </Link>
          </Button>
        </SurfaceCardContent>
      </SurfaceCard>
    </div>
  );
}

ComingSoon.layout = (props: ComingSoonProps) =>
  [
    HubLayout,
    {
      context: {
        title: props.title,
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: props.title },
        ],
        back: { label: "Back to dashboard", href: routes.dashboard() },
      },
      variant: "focused",
    },
  ] as const;
