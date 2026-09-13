import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  DataTable,
  type DataTableColumn,
  FilterControls,
  FilterField,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  MetricCard,
  MetricStrip,
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
import { buildListUrl } from "@/lib/list-query";
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

function formatDay(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleDateString(undefined, {
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
        <SelectTrigger size="sm" aria-label={label} className="w-full sm:w-44">
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

  function visit(next: Partial<ComplianceAckReportFilters>) {
    router.get(
      buildListUrl(routes.policy_ack_report(), window.location.search, {
        filters: { ...filters, q: query, ...next },
      }),
      {},
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

  const activeCount = [
    filters.policy,
    filters.office,
    filters.region,
    filters.role,
    filters.dueFrom,
    filters.dueTo,
    filters.status,
  ].filter(Boolean).length;

  const columns: DataTableColumn<ComplianceAckReportRow>[] = [
    {
      id: "person",
      header: "Person",
      cell: (row) => (
        <span className="grid min-w-0 gap-0.5">
          <span className="truncate font-medium">{row.userName}</span>
          <span className="text-muted-foreground truncate text-xs">
            {row.email}
            {row.officeName ? ` · ${row.officeName}` : ""}
          </span>
        </span>
      ),
    },
    {
      id: "policy",
      header: "Policy",
      cell: (row) => (
        <Link
          href={routes.policy_admin_edit(row.policyId)}
          className="hover:text-primary focus-visible:ring-ring truncate rounded-sm text-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
        >
          {row.policyTitle}
        </Link>
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
        <span className="text-muted-foreground text-xs tabular-nums">
          {formatDay(row.dueAt)}
        </span>
      ),
      hideBelow: "3xl",
    },
    {
      id: "acked",
      header: "Acknowledged",
      cell: (row) => (
        <span className="text-muted-foreground text-xs tabular-nums">
          {formatDay(row.acknowledgedAt)}
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
  ];

  return (
    <div className="grid gap-8">
      <Head title="Acknowledgements" />
      <PageHeader
        title="Acknowledgements"
        description="Who still needs to acknowledge mandatory policies in your scope."
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

      <MetricStrip>
        <MetricCard label="Pending" value={report.summary.pending} />
        <MetricCard
          label="Overdue"
          value={report.summary.overdue}
          tone={report.summary.overdue > 0 ? "destructive" : "neutral"}
        />
        <MetricCard label="Acknowledged" value={report.summary.acknowledged} />
        <MetricCard label="Waived" value={report.summary.waived} />
      </MetricStrip>

      <SurfaceCard>
        <PanelHeader divided title="Queue" />
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            activeCount={activeCount}
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
            leading={
              <SearchControl
                label="Search people"
                value={query}
                onValueChange={setQuery}
                onSearch={(q) => visit({ q })}
                onClear={() => {
                  setQuery("");
                  visit({ q: "" });
                }}
                placeholder="Search people"
              />
            }
          >
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
            <FilterField label="Due from" hideLabel>
              <Input
                type="date"
                aria-label="Due from"
                value={filters.dueFrom}
                onChange={(event) => visit({ dueFrom: event.target.value })}
              />
            </FilterField>
            <FilterField label="Due to" hideLabel>
              <Input
                type="date"
                aria-label="Due to"
                value={filters.dueTo}
                onChange={(event) => visit({ dueTo: event.target.value })}
              />
            </FilterField>
          </FilterControls>

          <DataTable
            frame="bleed"
            caption="Acknowledgement status by person and policy"
            rows={report.items}
            rowKey={(row) => `${row.policyId}-${row.userId}`}
            getRowLabel={(row) => `${row.userName} · ${row.policyTitle}`}
            emptyTitle={
              activeCount > 0
                ? "No rows match these filters"
                : "No acknowledgement rows"
            }
            emptyDescription={
              activeCount > 0
                ? "Reset the filters to see everything in your scope."
                : "Mandatory published policies with people in the audience will appear here."
            }
            columns={columns}
          />
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
        title: "Acknowledgements",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Compliance", href: routes.admin_compliance() },
          { label: "Acknowledgements" },
        ],
      },
      variant: "wide",
    },
  ] as const;
