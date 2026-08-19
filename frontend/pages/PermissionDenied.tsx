import { Head, usePage } from "@inertiajs/react";
import type { ReactNode } from "react";

import { HubLayout } from "@/components/HubLayout";
import { PermissionDenied } from "@/components/PermissionDenied";
import type { PageProps } from "@/types";

/**
 * Inertia page wrapper for `PermissionDenied`, registered so Django can
 * render it for real 403s — see apps/web/views.py `permission_denied` and
 * `handler403` in config/urls.py.
 */
export default function PermissionDeniedPage() {
  const { requestId } = usePage<PageProps>().props;

  return (
    <>
      <Head title="Permission denied" />
      <PermissionDenied requestId={requestId} />
    </>
  );
}

PermissionDeniedPage.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
