import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowDown, ArrowUp, Building2, Eye, Globe2, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { QuickAccessLinkFields } from "@/components/administration/QuickAccessLinkFields";
import {
  CreateSheet,
  DataTable,
  EmptyState,
  FilterControls,
  FilterField,
  FormErrorSummary,
  PageHeader,
  Pagination,
  PanelHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type {
  QuickAccessAdministrationPageProps,
  QuickAccessAudience,
  QuickAccessLinkRow,
} from "@/types";

const MANAGE = { all: ["web.manage_quick_access"] };

function audienceLabel(audience: QuickAccessAudience): string {
  const where = audience.companyWide
    ? "Every office"
    : audience.offices.length === 0
      ? "No office"
      : audience.offices.length === 1
        ? audience.offices[0].name
        : `${audience.offices.length} offices`;
  const who =
    audience.roles.length === 0
      ? "every role"
      : audience.roles.map((role) => role.label).join(", ");
  return `${where} · ${who}`;
}

/**
 * Manage the dashboard's Quick Access panel.
 *
 * Every row here already passed the server's scope filter, and `canManage`
 * repeats the server's answer so a control is never offered for a link the
 * save would refuse. The page cannot ask for a wider set and could not receive
 * one.
 */
function QuickAccessAdministrationPage() {
  const {
    links,
    statusOptions,
    roleOptions,
    officeOptions,
    preview,
    capabilities,
    createOptions,
    createSheet,
    errors,
    csrfToken,
  } = usePage<QuickAccessAdministrationPageProps>().props;
  const [query, setQuery] = useState(links.filters.q ?? "");
  const [reordering, setReordering] = useState(false);
  // Quick Create links here with ?create=1; a rejected create comes back with
  // the drawer flagged open so nothing typed is lost.
  const [createOpen, setCreateOpen] = useState(
    Boolean(createSheet?.open) || hasValidationErrors(errors),
  );
  const pendingConfirmation = createSheet?.pendingConfirmation ?? [];

  const rows = links.items;
  const status = links.filters.status ?? "";

  function visit(next: {
    q?: string;
    status?: string;
    page?: number;
    previewRole?: string;
    previewOffice?: string;
  }) {
    router.get(
      routes.admin_quick_access(),
      {
        q: next.q ?? query,
        status: next.status ?? status,
        page: next.page ?? 1,
        previewRole: next.previewRole ?? preview?.roleCode ?? "",
        previewOffice:
          next.previewOffice ??
          (preview?.officeId != null ? String(preview.officeId) : ""),
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  /**
   * Move one row and post the whole visible sequence.
   *
   * The server keeps unmanaged links in place, so this only ever reshuffles the
   * positions the administrator already occupies.
   */
  function move(index: number, direction: -1 | 1) {
    const next = [...rows];
    const target = index + direction;
    if (target < 0 || target >= next.length) {
      return;
    }
    [next[index], next[target]] = [next[target], next[index]];
    setReordering(true);
    router.post(
      routes.quick_access_reorder(),
      { order: next.map((row) => row.id).join(",") },
      {
        preserveScroll: true,
        onFinish: () => setReordering(false),
      },
    );
  }

  function changeState(row: QuickAccessLinkRow, action: string) {
    router.post(
      routes.quick_access_state(row.id),
      { action },
      { preserveScroll: true },
    );
  }

  return (
    <div className="grid gap-10">
      <Head title="Quick Access" />
      <PageHeader
        title="Quick Access"
        description="Decide which tools appear on the dashboard launcher, in what order, and for which offices and roles."
        meta={
          <span className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
            {capabilities.scopeLevel === "brokerage" ? (
              <>
                <Globe2 className="size-3.5" aria-hidden /> Brokerage-wide scope
              </>
            ) : (
              <>
                <Building2 className="size-3.5" aria-hidden /> Your office scope
              </>
            )}
          </span>
        }
        actions={
          <Button type="button" onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" aria-hidden />
            New link
          </Button>
        }
      />

      <CreateSheet
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="New Quick Access link"
        description="A launcher on every dashboard in its audience. Destinations must be https, or one of the approved in-app pages."
        action={routes.quick_access_create()}
        csrfToken={csrfToken}
        formId="quick-access-create-form"
        submitLabel={
          pendingConfirmation.length > 0 ? "Publish the change" : "Create link"
        }
      >
        {pendingConfirmation.length > 0 ? (
          // The exposure diff, shown before the link reaches anybody. The
          // acknowledgement rides the next submit, so a widening change is
          // still never applied by a single click.
          <div className="border-warning/40 bg-warning/10 grid gap-2 rounded-lg border p-3 text-sm">
            <p className="font-semibold">This change widens who can see the tool</p>
            <ul className="grid gap-1">
              {pendingConfirmation.map((change) => (
                <li key={change.label} className="text-muted-foreground text-xs">
                  <strong className="text-foreground">{change.label}:</strong>{" "}
                  {change.from} → {change.to}. {change.impact}
                </li>
              ))}
            </ul>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="acknowledge_exposure"
                value="on"
                defaultChecked
                className="accent-primary size-4"
              />
              I have checked the audience and destination
            </label>
          </div>
        ) : null}
        <QuickAccessLinkFields
          defaults={createSheet?.draft}
          errors={errors}
          iconOptions={createOptions.iconOptions}
          internalDestinations={createOptions.internalDestinations}
          destinationTypeOptions={createOptions.destinationTypeOptions}
          ssoOptions={createOptions.ssoOptions}
          healthOptions={createOptions.healthOptions}
          setupOptions={createOptions.setupOptions}
          roleOptions={roleOptions}
          officeOptions={officeOptions}
          capabilities={capabilities}
        />
      </CreateSheet>

      {errors ? <FormErrorSummary errors={errors} /> : null}

      <SurfaceCard>
        <PanelHeader
          divided
          title="Links in your scope"
          description="Ordered exactly as agents see them."
          meta={
            <span className="text-muted-foreground text-xs font-medium tabular-nums">
              {links.pagination.totalItems}{" "}
              {links.pagination.totalItems === 1 ? "link" : "links"}
            </span>
          }
        />
        <SurfaceCardContent className="grid gap-4">
          <SearchControl
            label="Search links"
            value={query}
            onValueChange={setQuery}
            onSearch={(next) => visit({ q: next })}
            onClear={() => visit({ q: "" })}
            placeholder="Name or stable key"
            className="max-w-xl"
          />
          <FilterControls
            activeCount={status ? 1 : 0}
            onReset={() => visit({ status: "" })}
          >
            <FilterField label="Lifecycle">
              <Select
                value={status || "all"}
                onValueChange={(next) => visit({ status: next === "all" ? "" : next })}
              >
                <SelectTrigger aria-label="Filter by lifecycle">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All except archived</SelectItem>
                  {statusOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          </FilterControls>

          <DataTable
            frame="bleed"
            caption="Quick Access links you may manage"
            rows={rows}
            rowKey={(row) => String(row.id)}
            emptyTitle="No links match"
            emptyDescription="No Quick Access link in your scope matches these filters."
            columns={[
              {
                id: "order",
                header: "Order",
                cell: (row) => {
                  const index = rows.findIndex((item) => item.id === row.id);
                  return (
                    <div className="flex items-center gap-1">
                      <span className="text-muted-foreground w-6 text-xs tabular-nums">
                        {row.sortOrder}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="size-8 px-0"
                        disabled={!row.canManage || index === 0 || reordering}
                        onClick={() => move(index, -1)}
                      >
                        <span className="sr-only">Move {row.name} up</span>
                        <ArrowUp className="size-3.5" aria-hidden />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="size-8 px-0"
                        disabled={
                          !row.canManage || index === rows.length - 1 || reordering
                        }
                        onClick={() => move(index, 1)}
                      >
                        <span className="sr-only">Move {row.name} down</span>
                        <ArrowDown className="size-3.5" aria-hidden />
                      </Button>
                    </div>
                  );
                },
              },
              {
                id: "name",
                header: "Link",
                cell: (row) => (
                  <div className="grid min-w-40 gap-0.5 sm:min-w-56">
                    <span className="truncate font-semibold">{row.name}</span>
                    <span className="text-muted-foreground truncate text-xs">
                      {row.stableKey} · {row.destinationValue}
                    </span>
                  </div>
                ),
              },
              {
                id: "audience",
                header: "Audience",
                cell: (row) => (
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <span className="truncate text-sm">
                      {audienceLabel(row.audience)}
                    </span>
                    {row.ownerScope === "company" ? (
                      <Badge variant="outline" className="shrink-0">
                        Company-owned
                      </Badge>
                    ) : null}
                  </div>
                ),
                className: "hidden md:table-cell",
                headerClassName: "hidden md:table-cell",
              },
              {
                id: "status",
                header: "Status",
                cell: (row) => (
                  <StatusBadge
                    status={{ label: row.status.label, tone: row.status.tone }}
                  />
                ),
                className: "hidden sm:table-cell",
                headerClassName: "hidden sm:table-cell",
              },
              {
                id: "actions",
                header: <span className="sr-only">Actions</span>,
                cell: (row) => (
                  <div className="flex items-center justify-end gap-2">
                    {row.canManage && !row.isArchived ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          changeState(row, row.isActive ? "deactivate" : "activate")
                        }
                      >
                        {row.isActive ? "Deactivate" : "Activate"}
                      </Button>
                    ) : null}
                    {row.canManage && !row.isArchived ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => changeState(row, "archive")}
                      >
                        Archive
                      </Button>
                    ) : null}
                    {row.canManage && row.isArchived ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => changeState(row, "restore")}
                      >
                        Restore
                      </Button>
                    ) : null}
                    <Button
                      variant="outline"
                      size="sm"
                      asChild
                      disabled={!row.canManage}
                      className="size-8 px-0 sm:h-8 sm:w-auto sm:px-3"
                    >
                      <Link href={routes.quick_access_edit(row.id)}>
                        <span className="sr-only">Edit {row.name}</span>
                        <span className="hidden sm:inline" aria-hidden>
                          Edit
                        </span>
                        <Pencil className="size-3.5" aria-hidden />
                      </Link>
                    </Button>
                  </div>
                ),
                className: "text-right",
                headerClassName: "text-right",
              },
            ]}
          />
          {links.pagination.totalPages > 1 ? (
            <Pagination
              pagination={links.pagination}
              onPageChange={(page) => visit({ page })}
            />
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      <SurfaceCard>
        <PanelHeader
          divided
          title="Preview effective visibility"
          description="Pick a role and an office to see exactly what that person would get — and why anything else stays hidden."
        />
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            // Two filter regions on one page need distinguishable names, or a
            // screen-reader landmark list reads "Filters" twice.
            aria-label="Preview filters"
            activeCount={
              (preview?.roleCode ? 1 : 0) + (preview?.officeId != null ? 1 : 0)
            }
            onReset={() => visit({ previewRole: "", previewOffice: "" })}
          >
            <FilterField label="Role">
              <Select
                value={preview?.roleCode || "none"}
                onValueChange={(next) =>
                  visit({ previewRole: next === "none" ? "" : next })
                }
              >
                <SelectTrigger aria-label="Preview role">
                  <SelectValue placeholder="Choose a role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No role</SelectItem>
                  {roleOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
            <FilterField label="Office" className="min-w-64">
              <Select
                value={preview?.officeId != null ? String(preview.officeId) : "none"}
                onValueChange={(next) =>
                  visit({ previewOffice: next === "none" ? "" : next })
                }
              >
                <SelectTrigger aria-label="Preview office">
                  <SelectValue placeholder="Choose an office" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No office</SelectItem>
                  {officeOptions.map((option) => (
                    <SelectItem key={option.value} value={String(option.value)}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          </FilterControls>

          {preview?.outOfScope ? (
            <EmptyState
              icon={Eye}
              title="That office is outside your scope"
              description="Pick an office your role covers."
            />
          ) : preview ? (
            <ul className="grid gap-2">
              {preview.links.map((item) => (
                <li
                  key={item.id}
                  className="border-border/60 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm"
                >
                  <StatusBadge
                    status={{
                      label: item.visible ? "Visible" : "Hidden",
                      tone: item.visible ? "success" : "neutral",
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {item.name}
                  </span>
                  {item.reasons.length > 0 ? (
                    <span className="text-muted-foreground min-w-0 basis-full text-xs sm:basis-auto">
                      {item.reasons.join(" ")}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Eye}
              title="Nothing previewed yet"
              description="Choose a role and an office above to check a change before you publish it."
            />
          )}
        </SurfaceCardContent>
      </SurfaceCard>
    </div>
  );
}

export default function QuickAccessAdministration() {
  return (
    <PermissionRequired permission={MANAGE}>
      <QuickAccessAdministrationPage />
    </PermissionRequired>
  );
}

QuickAccessAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Quick Access",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Quick Access", href: routes.admin_quick_access() },
        ],
      },
      variant: "standard",
    },
  ] as const;
