import { Head, usePage } from "@inertiajs/react";
import type { ReactNode } from "react";

import { HubLayout } from "@/components/HubLayout";
import { NotFound } from "@/components/NotFound";
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

NotFoundPage.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
