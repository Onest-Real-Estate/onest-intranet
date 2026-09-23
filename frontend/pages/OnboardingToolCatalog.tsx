import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Globe,
  Lock,
  Pencil,
  Plus,
  Search,
  TriangleAlert,
  X,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  EmptyState,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  FormSheet,
  FormSheetBody,
  NativeSelect,
  PageHeader,
  ReadOnlyValue,
  SearchControl,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  CatalogOffice,
  CatalogTool,
  OnboardingToolCatalogPageProps,
} from "@/types";
import type { ValidationErrors } from "@/types/design-system";

type Props = OnboardingToolCatalogPageProps;
type Filters = Props["filters"];

/** The same rule the server applies when the identifier is left blank, so the
 *  preview under the field is the value that will be stored. */
function slugify(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/\p{Diacritic}/gu, "")
    .trim()
    .replace(/[\s-]+/g, "-")
    .slice(0, 60)
    .replace(/^-+|-+$/g, "");
}

/** Navigate within the catalog, keeping the list's own filters. */
function visitCatalog(filters: Filters, extra: Record<string, string> = {}) {
  const data: Record<string, string> = { ...extra };
  if (filters.q) data.q = filters.q;
  if (filters.show !== "all") data.show = filters.show;
  router.get(routes.onboarding_tool_catalog(), data, {
    preserveScroll: true,
    preserveState: true,
    replace: true,
  });
}

/* -------------------------------------------------------------------------- */
/* Summary                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Four figures on one rule. The two that ask for work — rows with gaps, and
 * agents waiting on a check — are the ones that act: the first narrows the
 * list, the second opens the queue where the check is made.
 */
function CatalogSummary({
  summary,
  teamReadiness,
  onShowAttention,
}: {
  summary: Props["summary"];
  teamReadiness: string;
  onShowAttention: () => void;
}) {
  return (
    <section
      aria-label="Catalog summary"
      className="bg-card shadow-card @container/summary rounded-(--radius-card) border"
    >
      <dl className="grid @2xl/summary:grid-cols-4 @2xl/summary:divide-x @max-2xl/summary:grid-cols-2 @max-2xl/summary:[&>*:nth-child(n+3)]:border-t @max-2xl/summary:[&>*:nth-child(even)]:border-l">
        <SummaryFigure label="Active tools">
          <span className="tabular-nums">{summary.active}</span>
          {summary.inactive > 0 ? (
            <span className="text-muted-foreground text-sm font-normal">
              {" "}
              · {summary.inactive} retired
            </span>
          ) : null}
        </SummaryFigure>
        <SummaryFigure label="With published training">
          <span className="tabular-nums">{summary.trained}</span>
          <span className="text-muted-foreground text-sm font-normal">
            {" "}
            of {summary.active}
          </span>
        </SummaryFigure>
        <SummaryFigure label="Need attention">
          {summary.attention > 0 ? (
            <button
              type="button"
              onClick={onShowAttention}
              className="text-warning-ink focus-visible:ring-ring/50 inline-flex items-center gap-1.5 rounded-sm tabular-nums underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
            >
              <TriangleAlert className="size-4" aria-hidden />
              {summary.attention}
            </button>
          ) : (
            <span className="text-success inline-flex items-center gap-1.5">
              <Check className="size-4" aria-hidden />
              None
            </span>
          )}
        </SummaryFigure>
        <SummaryFigure label="Agent ticks to confirm">
          {summary.awaiting > 0 ? (
            <Link
              href={teamReadiness}
              className="text-info focus-visible:ring-ring/50 rounded-sm tabular-nums underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
            >
              {summary.awaiting}
            </Link>
          ) : (
            <span className="tabular-nums">0</span>
          )}
        </SummaryFigure>
      </dl>
    </section>
  );
}

