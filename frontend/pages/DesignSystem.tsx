import { Head, usePage } from "@inertiajs/react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Inbox,
  Plus,
  Trash2,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  CardStateMessage,
  DataTable,
  type DataTableColumn,
  DestructiveConfirmDialog,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  EmptyState,
  FileUploader,
  FilterControls,
  FilterField,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  MetricCard,
  MetricGroup,
  PageHeader,
  Pagination,
  PanelHeader,
  ReadOnlyValue,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardDescription,
  SurfaceCardFooter,
  SurfaceCardHeader,
  SurfaceCardMeta,
  SurfaceCardTitle,
  Timeline,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildListUrl, visitListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import { CONTRACT_STATUS, presentStatus } from "@/lib/status";
import type { PageProps } from "@/types";
import type { ListResponse, ValidationErrors } from "@/types/design-system";

interface ContractRow {
  id: string;
  client: string;
  property: string;
  status: string;
  updated: string;
}

interface CatalogFilters extends Record<string, unknown> {
  q: string;
  status: string;
}

interface DesignSystemPageProps extends PageProps {
  contracts: ListResponse<ContractRow, CatalogFilters>;
}

const columns: DataTableColumn<ContractRow>[] = [
  { id: "id", header: "Contract", cell: (row) => row.id, sortable: true },
  {
    id: "client",
    header: "Client",
    cell: (row) => <span className="font-medium">{row.client}</span>,
    sortable: true,
  },
  { id: "property", header: "Property", cell: (row) => row.property },
  {
    id: "status",
    header: "Status",
    cell: (row) => <StatusBadge status={presentStatus(row.status, CONTRACT_STATUS)} />,
  },
  { id: "updated", header: "Last update", cell: (row) => row.updated },
];

const exampleValidation: ValidationErrors = {
  fields: {
    client_name: ["Enter the client’s full name."],
    email: ["Enter a valid email address."],
  },
  form: ["The server could not save this draft. Review the fields and try again."],
};

function CatalogSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section
      className="grid gap-4"
      aria-labelledby={`${title.replaceAll(" ", "-")}-title`}
    >
      <div>
        <h2
          id={`${title.replaceAll(" ", "-")}-title`}
          className="text-xl font-semibold"
        >
          {title}
        </h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm leading-6">
          {description}
        </p>
      </div>
      {children}
    </section>
  );
}

