import { Head, Link, usePage } from "@inertiajs/react";
import { Building2 } from "lucide-react";
import { EmptyState, PageHeader, SurfaceCard } from "@/components/design-system";
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
          <EmptyState
            icon={Building2}
            title={empty?.title ?? "No office assigned"}
            description={
              empty?.description ?? "Your profile does not have a primary office yet."
            }
            actions={
              <Button asChild variant="outline">
                <Link href={routes.profile()}>Open profile</Link>
              </Button>
            }
          />
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