function SummaryFigure({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1 px-5 py-4">
      <dt className="text-muted-foreground text-xs font-semibold tracking-[0.02em]">
        {label}
      </dt>
      <dd className="text-metric font-bold tracking-[-0.02em]">{children}</dd>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Toolbar                                                                     */
/* -------------------------------------------------------------------------- */

function CatalogToolbar({
  filters,
  options,
  attention,
}: {
  filters: Filters;
  options: Props["options"]["show"];
  attention: number;
}) {
  const [q, setQ] = useState(filters.q);
  const first = useRef(true);

  // Typing narrows the list without a keypress per visit: the query settles
  // for a moment, then one `replace` visit, so history does not fill with
  // every letter.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (q === filters.q) return;
    const timer = window.setTimeout(() => visitCatalog({ ...filters, q }), 250);
    return () => window.clearTimeout(timer);
  }, [q, filters]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <fieldset className="bg-muted inline-flex flex-wrap gap-0.5 rounded-md border-0 p-0.5">
        <legend className="sr-only">Show</legend>
        {options.map((option) => {
          const active = filters.show === option.value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              onClick={() =>
                visitCatalog({ ...filters, show: option.value as Filters["show"] })
              }
              className={cn(
                "focus-visible:ring-ring/50 inline-flex h-8 items-center gap-1.5 rounded-sm px-3 text-sm font-medium outline-none transition-colors duration-(--motion-fast) focus-visible:ring-[3px]",
                active
                  ? "bg-card text-foreground shadow-card"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option.label}
              {option.value === "attention" && attention > 0 ? (
                <span className="bg-chip-warning text-warning-ink border-chip-warning-edge rounded-sm border px-1 text-xs tabular-nums">
                  {attention}
                </span>
              ) : null}
            </button>
          );
        })}
      </fieldset>
      <SearchControl
        value={q}
        onValueChange={setQ}
        onSearch={(value) => visitCatalog({ ...filters, q: value })}
        onClear={() => {
          setQ("");
          visitCatalog({ ...filters, q: "" });
        }}
        label="Search tools"
        placeholder="Search by name or identifier"
        size="sm"
        className="w-full max-w-xs"
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Rows                                                                        */
/* -------------------------------------------------------------------------- */

const ROW_GRID =
  "grid gap-x-4 gap-y-2 @4xl/list:grid-cols-[minmax(0,2.4fr)_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.1fr)_auto] @4xl/list:items-center";

function ColumnHeads() {
  return (
    <div
      aria-hidden
      className={cn(
        ROW_GRID,
        "text-muted-foreground hidden h-11 items-center border-b pr-5 pl-12 text-micro font-semibold tracking-[0.06em] uppercase @4xl/list:grid",
      )}
    >
      <span>Tool</span>
      <span>Applies to</span>
      <span>Training</span>
      <span>Agents in your reach</span>
      <span className="w-16" />
    </div>
  );
}

function AppliesTo({ tool }: { tool: CatalogTool }) {
  if (tool.companyWide) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm">
        <Globe className="text-muted-foreground size-3.5" aria-hidden />
        Every office
      </span>
    );
  }
  if (tool.audience.length === 0) {
    return <span className="text-warning-ink text-sm">Nobody yet</span>;
  }
  const [first, ...rest] = tool.audience;
  return (
    <span
      className="min-w-0 text-sm"
      title={tool.audience.map((row) => row.path).join("\n")}
    >
      <span className="block truncate">{first.name}</span>
      {rest.length > 0 ? (
        <span className="text-muted-foreground text-xs">+{rest.length} more</span>
      ) : null}
    </span>
  );
}

function TrainingCoverage({ tool }: { tool: CatalogTool }) {
  const { published, draft } = tool.training;
  return (
    <span className="grid text-sm">
      {published > 0 ? (
        <span className="inline-flex items-center gap-1.5">
          <BookOpen className="text-success size-3.5" aria-hidden />
          {published} published
        </span>
      ) : (
        <span className="text-warning-ink inline-flex items-center gap-1.5">
          <CircleAlert className="size-3.5" aria-hidden />
          None published
        </span>
      )}
      {draft > 0 ? (
        <span className="text-muted-foreground text-xs">{draft} in draft</span>
      ) : null}
    </span>
  );
}

function Adoption({
  tool,
  teamReadiness,
}: {
  tool: CatalogTool;
  teamReadiness: string;
}) {
  const { ready, blocked, awaiting } = tool.adoption;
  if (ready + blocked + awaiting === 0) {
    return <span className="text-muted-foreground text-sm">No activity yet</span>;
  }
  return (
    <span className="grid text-sm">
      <span className="tabular-nums">{ready} ready</span>
      <span className="flex flex-wrap gap-x-2 text-xs">
        {awaiting > 0 ? (
          <Link
            href={teamReadiness}
            className="text-info tabular-nums underline-offset-4 hover:underline"
          >
            {awaiting} to confirm
          </Link>
        ) : null}
        {blocked > 0 ? (
          <span className="text-destructive tabular-nums">{blocked} blocked</span>
        ) : null}
      </span>
    </span>
  );
}

