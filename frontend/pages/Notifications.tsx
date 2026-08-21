import { Head, Link, router, usePage } from "@inertiajs/react";
import { BellOff, CheckCheck, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  FormErrorSummary,
  PageHeader,
  Pagination,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import {
  type NotificationAction,
  NotificationList,
} from "@/components/notifications/NotificationList";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import type {
  NotificationFilterOption,
  NotificationRow,
  NotificationsPageProps,
} from "@/types";

/** Radix forbids an empty option value, so "everything" needs a sentinel. */
const ALL = "__all__";

function FilterSelect({
  label,
  value,
  options,
  allLabel,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  options: NotificationFilterOption[];
  allLabel: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <FilterField label={label}>
      <Select
        value={value || ALL}
        disabled={disabled}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger aria-label={label} className="w-full sm:w-44">
          <SelectValue placeholder={allLabel} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{allLabel}</SelectItem>
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

/**
 * The notification centre.
 *
 * Everything on this page describes the signed-in reader and nobody else: the
 * server never accepts a recipient, so there is no wider set for the page to
 * ask for. Rows arrive already resolved — a notification whose source has
 * withdrawn access shows its title, its reason, and no destination — so the
 * client is never in the position of deciding what it may reveal.
 */
export default function Notifications() {
  const { notificationList, filterOptions, summary, errors } =
    usePage<NotificationsPageProps>().props;
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const filters = notificationList.filters;
  const rows = notificationList.items;
  const pagination = notificationList.pagination;
  const activeCount =
    (filters.status && filters.status !== "unread" ? 1 : 0) +
    (filters.type ? 1 : 0) +
    (filters.priority ? 1 : 0);

  function visit(next: Partial<typeof filters> & { page?: number }) {
    router.get(
      routes.notifications(),
      {
        status: next.status ?? filters.status,
        type: next.type ?? filters.type,
        priority: next.priority ?? filters.priority,
        page: next.page ?? 1,
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  function mutate(row: NotificationRow, action: NotificationAction) {
    setPendingId(row.id);
    router.post(
      routes.notification_state(row.id),
      {
        action,
        status: filters.status,
        type: filters.type,
        priority: filters.priority,
        page: String(pagination.page),
      },
      {
        preserveScroll: true,
        onFinish: () => setPendingId(null),
      },
    );
  }

  function markAllRead() {
    setBusy(true);
    router.post(
      routes.notification_read_all(),
      {
        status: filters.status,
        type: filters.type,
        priority: filters.priority,
      },
      { preserveScroll: true, onFinish: () => setBusy(false) },
    );
  }

  const emptyCopy =
    filters.status === "archived"
      ? {
          title: "Nothing archived yet",
          description:
            "Notifications you file away are kept here so you can find them again.",
        }
      : activeCount > 0
        ? {
            title: "No notifications match these filters",
            description: "Clear the filters to see everything sent to you.",
          }
        : {
            title: "You are all caught up",
            description:
              "New contract, transaction, training, and administrative updates will appear here.",
          };

  return (
    <div className="grid gap-6">
      <Head title="Notifications" />
      <PageHeader
        title="Notifications"
        description="Updates addressed to you, newest first. Details are read from the source record each time, so a notification never outlives your access to what it refers to."
        meta={
          <span>
            {summary.unreadCount} unread
            {summary.mandatoryCount > 0
              ? ` · ${summary.mandatoryCount} requiring acknowledgement`
              : ""}
          </span>
        }
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || summary.unreadCount - summary.mandatoryCount <= 0}
              onClick={markAllRead}
            >
              <CheckCheck className="size-4" aria-hidden />
              Mark all read
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={routes.notification_preferences()}>
                <SlidersHorizontal className="size-4" aria-hidden />
                Settings
              </Link>
            </Button>
          </>
        }
      />

      <FormErrorSummary errors={errors} title="That action could not be applied" />

      <FilterControls
        activeCount={activeCount}
        disabled={busy}
        onReset={() => visit({ status: "unread", type: "", priority: "" })}
      >
        <FilterField label="Show">
          <Select
            value={filters.status || "unread"}
            disabled={busy}
            onValueChange={(status) => visit({ status })}
          >
            <SelectTrigger aria-label="Show" className="w-full sm:w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {filterOptions.status.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>
        <FilterSelect
          label="Type"
          value={filters.type}
          allLabel="All types"
          options={filterOptions.type}
          disabled={busy}
          onChange={(type) => visit({ type })}
        />
        <FilterSelect
          label="Priority"
          value={filters.priority}
          allLabel="All priorities"
          options={filterOptions.priority}
          disabled={busy}
          onChange={(priority) => visit({ priority })}
        />
      </FilterControls>

      <p role="status" aria-live="polite" className="sr-only">
        {`${pagination.totalItems} notifications match the current filters`}
      </p>

      <SurfaceCard className="py-0">
        {rows.length === 0 ? (
          <SurfaceCardContent className="px-0">
            <EmptyState
              icon={BellOff}
              title={emptyCopy.title}
              description={emptyCopy.description}
            />
          </SurfaceCardContent>
        ) : (
          <NotificationList
            rows={rows}
            onAction={mutate}
            pendingId={pendingId}
            busy={busy}
          />
        )}
      </SurfaceCard>

      {pagination.totalPages > 1 ? (
        <Pagination
          pagination={pagination}
          disabled={busy}
          onPageChange={(page) => visit({ page })}
        />
      ) : null}
    </div>
  );
}

Notifications.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Notifications",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Notifications", href: routes.notifications() },
        ],
        back: { label: "Back to dashboard", href: routes.dashboard() },
      },
      variant: "standard",
    },
  ] as const;
