import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, ClipboardList } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  DataTable,
  EmptyState,
  FilterControls,
  FilterField,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PageHeader,
  PanelHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type {
  ComplianceAckReportFilters,
  ComplianceAckReportPageProps,
  ComplianceAckReportRow,
  FilterOption,
} from "@/types";

const VIEW = {
  any: [
    "web.view_policy_acknowledgements",
    "web.view_compliance",
    "web.manage_policies",
  ],
};
const ANY = "__any__";

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

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (next: string) => void;
}) {
  return (
    <FilterField label={label} hideLabel>
      <Select
        value={value || ANY}
        onValueChange={(next) => onChange(next === ANY ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label}>
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any {label.toLowerCase()}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FilterField>
  );
}

function ComplianceAckReportPage() {
  const { report, filterOptions, filters, capabilities, errors } =
    usePage<ComplianceAckReportPageProps>().props;
  const [query, setQuery] = useState(filters.q ?? "");
  const [waiveUserId, setWaiveUserId] = useState("");
  const [waivePolicyId, setWaivePolicyId] = useState("");
  const [reason, setReason] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function visit(patch: Partial<ComplianceAckReportFilters>) {
    router.get(
      routes.policy_ack_report(),
      {
        ...filters,
        q: query,
        ...patch,
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  function startWaive(row: ComplianceAckReportRow, revoke = false) {
    setWaiveUserId(String(row.userId));
    setWaivePolicyId(String(row.policyId));
    setReason("");
    setCorrecting(revoke);
  }

  function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const policyId = Number(waivePolicyId);
    if (!policyId) {
      return;
    }
    setSubmitting(true);
    const href = correcting
      ? routes.policy_ack_correct(policyId)
      : routes.policy_ack_waive(policyId);
    router.post(
      href,
      toFormData({
        user: waiveUserId,
        reason,
        ...(correcting ? { kind: "revoke_waiver" } : {}),
      }),
      {
        onFinish: () => setSubmitting(false),
        onSuccess: () => {
          setWaiveUserId("");
          setWaivePolicyId("");
          setReason("");
          setCorrecting(false);
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

      <FilterControls
        activeCount={
          [
            filters.policy,
            filters.office,
            filters.region,
            filters.role,
            filters.dueFrom,
            filters.dueTo,
            filters.status,
            filters.q,
          ].filter(Boolean).length
        }
        onReset={() => {
          setQuery("");
          visit({
            policy: "",
            office: "",
            region: "",
            role: "",
            dueFrom: "",
            dueTo: "",
            status: "",
            q: "",
          });
        }}
      >
        <SearchControl
          value={query}
          onValueChange={setQuery}
          onSearch={(value) => visit({ q: value })}
          placeholder="Search people"
        />
        <FilterSelect
          label="Policy"
          value={filters.policy}
          options={filterOptions.policies}
          onChange={(policy) => visit({ policy })}
        />
        <FilterSelect
          label="Office"
          value={filters.office}
          options={filterOptions.offices}
          onChange={(office) => visit({ office })}
        />
        <FilterSelect
          label="Region"
          value={filters.region}
          options={filterOptions.regions}
          onChange={(region) => visit({ region })}
        />
        <FilterSelect
          label="Role"
          value={filters.role}
          options={filterOptions.roles}
          onChange={(role) => visit({ role })}
        />
        <FilterSelect
          label="Status"
          value={filters.status}
          options={filterOptions.statuses}
          onChange={(status) => visit({ status })}
        />
        <FilterField label="Due from">
          <Input
            type="date"
            aria-label="Due from"
            value={filters.dueFrom}
            onChange={(event) => visit({ dueFrom: event.target.value })}
          />
        </FilterField>
        <FilterField label="Due to">
          <Input
            type="date"
            aria-label="Due to"
            value={filters.dueTo}
            onChange={(event) => visit({ dueTo: event.target.value })}
          />
        </FilterField>
      </FilterControls>

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
              description="Mandatory published policies with people in the effective audience will appear here."
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
                    capabilities.canWaive &&
                    (row.status === "pending" ||
                      row.status === "overdue" ||
                      row.status === "waived") ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => startWaive(row, row.status === "waived")}
                      >
                        {row.status === "waived" ? "Revoke waiver" : "Waive"}
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

      {capabilities.canWaive && waivePolicyId ? (
        <SurfaceCard>
          <PanelHeader
            divided
            title={correcting ? "Revoke waiver" : "Waive acknowledgement"}
            description="Explain why in at least 8 characters. Evidence is kept."
          />
          <SurfaceCardContent>
            <form className="grid max-w-xl gap-4" onSubmit={submitAction} noValidate>
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
                  {correcting ? "Confirm revocation" : "Confirm waiver"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={submitting}
                  onClick={() => {
                    setWaiveUserId("");
                    setWaivePolicyId("");
                    setReason("");
                    setCorrecting(false);
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
    <PermissionRequired permission={VIEW}>
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