function CatalogRow({
  tool,
  index,
  count,
  canReorder,
  teamReadiness,
  onMove,
  onEdit,
}: {
  tool: CatalogTool;
  index: number;
  count: number;
  canReorder: boolean;
  teamReadiness: string;
  onMove: (index: number, delta: -1 | 1) => void;
  onEdit: (slug: string) => void;
}) {
  // Training has its own column, so the inline line names the other gaps. A
  // missing audience is a real gap; a missing open link is only a hint, so it
  // reads in the muted voice instead of competing with the warnings.
  const gaps = tool.health.filter((issue) => issue.code === "no_audience");
  const hints = tool.health.filter((issue) => issue.code === "no_open_link");

  return (
    <li
      aria-label={tool.name}
      className={cn(
        "flex items-start gap-3 border-b py-3.5 pr-5 pl-3 last:border-b-0 @4xl/list:items-center",
        "transition-colors duration-(--motion-fast) hover:bg-muted/40",
        !tool.active && "bg-muted/30",
      )}
    >
      <div className="flex shrink-0 flex-col">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground size-6"
          disabled={!canReorder || index === 0}
          onClick={() => onMove(index, -1)}
          aria-label={`Move ${tool.name} up`}
        >
          <ChevronUp aria-hidden />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground size-6"
          disabled={!canReorder || index === count - 1}
          onClick={() => onMove(index, 1)}
          aria-label={`Move ${tool.name} down`}
        >
          <ChevronDown aria-hidden />
        </Button>
      </div>

      <div className={cn(ROW_GRID, "min-w-0 flex-1")}>
        <div className="grid min-w-0 gap-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <button
              type="button"
              onClick={() => onEdit(tool.slug)}
              className={cn(
                "focus-visible:ring-ring/50 rounded-sm text-left text-sm font-semibold outline-none underline-offset-4 hover:underline focus-visible:ring-[3px]",
                !tool.active && "text-muted-foreground",
              )}
            >
              {tool.name}
            </button>
            {tool.active ? null : (
              <span className="bg-chip-neutral border-chip-neutral-edge text-muted-foreground rounded-sm border px-1.5 text-xs font-medium">
                Retired
              </span>
            )}
            {tool.required ? null : (
              <span className="text-muted-foreground text-xs font-medium">
                Optional
              </span>
            )}
          </div>
          <p className="text-muted-foreground truncate text-xs">
            {tool.provisioningLabel} · {tool.description}
          </p>
          {gaps.length > 0 ? (
            <p className="text-warning-ink flex flex-wrap items-center gap-x-1.5 text-xs">
              <TriangleAlert className="size-3" aria-hidden />
              {gaps.map((issue) => issue.label).join(" · ")}
            </p>
          ) : null}
          {hints.length > 0 ? (
            <p className="text-muted-foreground text-xs">
              {hints.map((issue) => issue.label).join(" · ")}
            </p>
          ) : null}
        </div>
        <AppliesTo tool={tool} />
        <TrainingCoverage tool={tool} />
        <Adoption tool={tool} teamReadiness={teamReadiness} />
        <div className="@4xl/list:w-16 @4xl/list:text-right">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onEdit(tool.slug)}
            aria-label={`Edit ${tool.name}`}
          >
            <Pencil aria-hidden />
            Edit
          </Button>
        </div>
      </div>
    </li>
  );
}

/* -------------------------------------------------------------------------- */
/* Editor                                                                      */
/* -------------------------------------------------------------------------- */

interface EditorState {
  name: string;
  slug: string;
  description: string;
  group: string;
  provisioning: string;
  openUrl: string;
  helpUrl: string;
  requestPath: string;
  contact: string;
  companyWide: boolean;
  required: boolean;
  active: boolean;
  sortOrder: string;
  steps: string[];
  officeIds: number[];
}

function initialState(tool: CatalogTool | null, draft: Props["draft"]): EditorState {
  return {
    name: draft.name ?? tool?.name ?? "",
    slug: draft.slug ?? tool?.slug ?? "",
    description: draft.description ?? tool?.description ?? "",
    group: draft.group ?? tool?.group ?? "",
    provisioning: draft.provisioning ?? tool?.provisioning ?? "",
    openUrl: draft.openUrl ?? tool?.openUrl ?? "",
    helpUrl: draft.helpUrl ?? tool?.helpUrl ?? "",
    requestPath: draft.requestPath ?? tool?.requestPath ?? "",
    contact: draft.contact ?? tool?.contact ?? "",
    companyWide: draft.companyWide ?? tool?.companyWide ?? true,
    required: draft.required ?? tool?.required ?? true,
    active: draft.active ?? tool?.active ?? true,
    sortOrder: String(draft.sortOrder ?? tool?.sortOrder ?? 0),
    steps: draft.steps ?? tool?.steps ?? [],
    officeIds: draft.officeIds ?? tool?.officeIds ?? [],
  };
}

