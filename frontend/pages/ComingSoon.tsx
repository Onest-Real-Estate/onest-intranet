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
}

/**
 * Placeholder for the hub sections that have no backend yet. Seven of the
 * eleven nav items land here, so it is the second most visited screen in the
 * product and is written for agents rather than for the team building it.
 */
export default function ComingSoon() {
  const { title } = usePage<ComingSoonProps>().props;

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
            We&apos;re still building this part of the hub. It isn&apos;t available yet,
            and nothing you need to act on is hiding here.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <p className="text-muted-foreground text-sm">
            Your transactions, schedule, and action items are on the dashboard in the
            meantime.
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
