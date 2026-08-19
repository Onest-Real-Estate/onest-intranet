import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Construction } from "lucide-react";
import type { ReactNode } from "react";

import { HubLayout } from "@/components/HubLayout";
import { IconWell } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <Head title={title} />
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle asChild className="flex items-center gap-3">
            <h1>
              <IconWell icon={Construction} />
              {title}
            </h1>
          </CardTitle>
          <CardDescription>
            {administrative
              ? "This administrative module is registered and protected, but it isn’t enabled yet."
              : "We’re still building this part of the hub. It isn’t available yet, and nothing you need to act on is hiding here."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
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
        </CardContent>
      </Card>
    </div>
  );
}

ComingSoon.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