/**
 * Steps as an ordered list of fields. A textarea split on newlines silently
 * gains a step the moment somebody pastes a wrapped sentence.
 */
function StepsEditor({
  steps,
  max,
  onChange,
  error,
}: {
  steps: string[];
  max: number;
  onChange: (next: string[]) => void;
  error?: string;
}) {
  const rows = steps.length > 0 ? steps : [""];

  function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const next = [...rows];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <FormField>
      <FormLabel htmlFor="step-0" optional>
        Setup steps
      </FormLabel>
      <FormDescription id="steps-help">
        What the agent does, in order. Leave empty for a tool oNEST provisions — the
        contact below is what they see instead.
      </FormDescription>
      <ol className="grid gap-2">
        {rows.map((step, index) => (
          // Position is the identity: two steps may hold the same text while
          // being edited, and reordering must not remount their inputs.
          // biome-ignore lint/suspicious/noArrayIndexKey: position is the identity
          <li key={index} className="flex items-center gap-2">
            <span className="text-muted-foreground w-5 shrink-0 text-right text-xs tabular-nums">
              {index + 1}.
            </span>
            <Input
              id={`step-${index}`}
              value={step}
              maxLength={200}
              onChange={(event) =>
                onChange(rows.map((row, i) => (i === index ? event.target.value : row)))
              }
              placeholder="Go to narrpr.com and choose Create Account."
              aria-label={`Step ${index + 1}`}
            />
            <div className="flex shrink-0 items-center">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8"
                disabled={index === 0}
                onClick={() => move(index, -1)}
                aria-label={`Move step ${index + 1} up`}
              >
                <ArrowUp aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8"
                disabled={index === rows.length - 1}
                onClick={() => move(index, 1)}
                aria-label={`Move step ${index + 1} down`}
              >
                <ArrowDown aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={() =>
                  onChange(rows.length === 1 ? [] : rows.filter((_, i) => i !== index))
                }
                aria-label={`Remove step ${index + 1}`}
              >
                <X aria-hidden />
              </Button>
            </div>
          </li>
        ))}
      </ol>
      {rows.length < max ? (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onChange([...rows, ""])}
          >
            <Plus aria-hidden />
            Add step
          </Button>
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">
          {max} steps is the limit. Longer than that is a document — link to it instead.
        </p>
      )}
      <FormFieldError id="setup_steps_error" message={error} />
    </FormField>
  );
}

/**
 * A searchable, path-labelled office picker.
 *
 * The flat list it replaces named "Branford" and "Branford" with nothing to
 * tell them apart. Every option carries its path, the search matches it, and
 * what is chosen sits above as removable chips so the answer to "who gets
 * this" is readable without scrolling a list.
 */
