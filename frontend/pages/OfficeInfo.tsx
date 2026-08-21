import { Head, Link, usePage } from "@inertiajs/react";
import { Building2 } from "lucide-react";
import {
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { OfficeInfoPanel } from "@/components/office/OfficeInfoPanel";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { OfficeInfoPageProps } from "@/types";

/**
 * Agent-facing office brochure for the signed-in user's primary office.
 */
export default function OfficeInfo() {
  const { officeInfo, empty } = usePage<OfficeInfoPageProps>().props;

  return (
    <div className="grid gap-10">
      <Head title="Office info" />
      <PageHeader
        title="Office info"
        description="Where you work, who supports the branch, and how to get in."
      />
      {officeInfo ? (
        <OfficeInfoPanel info={officeInfo} />
      ) : (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4 py-10 text-center">
            <Building2 className="text-muted-foreground mx-auto size-10" aria-hidden />
            <div className="grid gap-2">
              <h2 className="text-foreground text-lg font-semibold">
                {empty?.title ?? "No office assigned"}
              </h2>
              <p className="text-muted-foreground mx-auto max-w-md text-sm">
                {empty?.description ??
                  "Your profile does not have a primary office yet."}
              </p>
            </div>
            <Button asChild variant="outline" className="mx-auto w-fit">
              <Link href={routes.profile()}>Open profile</Link>
            </Button>
          </SurfaceCardContent>
        </SurfaceCard>
      )}
    </div>
  );
}

OfficeInfo.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Office info",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Office info" },
        ],
      },
    },
  ] as const;
