import { Head, usePage } from "@inertiajs/react";

import { HubLayout } from "@/components/HubLayout";
import { NotFound } from "@/components/NotFound";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

export default function NotFoundPage() {
  const { requestId } = usePage<PageProps>().props;

  return (
    <>
      <Head title="Not found" />
      <NotFound requestId={requestId} />
    </>
  );
}

NotFoundPage.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Page not found",
        back: { label: "Back to dashboard", href: routes.dashboard() },
      },
      variant: "focused",
    },
  ] as const;