function OfficePicker({
  offices,
  selected,
  onChange,
  error,
}: {
  offices: CatalogOffice[];
  selected: number[];
  onChange: (next: number[]) => void;
  error?: string;
}) {
  const [query, setQuery] = useState("");
  const byId = useMemo(
    () => new Map(offices.map((office) => [Number(office.value), office])),
    [offices],
  );
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle
      ? offices.filter((office) => office.path.toLowerCase().includes(needle))
      : offices;
  }, [offices, query]);

  function toggle(id: number, on: boolean) {
    onChange(on ? [...selected, id] : selected.filter((value) => value !== id));
  }

  return (
    <div className="grid gap-2">
      {selected.length > 0 ? (
        <ul aria-label="Chosen offices" className="flex flex-wrap gap-1.5">
          {selected.map((id) => {
            const office = byId.get(id);
            const label = office?.label ?? `Office ${id}`;
            return (
              <li key={id}>
                <span
                  title={office?.path}
                  className="bg-chip-neutral border-chip-neutral-edge inline-flex h-7 items-center gap-1 rounded-sm border pr-1 pl-2 text-xs font-medium"
                >
                  {label}
                  <button
                    type="button"
                    onClick={() => toggle(id, false)}
                    aria-label={`Remove ${label}`}
                    className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 grid size-5 place-items-center rounded-sm outline-none focus-visible:ring-[3px]"
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className="rounded-md border">
        <div className="relative border-b">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
            aria-hidden
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find an office, region, or state"
            aria-label="Find an office"
            aria-describedby="offices-help"
            className="placeholder:text-muted-foreground h-9 w-full bg-transparent pr-3 pl-9 text-sm outline-none"
          />
        </div>
        <ul aria-label="Offices" className="max-h-60 overflow-y-auto p-1">
          {visible.length === 0 ? (
            <li className="text-muted-foreground px-2 py-3 text-sm">
              No office matches “{query}”.
            </li>
          ) : (
            visible.map((office) => {
              const id = Number(office.value);
              const checked = selected.includes(id);
              const control = `office-${office.value}`;
              return (
                <li key={office.value}>
                  <label
                    htmlFor={control}
                    className="hover:bg-muted/60 flex cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1.5"
                  >
                    <Checkbox
                      id={control}
                      checked={checked}
                      onCheckedChange={(next) => toggle(id, next === true)}
                    />
                    <span className="grid min-w-0">
                      <span className="truncate text-sm">{office.label}</span>
                      {office.path !== office.label ? (
                        <span className="text-muted-foreground truncate text-xs">
                          {office.path}
                        </span>
                      ) : null}
                    </span>
                  </label>
                </li>
              );
            })
          )}
        </ul>
      </div>
      <FormFieldError id="offices_error" message={error} />
    </div>
  );
}

function EditorSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 border-b pb-6 last:border-b-0 last:pb-0">
      <div className="grid gap-0.5">
        <h3 className="text-sm font-semibold">{title}</h3>
        {description ? (
          <p className="text-muted-foreground max-w-measure text-xs">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function ToggleRow({
  id,
  checked,
  onChange,
  title,
  description,
}: {
  id: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  title: string;
  description: string;
}) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-3 text-sm">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(next) => onChange(next === true)}
        className="mt-0.5"
      />
      <span className="grid gap-0.5">
        <span className="font-medium">{title}</span>
        <span className="text-muted-foreground text-xs">{description}</span>
      </span>
    </label>
  );
}

function fieldError(errors: ValidationErrors, field: string): string | undefined {
  return errors.fields[field]?.[0];
}

const ERROR_LABELS: Record<string, string> = {
  name: "Name",
  slug: "Identifier",
  description: "What it is for",
  group: "Shelf",
  provisioning: "Who creates the account",
  open_url: "Open link",
  help_url: "Vendor help link",
  request_path: "Support link",
  contact_label: "Who to contact",
  offices: "Applies to",
  setup_steps: "Setup steps",
};

/**
 * One tool, in a side sheet over the list.
 *
 * The list stays on screen behind it, which is what the inline editor was
 * for — "does this read right next to its neighbours" — without pushing every
 * row below it down the page. Posts through Inertia with the page's own
 * validation contract; a refused save re-renders with the sheet still open and
 * everything typed still in the fields.
 */
function ToolEditor({
  tool,
  props,
  onClose,
}: {
  tool: CatalogTool | null;
  props: Props;
  onClose: () => void;
}) {
  const { offices, options, maxSteps, errors, draft, links } = props;
  const [state, setState] = useState<EditorState>(() => initialState(tool, draft));
  const [processing, setProcessing] = useState(false);
  const set = <K extends keyof EditorState>(key: K, value: EditorState[K]) =>
    setState((current) => ({ ...current, [key]: value }));
  const derivedSlug = slugify(state.slug || state.name);

  function submit(event: FormEvent) {
    event.preventDefault();
    router.post(
      tool ? routes.onboarding_tool_save(tool.slug) : routes.onboarding_tool_create(),
      {
        name: state.name,
        slug: tool ? tool.slug : state.slug,
        description: state.description,
        group: state.group,
        provisioning: state.provisioning,
        open_url: state.openUrl,
        help_url: state.helpUrl,
        request_path: state.requestPath,
        contact_label: state.contact,
        company_wide: state.companyWide,
        is_required: state.required,
        is_active: state.active,
        sort_order: state.sortOrder,
        step: state.steps.filter((step) => step.trim()),
        offices: state.companyWide ? [] : state.officeIds.map(String),
      },
      {
        preserveScroll: true,
        preserveState: true,
        onStart: () => setProcessing(true),
        onFinish: () => setProcessing(false),
      },
    );
  }

  return (
    <FormSheet
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={tool ? `Edit ${tool.name}` : "Add a tool"}
      description={
        tool
          ? "Changes reach every agent's checklist as soon as you save."
          : "It appears on the checklist of every agent it applies to."
      }
      className="sm:max-w-2xl"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="tool-editor" disabled={processing}>
            {processing ? "Saving…" : tool ? "Save changes" : "Add tool"}
          </Button>
        </div>
      }
    >
      <FormSheetBody>
        <form
          id="tool-editor"
          onSubmit={submit}
          className="@container grid gap-6"
          noValidate
        >
          <FormErrorSummary errors={errors} labels={ERROR_LABELS} />

          <EditorSection title="The tool">
            <div className="grid gap-4 @xl:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="name" required>
                  Name
                </FormLabel>
                <Input
                  id="name"
                  value={state.name}
                  maxLength={80}
                  onChange={(event) => set("name", event.target.value)}
                  aria-invalid={Boolean(fieldError(errors, "name")) || undefined}
                  aria-describedby={
                    fieldError(errors, "name") ? "name_error" : undefined
                  }
                />
                <FormFieldError id="name_error" message={fieldError(errors, "name")} />
              </FormField>
              {tool ? (
                <ReadOnlyValue label="Identifier">
                  <span className="inline-flex items-center gap-1.5 font-mono text-sm">
                    <Lock className="text-muted-foreground size-3.5" aria-hidden />
                    {tool.slug}
                  </span>
                </ReadOnlyValue>
              ) : (
                <FormField>
                  <FormLabel htmlFor="slug" optional>
                    Identifier
                  </FormLabel>
                  <Input
                    id="slug"
                    value={state.slug}
                    maxLength={60}
                    placeholder={derivedSlug || "made-from-the-name"}
                    onChange={(event) => set("slug", event.target.value)}
                    aria-describedby={
                      fieldError(errors, "slug") ? "slug-help slug_error" : "slug-help"
                    }
                    aria-invalid={Boolean(fieldError(errors, "slug")) || undefined}
                  />
                  <FormDescription id="slug-help">
                    {derivedSlug ? (
                      <>
                        Saved as <span className="font-mono">{derivedSlug}</span>.
                      </>
                    ) : (
                      "Made from the name."
                    )}{" "}
                    Training links to it, so it cannot change once saved.
                  </FormDescription>
                  <FormFieldError
                    id="slug_error"
                    message={fieldError(errors, "slug")}
                  />
                </FormField>
              )}
            </div>

            <FormField>
              <FormLabel htmlFor="description" required>
                What it is for
              </FormLabel>
              <Input
                id="description"
                value={state.description}
                maxLength={200}
                onChange={(event) => set("description", event.target.value)}
                placeholder="Transaction documents, signatures, and compliance files."
                aria-describedby={
                  fieldError(errors, "description")
                    ? "description-help description_error"
                    : "description-help"
                }
                aria-invalid={Boolean(fieldError(errors, "description")) || undefined}
              />
              <FormDescription id="description-help">
                In the agent's terms, not the vendor's. Shown on their card.
              </FormDescription>
              <FormFieldError
                id="description_error"
                message={fieldError(errors, "description")}
              />
            </FormField>

            <div className="grid gap-4 @xl:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="group" required>
                  Shelf
                </FormLabel>
                <NativeSelect
                  id="group"
                  value={state.group}
                  onChange={(event) => set("group", event.target.value)}
                  aria-invalid={Boolean(fieldError(errors, "group")) || undefined}
                >
                  <option value="">Choose a shelf</option>
                  {options.groups.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </NativeSelect>
                <FormFieldError
                  id="group_error"
                  message={fieldError(errors, "group")}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="provisioning" required>
                  Who creates the account
                </FormLabel>
                <NativeSelect
                  id="provisioning"
                  value={state.provisioning}
                  onChange={(event) => set("provisioning", event.target.value)}
                  aria-invalid={
                    Boolean(fieldError(errors, "provisioning")) || undefined
                  }
                >
                  <option value="">Choose one</option>
                  {options.provisioning.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </NativeSelect>
                <FormFieldError
                  id="provisioning_error"
                  message={fieldError(errors, "provisioning")}
                />
              </FormField>
            </div>
          </EditorSection>

          <EditorSection
            title="Who gets it"
            description="Naming a region or state covers every office beneath it — an MLS attaches once, not once per branch."
          >
            <ToggleRow
              id="company_wide"
              checked={state.companyWide}
              onChange={(next) => set("companyWide", next)}
              title="Every office"
              description="On every agent's checklist, wherever they work."
            />
            {state.companyWide ? null : (
              <>
                <p id="offices-help" className="sr-only">
                  Choose the offices, regions, or states this tool applies to.
                </p>
                <OfficePicker
                  offices={offices}
                  selected={state.officeIds}
                  onChange={(next) => set("officeIds", next)}
                  error={fieldError(errors, "offices")}
                />
              </>
            )}
            <ToggleRow
              id="is_required"
              checked={state.required}
              onChange={(next) => set("required", next)}
              title="Expected of every agent it reaches"
              description="Counts toward their readiness. Turn off for a tool that is available but optional."
            />
          </EditorSection>

          <EditorSection
            title="How agents get it"
            description="Every tool needs steps, a contact, or both — a card an agent cannot act on is a dead row."
          >
            <StepsEditor
              steps={state.steps}
              max={maxSteps}
              onChange={(next) => set("steps", next)}
              error={fieldError(errors, "setup_steps")}
            />
            <FormField>
              <FormLabel htmlFor="contact_label" optional>
                Who to contact
              </FormLabel>
              <Input
                id="contact_label"
                value={state.contact}
                maxLength={120}
                onChange={(event) => set("contact", event.target.value)}
                placeholder="IT support — we create the seat"
                aria-invalid={Boolean(fieldError(errors, "contact_label")) || undefined}
                aria-describedby={
                  fieldError(errors, "contact_label")
                    ? "contact_label_error"
                    : undefined
                }
              />
              <FormFieldError
                id="contact_label_error"
                message={fieldError(errors, "contact_label")}
              />
            </FormField>
          </EditorSection>

          <EditorSection title="Links on the agent's card">
            <div className="grid gap-4 @xl:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="open_url" optional>
                  Open link
                </FormLabel>
                <Input
                  id="open_url"
                  type="url"
                  value={state.openUrl}
                  onChange={(event) => set("openUrl", event.target.value)}
                  placeholder="https://…"
                  aria-invalid={Boolean(fieldError(errors, "open_url")) || undefined}
                />
                <FormFieldError
                  id="open_url_error"
                  message={fieldError(errors, "open_url")}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="help_url" optional>
                  Vendor help link
                </FormLabel>
                <Input
                  id="help_url"
                  type="url"
                  value={state.helpUrl}
                  onChange={(event) => set("helpUrl", event.target.value)}
                  placeholder="https://…"
                  aria-invalid={Boolean(fieldError(errors, "help_url")) || undefined}
                />
                <FormFieldError
                  id="help_url_error"
                  message={fieldError(errors, "help_url")}
                />
              </FormField>
            </div>
            <FormField>
              <FormLabel htmlFor="request_path" optional>
                Support link
              </FormLabel>
              <Input
                id="request_path"
                value={state.requestPath}
                maxLength={200}
                onChange={(event) => set("requestPath", event.target.value)}
                placeholder="/support/it"
                aria-describedby={
                  fieldError(errors, "request_path")
                    ? "request-path-help request_path_error"
                    : "request-path-help"
                }
                aria-invalid={Boolean(fieldError(errors, "request_path")) || undefined}
              />
              <FormDescription id="request-path-help">
                Where the card's Support button goes. Leave blank to open IT support
                already about this tool.
              </FormDescription>
              <FormFieldError
                id="request_path_error"
                message={fieldError(errors, "request_path")}
              />
            </FormField>
          </EditorSection>

          {tool ? (
            <EditorSection
              title="Training"
              description="An item appears on this tool's card when it is published and tagged with this tool."
            >
              {tool.training.items.length > 0 ? (
                <ul className="grid gap-1">
                  {tool.training.items.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3"
                    >
                      <Link
                        href={item.href}
                        className="truncate text-sm font-medium underline-offset-4 hover:underline"
                      >
                        {item.title}
                      </Link>
                      <span
                        className={cn(
                          "shrink-0 rounded-sm border px-1.5 text-xs font-medium",
                          item.published
                            ? "bg-chip-success border-chip-success-edge text-success"
                            : "bg-chip-neutral border-chip-neutral-edge text-muted-foreground",
                        )}
                      >
                        {item.published ? "Published" : "Draft"}
                      </span>
                    </li>
                  ))}
                  {tool.training.more > 0 ? (
                    <li className="text-muted-foreground text-xs">
                      and {tool.training.more} more
                    </li>
                  ) : null}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">
                  {tool.training.published + tool.training.draft > 0
                    ? "Tagged training exists outside the offices you manage."
                    : "Nothing is tagged with this tool yet."}
                </p>
              )}
              <div>
                <Button asChild variant="outline" size="sm">
                  <Link href={links.trainingAdmin}>
                    <BookOpen aria-hidden />
                    Open training admin
                  </Link>
                </Button>
              </div>
            </EditorSection>
          ) : null}

          <EditorSection title="Status">
            <ToggleRow
              id="is_active"
              checked={state.active}
              onChange={(next) => set("active", next)}
              title="Active"
              description="Off retires it from every checklist without deleting anybody's recorded progress."
            />
          </EditorSection>
        </form>
      </FormSheetBody>
    </FormSheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

/**
 * The catalog every agent's checklist is built from.
 *
 * Each row says what an administrator needs to decide whether it is finished:
 * where it applies, whether there is training to watch, how the agents in
 * their reach are getting on, and what is missing.
 */
export default function OnboardingToolCatalog() {
  const props = usePage<Props>().props;
  const { groups, summary, filters, canReorder, editing, links } = props;

  const tools = groups.flatMap((group) => group.tools);
  const editingTool =
    editing && editing !== "new"
      ? (tools.find((tool) => tool.slug === editing) ?? null)
      : null;
  const editorOpen = editing === "new" || editingTool !== null;
  const shown =
    filters.q || filters.show !== "all"
      ? groups.filter((group) => group.tools.length > 0)
      : groups;

  function edit(slug: string) {
    visitCatalog(filters, { edit: slug });
  }

  function moveWithin(group: Props["groups"][number], index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= group.tools.length) return;
    const order = group.tools.map((row) => row.slug);
    [order[index], order[target]] = [order[target], order[index]];
    // The complete intended sequence, so the server never reconstructs a move
    // from a delta it did not witness.
    router.post(
      routes.onboarding_tool_reorder(),
      { group: group.code, order },
      { preserveScroll: true },
    );
  }

  return (
    <PermissionRequired permission={{ all: ["web.manage_onboarding_tools"] }}>
      <div className="@container grid gap-6">
        <Head title="Tool catalog" />
        <PageHeader
          title="Tool catalog"
          description="What every agent is set up with, where each tool applies, and how agents get it."
          actions={
            <Button type="button" onClick={() => edit("new")}>
              <Plus aria-hidden />
              Add tool
            </Button>
          }
        />

        <CatalogSummary
          summary={summary}
          teamReadiness={links.teamReadiness}
          onShowAttention={() => visitCatalog({ ...filters, show: "attention" })}
        />

        <CatalogToolbar
          filters={filters}
          options={props.options.show}
          attention={summary.attention}
        />

        {shown.length === 0 ? (
          <EmptyState
            icon={Search}
            title="No tools match"
            description={
              filters.q
                ? `Nothing matches “${filters.q}” in this view.`
                : "Nothing in the catalog is in this view."
            }
            actions={
              <Button
                type="button"
                variant="outline"
                onClick={() => visitCatalog({ q: "", show: "all" })}
              >
                Show all tools
              </Button>
            }
          />
        ) : (
          shown.map((group) => (
            <section
              key={group.code}
              aria-labelledby={`shelf-${group.code}`}
              className="bg-card shadow-card @container/list overflow-hidden rounded-(--radius-card) border"
            >
              <header className="flex items-baseline justify-between gap-3 border-b px-5 py-3.5">
                <h2
                  id={`shelf-${group.code}`}
                  className="text-base font-semibold tracking-[-0.01em]"
                >
                  {group.label}
                </h2>
                <span className="text-muted-foreground text-xs tabular-nums">
                  {group.tools.length} {group.tools.length === 1 ? "tool" : "tools"}
                </span>
              </header>
              {group.tools.length === 0 ? (
                <p className="text-muted-foreground px-5 py-6 text-sm">
                  No tools on this shelf yet.
                </p>
              ) : (
                <>
                  <ColumnHeads />
                  <ul>
                    {group.tools.map((tool, index) => (
                      <CatalogRow
                        key={tool.slug}
                        tool={tool}
                        index={index}
                        count={group.tools.length}
                        canReorder={canReorder}
                        teamReadiness={links.teamReadiness}
                        onMove={(at, delta) => moveWithin(group, at, delta)}
                        onEdit={edit}
                      />
                    ))}
                  </ul>
                </>
              )}
            </section>
          ))
        )}

        {canReorder ? null : (
          <p className="text-muted-foreground text-xs">
            Clear the search and filter to reorder a shelf.
          </p>
        )}

        {editorOpen ? (
          <ToolEditor
            key={editing}
            tool={editingTool}
            props={props}
            onClose={() => visitCatalog(filters)}
          />
        ) : null}
      </div>
    </PermissionRequired>
  );
}

OnboardingToolCatalog.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Tool catalog",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Tool catalog" },
        ],
      },
    },
  ] as const;
