import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  StickyNote,
  Users,
} from "lucide-react";
import {
  Fragment,
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { ActivityTimeline } from "@/components/activity/ActivityTimeline";
import {
  Callout,
  DatePicker,
  EmptyState,
  FormActionBar,
  FormFieldError,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  TimezonePicker,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { DocumentsPanel } from "@/components/transactions/DocumentsPanel";
import { SignaturesPanel } from "@/components/transactions/SignaturesPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useValidationToasts } from "@/hooks/use-validation-toasts";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  TransactionKeyDateRow,
  TransactionNoteRow,
  TransactionPartyRow,
  TransactionWorkspacePageProps,
  TransactionWorkspaceSection,
} from "@/types";

const ACCESS = {
  any: [
    "web.view_transactions",
    "web.manage_transactions",
    "web.create_own_transactions",
    "web.view_own_transactions",
  ],
};

const PARTY_ROLES = [
  { value: "buyer", label: "Buyer" },
  { value: "seller", label: "Seller" },
  { value: "tenant", label: "Tenant" },
  { value: "landlord", label: "Landlord" },
  { value: "lender", label: "Lender" },
  { value: "title", label: "Title" },
  { value: "attorney", label: "Attorney" },
  { value: "inspector", label: "Inspector" },
  { value: "referral_agent", label: "Referral agent" },
  { value: "co_party", label: "Co-party" },
];

const DATE_TYPES = [
  { value: "acceptance", label: "Acceptance" },
  { value: "closing", label: "Closing" },
  { value: "inspection", label: "Inspection" },
  { value: "appraisal", label: "Appraisal" },
  { value: "financing", label: "Financing" },
  { value: "earnest_money", label: "Earnest money" },
  { value: "possession", label: "Possession" },
  { value: "other", label: "Other" },
];

const NOTE_VISIBILITIES = [
  { value: "team", label: "Team" },
  { value: "broker_compliance", label: "Broker / compliance" },
  { value: "private_author", label: "Private (author only)" },
];

function sectionHref(publicId: string, sectionId: string) {
  return `${routes.transaction_workspace(publicId)}?section=${sectionId}`;
}

function WorkspaceTabs({
  sections,
  active,
  publicId,
}: {
  sections: TransactionWorkspaceSection[];
  active: string;
  publicId: string;
}) {
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const live = sections.filter((s) => s.live || s.stub);

  function scrollByPage(direction: -1 | 1) {
    const el = scrollerRef.current;
    if (!el) return;
    const delta = Math.max(160, Math.round(el.clientWidth * 0.6)) * direction;
    el.scrollBy({ left: delta, behavior: "smooth" });
  }

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    // Capture tab count so we remeasure when sections change. scrollWidth can
    // grow without the scroller's client box changing, so ResizeObserver alone
    // would miss newly-added tabs.
    void live.length;

    function updateScrollState() {
      // Re-read the node so the nested callback stays null-safe for tsc.
      const node = scrollerRef.current;
      if (!node) return;
      const max = node.scrollWidth - node.clientWidth;
      setCanScrollLeft(node.scrollLeft > 1);
      setCanScrollRight(max > 1 && node.scrollLeft < max - 1);
    }

    updateScrollState();
    const observer = new ResizeObserver(updateScrollState);
    observer.observe(el);
    el.addEventListener("scroll", updateScrollState, { passive: true });
    window.addEventListener("resize", updateScrollState);
    return () => {
      observer.disconnect();
      el.removeEventListener("scroll", updateScrollState);
      window.removeEventListener("resize", updateScrollState);
    };
  }, [live.length]);

  useEffect(() => {
    refs.current.get(active)?.scrollIntoView({
      inline: "nearest",
      block: "nearest",
      behavior: "smooth",
    });
  }, [active]);

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const offset =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : null;
    if (offset === null) return;
    event.preventDefault();
    const index = live.findIndex((tab) => tab.id === active);
    const next = live[(index + offset + live.length) % live.length];
    if (!next) return;
    router.get(sectionHref(publicId, next.id), {}, { preserveScroll: true });
    refs.current.get(next.id)?.focus();
  }

  return (
    <div className="border-border relative border-b">
      {canScrollLeft ? (
        <div className="from-background via-background/80 pointer-events-none absolute inset-y-0 left-0 z-10 flex items-center bg-gradient-to-r to-transparent pr-8 pl-0.5">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="pointer-events-auto size-7 rounded-full shadow-xs"
            aria-label="Scroll tabs left"
            onClick={() => scrollByPage(-1)}
          >
            <ChevronLeft className="size-4" aria-hidden />
          </Button>
        </div>
      ) : null}
      <div
        ref={scrollerRef}
        role="tablist"
        aria-label="Transaction workspace sections"
        onKeyDown={onKeyDown}
        className="flex items-center gap-1 overflow-x-auto scrollbar-none"
      >
        {live.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`txn-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`txn-panel-${tab.id}`}
              aria-disabled={tab.stub || undefined}
              tabIndex={selected ? 0 : -1}
              ref={(node) => {
                if (node) refs.current.set(tab.id, node);
                else refs.current.delete(tab.id);
              }}
              onClick={() => {
                if (tab.stub) return;
                router.get(sectionHref(publicId, tab.id), {}, { preserveScroll: true });
              }}
              className={cn(
                "focus-visible:ring-ring relative flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors duration-(--motion-fast) focus-visible:ring-3 focus-visible:-outline-offset-2 focus-visible:outline-none",
                selected
                  ? "text-foreground"
                  : tab.stub
                    ? "text-muted-foreground/60 cursor-not-allowed"
                    : "text-muted-foreground hover:text-foreground",
              )}
            >
              {selected ? (
                <span
                  className="bg-primary absolute inset-x-0 -bottom-px h-0.5"
                  aria-hidden
                />
              ) : null}
              {tab.label}
              {tab.stub ? (
                <span className="text-muted-foreground text-xs">Soon</span>
              ) : null}
            </button>
          );
        })}
      </div>
      {canScrollRight ? (
        <div className="from-background via-background/80 pointer-events-none absolute inset-y-0 right-0 z-10 flex items-center bg-gradient-to-l to-transparent pr-0.5 pl-8">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="pointer-events-auto size-7 rounded-full shadow-xs"
            aria-label="Scroll tabs right"
            onClick={() => scrollByPage(1)}
          >
            <ChevronRight className="size-4" aria-hidden />
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function OverviewPanel({ props }: { props: TransactionWorkspacePageProps }) {
  const { transaction, activityTeaser } = props;
  const propertyLine = [
    transaction.property?.line1,
    transaction.property?.city,
    transaction.property?.state,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)] lg:items-start">
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

      {activityTeaser ? (
        <ActivityTimeline title="Recent activity" compactEmpty page={activityTeaser} />
      ) : null}
    </div>
  );
}

function PartiesPanel({
  parties,
  expectedVersion,
  publicId,
  canEdit,
  canSeeContacts,
  errors,
}: {
  parties: TransactionPartyRow[];
  expectedVersion: string;
  publicId: string;
  canEdit: boolean;
  canSeeContacts: boolean;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [role, setRole] = useState("buyer");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [isPrimary, setIsPrimary] = useState(true);
  const [busy, setBusy] = useState(false);

  function save() {
    setBusy(true);
    router.post(
      routes.transaction_party_save(publicId),
      {
        expectedVersion,
        role,
        displayName,
        email,
        phone,
        isPrimary,
        kind: "person",
      },
      { onFinish: () => setBusy(false) },
    );
  }

  return (
    <div className="grid gap-6">
      <h2 className="text-lg font-medium">Parties</h2>
      {parties.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No parties yet"
          description="Add buyers, sellers, vendors, or co-parties for this deal."
          compact
        />
      ) : (
        <ul className="grid gap-2">
          {parties.map((row) => (
            <li
              key={row.publicId}
              className="border-border/60 flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
            >
              <div>
                <p className="font-medium">
                  {row.displayName}
                  {row.isPrimary ? (
                    <span className="text-muted-foreground ml-2 text-xs">Primary</span>
                  ) : null}
                </p>
                <p className="text-muted-foreground">{row.roleLabel}</p>
                {canSeeContacts && (row.email || row.phone) ? (
                  <p className="text-muted-foreground text-xs">
                    {[row.email, row.phone].filter(Boolean).join(" · ")}
                  </p>
                ) : null}
              </div>
              {canEdit ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    router.post(routes.transaction_party_end(publicId), {
                      expectedVersion,
                      partyPublicId: row.publicId,
                    })
                  }
                >
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {canEdit ? (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4 py-5">
            <p className="text-sm font-medium">Add party</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="party-role">Role</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger id="party-role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PARTY_ROLES.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormFieldError messages={errors?.fields?.role} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="party-name">Display name</Label>
                <Input
                  id="party-name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
                <FormFieldError messages={errors?.fields?.displayName} />
              </div>
              {canSeeContacts ? (
                <>
                  <div className="grid gap-1.5">
                    <Label htmlFor="party-email">Email</Label>
                    <Input
                      id="party-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="party-phone">Phone</Label>
                    <Input
                      id="party-phone"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                    />
                  </div>
                </>
              ) : null}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isPrimary}
                onChange={(e) => setIsPrimary(e.target.checked)}
              />
              Primary for this role
            </label>
            <FormActionBar status={busy ? "Saving…" : "Adds a party to this deal."}>
              <Button type="button" disabled={busy || !displayName} onClick={save}>
                Save party
              </Button>
            </FormActionBar>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

function PropertyPanel({ props }: { props: TransactionWorkspacePageProps }) {
  const { transaction, expectedVersion, capabilities, propertyHistory, errors } = props;
  const [line1, setLine1] = useState(transaction.property?.line1 || "");
  const [city, setCity] = useState(transaction.property?.city || "");
  const [state, setState] = useState(transaction.property?.state || "");
  const [postalCode, setPostalCode] = useState(transaction.property?.postalCode || "");
  const [mlsNumber, setMlsNumber] = useState(transaction.mlsNumber || "");
  const [busy, setBusy] = useState(false);

  function save() {
    setBusy(true);
    router.post(
      routes.transaction_property_save(transaction.publicId),
      {
        expectedVersion,
        mlsNumber,
        line1,
        city,
        state,
        postal_code: postalCode,
      },
      { onFinish: () => setBusy(false) },
    );
  }

  return (
    <div className="grid gap-6">
      <h2 className="text-lg font-medium">Property</h2>
      {capabilities.manage ? (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-3 py-5 sm:grid-cols-2">
            <div className="grid gap-1.5 sm:col-span-2">
              <Label htmlFor="prop-line1">Street</Label>
              <Input
                id="prop-line1"
                value={line1}
                onChange={(e) => setLine1(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="prop-city">City</Label>
              <Input
                id="prop-city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="prop-state">State</Label>
              <Input
                id="prop-state"
                value={state}
                onChange={(e) => setState(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="prop-postal">Postal code</Label>
              <Input
                id="prop-postal"
                value={postalCode}
                onChange={(e) => setPostalCode(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="prop-mls">MLS number</Label>
              <Input
                id="prop-mls"
                value={mlsNumber}
                onChange={(e) => setMlsNumber(e.target.value)}
              />
            </div>
            <FormActionBar
              className="sm:col-span-2"
              status={busy ? "Saving…" : "Updates the property snapshot."}
            >
              <Button type="button" disabled={busy} onClick={save}>
                Save property
              </Button>
            </FormActionBar>
            <FormFieldError messages={errors?.fields?.property} />
          </SurfaceCardContent>
        </SurfaceCard>
      ) : (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
            <ReadOnlyValue label="Street">
              {transaction.property?.line1 || "—"}
            </ReadOnlyValue>
            <ReadOnlyValue label="MLS">{transaction.mlsNumber || "—"}</ReadOnlyValue>
          </SurfaceCardContent>
        </SurfaceCard>
      )}

      {propertyHistory.length > 0 ? (
        <div className="grid gap-2">
          <h3 className="text-sm font-medium">History</h3>
          <ul className="text-muted-foreground grid gap-1 text-sm">
            {propertyHistory.map((row) => (
              <li key={row.publicId}>
                {row.recordedAt || "—"} ·{" "}
                {(row.changeSummary || []).join(", ") || "updated"}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function DatesPanel({
  keyDates,
  expectedVersion,
  publicId,
  canEdit,
  errors,
}: {
  keyDates: TransactionKeyDateRow[];
  expectedVersion: string;
  publicId: string;
  canEdit: boolean;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [dateType, setDateType] = useState("closing");
  const [occursAt, setOccursAt] = useState("");
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Chicago",
  );
  const [busy, setBusy] = useState(false);

  function save() {
    setBusy(true);
    router.post(
      routes.transaction_key_date_save(publicId),
      { expectedVersion, dateType, occursAt, timezone, isRequired: false },
      { onFinish: () => setBusy(false) },
    );
  }

  return (
    <div className="grid gap-6">
      <h2 className="text-lg font-medium">Key dates</h2>
      {keyDates.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title="No key dates"
          description="Track acceptance, closing, and contingency deadlines here."
          compact
        />
      ) : (
        <ul className="grid gap-2">
          {keyDates.map((row) => (
            <li
              key={row.publicId}
              className="border-border/60 flex items-center justify-between rounded-md border px-3 py-2 text-sm"
            >
              <div>
                <p className="font-medium">{row.dateTypeLabel}</p>
                <p className="text-muted-foreground">
                  {row.occursAt || "Unset"}
                  {row.timezone ? ` · ${row.timezone}` : ""}
                </p>
              </div>
              {canEdit ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    router.post(routes.transaction_key_date_end(publicId), {
                      expectedVersion,
                      keyDatePublicId: row.publicId,
                    })
                  }
                >
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-3 py-5 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="date-type">Type</Label>
              <Select value={dateType} onValueChange={setDateType}>
                <SelectTrigger id="date-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DATE_TYPES.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormFieldError messages={errors?.fields?.dateType} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="date-occurs">Occurs at</Label>
              <DatePicker
                id="date-occurs"
                value={occursAt}
                onChange={setOccursAt}
                includeTime
                placeholder="Pick date and time"
                disabled={busy}
                invalid={Boolean(errors?.fields?.occursAt?.length)}
              />
              <FormFieldError messages={errors?.fields?.occursAt} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="date-tz">Timezone</Label>
              <TimezonePicker
                id="date-tz"
                value={timezone}
                onChange={setTimezone}
                disabled={busy}
                invalid={Boolean(errors?.fields?.timezone?.length)}
              />
              <FormFieldError messages={errors?.fields?.timezone} />
            </div>
            <FormActionBar
              className="sm:col-span-2"
              status={busy ? "Saving…" : "Records a key date."}
            >
              <Button type="button" disabled={busy} onClick={save}>
                Save date
              </Button>
            </FormActionBar>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

function NotesPanel({
  notes,
  expectedVersion,
  publicId,
  canEdit,
  viewBrokerNotes,
  errors,
}: {
  notes: TransactionNoteRow[];
  expectedVersion: string;
  publicId: string;
  canEdit: boolean;
  viewBrokerNotes: boolean;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState("team");
  const [busy, setBusy] = useState(false);
  const options = NOTE_VISIBILITIES.filter(
    (opt) => opt.value !== "broker_compliance" || viewBrokerNotes,
  );

  function save() {
    setBusy(true);
    router.post(
      routes.transaction_note_save(publicId),
      { expectedVersion, body, visibility },
      {
        onFinish: () => setBusy(false),
        onSuccess: () => setBody(""),
      },
    );
  }

  return (
    <div className="grid gap-6">
      <h2 className="text-lg font-medium">Notes</h2>
      {notes.length === 0 ? (
        <EmptyState
          icon={StickyNote}
          title="No notes in view"
          description="Notes are filtered by visibility — only what you are allowed to see appears here."
          compact
        />
      ) : (
        <ul className="grid gap-3">
          {notes.map((row) => (
            <li
              key={row.publicId}
              className="border-border/60 rounded-md border px-3 py-3 text-sm"
            >
              <div className="text-muted-foreground mb-1 flex flex-wrap gap-2 text-xs">
                <span>{row.visibilityLabel}</span>
                <span>{row.author?.displayName || "Unknown"}</span>
                <span>{row.createdAt || ""}</span>
              </div>
              <p className="whitespace-pre-wrap">{row.body}</p>
              {canEdit && row.mine ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() =>
                    router.post(routes.transaction_note_end(publicId), {
                      expectedVersion,
                      notePublicId: row.publicId,
                    })
                  }
                >
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-3 py-5">
            <div className="grid gap-1.5">
              <Label htmlFor="note-visibility">Visibility</Label>
              <Select value={visibility} onValueChange={setVisibility}>
                <SelectTrigger id="note-visibility">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {options.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormFieldError messages={errors?.fields?.visibility} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="note-body">Note</Label>
              <Textarea
                id="note-body"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={4}
              />
              <FormFieldError messages={errors?.fields?.body} />
            </div>
            <FormActionBar
              status={busy ? "Saving…" : "Posts a visibility-scoped note."}
            >
              <Button type="button" disabled={busy || !body.trim()} onClick={save}>
                Save note
              </Button>
            </FormActionBar>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

function AssignmentsPanel({ props }: { props: TransactionWorkspacePageProps }) {
  const { transaction } = props;
  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-medium">Assignments</h2>
      {transaction.assignments.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No active assignments"
          description="Primary agent and coordinator appear here when assigned."
          compact
        />
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
    </div>
  );
}

function StubPanel({ label }: { label: string }) {
  return (
    <Callout tone="info" title={`${label} coming soon`}>
      This section lands in a later transaction epic (#103–#106).
    </Callout>
  );
}

export default function TransactionWorkspace() {
  const props = usePage<TransactionWorkspacePageProps>().props;
  const {
    transaction,
    section,
    sections,
    expectedVersion,
    capabilities,
    parties,
    keyDates,
    notes,
    documents,
    documentSchema,
    signaturePackages,
    signatureSchema,
    activity,
    errors,
  } = props;

  useValidationToasts(errors);

  const activeSection = sections.find((s) => s.id === section)?.id || "overview";
  const propertyLine = [
    transaction.property?.line1,
    transaction.property?.city,
    transaction.property?.state,
  ]
    .filter(Boolean)
    .join(", ");
  const typeLine = [
    transaction.transactionTypeLabel || transaction.transactionType,
    transaction.representationTypeLabel || transaction.representationType,
  ]
    .filter(Boolean)
    .join(" · ");
  const metaBits = [
    typeLine || null,
    transaction.office?.name || null,
    transaction.primaryAgent?.displayName
      ? `Agent ${transaction.primaryAgent.displayName}`
      : null,
    transaction.mlsNumber ? `MLS ${transaction.mlsNumber}` : null,
    transaction.closingDate ? `Closing ${transaction.closingDate}` : null,
  ].filter(Boolean) as string[];

  return (
    <PermissionRequired permission={ACCESS}>
      <Head title={transaction.reference || "Transaction"} />
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 py-4">
        <PageHeader
          rule={false}
          className="gap-2"
          breadcrumbs={
            <Link
              href={routes.my_transactions()}
              className="hover:text-foreground transition-colors"
            >
              Transactions
            </Link>
          }
          title={transaction.reference || "Transaction"}
          description={propertyLine || undefined}
          meta={
            <>
              <StatusBadge status={{ label: transaction.statusLabel, tone: "info" }} />
              {metaBits.map((bit) => (
                <Fragment key={bit}>
                  <span aria-hidden>·</span>
                  <span>{bit}</span>
                </Fragment>
              ))}
            </>
          }
        />

        <WorkspaceTabs
          sections={sections}
          active={activeSection}
          publicId={transaction.publicId}
        />

        <div
          role="tabpanel"
          id={`txn-panel-${activeSection}`}
          aria-labelledby={`txn-tab-${activeSection}`}
          className="min-h-48"
        >
          {activeSection === "overview" ? <OverviewPanel props={props} /> : null}
          {activeSection === "parties" ? (
            <PartiesPanel
              parties={parties}
              expectedVersion={expectedVersion}
              publicId={transaction.publicId}
              canEdit={capabilities.manage}
              canSeeContacts={capabilities.viewClients}
              errors={errors}
            />
          ) : null}
          {activeSection === "property" ? <PropertyPanel props={props} /> : null}
          {activeSection === "dates" ? (
            <DatesPanel
              keyDates={keyDates}
              expectedVersion={expectedVersion}
              publicId={transaction.publicId}
              canEdit={capabilities.manage}
              errors={errors}
            />
          ) : null}
          {activeSection === "notes" ? (
            <NotesPanel
              notes={notes}
              expectedVersion={expectedVersion}
              publicId={transaction.publicId}
              canEdit={capabilities.manage}
              viewBrokerNotes={capabilities.viewBrokerNotes}
              errors={errors}
            />
          ) : null}
          {activeSection === "assignments" ? <AssignmentsPanel props={props} /> : null}
          {activeSection === "documents" ? (
            <DocumentsPanel
              documents={documents}
              documentSchema={documentSchema}
              expectedVersion={expectedVersion}
              publicId={transaction.publicId}
              canEdit={capabilities.manage}
              canLock={capabilities.manage || capabilities.transition}
              errors={errors}
            />
          ) : null}
          {activeSection === "signatures" ? (
            <SignaturesPanel
              signaturePackages={signaturePackages}
              signatureSchema={signatureSchema}
              documents={documents}
              parties={parties}
              expectedVersion={expectedVersion}
              publicId={transaction.publicId}
              canEdit={capabilities.manage}
              errors={errors}
            />
          ) : null}
          {activeSection === "activity" ? (
            activity ? (
              <ActivityTimeline title="Activity" page={activity} />
            ) : (
              <EmptyState
                icon={ClipboardList}
                title="No activity yet"
                description="Lifecycle and field changes will appear here."
                compact
              />
            )
          ) : null}
          {["checklist", "tasks", "commission", "compliance"].includes(
            activeSection,
          ) ? (
            <StubPanel
              label={
                sections.find((s) => s.id === activeSection)?.label || activeSection
              }
            />
          ) : null}
        </div>
      </div>
    </PermissionRequired>
  );
}

TransactionWorkspace.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
