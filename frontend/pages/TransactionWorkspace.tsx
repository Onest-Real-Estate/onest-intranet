import { Head, Link, usePage } from "@inertiajs/react";
import {
  Callout,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { TransactionWorkspacePageProps } from "@/types";

const ACCESS = {
  any: [
    "web.view_transactions",
    "web.manage_transactions",
    "web.create_own_transactions",
    "web.view_own_transactions",
  ],
};

export default function TransactionWorkspace() {
  const { transaction } = usePage<TransactionWorkspacePageProps>().props;
  const propertyLine = [
    transaction.property?.line1,
    transaction.property?.city,
    transaction.property?.state,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <PermissionRequired permission={ACCESS}>
      <Head title={transaction.reference || "Transaction"} />
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-6">
        <PageHeader
          title={transaction.reference || "Transaction"}
          description={`${transaction.transactionType} · ${transaction.representationType}`}
          actions={
            <Button asChild variant="outline">
              <Link href={routes.transaction_new()}>New transaction</Link>
            </Button>
          }
          meta={
            <StatusBadge status={{ label: transaction.statusLabel, tone: "info" }} />
          }
        />

        <Callout tone="info" title="Workspace shell">
          Parties, documents, tasks, and compliance land in later issues. This page
          confirms the deal was created and shows the fields captured so far.
        </Callout>

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
            <ReadOnlyValue label="Office">
              {transaction.office?.name || "—"}
            </ReadOnlyValue>
            <ReadOnlyValue label="MLS">{transaction.mlsNumber || "—"}</ReadOnlyValue>
            <ReadOnlyValue label="Property">{propertyLine || "—"}</ReadOnlyValue>
            <ReadOnlyValue label="Primary agent">
              {transaction.primaryAgent?.displayName || "—"}
            </ReadOnlyValue>
            <ReadOnlyValue label="Coordinator">
              {transaction.coordinator?.displayName || "—"}
            </ReadOnlyValue>
            <ReadOnlyValue label="Acceptance">
              {transaction.acceptanceDate || "—"}
            </ReadOnlyValue>
            <ReadOnlyValue label="Closing">
              {transaction.closingDate || "—"}
            </ReadOnlyValue>
            {"listPrice" in transaction ? (
              <ReadOnlyValue label="List price">
                {transaction.listPrice ?? "—"}
              </ReadOnlyValue>
            ) : null}
            {"contractPrice" in transaction ? (
              <ReadOnlyValue label="Contract price">
                {transaction.contractPrice ?? "—"}
              </ReadOnlyValue>
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <SurfaceCardContent className="space-y-3 py-5">
            <p className="text-sm font-medium">Assignments</p>
            {transaction.assignments.length === 0 ? (
              <p className="text-muted-foreground text-sm">No active assignments.</p>
            ) : (
              <ul className="grid gap-2">
                {transaction.assignments.map((row) => (
                  <li
                    key={row.publicId}
                    className="border-border/60 flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                  >
                    <span>{row.user?.displayName || "—"}</span>
                    <span className="text-muted-foreground">{row.roleLabel}</span>
                  </li>
                ))}
              </ul>
            )}
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-3 py-5 sm:grid-cols-3">
            <div className="border-border/60 rounded-md border border-dashed p-4 text-sm">
              <p className="font-medium">Parties</p>
              <p className="text-muted-foreground mt-1">Coming in #101</p>
            </div>
            <div className="border-border/60 rounded-md border border-dashed p-4 text-sm">
              <p className="font-medium">Documents</p>
              <p className="text-muted-foreground mt-1">Coming in #102</p>
            </div>
            <div className="border-border/60 rounded-md border border-dashed p-4 text-sm">
              <p className="font-medium">Tasks & compliance</p>
              <p className="text-muted-foreground mt-1">Coming in #105–#106</p>
            </div>
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

TransactionWorkspace.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
