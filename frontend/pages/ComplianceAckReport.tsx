import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, ClipboardList } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  DataTable,
  EmptyState,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type { ComplianceAckReportPageProps, ComplianceAckReportRow } from "@/types";

const MANAGE = { all: ["web.manage_policies"] };

const STATUS_TONE: Record<string, string> = {
  pending: "warning",
  acknowledged: "success",
  waived: "neutral",
  overdue: "destructive",
};

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function ComplianceAckReportPage() {
  const { report, capabilities, errors } =
    usePage<ComplianceAckReportPageProps>().props;
  const [waiveUserId, setWaiveUserId] = useState("");
  const [waivePolicyId, setWaivePolicyId] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function startWaive(row: ComplianceAckReportRow) {
    setWaiveUserId(String(row.userId));
    setWaivePolicyId(String(row.policyId));
    setReason("");
  }

  function submitWaive(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const policyId = Number(waivePolicyId);
    if (!policyId) {
      return;
    }
    setSubmitting(true);
    router.post(
      routes.policy_ack_waive(policyId),
      toFormData({
        user: waiveUserId,
        reason,
      }),
      {
        onFinish: () => setSubmitting(false),
        onSuccess: () => {
          setWaiveUserId("");
          setWaivePolicyId("");
          setReason("");
        },
      },
    );
  }

  return (
    <div className="grid gap-8">
      <Head title="Acknowledgement report" />
      <PageHeader
        title="Acknowledgement report"
        description="Who still needs to acknowledge mandatory published policies in your scope."
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link href={routes.admin_compliance()}>
              <ArrowLeft className="size-4" aria-hidden />
              Back to policies
            </Link>
          </Button>
        }
      />

      <FormErrorSummary errors={errors} />

      <SurfaceCard>
        <PanelHeader
          divided
          title="Requirements"
          description="Pending and overdue rows are actionable. Waivers need a short reason."
          meta={
            <span className="text-muted-foreground text-xs font-medium tabular-nums">
              {report.totalItems} {report.totalItems === 1 ? "row" : "rows"}
            </span>
          }
        />
        <SurfaceCardContent className="grid gap-4">
          {report.items.length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title="No acknowledgement rows"
              description="Mandatory published policies with people in your scope will appear here."
            />
          ) : (
            <DataTable
              frame="bleed"
              caption="Acknowledgement status by person and policy"
              rows={report.items}
              rowKey={(row) => `${row.policyId}-${row.userId}`}
              emptyTitle="No rows"
              emptyDescription="Nothing to show."
              columns={[
                {
                  id: "person",
                  header: "Person",
                  cell: (row) => (
                    <div className="grid min-w-40 gap-0.5">
                      <span className="truncate font-semibold">{row.userName}</span>
                      <span className="text-muted-foreground truncate text-xs">
                        {row.email}
                        {row.officeName ? ` · ${row.officeName}` : ""}
                      </span>
                    </div>
                  ),
                },
                {
                  id: "policy",
                  header: "Policy",
                  cell: (row) => (
                    <span className="truncate text-sm">{row.policyTitle}</span>
                  ),
                },
                {
                  id: "status",
                  header: "Status",
                  cell: (row) => (
                    <StatusBadge
                      status={{
                        label: row.status,
                        tone: toStatusTone(STATUS_TONE[row.status] ?? "neutral"),
                      }}
                    />
                  ),
                },
                {
                  id: "due",
                  header: "Due",
                  cell: (row) => (
                    <span className="text-sm tabular-nums">
                      {formatDate(row.dueAt)}
                    </span>
                  ),
                  hideBelow: "3xl",
                },
                {
                  id: "acked",
                  header: "Acknowledged",
                  cell: (row) => (
                    <span className="text-sm tabular-nums">
                      {formatDate(row.acknowledgedAt)}
                    </span>
                  ),
                  hideBelow: "4xl",
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Actions</span>,
                  cell: (row) =>
                    capabilities.canAuthor &&
                    (row.status === "pending" || row.status === "overdue") ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => startWaive(row)}
                      >
                        Waive
                      </Button>
                    ) : null,
                  className: "text-right",
                  headerClassName: "text-right",
                },
              ]}
            />
          )}
        </SurfaceCardContent>
      </SurfaceCard>

      {capabilities.canAuthor && waivePolicyId ? (
        <SurfaceCard>
          <PanelHeader
            divided
            title="Waive acknowledgement"
            description="Explain why this person does not need to acknowledge. At least 8 characters."
          />
          <SurfaceCardContent>
            <form className="grid max-w-xl gap-4" onSubmit={submitWaive} noValidate>
              <input type="hidden" name="user" value={waiveUserId} />
              <FormField>
                <FormLabel htmlFor="waive_user">User id</FormLabel>
                <Input id="waive_user" value={waiveUserId} readOnly />
              </FormField>
              <FormField>
                <FormLabel htmlFor="reason" required>
                  Reason
                </FormLabel>
                <Textarea
                  id="reason"
                  rows={3}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  {...fieldA11yProps("reason", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "reason")} />
              </FormField>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={submitting || reason.trim().length < 8}>
                  Confirm waiver
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={submitting}
                  onClick={() => {
                    setWaiveUserId("");
                    setWaivePolicyId("");
                    setReason("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

export default function ComplianceAckReport() {
  return (
    <PermissionRequired permission={MANAGE}>
      <ComplianceAckReportPage />
    </PermissionRequired>
  );
}

ComplianceAckReport.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Acknowledgement report",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Compliance administration",
            href: routes.admin_compliance(),
          },
          { label: "Acknowledgements" },
        ],
      },
      variant: "standard",
    },
  ] as const;
