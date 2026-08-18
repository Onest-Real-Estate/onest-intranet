import { Head, usePage } from "@inertiajs/react";
import { Construction } from "lucide-react";
import type { ReactNode } from "react";

import { HubLayout } from "@/components/HubLayout";
import { IconWell } from "@/components/IconWell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { PageProps } from "@/types";

interface ComingSoonProps extends PageProps {
  title: string;
  section: string;
}

export default function ComingSoon() {
  const { title } = usePage<ComingSoonProps>().props;

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <Head title={title} />
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            <IconWell icon={Construction} />
            {title}
          </CardTitle>
          <CardDescription>
            This section of ONEST HUB is not wired up yet. Dummy dashboard data lives on
            the home screen until these tools have real backends.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Check back after the next release.
        </CardContent>
      </Card>
    </div>
  );
}

ComingSoon.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