export default function DesignSystem() {
  const page = usePage<DesignSystemPageProps>();
  const { contracts } = page.props;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState(contracts.sort);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const [pathname, search = ""] = page.url.split("?");
  function visit(patch: Parameters<typeof buildListUrl>[2]) {
    visitListUrl(buildListUrl(pathname, search, patch));
  }

  const activeFilterCount = contracts.filters.status ? 1 : 0;

  return (
    <div className="grid gap-12">
      <Head title="Design system" />
      <PageHeader
        eyebrow="ONEST foundation"
        title="Component catalog"
        description="Stable, accessible patterns for operational pages. Examples show real states and safe composition—not product authorization."
        actions={
          <Button>
            <Plus className="size-4" aria-hidden />
            Primary action
          </Button>
        }
        meta={
          <StatusBadge
            status={{ label: "Version 1", tone: "success", icon: CheckCircle2 }}
          />
        }
      />

      <CatalogSection
        title="Cards and metrics"
        description="Use one surface per concept. State belongs on the component API; consumers do not invent one-off borders or shadows."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <SurfaceCard>
            <SurfaceCardHeader>
              <SurfaceCardTitle>Default card</SurfaceCardTitle>
              <SurfaceCardDescription>
                Calm structure for supporting information.
              </SurfaceCardDescription>
            </SurfaceCardHeader>
            <SurfaceCardContent className="text-sm">
              Content can grow, wrap, and localize without breaking the surface.
            </SurfaceCardContent>
          </SurfaceCard>
          <SurfaceCard state="loading">
            <SurfaceCardHeader>
              <SurfaceCardTitle>Loading card</SurfaceCardTitle>
            </SurfaceCardHeader>
            <SurfaceCardContent>
              <CardStateMessage state="loading">Loading latest data</CardStateMessage>
            </SurfaceCardContent>
          </SurfaceCard>
          <SurfaceCard state="error">
            <SurfaceCardHeader>
              <SurfaceCardTitle>Error card</SurfaceCardTitle>
            </SurfaceCardHeader>
            <SurfaceCardContent>
              <CardStateMessage state="error">
                This section could not be refreshed.
              </CardStateMessage>
            </SurfaceCardContent>
          </SurfaceCard>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <SurfaceCard>
            <PanelHeader
              title="Panel with a static fact"
              description="A heading, an optional line of context, and at most one quiet fact."
              meta={<SurfaceCardMeta>4 of 9 open</SurfaceCardMeta>}
            />
            <SurfaceCardContent className="text-sm">
              Panels carry no decorative icon tile: the heading identifies the panel,
              and a repeated tile beside every title competes with the data.
            </SurfaceCardContent>
          </SurfaceCard>
          <SurfaceCard>
            <PanelHeader
              title="Panel with one action"
              description="Use `action` for a real control and `meta` for a fact — never both as chips."
              action={
                <Button variant="outline" size="sm">
                  Manage
                </Button>
              }
            />
            <SurfaceCardContent className="text-sm">
              The right-hand slot never shrinks; the heading wraps instead, so a long or
              localized title cannot push the control off the card.
            </SurfaceCardContent>
          </SurfaceCard>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <MetricGroup title="Pipeline value" description="Current book of business">
            <MetricCard
              label="Active volume"
              value="$24.5M"
              hint="14% vs last month"
              trend="up"
              tone="success"
            />
            <MetricCard
              label="Commission"
              value="$490K"
              hint="5% vs last month"
              trend="up"
              tone="success"
            />
          </MetricGroup>
          <MetricGroup title="State examples">
            <MetricCard
              label="Pending tasks"
              value="12"
              hint="3 overdue"
              tone="warning"
            />
            <MetricCard label="Server metric" value="—" loading />
          </MetricGroup>
        </div>
      </CatalogSection>

      <CatalogSection
        title="Statuses"
        description="Backend codes map through explicit adapters. Unknown values render a neutral fallback and never become CSS classes."
      >
        <SurfaceCard>
          <SurfaceCardContent className="flex flex-wrap gap-2 pt-6">
            {[
              ...Object.values(CONTRACT_STATUS),
              presentStatus("unexpected", CONTRACT_STATUS),
            ].map((status) => (
              <StatusBadge key={status.label} status={status} />
            ))}
          </SurfaceCardContent>
        </SurfaceCard>
      </CatalogSection>

      <CatalogSection
        title="Search, filters, tables, and pagination"
        description="This example is backed by the Django list-response convention and uses URL query state, so browser history and Inertia visits remain predictable."
      >
        <SurfaceCard>
          <SurfaceCardHeader className="gap-4">
            <SearchControl
              defaultValue={String(contracts.filters.q ?? "")}
              label="Search contracts"
              placeholder="Search client, property, or contract ID"
              onSearch={(q) => visit({ q })}
              onClear={() => visit({ q: "" })}
            />
            {/* `tone="subtle"` is the app-header variant: no border, so it does
                not out-weigh the icon buttons beside it. */}
            <SearchControl
              label="Subtle search"
              placeholder="Subtle tone, small size — for toolbars and app headers"
              tone="subtle"
              size="sm"
            />
            <FilterControls
              activeCount={activeFilterCount}
              onReset={() => visit({ filters: { status: "" } })}
            >
              <FilterField label="Contract status">
                <Select
                  value={String(contracts.filters.status || "all")}
                  onValueChange={(status) =>
                    visit({ filters: { status: status === "all" ? "" : status } })
                  }
                >
                  <SelectTrigger aria-label="Filter by contract status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="pending_signature">Pending signature</SelectItem>
                    <SelectItem value="pending_documents">Pending documents</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                  </SelectContent>
                </Select>
              </FilterField>
            </FilterControls>
          </SurfaceCardHeader>
          <SurfaceCardContent className="grid gap-4">
            <DataTable
              rows={contracts.items}
              columns={columns}
              rowKey={(row) => row.id}
              caption="Example contracts"
              sort={sort}
              onSortChange={setSort}
              selectedKeys={selected}
              onSelectionChange={setSelected}
              getRowLabel={(row) => row.id}
              emptyTitle="No matching contracts"
              emptyDescription="Clear the search or filters to see more contracts."
            />
            <Pagination
              pagination={contracts.pagination}
              onPageChange={(nextPage) => visit({ page: nextPage })}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </CatalogSection>

      <CatalogSection
        title="Forms and uploaders"
        description="Labels remain visible, summaries link to fields, and client upload hints never replace server validation."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <SurfaceCard state="error">
            <SurfaceCardHeader>
              <SurfaceCardTitle>Server validation</SurfaceCardTitle>
              <SurfaceCardDescription>
                The messages below are rendered as text, including untrusted content.
              </SurfaceCardDescription>
            </SurfaceCardHeader>
            <SurfaceCardContent>
              <form className="grid gap-5" onSubmit={(event) => event.preventDefault()}>
                <FormErrorSummary
                  errors={exampleValidation}
                  labels={{ client_name: "Client name", email: "Email" }}
                />
                <FormField>
                  <FormLabel htmlFor="client_name" required>
                    Client name
                  </FormLabel>
                  <Input
                    id="client_name"
                    aria-invalid
                    aria-describedby="client_name_error"
                  />
                  <FormDescription>
                    Use the name shown on the agreement.
                  </FormDescription>
                  <FormFieldError
                    id="client_name_error"
                    messages={exampleValidation.fields.client_name}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="email" required>
                    Email
                  </FormLabel>
                  <Input id="email" value={'<img src=x onerror="alert(1)">'} readOnly />
                  <FormFieldError messages={exampleValidation.fields.email} />
                </FormField>
                <dl className="bg-muted/40 grid gap-4 rounded-lg p-4 sm:grid-cols-2">
                  <ReadOnlyValue label="Office">Charlottesville</ReadOnlyValue>
                  <ReadOnlyValue label="Role">Agent</ReadOnlyValue>
                </dl>
                <Button type="submit">Save changes</Button>
              </form>
            </SurfaceCardContent>
          </SurfaceCard>
          <SurfaceCard>
            <SurfaceCardHeader>
              <SurfaceCardTitle>Document uploader</SurfaceCardTitle>
              <SurfaceCardDescription>
                Drag/drop, keyboard selection, progress, retry, preview, and removal.
              </SurfaceCardDescription>
            </SurfaceCardHeader>
            <SurfaceCardContent>
              <FileUploader
                accept="image/jpeg,image/png,application/pdf"
                maxSize={5 * 1024 * 1024}
                description="PDF, JPEG, or PNG · client limit 5 MB · server rules remain authoritative"
                upload={(file, { signal, onProgress }) =>
                  new Promise((resolve, reject) => {
                    onProgress(35);
                    const timer = window.setTimeout(() => {
                      onProgress(100);
                      resolve({
                        name: file.name,
                        size: file.size,
                        type: file.type,
                      });
                    }, 450);
                    signal.addEventListener("abort", () => {
                      window.clearTimeout(timer);
                      reject(new Error("Upload cancelled."));
                    });
                  })
                }
              />
            </SurfaceCardContent>
          </SurfaceCard>
        </div>
      </CatalogSection>

      <CatalogSection
        title="Empty states, timelines, and dialogs"
        description="Empty states teach the next step; timelines remain ordered content; dialogs are reserved for focused decisions."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <SurfaceCard>
            <EmptyState
              icon={Inbox}
              title="No documents yet"
              description="Upload the signed agreement to make it available to your office team."
              actions={<Button size="sm">Upload document</Button>}
            />
          </SurfaceCard>
          <SurfaceCard>
            <SurfaceCardHeader>
              <SurfaceCardTitle>Contract timeline</SurfaceCardTitle>
            </SurfaceCardHeader>
            <SurfaceCardContent>
              <Timeline
                items={[
                  {
                    id: "created",
                    title: "Draft created",
                    meta: "Aug 17",
                    tone: "success",
                  },
                  {
                    id: "signature",
                    title: "Awaiting signature",
                    description: "Two of three parties have signed.",
                    meta: "Current",
                    tone: "warning",
                    current: true,
                  },
                  { id: "approved", title: "Office approval", tone: "neutral" },
                ]}
              />
            </SurfaceCardContent>
          </SurfaceCard>
          <SurfaceCard>
            <SurfaceCardHeader>
              <SurfaceCardTitle>Dialog patterns</SurfaceCardTitle>
              <SurfaceCardDescription>
                Focus is trapped and restored; Escape closes the standard dialog.
              </SurfaceCardDescription>
            </SurfaceCardHeader>
            <SurfaceCardContent className="grid gap-2">
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="outline">Open standard dialog</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Share contract</DialogTitle>
                    <DialogDescription>
                      Choose who should receive access. Authorization remains a backend
                      concern.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <DialogClose asChild>
                      <Button variant="outline">Cancel</Button>
                    </DialogClose>
                    <Button>Share contract</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
                <Trash2 className="size-4" aria-hidden />
                Delete draft
              </Button>
              <DestructiveConfirmDialog
                open={confirmOpen}
                onOpenChange={setConfirmOpen}
                title="Delete contract draft?"
                description="This cannot be undone. You are deleting"
                target="ON-1048"
                onConfirm={() => setConfirmOpen(false)}
              />
            </SurfaceCardContent>
          </SurfaceCard>
        </div>
      </CatalogSection>

      <SurfaceCard state="read-only">
        <SurfaceCardHeader>
          <SurfaceCardTitle className="flex items-center gap-2">
            <FileText className="size-4" aria-hidden />
            Usage guidance
          </SurfaceCardTitle>
        </SurfaceCardHeader>
        <SurfaceCardContent className="grid gap-5 text-sm sm:grid-cols-2">
          <div>
            <h3 className="font-semibold">Do</h3>
            <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5">
              <li>Compose permission guards around components.</li>
              <li>Map backend statuses through presentation adapters.</li>
              <li>Keep labels, table headers, and focus indicators visible.</li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold">Don’t</h3>
            <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5">
              <li>Use hidden or disabled controls as authorization.</li>
              <li>Pass raw class names or unsafe HTML from the backend.</li>
              <li>Treat client upload checks as security validation.</li>
            </ul>
          </div>
        </SurfaceCardContent>
        <SurfaceCardFooter>
          <AlertTriangle className="text-warning-ink size-4" aria-hidden />
          <p className="text-muted-foreground text-xs">
            Breaking public API changes require migration notes in this document.
          </p>
        </SurfaceCardFooter>
      </SurfaceCard>
    </div>
  );
}

DesignSystem.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Design system",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Design system", href: routes.design_system() },
        ],
      },
      variant: "standard",
    },
  ] as const;
