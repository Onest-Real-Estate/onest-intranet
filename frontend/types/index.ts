import type {
  ListResponse,
  PaginationMeta,
  StatusTone,
  ValidationErrors,
} from "@/types/design-system";

export interface User {
  id: number;
  email: string;
  name: string;
  headshotUrl: string | null;
  /** Django auth permission codenames, e.g. "user.view_user". */
  permissions: string[];
  /** Stable role codes (`apps/user/roles.py`), highest-priority first. */
  roles: string[];
  /** Display label: Superadmin, Admin, Region manager, Branch manager, Agent. */
  roleLabel: string;
  isStaff: boolean;
  isSuperuser: boolean;
}

/**
 * Dashboard metrics, selected and calculated server-side by
 * `apps/web/metrics.py`. The page renders whatever arrives: which cards a user
 * gets is a permission and scope decision the client is never asked to make.
 */
export type MetricScopeLevel = "self" | "office" | "region" | "company";

export interface DashboardMetric {
  key: string;
  label: string;
  /** Presentation hint for the figure; the value arrives already formatted. */
  format: "count" | "currency" | "percent";
  scopeLevel: MetricScopeLevel;
  /** How the figure is calculated — surfaced as the card's tooltip. */
  definition: string;
  /** ISO timestamp for when this figure was calculated (server clock). */
  asOf: string;
  availability: "available" | "unavailable";
  /** Why the figure cannot be shown; present only when unavailable. */
  unavailableReason?: string;
  /** Null while unavailable — an unmeasured metric has no number to round. */
  value: string | null;
  /** Machine-readable figure; omitted when unavailable. */
  rawValue?: number | string;
  /** What ``rawValue`` measures — e.g. count, usd, ratio. */
  unit?: string;
  hint: string;
  tone: "neutral" | "success" | "warning" | "destructive";
  trend: "up" | "down" | "flat";
  /** Signed period-over-period change, e.g. "+15%"; omitted when none exists. */
  delta?: string;
  /** The figure the delta compares against; renders as "vs. N last period". */
  comparedTo?: string;
  /** Key from the approved metric-icon set (`frontend/lib/metric-icons.ts`). */
  icon: string;
  /** Server-reversed destination, already guarded by its own permission. */
  drillDown: { href: string; label: string } | null;
}

export interface DashboardMetricGroup {
  key: string;
  title: string;
  description: string;
  metrics: DashboardMetric[];
}

export interface DashboardMetrics {
  /** What the team figures cover, e.g. "Fairfax VA" or "Brokerage-wide". */
  scope: { level: MetricScopeLevel; label: string };
  groups: DashboardMetricGroup[];
}

export interface DashboardQuickApp {
  /** The link's stable key — also the icon lookup and the React key. */
  id: string;
  name: string;
  description: string;
  /** Server-resolved: an https URL, or a reversed in-app path. */
  href: string;
  /** Key from the approved icon set (`frontend/lib/quick-access-icons.ts`). */
  icon: string;
  /** External links open in a new tab; internal ones navigate in place. */
  external: boolean;
  sso: QuickAccessSsoCapability;
  health: QuickAccessIntegrationHealth;
  setup: QuickAccessSetupBehavior;
}

export interface DashboardAnnouncement {
  id: number;
  tag: string;
  title: string;
  excerpt: string;
  /** Detail route; the destination re-checks the audience on arrival. */
  href: string;
  imageUrl?: string;
}

export interface DashboardAnnouncements {
  featured: DashboardAnnouncement;
  items: DashboardAnnouncement[];
}

export interface DashboardTransaction {
  id: string;
  address: string;
  imageUrl: string;
  type: string;
  stage: string;
  closing: string;
  /** Raw backend code; rendered only through an explicit presentation adapter. */
  status: string;
}

export interface DashboardTraining {
  percent: number;
  label: string;
  resourceTitle: string;
  resourceHint: string;
}

/** Where an agenda row came from. Mirrors `my_day.contract.EventSource`; a
 *  chip label, never something to authorize from. */
export type AgendaSource =
  | "operational_task"
  | "training"
  | "consultation"
  | "closing"
  | "meeting"
  | "room_booking"
  | "inventory"
  | "microsoft_calendar";

/**
 * One time-bound obligation.
 *
 * Every label is rendered server-side in the reader's timezone. `startAt` and
 * `endAt` travel alongside for grouping and tests — never to be reformatted
 * against the browser clock, which would let a laptop on the wrong timezone
 * disagree with the buckets the server computed.
 */
export interface AgendaEvent {
  id: string;
  dedupeKey: string;
  source: AgendaSource;
  sourceLabel: string;
  title: string;
  startAt: string;
  endAt: string | null;
  allDay: boolean;
  localDate: string;
  /** "9:00 a.m. – 10:30 a.m.", or "All day" — never a synthesized midnight. */
  timeLabel: string;
  /** "Today", "Tomorrow", or a short date. */
  dayLabel: string;
  /** Server-decided. A row on another day must say so, or a later time on an
   *  earlier day reads as a sorting bug. */
  isToday: boolean;
  location: string;
  status: "confirmed" | "tentative";
  /** Empty for a confirmed event: the default state needs no chip. */
  statusLabel: string;
  priority: "critical" | "high" | "normal" | "low";
  overdue: boolean;
  context: string;
  ctaLabel: string;
  ctaHref: string;
}

/**
 * The agenda, already bucketed by the server.
 *
 * Three lists rather than one sorted array, because past-due work must never
 * be filed among future appointments — the split is the contract, not a
 * presentation choice the client could undo.
 */
export interface DashboardSchedule {
  dateLabel: string;
  timezone: string;
  overdue: AgendaEvent[];
  today: AgendaEvent[];
  upcoming: AgendaEvent[];
  /** Uncapped, so a "+N more" count is honest about what was trimmed. */
  total: number;
  viewAllHref: string;
  viewAllLabel: string;
}

export interface DashboardActionItem {
  id: string;
  dedupeKey: string;
  title: string;
  type: string;
  priority: "critical" | "high" | "normal" | "low";
  /** Always paired with colour — never colour alone. */
  priorityLabel: string;
  dueAt: string | null;
  dueLabel: string;
  overdue: boolean;
  state: "open";
  source: {
    module: string;
    recordType: string;
    recordId: string;
  };
  context: string;
  ctaLabel: string;
  ctaHref: string;
  assigneeId: number;
}

export interface DashboardActionItems {
  total: number;
  items: DashboardActionItem[];
  viewAllHref: string;
}

export interface DashboardMarketRate {
  label: string;
  value: string;
  bar: number;
}

export interface DashboardMarket {
  rates: DashboardMarketRate[];
}

export interface DashboardDocument {
  id: string;
  name: string;
  /** `file` or `link`; picks the icon and nothing else. */
  kind: string;
  /** Server-reversed: a protected download that re-checks scope, or the link. */
  href: string;
  /** The office that published it, shown when it is not the reader's own. */
  office: string;
}

export interface DashboardDocuments {
  /** Total in the reader's library, which may exceed `items.length`. */
  total: number;
  items: DashboardDocument[];
  viewAllHref: string;
}

export interface DashboardGreeting {
  salutation: string;
  name: string;
  dateLabel: string;
  /** Local calendar date in ISO 8601 form. */
  dateIso: string;
  timezone: string;
}

/**
 * Shapes shared by the administrative widgets. Four presentations cover every
 * administrative widget in the registry, so a new one is a registry row rather
 * than another bespoke component: a staged funnel, a work queue, a utilization
 * meter, and an activity feed.
 */
export interface DashboardStage {
  key: string;
  label: string;
  /** Already formatted server-side; the page never rounds a figure. */
  value: string;
  hint?: string;
  tone: StatusTone;
}

export interface DashboardStages {
  stages: DashboardStage[];
  /** What the funnel totals, e.g. "48 files in flight". */
  caption: string;
  /** Server-reversed list this funnel counts, guarded by its own policy. */
  viewAllHref?: string;
}

export interface DashboardQueueRow {
  id: string;
  title: string;
  subtitle?: string;
  /** Right-aligned fact: a due date, an age, an amount. */
  meta?: string;
  /** Short status word; paired with `tone` so color is never the only signal. */
  badge?: string;
  tone: StatusTone;
  /** Server-reversed destination, guarded by its own permission. */
  href?: string;
}

export interface DashboardQueue {
  /** Total matching records in scope, which may exceed `rows.length`. */
  total: number;
  rows: DashboardQueueRow[];
  /** Server-reversed queue this panel is a window on, guarded by its own policy. */
  viewAllHref?: string;
}

export interface DashboardMeterSeries {
  label: string;
  /** 0–1. Null means unmeasured — a window with no bookable minutes. */
  ratio: number | null;
  caption?: string;
}

export interface DashboardMeter {
  headline: string;
  caption: string;
  series: DashboardMeterSeries[];
}

export interface DashboardActivityEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  /** Already formatted in the brokerage timezone. */
  at: string;
  tone: StatusTone;
}

export interface DashboardActivity {
  entries: DashboardActivityEntry[];
}

export interface DashboardWidgetEmptyState {
  title: string;
  description: string;
  actionLabel?: string;
  /** Server-reversed destination for the next useful action. */
  actionHref?: string;
}

export interface DashboardWidgetUnavailable {
  reason: string;
  retryable: boolean;
  actionLabel?: string;
  /** Server-reversed destination for a module that is not connected yet. */
  actionHref?: string;
}

interface DashboardWidgetBase {
  /** Bumped when this widget's data shape changes. */
  version: number;
  generatedAt: string;
  meta: { truncated?: boolean; [key: string]: unknown };
}

export type DashboardWidget<T> = DashboardWidgetBase &
  (
    | {
        status: "ready";
        data: T;
        emptyState: null;
        unavailable: null;
      }
    | {
        status: "empty";
        data: null;
        emptyState: DashboardWidgetEmptyState;
        unavailable: null;
      }
    | {
        status: "unavailable";
        data: null;
        emptyState: null;
        unavailable: DashboardWidgetUnavailable;
      }
  );

export type DashboardWidgetProp =
  | "metrics"
  | "quickApps"
  | "announcements"
  | "transactions"
  | "training"
  | "schedule"
  | "actionItems"
  | "market"
  | "documents"
  // Administrative widgets. Registered here so `router.reload({ only: [...] })`
  // stays typed; each is marked `backed: false` in the widget registry until
  // its provider ships, and renders as not connected in the meantime.
  | "agentOnboarding"
  | "closingPipeline"
  | "contractsAwaitingSignature"
  | "complianceExceptions"
  | "teamTasks"
  | "overdueInventory"
  | "roomUtilization"
  | "operationalActivity"
  | "supportQueue"
  | "feedbackSignals";

/* -------------------------------------------------------------------------- */
/* Feedback and support                                                       */
/* -------------------------------------------------------------------------- */

export interface FeedbackBadge {
  code: string;
  label: string;
  tone: StatusTone;
}

export interface FeedbackStatusBadge extends FeedbackBadge {
  known: boolean;
}

export interface FeedbackPriorityBadge extends FeedbackBadge {
  rank: number;
}

export interface FeedbackPerson {
  id: number;
  name: string;
}

export interface FeedbackRow {
  id: string;
  reference: string;
  summary: string;
  category: { code: string; label: string };
  status: FeedbackStatusBadge;
  priority: FeedbackPriorityBadge;
  /** What the submitter said. Distinct from the staff-set priority. */
  urgency: { code: string; label: string };
  submitter: FeedbackPerson | null;
  assignee: FeedbackPerson | null;
  office: { id: number; name: string } | null;
  createdAt: string;
  updatedAt: string;
}

export interface FeedbackNote {
  id: string;
  author: FeedbackPerson | null;
  body: string;
  /** Staff-only. The server never serializes one to the submitter, so this is
   *  a display hint and never the boundary. */
  internal: boolean;
  createdAt: string;
}

/** `href` is a route that re-authorizes, never a storage path. */
export interface FeedbackScreenshot {
  id: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  width: number | null;
  height: number | null;
  href: string;
}

export interface FeedbackTransition {
  target: string;
  label: string;
  requiresReply: boolean;
  tone: StatusTone;
}

export interface FeedbackDetail extends FeedbackRow {
  description: string;
  notes: FeedbackNote[];
  screenshots: FeedbackScreenshot[];
  transitions: FeedbackTransition[];
  resolvedAt: string | null;
  closedAt: string | null;
  convertedTaskId: string;
  /** Present only for a reader who may triage — already scrubbed server-side. */
  diagnostics?: { pageUrl: string; metadata: Record<string, string> };
}

export interface FeedbackCapabilities {
  triage: boolean;
  assign: boolean;
  note: boolean;
}

/** A real office assignment, narrowed to what somebody stuck actually needs. */
export interface SupportContact {
  key: string;
  role: string;
  purpose: string;
  name: string;
  email: string;
  phone: string;
}

export interface FeedbackSubmitPageProps extends PageProps {
  categories: FilterOption[];
  urgencies: FilterOption[];
  /** Generated from the constants that do the capturing, so the promise and
   *  the behaviour cannot drift apart. */
  disclosure: string[];
  contacts: SupportContact[];
  /** The page the reader came from, already scrubbed and same-origin checked. */
  pageUrl: string;
  errors: ValidationErrors;
}

export interface FeedbackMinePageProps extends PageProps {
  tickets: ListResponse<FeedbackRow, Record<string, never>>;
  errors: ValidationErrors;
}

export interface FeedbackDetailPageProps extends PageProps {
  ticket: FeedbackDetail;
  can: FeedbackCapabilities;
  /** Support staff inside the reader's own reach. Empty without triage. */
  assignees: FeedbackPerson[];
  priorities: FilterOption[];
  errors: ValidationErrors;
}

export interface FeedbackInboxFilters {
  status: string;
  category: string;
  assigned: string;
  q: string;
  [key: string]: string | string[];
}

export interface FeedbackInboxPageProps extends PageProps {
  tickets: ListResponse<FeedbackRow, FeedbackInboxFilters>;
  filterOptions: {
    statuses: FilterOption[];
    categories: FilterOption[];
    priorities: FilterOption[];
    urgencies: FilterOption[];
  };
  summary: { open: number; mine: number };
  can: { triage: boolean; assign: boolean };
  errors: ValidationErrors;
}

/* -------------------------------------------------------------------------- */
/* Operational tasks                                                          */
/* -------------------------------------------------------------------------- */

/** A resolved code plus everything a surface needs to draw it. */
export interface TaskBadge {
  code: string;
  label: string;
  tone: StatusTone;
}

export interface TaskStatusBadge extends TaskBadge {
  /** False when the row holds a code this build does not recognise. */
  known: boolean;
}

export interface TaskPriorityBadge extends TaskBadge {
  /** Sort key; lower is more urgent. */
  rank: number;
}

/** Just enough to name somebody — never an email. */
export interface TaskPerson {
  id: number;
  name: string;
}

export interface TaskRow {
  id: string;
  reference: string;
  title: string;
  category: { code: string; label: string };
  status: TaskStatusBadge;
  priority: TaskPriorityBadge;
  office: { id: number; name: string };
  assignee: TaskPerson | null;
  team: string;
  dueAt: string | null;
  isOverdue: boolean;
  source: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

export interface TaskComment {
  id: string;
  author: TaskPerson | null;
  body: string;
  /** Staff-only. The server never serializes one to a reader without the
   *  management grant, so this is a display hint, never the boundary. */
  internal: boolean;
  createdAt: string;
}

/** No URL: files are fetched through `routes.operational_task_attachment`,
 *  which re-authorizes the reader against the parent task on every request. */
export interface TaskAttachment {
  id: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  internal: boolean;
  uploadedBy: TaskPerson | null;
  createdAt: string;
}

/** One legal move, already filtered to what this actor may make. */
export interface TaskTransition {
  target: string;
  label: string;
  requiresNote: boolean;
  tone: StatusTone;
}

export interface TaskDetail extends TaskRow {
  description: string;
  reporter: TaskPerson | null;
  sourceReference: string;
  relatedObject: { type: string; id: string } | null;
  startedAt: string | null;
  resolvedAt: string | null;
  closedAt: string | null;
  comments: TaskComment[];
  attachments: TaskAttachment[];
  transitions: TaskTransition[];
}

export interface TaskBoardColumn {
  status: TaskStatusBadge;
  items: TaskRow[];
  count: number;
}

export interface TaskFilters {
  status: string;
  category: string;
  priority: string;
  assigned: string;
  q: string;
  /** Matches the shape `buildListUrl` and `ListResponse` both expect. */
  [key: string]: string | string[];
}

/** Mirrors the service's grants so the UI can hide what it may not do. It is
 *  never the authorization — every write re-checks server-side. */
export interface TaskCapabilities {
  manage: boolean;
  assign: boolean;
  comment: boolean;
}

/** The create drawer's fields, echoed verbatim when a save is refused. Mirrors
 *  `views.DRAFT_FIELDS`; every value is a form string, never a parsed one. */
export interface TaskDraft {
  office: string;
  category: string;
  title: string;
  description: string;
  priority: string;
  team: string;
  assignee: string;
  dueAt: string;
  tags: string;
}

/** Mirrors `it_support.taxonomy`. Codes are stable; labels are presentation. */
export interface SupportPerson {
  id: number;
  name: string;
}

export interface SupportTicketRow {
  id: string;
  reference: string;
  subject: string;
  category: { code: string; label: string };
  status: TaskStatusBadge;
  priority: TaskPriorityBadge;
  office: { id: number; name: string } | null;
  submitter: SupportPerson | null;
  /** Set when the ticket is about somebody other than its submitter. */
  aboutUser: SupportPerson | null;
  assignee: SupportPerson | null;
  createdAt: string;
  updatedAt: string;
}

export interface SupportReply {
  id: string;
  author: SupportPerson | null;
  body: string;
  /** IT-only. The server never serializes one to a reader without the note
   *  grant, so this is a display hint, never the boundary. */
  internal: boolean;
  /** The reply that closed the loop, led with rather than buried in a thread. */
  isResolution: boolean;
  createdAt: string;
}

/** No URL: files are fetched through `routes.it_support_attachment`, which
 *  re-authorizes the reader against the parent ticket on every request. */
export interface SupportAttachment {
  id: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  internal: boolean;
  uploadedBy: SupportPerson | null;
  createdAt: string;
}

export interface SupportTransition {
  target: string;
  label: string;
  requiresNote: boolean;
  tone: StatusTone;
}

export interface SupportTicketDetail extends SupportTicketRow {
  description: string;
  location: string;
  preferredContact: { code: string; label: string };
  /** Empty for a requester: diagnostics describe their own machine and are of
   *  no use to them on a page they may screen-share. */
  deviceInfo: string;
  pageUrl: string;
  resolvedAt: string | null;
  closedAt: string | null;
  replies: SupportReply[];
  attachments: SupportAttachment[];
  transitions: SupportTransition[];
}

/** Mirrors the service's grants so the UI can hide what it may not do. Never
 *  the authorization — every write re-checks server-side. */
export interface SupportCapabilities {
  triage: boolean;
  assign: boolean;
  note: boolean;
  reply: boolean;
}

export interface SupportOptions {
  statuses: FilterOption[];
  categories: FilterOption[];
  priorities: FilterOption[];
  contactMethods: FilterOption[];
}

export interface AgentTool {
  slug: string;
  name: string;
  description: string;
  group: string;
  provisioning: "self_serve" | "onest" | "both";
  provisioningLabel: string;
  selfServe: boolean;
  required: boolean;
  openUrl: string;
  helpUrl: string;
  /** The guide. Both halves travel: a self-serve tool can still have somebody
   *  to chase when a step fails. */
  steps: string[];
  contact: string;
  requestPath: string;
  state: { code: string; label: string; tone: StatusTone };
  /** Whether the office has sent the vendor invitation, from stored provenance. */
  invitation: { state: string; label: string; sentAt: string | null };
  complete: boolean;
  note: string;
  updatedAt: string | null;
}

/** Grouped server-side so the order, counts, and empty groups are the same
 *  fact the readiness figure reads. */
export interface AgentToolGroup {
  code: string;
  label: string;
  tools: AgentTool[];
  ready: number;
  total: number;
}

export interface ToolReadiness {
  ready: number;
  total: number;
  percent: number;
  complete: boolean;
}

export interface MyToolsPageProps extends PageProps {
  agent: {
    id: number;
    name: string;
    office: string | null;
    isSelf: boolean;
  };
  groups: AgentToolGroup[];
  readiness: ToolReadiness;
  /** Whether this reader may move this agent's rows. Self-management is
   *  refused, so an admin viewing their own page gets a read-only checklist. */
  canManage: boolean;
  stateOptions: FilterOption[];
  supportPath: string;
  errors: ValidationErrors;
}

/** One catalog row as the management screen reads it. */
export interface CatalogTool {
  slug: string;
  name: string;
  description: string;
  group: string;
  provisioning: string;
  provisioningLabel: string;
  openUrl: string;
  helpUrl: string;
  steps: string[];
  contact: string;
  requestPath: string;
  companyWide: boolean;
  /** Named in words: "not company-wide" tells an administrator nothing about
   *  who actually gets the tool. */
  appliesTo: string;
  officeIds: number[];
  required: boolean;
  active: boolean;
  sortOrder: number;
}

export interface OnboardingToolCatalogPageProps extends PageProps {
  groups: { code: string; label: string; tools: CatalogTool[] }[];
  offices: FilterOption[];
  options: {
    groups: FilterOption[];
    provisioning: FilterOption[];
  };
  maxSteps: number;
  /** Which row's editor is open — a slug, "new", or "". */
  editing: string;
  /** Echoed back on a refused save so nothing typed is lost. */
  draft: Partial<{
    slug: string;
    name: string;
    description: string;
    group: string;
    provisioning: string;
    openUrl: string;
    helpUrl: string;
    contact: string;
    requestPath: string;
    companyWide: boolean;
    required: boolean;
    active: boolean;
    sortOrder: string;
    steps: string[];
    officeIds: number[];
  }>;
  errors: ValidationErrors;
}

export interface TeamToolReadinessPageProps extends PageProps {
  filters: { q: string };
  agents: {
    id: number;
    name: string;
    office: string | null;
    ready: number;
    total: number;
    percent: number;
    complete: boolean;
  }[];
  errors: ValidationErrors;
}

export interface ITSupportPageProps extends PageProps {
  tickets: SupportTicketRow[];
  openCount: number;
  options: SupportOptions;
  /** Echoed back on a refused save; the form posts natively, so anything the
   *  server does not return is lost. */
  draft: Record<string, string>;
  errors: ValidationErrors;
}

export interface ITSupportTicketPageProps extends PageProps {
  ticket: SupportTicketDetail;
  can: SupportCapabilities;
  assignees: SupportPerson[];
  options: SupportOptions;
  errors: ValidationErrors;
}

export interface SupportQueueFilters {
  status: string;
  category: string;
  priority: string;
  assigned: string;
  office: string;
  q: string;
  [key: string]: string | string[];
}

export interface ITSupportQueuePageProps extends PageProps {
  tickets: ListResponse<SupportTicketRow, SupportQueueFilters>;
  /** Counted on the scoped queryset, so a triager whose reach is one branch
   *  sees that branch's figures rather than the brokerage's. */
  metrics: {
    open: number;
    urgent: number;
    unassigned: number;
    waitingUser: number;
    resolvedRecently: number;
  };
  options: SupportOptions;
  offices: FilterOption[];
  can: SupportCapabilities;
  errors: ValidationErrors;
}

export interface OperationalTasksPageProps extends PageProps {
  tasks: ListResponse<TaskRow, TaskFilters>;
  /** Present only in board view; the list view sends null. */
  board: TaskBoardColumn[] | null;
  view: "list" | "board";
  filterOptions: {
    statuses: FilterOption[];
    categories: FilterOption[];
    priorities: FilterOption[];
  };
  summary: { open: number; overdue: number; mine: number };
  can: TaskCapabilities;
  /** Offices this actor may file a task against, scoped server-side. Empty for
   *  a reader without the management grant — the create form never renders. */
  offices: { id: number; name: string }[];
  categories: FilterOption[];
  /** Reopened by the server on a refused save, with the draft echoed back:
   *  the drawer posts natively, so anything not returned is lost. */
  createSheet: { open: boolean; draft: TaskDraft };
  errors: ValidationErrors;
}

export interface OperationalTaskDetailPageProps extends PageProps {
  task: TaskDetail;
  can: TaskCapabilities;
  /** Candidate assignees inside this actor's own reach. Empty for somebody
   *  without the assign grant, so the picker never becomes a staff directory. */
  assignees: TaskPerson[];
  errors: ValidationErrors;
}

/**
 * Props available on every Inertia page. `user` and `csrfToken` are shared by
 * `web.middleware.InertiaShareMiddleware`; pages can extend this interface.
 */
/** The signed-in user's own office. Never addressed by an id from the client. */
export interface PrimaryOffice {
  id: number;
  name: string;
  regionName: string;
}

/**
 * Availability per agent or administrative module, keyed by the stable item
 * slug in the shared navigation registries. Shared by web.navigation.HUB_FEATURES.
 */
export type HubFeatures = Record<string, boolean>;

export interface ShellSharedProps {
  /** Changes whenever roles, permissions, or authorization scope changes. */
  authorizationVersion: string;
  /** Reviewed permission-catalog version (not a grant matrix). */
  capabilitySchemaVersion: string;
  help: {
    /** Backend-validated HTTPS destination; null keeps the entry point disabled. */
    url: string | null;
  };
  session: {
    authenticated: boolean;
  };
}

export interface FlashMessage {
  /** Django ``messages`` tag / ``set_flash`` level. */
  level: "debug" | "info" | "success" | "warning" | "error";
  message: string;
}

export interface PageProps {
  user: User | null;
  csrfToken: string;
  requestId: string;
  features: HubFeatures;
  primaryOffice: PrimaryOffice | null;
  shell: ShellSharedProps;
  /** Header badge counts for the signed-in reader; null when signed out. */
  notifications: NotificationShell | null;
  /** Quick Create actions, already filtered to what this actor may start. */
  quickCreate?: QuickCreate;
  /** One-shot toast from the previous mutating request; absent or null when none. */
  flash?: FlashMessage | null;
  [key: string]: unknown;
}

/**
 * In-app notifications.
 *
 * The wire shape is deliberately thin. `title` is fixed producer copy that
 * names nobody; `detail` is resolved from the source record on every read and
 * arrives empty the moment the reader stops being allowed to see it. The
 * client never decides which of the two it may show — the server has already
 * decided by the time the prop exists.
 */
export type NotificationPriority = "critical" | "high" | "normal" | "low";

export type NotificationStatusFilter = "unread" | "all" | "archived";

export interface NotificationShell {
  unreadCount: number;
  /** Unread notifications that must be acknowledged individually. */
  mandatoryCount: number;
  /** Server-reversed path to the notification centre. */
  href: string;
}

export interface NotificationActionLink {
  label: string;
  /** Server-reversed in-app path; the destination re-authorizes on arrival. */
  href: string;
}

export interface NotificationRow {
  /** Opaque server id (UUID). Never a database primary key. */
  id: string;
  type: string;
  typeLabel: string;
  eventKey: string;
  title: string;
  /** Source-resolved context, or "" when the source declines to say. */
  detail: string;
  priority: NotificationPriority;
  priorityLabel: string;
  mandatory: boolean;
  createdAt: string;
  availableAt: string;
  receivedLabel: string;
  expiresAt: string | null;
  readAt: string | null;
  archivedAt: string | null;
  read: boolean;
  archived: boolean;
  expired: boolean;
  /** Absent whenever the destination no longer resolves for this reader. */
  action: NotificationActionLink | null;
  /** The notification offered a destination that no longer resolves. */
  staleAction: boolean;
  staleActionNote: string;
  /** Why detail and action are missing; "" when nothing is missing. */
  unavailableReason: string;
}

export interface NotificationFilters {
  status: string;
  type: string;
  priority: string;
  [key: string]: unknown;
}

export interface NotificationFilterOption {
  value: string;
  label: string;
}

export interface NotificationsPageProps extends PageProps {
  notificationList: ListResponse<NotificationRow, NotificationFilters>;
  filterOptions: {
    status: NotificationFilterOption[];
    type: NotificationFilterOption[];
    priority: NotificationFilterOption[];
  };
  summary: { unreadCount: number; mandatoryCount: number };
  unreadByType: Record<string, number>;
  errors: ValidationErrors;
}

/**
 * Notification preferences.
 *
 * The server sends the whole matrix, locked cells included. A switch that is
 * simply absent reads as a channel that does not exist, so a cell the reader
 * may not change arrives on, disabled, and carrying the sentence that says
 * why. `locked` is presentation of a decision the server has already made and
 * re-makes on write: the submit form has no field for a locked cell at all.
 */
export interface NotificationChannelDefinition {
  key: string;
  label: string;
  description: string;
  /** False for channels the reader cannot switch off, e.g. the hub itself. */
  configurable: boolean;
  lockedReason: string;
}

export interface NotificationCategoryChannel {
  key: string;
  /** Field name the submit form expects for this cell. */
  field: string;
  enabled: boolean;
  locked: boolean;
  lockedReason: string;
  /** What applies to a reader who has never chosen. */
  defaultEnabled: boolean;
}

export interface NotificationCategoryPreference {
  key: string;
  label: string;
  description: string;
  mandatory: boolean;
  mandatoryReason: string;
  channels: NotificationCategoryChannel[];
}

export interface NotificationPreferencePolicy {
  version: number;
  savedVersion: number;
  /** Categories were added, or a default changed, since this reader saved. */
  outdated: boolean;
  updatedAt: string | null;
  configurableChannels: string[];
}

export interface NotificationPreferencePayload {
  channels: NotificationChannelDefinition[];
  categories: NotificationCategoryPreference[];
  policy: NotificationPreferencePolicy;
}

export interface NotificationPreferencesPageProps extends PageProps {
  preferences: NotificationPreferencePayload;
  /** Server-reversed path back to the notification centre. */
  notificationsHref: string;
  errors: ValidationErrors;
}

/**
 * A breadth the reader may look at the administrative widgets through.
 *
 * The list is composed server-side from effective access, and the selected key
 * is revalidated on every request. The client never invents a key, and holding
 * one does not widen what the server will answer with.
 */
export interface DashboardScopeOption {
  /** Opaque server-issued key; never an office or region primary key. */
  key: string;
  label: string;
  level: MetricScopeLevel;
}

export interface DashboardScope {
  /** Empty or single-entry means there is nothing to choose between. */
  options: DashboardScopeOption[];
  /** The key the arriving widgets were computed at. */
  selectedKey: string | null;
}

/**
 * Dashboard profile assignment, resolved server-side.
 *
 * Assignment is presentation only: it decides which widgets are laid out and
 * in what order, never which records a provider will return or which Django
 * permissions the reader holds.
 */
export interface DashboardAssignment {
  /** Explicit, currently-valid user-targeted assignment. */
  assignedProfileId: string | null;
  /** The reader's designated primary role code. */
  primaryRoleCode: string | null;
  /** Office- or region-targeted assignment covering the reader. */
  scopeProfileId: string | null;
}

export type AgentJourneyProfileState = "not_started" | "in_progress" | "complete";
export type AgentJourneyOfficeState = "not_selected" | "selected" | "confirmed";
export type AgentJourneyOfficeHandoffState =
  | "pending"
  | "notified"
  | "notification_failed";
export type AgentJourneyContractState =
  | "generated"
  | "sent"
  | "signed"
  | "active"
  | "blocked"
  | "unavailable";
export type AgentJourneyToolSourceState = "available" | "unavailable";
export type AgentJourneyToolStatus = "complete" | "pending" | "blocked" | "unavailable";
export type AgentJourneyInvitationState =
  | "not_applicable"
  | "pending"
  | "sent"
  | "unavailable";
export type AgentJourneyStep = "profile" | "office" | "activation" | "complete";
export type AgentJourneyAction =
  | "complete_profile"
  | "confirm_office"
  | "set_up_tool"
  | "wait_for_office"
  | "wait_for_activation"
  | "none";

export interface AgentJourneyState<T extends string> {
  state: T;
  label: string;
  updatedAt: string | null;
}

export interface AgentJourneyTool {
  key: string;
  label: string;
  description: string;
  provisioning: "self_serve" | "onest" | "both";
  provisioningLabel: string;
  selfService: boolean;
  required: boolean;
  state: string;
  stateLabel: string;
  status: AgentJourneyToolStatus;
  statusLabel: string;
  invitationState: AgentJourneyInvitationState;
  invitationLabel: string;
  /** When the office sent it. Null until somebody records the send. */
  invitationSentAt: string | null;
  complete: boolean;
  updatedAt: string | null;
}

/** Versioned server composition; clients display it and never infer progress. */
export interface AgentOnboardingJourney {
  schemaVersion: 1;
  profile: AgentJourneyState<AgentJourneyProfileState>;
  office: AgentJourneyState<AgentJourneyOfficeState>;
  officeHandoff: AgentJourneyState<AgentJourneyOfficeHandoffState> & {
    recipient: { name: string } | null;
    message: string;
    delivery: {
      state: "pending" | "recorded" | "queued" | "sent" | "retryable" | "failed";
      label: string;
      channels: {
        channel: string;
        state: string;
        label: string;
        retryable: boolean;
      }[];
    };
  };
  contract: AgentJourneyState<AgentJourneyContractState>;
  toolsSource: AgentJourneyToolSourceState;
  tools: AgentJourneyTool[];
  requiredSetupComplete: boolean;
  activationComplete: boolean;
  strictGateActive: boolean;
  currentStep: { code: AgentJourneyStep; label: string };
  nextAction: {
    code: AgentJourneyAction;
    label: string;
    href: string | null;
    method: "get" | null;
  };
  version: string;
  updatedAt: string;
  blockers: { key: string; message: string }[];
}

/** Dashboard page props. Deferred widgets are undefined until Inertia loads them. */
export interface DashboardPageProps extends PageProps {
  greeting: DashboardGreeting;
  /** Present only for ordinary users with an effective Agent role. */
  onboardingJourney?: AgentOnboardingJourney;
  /** Absent until the assignment model ships; resolution falls back to roles. */
  assignment?: DashboardAssignment;
  scope?: DashboardScope;
  metrics?: DashboardWidget<DashboardMetrics>;
  quickApps?: DashboardWidget<DashboardQuickApp[]>;
  announcements?: DashboardWidget<DashboardAnnouncements>;
  transactions?: DashboardWidget<DashboardTransaction[]>;
  training?: DashboardWidget<DashboardTraining>;
  schedule?: DashboardWidget<DashboardSchedule>;
  actionItems?: DashboardWidget<DashboardActionItems>;
  market?: DashboardWidget<DashboardMarket>;
  documents?: DashboardWidget<DashboardDocuments>;
  // Administrative widgets — providers land in P1-021..P1-027.
  agentOnboarding?: DashboardWidget<DashboardStages>;
  closingPipeline?: DashboardWidget<DashboardStages>;
  contractsAwaitingSignature?: DashboardWidget<DashboardQueue>;
  complianceExceptions?: DashboardWidget<DashboardQueue>;
  teamTasks?: DashboardWidget<DashboardQueue>;
  overdueInventory?: DashboardWidget<DashboardQueue>;
  roomUtilization?: DashboardWidget<DashboardMeter>;
  operationalActivity?: DashboardWidget<DashboardActivity>;
  supportQueue?: DashboardWidget<DashboardQueue>;
  feedbackSignals?: DashboardWidget<DashboardQueue>;
}

/** Full action-item queue page — same rows as the dashboard widget, uncapped. */
export interface ActionItemsQueuePageProps extends PageProps {
  queue: DashboardActionItems | null;
  emptyState: {
    title: string;
    description: string;
    actionLabel?: string;
    actionHref?: string;
  } | null;
  unavailable: {
    reason: string;
    retryable: boolean;
    actionLabel?: string;
    actionHref?: string;
  } | null;
  partialFailure: boolean;
}

// ---------------------------------------------------------------------------
// Profile and onboarding
// ---------------------------------------------------------------------------

/** Assignable offices, grouped by region for a `<select>` with optgroups. */
export interface OfficeGroup {
  label: string;
  offices: {
    id: number;
    name: string;
    city?: string;
    state?: string;
    region?: string;
  }[];
}

export interface StateOption {
  code: string;
  name: string;
}

export interface LanguageOption {
  code: string;
  name: string;
}

export interface ContactMethodOption {
  value: string;
  label: string;
}

/** One supported social destination. `name` is the POSTed Django field name. */
export interface SocialPlatformOption {
  name: string;
  prop: string;
  label: string;
  placeholder: string;
}

/**
 * Everything a user may maintain about themselves, per `SelfProfileForm`.
 * Keys mirror `forms.SELF_PROFILE_FIELD_MAP`, shared by onboarding and /profile.
 */
export interface SelfProfileValues {
  firstName: string;
  lastName: string;
  phoneNumber: string;
  streetAddress: string;
  city: string;
  state: string;
  zipCode: string;
  officeId: string;
  mlsNumber: string;
  nrdsNumber: string;
  headshotUrl: string | null;
  preferredName: string;
  preferredContactMethod: string;
  licenseNumber: string;
  /** ISO 8601 calendar date (`yyyy-MM-dd`), or "". */
  licenseExpiresOn: string;
  licenseState: string;
  bio: string;
  websiteUrl: string;
  linkedinUrl: string;
  facebookUrl: string;
  instagramUrl: string;
  xUrl: string;
  languages: string[];
  specialties: string[];
}

export interface ProfileOffice {
  id: number;
  name: string;
  pathLabel: string;
  regionName: string;
  streetAddress: string;
  city: string;
  state: string;
  zipCode: string;
  mainPhone: string;
}

export interface ProfileLicenseStatus {
  state: "expired" | "expiring" | "current";
  /** Days until expiry; negative once the license has lapsed. */
  days: number;
  tone: StatusTone;
}

/**
 * Account facts the account holder cannot change. Rendered read-only and never
 * accepted back: the Microsoft directory owns the email, an admin owns the rest.
 */
export interface ProfileIdentity {
  email: string;
  legalName: string;
  displayName: string;
  preferredDisplayName: string;
  roles: string[];
  office: ProfileOffice | null;
  accountStatus: "active" | "inactive";
  isStaff: boolean;
  memberSince: string | null;
  onboardingCompletedAt: string | null;
  licenseStatus: ProfileLicenseStatus | null;
  /** Broker-controlled values. Read-only here; POSTing one returns 403. */
  administrative: ProfileAdministrativeSummary;
}

export interface ProfileCompletenessItem {
  key: string;
  label: string;
  section: string;
  sectionLabel: string;
  /** Collected during onboarding — reported separately from optional gaps. */
  required: boolean;
}

export interface ProfileCompleteness {
  completed: number;
  total: number;
  percent: number;
  missing: ProfileCompletenessItem[];
}

export interface ProfileLimits {
  headshotMaxBytes: number;
  headshotMinDimension: number;
  bioMaxLength: number;
  maxLanguages: number;
  maxSpecialties: number;
}

export type OnboardingProfileSectionCode =
  | "identity"
  | "contact"
  | "credentials"
  | "review";
export type OnboardingEditableSectionCode = Exclude<
  OnboardingProfileSectionCode,
  "review"
>;
export type OnboardingProfileSectionStatus = "not_started" | "in_progress" | "complete";
/** Who is the source of truth for a value: Microsoft, the brokerage, or the agent. */
export type ProfileFieldOwner = "agent" | "microsoft" | "brokerage";

export interface OnboardingProfileSection {
  code: OnboardingProfileSectionCode;
  label: string;
  description: string;
  /** Null for review, which confirms rather than saves. */
  status: OnboardingProfileSectionStatus | null;
  /** Fingerprint of the section's stored values; echoed back on save. */
  revision: string | null;
}

/** Server-owned policy for one Django field. React renders it; it never decides it. */
export interface OnboardingFieldPolicy {
  label: string;
  section: OnboardingEditableSectionCode;
  required: boolean;
  owner: ProfileFieldOwner;
  readOnly: boolean;
  /** Availability reasons and helper copy, e.g. why MLS may be left blank. */
  guidance: string;
}

export interface OnboardingReviewRow {
  field: string;
  label: string;
  /** The stored, normalized value as it will be saved. Empty when not provided. */
  display: string;
  required: boolean;
  owner: ProfileFieldOwner;
}

export interface OnboardingReview {
  ready: boolean;
  missing: { field: string; label: string; section: OnboardingEditableSectionCode }[];
  groups: {
    section: OnboardingEditableSectionCode;
    label: string;
    rows: OnboardingReviewRow[];
  }[];
}

export interface OnboardingProfileFlow {
  onboardingVersion: number;
  currentSection: OnboardingProfileSectionCode;
  sections: OnboardingProfileSection[];
  fields: Record<string, OnboardingFieldPolicy>;
  review: OnboardingReview;
}

export interface OnboardingIdentity {
  email: string;
  emailOwner: "microsoft";
  /** Microsoft's name when it sent a complete one; otherwise what is stored. */
  legalName: { firstName: string; lastName: string };
  legalNameLocked: boolean;
  legalNameNotice: string | null;
}

export type OnboardingLimits = Omit<ProfileLimits, "maxSpecialties">;

export type OnboardingOfficeAdminResolution = "office" | "region" | "company";

export interface OnboardingOfficeSelection {
  office: {
    id: number;
    name: string;
    hierarchy: string;
    region: string;
    streetAddress: string;
    city: string;
    state: string;
    zipCode: string;
    mainPhone: string;
    publicEmail: string;
    officeHours: unknown[];
  };
  administrator: {
    id: number;
    name: string;
    phone: string;
    email: string;
    isPrimary: boolean;
    resolutionLevel: OnboardingOfficeAdminResolution;
    resolutionLabel: string;
  } | null;
  support: { available: boolean; message: string };
}

export interface OnboardingPageProps extends PageProps {
  profileFlow: OnboardingProfileFlow;
  identity: OnboardingIdentity;
  /** Values to show: what was just submitted after a 422 or 409, else `saved`. */
  initial: SelfProfileValues;
  /** What the server holds right now. */
  saved: SelfProfileValues;
  validation: ValidationErrors;
  /** Empty when the office is administrative for this user. */
  offices: OfficeGroup[];
  officeLabel: string;
  /** Public facts for only the selected office; internal instructions are excluded. */
  officeSelection: OnboardingOfficeSelection | null;
  officeConfirmed: boolean;
  states: StateOption[];
  languageOptions: LanguageOption[];
  contactMethods: ContactMethodOption[];
  socialPlatforms: SocialPlatformOption[];
  limits: OnboardingLimits;
  /** Present for the Agent journey; omitted by the explicit non-Agent policy. */
  onboardingJourney?: AgentOnboardingJourney;
}

export interface ProfilePageProps extends PageProps {
  initial: SelfProfileValues;
  validation: ValidationErrors;
  /** Empty when the signed-in user may not move themselves between offices. */
  offices: OfficeGroup[];
  states: StateOption[];
  languageOptions: LanguageOption[];
  specialtyOptions: LanguageOption[];
  contactMethods: ContactMethodOption[];
  socialPlatforms: SocialPlatformOption[];
  identity: ProfileIdentity;
  editable: { office: boolean };
  completeness: ProfileCompleteness;
  limits: ProfileLimits;
}

// ---------------------------------------------------------------------------
// Broker-controlled administration
// ---------------------------------------------------------------------------

/** A closed-set value with the wording and tone the server chose for it. */
export interface AdministrativeChoice {
  value: string;
  label: string;
  tone: StatusTone;
}

export interface LicenseVerification {
  state: string;
  label: string;
  tone: StatusTone;
  verifiedAt: string | null;
  verifiedBy: string | null;
  note: string;
}

/**
 * Contract standing, owned by the contract domain and never stored on the
 * profile. `available: false` means the module is not connected — not that the
 * agent has no contract.
 */
export interface ContractStatus {
  status: string | null;
  label: string;
  tone: StatusTone;
  source: string;
  available: boolean;
  reason: string;
}

/** What an agent may read about their own administrative record. */
export interface ProfileAdministrativeSummary {
  agentStatus: AdministrativeChoice;
  startDate: string | null;
  agentIdentifier: string;
  licenseVerification: LicenseVerification;
  contractStatus: ContractStatus;
  lastReviewedAt: string | null;
}

export interface AdministrationFieldSpec {
  key: string;
  prop: string;
  label: string;
  description: string;
  /** Who owns the value — rendered so nobody has to guess. */
  source: string;
  highImpact: boolean;
  /** Withheld from the person the record is about. */
  private: boolean;
}

export interface AdministrationSubject {
  id: number;
  email: string;
  displayName: string;
  legalName: string;
  preferredDisplayName: string;
  headshotUrl: string | null;
  isActive: boolean;
  isSelf: boolean;
  office: AdministrationOffice | null;
  profileCompleted: boolean;
}

export interface AdministrationOffice {
  id: number;
  name: string;
  pathLabel: string;
  regionName: string;
  isActive: boolean;
  isAssignable: boolean;
}

/** Keys mirror `forms.ADMINISTRATION_FIELD_MAP`. */
export interface AdministrationValues {
  officeId: string;
  agentStatus: string;
  startDate: string;
  agentIdentifier: string;
  licenseVerificationState: string;
  licenseVerificationNote: string;
  /** Omitted without `user.change_user_administration`. */
  internalNotes?: string;
}

export interface AdministrationAssignment {
  id: number;
  /** Stable role code — never use as an authorization check in the UI. */
  role: string;
  roleLabel: string;
  roleDescription: string;
  scopeType: string;
  scopeLabel: string;
  status: string;
  startsAt: string | null;
  endsAt: string | null;
  assignedBy: string | null;
  businessReason: string;
  /** False when the actor may see the assignment but not undo it. */
  canRevoke: boolean;
}

export interface AdministrationHistoryEntry {
  id: string;
  action: string;
  /** Human wording for `action`, resolved server-side. */
  label: string;
  occurredAt: string;
  actor: string;
  outcome: string;
  fields: string[];
  reason: string;
}

// ---------------------------------------------------------------------------
// Activity timeline (P1-080)
// ---------------------------------------------------------------------------

export type ActivityActorKind = "user" | "system" | "service" | "anonymous" | "unknown";

export type ActivityVisibility = "full" | "redacted" | "summary";

export interface ActivityRecordRef {
  type: string;
  id: string;
  label: string;
}

export interface ActivityFileRef {
  id: string;
  name: string;
  contentType: string;
}

export interface ActivityTimelineEntry {
  id: string;
  eventType: string;
  summary: string;
  occurredAt: string;
  occurredAtDisplay: string;
  actorLabel: string;
  actorKind: ActivityActorKind;
  target: ActivityRecordRef;
  related: ActivityRecordRef[];
  source: string;
  visibility: ActivityVisibility;
  outcome: string;
  reason: string;
  metadata: Record<string, unknown>;
  typedAction: string | null;
  files: ActivityFileRef[];
  changeSummary: string[];
}

export interface ActivityTimelinePage {
  entries: ActivityTimelineEntry[];
  nextCursor: string | null;
  hasMore: boolean;
  timezone: string;
}

// ---------------------------------------------------------------------------

export interface AdministrationRoleScope {
  value: string;
  label: string;
  available?: boolean;
  unavailableReason?: string | null;
}

export interface AdministrationRoleOption {
  value: string;
  label: string;
  description?: string;
  protected?: boolean;
  available?: boolean;
  unavailableReason?: string | null;
  scopes: AdministrationRoleScope[];
}

export interface AdministrationOfficeOption {
  id: number;
  name: string;
  pathLabel: string;
  regionName: string;
}

/** The account-access half of a record: who is signed in, and who may end it. */
export interface AccountStatePayload {
  isActive: boolean;
  label: string;
  tone: StatusTone;
  lastLoginAt: string | null;
  joinedAt: string | null;
  /** False for your own record, out of scope, or without the grant. */
  canManage: boolean;
  /** Why `canManage` is false, in the words the page renders. */
  reason: string;
  sessionPolicy: string;
}

export interface AdministrationPayload {
  subject: AdministrationSubject;
  values: AdministrationValues;
  /** Optimistic-concurrency token; posted back as `expected_version`. */
  version: string;
  fields: AdministrationFieldSpec[];
  license: {
    number: string;
    state: string;
    expiresOn: string | null;
    verification: LicenseVerification;
  };
  /** Omitted without `web.view_agent_contracts` — never sent as null. */
  contractStatus?: ContractStatus;
  accountState: AccountStatePayload;
  provenance: { lastChangedAt: string | null; lastChangedBy: string | null };
  history: AdministrationHistoryEntry[];
  assignments: AdministrationAssignment[];
  effectiveAccess: {
    roles: string[];
    scopeLabel: string;
    isSuperuser: boolean;
    liveAssignments: number;
  };
  options: {
    agentStatuses: AdministrativeChoice[];
    licenseVerificationStates: AdministrativeChoice[];
    offices: AdministrationOfficeOption[];
    roles: AdministrationRoleOption[];
  };
  editable: { administration: boolean; roleAssignments: boolean };
  /** Django field names whose change needs confirming before submission. */
  highImpactFields: string[];
  /**
   * Present only when the subject is in the scoped New Agent List. Its
   * contract milestone is contract-domain data, so it is omitted without
   * `web.view_agent_contracts` even when the onboarding block itself is sent.
   */
  onboardingState?: Omit<OnboardingSummary, "contract" | "contractStatus"> & {
    href: string;
    contract?: OnboardingPresentation;
    contractStatus?: string;
  };
}

export interface UserAdministrationPageProps extends PageProps {
  administration: AdministrationPayload;
  validation: ValidationErrors;
  statusOptions: AdministrativeChoice[];
  verificationOptions: AdministrativeChoice[];
}

// ---------------------------------------------------------------------------
// People directory (Operations → Users)
// ---------------------------------------------------------------------------

export interface DirectoryStateBadge {
  value: string;
  label: string;
  tone: StatusTone;
}

/**
 * One row of the directory.
 *
 * The optional members are not "sometimes empty" — they are **absent** unless
 * the reader holds the permission behind them, so `"agentStatus" in row` is a
 * meaningful question. Never render a placeholder for a missing key; the
 * column itself should not exist.
 */
export interface DirectoryRow {
  id: number;
  name: string;
  email: string;
  officeName: string | null;
  officePathLabel: string | null;
  regionName: string | null;
  isActive: boolean;
  accountState: DirectoryStateBadge;
  lastLoginAt: string | null;
  onboarding: DirectoryStateBadge;
  /** Needs `user.view_user_administration`. */
  agentStatus?: DirectoryStateBadge;
  agentIdentifier?: string;
  startDate?: string | null;
  /** Needs `web.view_agent_contracts`. */
  contract?: DirectoryStateBadge & { available: boolean };
}

export interface DirectoryFilters {
  [key: string]: string;
  q: string;
  office: string;
  region: string;
  role: string;
  status: string;
  account: string;
  onboarding: string;
  contract: string;
  lastLogin: string;
}

export interface DirectorySummary {
  total: number;
  active: number;
  disabled: number;
  pendingOnboarding: number;
}

export interface DirectoryFilterOptions {
  offices: FilterOption[];
  regions: FilterOption[];
  roles: FilterOption[];
  accountStates: FilterOption[];
  onboardingStates: FilterOption[];
  lastLoginWindows: FilterOption[];
  contract: { available: boolean; reason: string; options: FilterOption[] };
  /** Present only with `user.view_user_administration`. */
  agentStatuses?: AdministrativeChoice[];
}

export interface UserDirectoryPageProps extends PageProps {
  users: ListResponse<DirectoryRow, DirectoryFilters>;
  summary: DirectorySummary;
  filterOptions: DirectoryFilterOptions;
  scope: { level: string; label: string };
  /** Which permission-gated column groups this reader may render. */
  visible: { administration: boolean; contract: boolean; onboarding: boolean };
  /** Whether rows may link into the administrative record. */
  canOpenRecord: boolean;
}

// ---------------------------------------------------------------------------
// Peer Agent Directory (privacy-aware)
// ---------------------------------------------------------------------------

export interface AgentDirectoryCodeLabel {
  code: string;
  name: string;
}

export interface AgentDirectoryOffice {
  id: number;
  name: string;
  pathLabel: string;
  regionName: string;
}

export interface AgentDirectoryPerson {
  id: number;
  preferredName: string;
  roles: string[];
  office: AgentDirectoryOffice | null;
  workPhone: string;
  workEmail: string;
  specialties: AgentDirectoryCodeLabel[];
  languages: AgentDirectoryCodeLabel[];
  licenseState: string;
  licenseStateName: string;
  /** Gated headshot path — never a permanent public media URL. */
  headshotPath: string | null;
}

export interface AgentDirectoryFilters {
  q: string;
  office: string;
  region: string;
  role: string;
  licenseState: string;
  specialty: string;
  language: string;
  view: string;
  [key: string]: string;
}

export interface AgentDirectoryFilterOptions {
  offices: FilterOption[];
  regions: FilterOption[];
  roles: FilterOption[];
  licenseStates: FilterOption[];
  specialties: FilterOption[];
  languages: FilterOption[];
}

export interface AgentDirectoryEmptyState {
  kind: "no-people" | "no-results";
  title: string;
  description: string;
}

export interface AgentDirectoryPageProps extends PageProps {
  people: ListResponse<AgentDirectoryPerson, AgentDirectoryFilters>;
  filterOptions: AgentDirectoryFilterOptions;
  empty: AgentDirectoryEmptyState | null;
}

export interface AgentDirectoryDetailPageProps extends PageProps {
  person: AgentDirectoryPerson;
}

// ---------------------------------------------------------------------------
// Operational onboarding
// ---------------------------------------------------------------------------

export interface OnboardingPresentation {
  value: string;
  label: string;
  tone: StatusTone;
}

export interface OnboardingSummary {
  user: {
    id: number;
    name: string;
    email: string;
    office: string | null;
    region: string | null;
    startDate: string | null;
    isActive: boolean;
  };
  owner: { id: number; name: string } | null;
  overallStatus: string;
  overall: OnboardingPresentation;
  blockers: { key: string; label: string }[];
  progress: { complete: number; total: number };
  contractStatus: string;
  contract: OnboardingPresentation;
  trainingStatus: string;
  training: OnboardingPresentation;
  openTaskCount: number;
  version: string;
  lastChangedAt: string | null;
  lastChangedBy: string | null;
  requiredSetupComplete?: boolean;
  activationComplete?: boolean;
  currentStep?: AgentJourneyStep;
  journeyVersion?: string;
  journeyUpdatedAt?: string;
  journey?: AgentOnboardingJourney;
}

export interface OnboardingMilestone {
  key: string;
  label: string;
  status: string;
  statusLabel: string;
  tone: StatusTone;
  source: string;
  detail: string;
  updatedAt: string | null;
  correction: { label: string; href: string } | null;
}

/** One catalog tool for one agent, keyed by the catalog's stable slug. */
export interface OnboardingTool {
  key: string;
  label: string;
  state: string;
  stateLabel: string;
  status: string;
  statusLabel: string;
  tone: StatusTone;
  required: boolean;
  invitationState: AgentJourneyInvitationState;
  invitationLabel: string;
  /** When the office sent the vendor invitation, from stored provenance. */
  invitationSentAt: string | null;
  updatedAt: string | null;
  updatedBy: string | null;
  description: string;
  provisioning: string;
  provisioningLabel: string;
  selfService: boolean;
  group: "waiting" | "invitation_sent" | "ready" | "blocked" | "not_applicable";
  delivery: {
    state:
      | "not_recorded"
      | "recorded"
      | "queued"
      | "sent"
      | "retryable"
      | "failed"
      | "suppressed";
    label: string;
    retryable: boolean;
    channels: { channel: string; state: string; label: string }[];
  };
  actions: OnboardingWorkspaceAction[];
}

export type OnboardingWorkspaceActionCode =
  | "mark_invitation_sent"
  | "revoke_invitation"
  | "mark_ready"
  | "mark_blocked"
  | "retry_notification"
  | "initiate_contract"
  | "open_contract"
  | "wait_for_required_setup"
  | "review_blockers";

export interface OnboardingWorkspaceAction {
  code: OnboardingWorkspaceActionCode;
  label: string;
  enabled: boolean;
  unavailableReason: string;
  requiresReason?: boolean;
  tool?: string | null;
  method?: "get" | "post";
  href?: string | null;
  permission?: string;
  source?: "tool" | "contract" | "profile" | "onboarding";
  description?: string;
}

export interface OnboardingOperationalTask {
  id: number;
  title: string;
  dueOn: string | null;
  isBlocking: boolean;
  createdAt: string;
  createdBy: string;
}

export interface OnboardingDetail extends OnboardingSummary {
  milestones: OnboardingMilestone[];
  tools: OnboardingTool[];
  tasks: OnboardingOperationalTask[];
  eligibleNotices: { source: string; key: string; label: string }[];
  contractAction: OnboardingWorkspaceAction;
  recommendedAction: OnboardingWorkspaceAction;
  editable: boolean;
}

export interface NewAgentFilters {
  [key: string]: string;
  q: string;
  office: string;
  owner: string;
  blocker: string;
  overallStatus: string;
  startFrom: string;
  startTo: string;
  contractStatus: string;
  trainingStatus: string;
}

/**
 * One Quick Create action.
 *
 * The list arrives already filtered to what the actor may start — permission,
 * scope, and feature are all decided server-side, so an unavailable action is
 * *absent* rather than hidden here. `href` was reversed from a registered route
 * name; the registry never stores URL strings. See `apps/web/quick_actions.py`.
 */
export interface QuickCreateAction {
  key: string;
  label: string;
  description: string;
  group: string;
  /** Lucide icon name, mapped to a component by the menu. */
  icon: string;
  href: string;
  /** Leaves the hub; the menu discloses this before the click. */
  external: boolean;
}

export interface QuickCreate {
  actions: QuickCreateAction[];
  /** Which offices these actions apply to, shown so the actor knows their hat. */
  scope: { level: string; label: string };
  /** The server decided the set is large enough to deserve a search box. */
  searchable: boolean;
}

/**
 * Global search.
 *
 * Every hit was authorized by the domain that produced it, and `snippet` /
 * `title` are **plain text** — no markup crosses the wire, so highlighting is a
 * client-side match against the string and there is nothing to sanitize.
 */
export interface SearchHit {
  id: string;
  title: string;
  href: string;
  snippet: string;
  meta: string;
}

export interface SearchGroup {
  key: string;
  label: string;
  icon: string;
  hits: SearchHit[];
  /** This source errored; its results are missing rather than empty. */
  failed: boolean;
  /** More matches exist than the cap returned. */
  truncated: boolean;
  allResultsHref: string;
}

export interface SearchResults {
  query: string;
  groups: SearchGroup[];
  total: number;
  /** The query was below the minimum length and was not run. */
  tooShort: boolean;
  minLength: number;
  /** At least one source failed or was skipped; the answer is incomplete. */
  partial: boolean;
}

export interface SearchPageProps extends PageProps {
  results: SearchResults;
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface NewAgentListPageProps extends PageProps {
  agents: ListResponse<OnboardingSummary, NewAgentFilters>;
  filterOptions: {
    offices: FilterOption[];
    owners: FilterOption[];
    blockers: FilterOption[];
    overallStatuses: FilterOption[];
    sourceStatuses: FilterOption[];
  };
  scopeLabel: string;
}

export interface OnboardingWorkspacePageProps extends PageProps {
  onboarding: OnboardingDetail;
  profileSummary: {
    headshotUrl: string | null;
    fields: { key: string; label: string; value: string }[];
    sensitiveFieldsIncluded: boolean;
  };
  confirmedOffice: OnboardingOfficeSelection | null;
  ownerOptions: FilterOption[];
  toolStateOptions: FilterOption[];
  activity: {
    id: string;
    action: string;
    actor: string;
    occurredAt: string;
    changes: string[];
  }[];
  validation: ValidationErrors;
  privacy: { notesAllowed: boolean; taskPolicy: string };
}

// ---------------------------------------------------------------------------
// Quick Access administration
// ---------------------------------------------------------------------------

export type QuickAccessDestinationType = "external_url" | "internal_route";
export type QuickAccessSsoCapability = "none" | "microsoft_entra" | "saml" | "oidc";
export type QuickAccessIntegrationHealth =
  | "unknown"
  | "healthy"
  | "degraded"
  | "offline";
export type QuickAccessSetupBehavior =
  | "none"
  | "self_service"
  | "request_access"
  | "provisioned";
export type QuickAccessOwnerScope = "company" | "scoped";

export interface QuickAccessChoice {
  value: string;
  label: string;
}

export interface QuickAccessOfficeChoice {
  value: number;
  label: string;
}

export interface QuickAccessAudience {
  companyWide: boolean;
  roles: { code: string; label: string }[];
  offices: {
    id: number;
    name: string;
    stableKey: string;
    includeDescendants: boolean;
  }[];
}

/**
 * One row of the administration list.
 *
 * `status` is a derived badge, not a raw field: a link can be active and still
 * be invisible because its publish window has not opened.
 */
export interface QuickAccessLinkRow {
  id: number;
  stableKey: string;
  name: string;
  description: string;
  destinationType: QuickAccessDestinationType;
  destinationValue: string;
  href: string;
  icon: string;
  sortOrder: number;
  isActive: boolean;
  isArchived: boolean;
  status: { value: string; label: string; tone: StatusTone };
  publishStartAt: string | null;
  publishEndAt: string | null;
  ssoCapability: QuickAccessSsoCapability;
  integrationHealth: QuickAccessIntegrationHealth;
  setupBehavior: QuickAccessSetupBehavior;
  ownerScope: QuickAccessOwnerScope;
  ownerOffice: string | null;
  audience: QuickAccessAudience;
  /** Server's answer, mirrored in the UI. Never the basis for authorization. */
  canManage: boolean;
  updatedAt: string | null;
  /** Optimistic-concurrency token echoed back on submit. */
  version: string;
}

export interface QuickAccessPreviewLink {
  id: number;
  name: string;
  stableKey: string;
  visible: boolean;
  /** Every reason it stays hidden, not just the first. */
  reasons: string[];
}

export interface QuickAccessPreview {
  roleCode: string;
  officeId: number | null;
  officeName: string | null;
  /** The chosen office is outside the administrator's scope. */
  outOfScope: boolean;
  links: QuickAccessPreviewLink[];
}

export interface QuickAccessCapabilities {
  companyWide: boolean;
  scopeLevel: "brokerage" | "scoped";
}

/** Static choice lists the create drawer renders without a round trip. */
export interface QuickAccessCreateOptions {
  iconOptions: QuickAccessChoice[];
  internalDestinations: QuickAccessChoice[];
  destinationTypeOptions: QuickAccessChoice[];
  ssoOptions: QuickAccessChoice[];
  healthOptions: QuickAccessChoice[];
  setupOptions: QuickAccessChoice[];
}

export interface QuickAccessCreateSheet {
  open: boolean;
  /** Echoed submission, shaped for the field set's `defaults`. */
  draft: Record<string, unknown>;
  /** Widening changes the server refused until they are acknowledged. */
  pendingConfirmation: QuickAccessExposureChange[];
}

export interface QuickAccessAdministrationPageProps extends PageProps {
  links: ListResponse<QuickAccessLinkRow, { q: string; status: string }>;
  statusOptions: QuickAccessChoice[];
  roleOptions: QuickAccessChoice[];
  officeOptions: QuickAccessOfficeChoice[];
  preview: QuickAccessPreview | null;
  capabilities: QuickAccessCapabilities;
  createOptions: QuickAccessCreateOptions;
  createSheet: QuickAccessCreateSheet | null;
  errors?: ValidationErrors;
}

/** One widening change the administrator has to confirm before it is saved. */
export interface QuickAccessExposureChange {
  label: string;
  from: string;
  to: string;
  impact: string;
}

export interface QuickAccessLinkFormPageProps extends PageProps {
  link: QuickAccessLinkRow | null;
  errors: ValidationErrors;
  posted: Record<string, string[]> | null;
  pendingConfirmation: QuickAccessExposureChange[];
  iconOptions: QuickAccessChoice[];
  internalDestinations: QuickAccessChoice[];
  destinationTypeOptions: QuickAccessChoice[];
  ssoOptions: QuickAccessChoice[];
  healthOptions: QuickAccessChoice[];
  setupOptions: QuickAccessChoice[];
  roleOptions: QuickAccessChoice[];
  officeOptions: QuickAccessOfficeChoice[];
  capabilities: QuickAccessCapabilities;
}

/** Role-assignment administration (ops: Assign User Roles). */

export interface RoleAssignmentListFilters {
  [key: string]: string;
  q: string;
  role: string;
  status: string;
  office: string;
  region: string;
}

export interface RoleAssignmentListRow {
  id: number;
  email: string;
  displayName: string;
  isActive: boolean;
  isSelf: boolean;
  office: { id: number; name: string; pathLabel: string } | null;
  liveRoles: Array<{
    role: string;
    roleLabel: string;
    scopeLabel: string;
    status: string;
  }>;
  counts: {
    active: number;
    scheduled: number;
    expired: number;
    revoked: number;
  };
}

export interface RoleAssignmentAccessSnapshot {
  roles: string[];
  roleKeys: string[];
  permissions: string[];
  scopeLabel: string;
  companyWide: boolean;
  assignedRecord: boolean;
  liveAssignments: number;
}

export interface RoleAssignmentAccessChange {
  label: string;
  from: string;
  to: string;
  impact: string;
}

export interface RoleAssignmentNavItem {
  key: string;
  label: string;
  section: string;
}

export interface RoleAssignmentPreview {
  before: RoleAssignmentAccessSnapshot;
  after: RoleAssignmentAccessSnapshot;
  permissionDelta: { added: string[]; removed: string[] };
  navigationDelta: {
    added: RoleAssignmentNavItem[];
    removed: RoleAssignmentNavItem[];
  };
  highImpact: RoleAssignmentAccessChange[];
  requiresConfirmation: boolean;
  warnings: string[];
}

export interface RoleAssignmentWorkspaceAssignment {
  id: number;
  role: string;
  roleLabel: string;
  roleDescription: string;
  scopeType: string;
  scopeLabel: string;
  scopeOfficeId: number | null;
  status: string;
  startsAt: string | null;
  endsAt: string | null;
  assignedBy: string | null;
  revokedBy: string | null;
  revokedAt: string | null;
  businessReason: string;
  version: string;
  canEdit: boolean;
  canRevoke: boolean;
  access: {
    roleLabel: string;
    scopeLabel: string;
    permissions: string[];
    orgReach: string;
  };
  isLastLive: boolean;
  isManagement: boolean;
}

export interface RoleAssignmentWorkspace {
  subject: {
    id: number;
    email: string;
    displayName: string;
    isActive: boolean;
    isSelf: boolean;
    office: { id: number; name: string; pathLabel: string } | null;
    agentStatus: string;
  };
  assignments: RoleAssignmentWorkspaceAssignment[];
  effectiveAccess: RoleAssignmentAccessSnapshot;
  grantVersion: string;
  options: {
    roles: AdministrationRoleOption[];
    offices: AdministrationOfficeOption[];
  };
  editable: boolean;
  administrationHref: string;
}

export interface RoleAssignmentAdministrationPageProps extends PageProps {
  users: ListResponse<RoleAssignmentListRow, RoleAssignmentListFilters>;
  filterOptions: {
    roles: FilterOption[];
    statuses: FilterOption[];
    offices: Array<{
      id: number;
      name: string;
      pathLabel: string;
      kind: string;
    }>;
  };
  scope: { level: string; label: string };
}

export interface RoleAssignmentWorkspacePageProps extends PageProps {
  workspace: RoleAssignmentWorkspace;
  validation: ValidationErrors;
  preview: RoleAssignmentPreview | null;
  scope: { level: string; label: string };
}

export interface OfficeContactPerson {
  id: number;
  displayName: string;
  email: string;
  phoneNumber?: string;
  isPrimary: boolean;
  assignmentType: string;
  assignmentTypeLabel: string;
}

export interface OfficeHourEntry {
  day?: string;
  open?: string | null;
  close?: string | null;
  [key: string]: unknown;
}

export interface OfficeInfoPayload {
  id: number;
  name: string;
  slug: string;
  stableKey: string;
  kind: string;
  pathLabel: string;
  regionName: string;
  isActive: boolean;
  streetAddress: string;
  city: string;
  state: string;
  zipCode: string;
  mainPhone: string;
  publicEmail: string;
  internalEmail: string;
  officeHours: unknown[];
  parkingInstructions: string;
  accessInstructions: string;
  accessInstructionsInternal: boolean;
  directionsUrl: string;
  includeInternal: boolean;
  updatedAt: string;
  version: string;
  generatedAt?: string;
  contacts: {
    branchManager: OfficeContactPerson | null;
    branchAdmin: OfficeContactPerson | null;
    brokers: OfficeContactPerson[];
    transactionCoordinator: OfficeContactPerson | null;
    itSupport: OfficeContactPerson | null;
  };
  corporateContacts: OfficeContactPerson[];
}

export interface OfficeInfoPageProps extends PageProps {
  officeInfo: OfficeInfoPayload | null;
  empty: { title: string; description: string } | null;
}

export type OfficeResourceType = "content" | "link" | "file";

export type OfficeResourceSourceLevel = "company" | "region" | "office";

export interface OfficeResourceItem {
  slug: string;
  title: string;
  summary: string;
  category: string;
  categoryLabel: string;
  resourceType: OfficeResourceType;
  sourceLabel: string;
  sourceLevel: OfficeResourceSourceLevel;
  /** Present for link resources; guaranteed HTTPS by model validation. */
  url?: string;
  /** Present for file resources; authorized download endpoint on the app origin. */
  downloadUrl?: string;
  fileName?: string;
  /** Present for content resources. */
  body?: string;
}

export interface OfficeResourceGroup {
  key: string;
  label: string;
  items: OfficeResourceItem[];
}

export interface OfficeResourcesPageProps extends PageProps {
  groups: OfficeResourceGroup[];
  filters: { q: string; category: string };
  categories: { value: string; label: string }[];
  empty: {
    title: string;
    description: string;
    kind: "empty" | "no-results" | "no-office";
  } | null;
}

export type OfficeResourceState =
  | "active"
  | "inactive"
  | "scheduled"
  | "expired"
  | "archived";

export interface AdminOfficeResourceRow {
  id: number;
  slug: string;
  title: string;
  summary: string;
  category: string;
  categoryLabel: string;
  resourceType: string;
  typeLabel: string;
  ownerPathLabel: string;
  ownerStableKey: string;
  sourceLabel: string;
  state: OfficeResourceState;
  isActive: boolean;
  isArchived: boolean;
  processingState: string;
  fileName: string;
  startsAt: string;
  endsAt: string;
  updatedAt: string;
}

export interface AdminOfficeResourceDetail {
  id: number;
  slug: string;
  title: string;
  summary: string;
  category: string;
  resourceType: string;
  body: string;
  url: string;
  ownerId: number;
  ownerPathLabel: string;
  isActive: boolean;
  isArchived: boolean;
  archivedAt: string;
  processingState: string;
  fileName: string;
  downloadUrl: string;
  sortOrder: number;
  startsAt: string;
  endsAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface AdminResourcePreviewItem {
  slug: string;
  title: string;
  summary: string;
  categoryLabel: string;
  resourceType: string;
  sourceLabel: string;
  origin: "local" | "inherited";
  url?: string;
  downloadUrl?: string;
  body?: string;
}

export interface OfficeResourceListFilters {
  q: string;
  category: string;
  resource_type: string;
  status: string;
  owner: string;
  region: string;
  [key: string]: string;
}

export interface OfficeResourceCreateSheet {
  open: boolean;
  /** Previously submitted values (camelCase form defaults) after a 422. */
  draft: Record<string, string>;
}

export interface OfficeResourcesAdministrationPageProps extends PageProps {
  resources: ListResponse<AdminOfficeResourceRow, OfficeResourceListFilters>;
  writableOffices: { id: number; label: string; kind: string }[];
  createSheet: OfficeResourceCreateSheet | null;
  filterOptions: {
    categories: FilterOption[];
    types: FilterOption[];
    statuses: FilterOption[];
    owners: FilterOption[];
  };
  capabilities: { canManage: boolean; canPublishCompany: boolean };
  scope: { level: string; label: string };
  validation: ValidationErrors;
}

export interface OfficeResourceWorkspacePageProps extends PageProps {
  resource: AdminOfficeResourceDetail | null;
  version: string;
  preview: {
    officeId: number;
    officeLabel: string;
    items: AdminResourcePreviewItem[];
    localCount: number;
    inheritedCount: number;
  } | null;
  writableOffices: { id: number; label: string; kind: string }[];
  capabilities: { canManage: boolean; canPublishCompany: boolean };
  categories: FilterOption[];
  types: FilterOption[];
  scope: { level: string; label: string };
  validation: ValidationErrors;
}

export interface OfficeListFilters {
  q: string;
  kind: string;
  status: string;
  region: string;
  [key: string]: string;
}

export interface OfficeListRow {
  id: number;
  name: string;
  stableKey: string;
  slug: string;
  kind: string;
  kindLabel: string;
  pathLabel: string;
  regionName: string;
  isActive: boolean;
  isAssignable: boolean;
  city: string;
  state: string;
}

export interface OfficeAdministrationPageProps extends PageProps {
  offices: ListResponse<OfficeListRow, OfficeListFilters>;
  filterOptions: {
    kinds: FilterOption[];
    statuses: FilterOption[];
    regions: FilterOption[];
  };
  capabilities: {
    companyWide: boolean;
    canRestructure: boolean;
  };
  scope: { level: string; label: string };
}

export interface OfficeContactRow {
  id: number;
  assignmentType: string;
  assignmentTypeLabel: string;
  userId: number;
  displayName: string;
  email: string;
  isPrimary: boolean;
  startsAt: string;
  endsAt: string;
  isCurrent: boolean;
}

export interface OfficeResourceLink {
  key: string;
  label: string;
  description: string;
  href: string;
  available: boolean;
  note?: string;
}

export interface OfficeAdministrationDetail {
  office: {
    id: number;
    name: string;
    stableKey: string;
    slug: string;
    kind: string;
    kindLabel: string;
    pathLabel: string;
    regionName: string;
    parentId: number | null;
    parentPathLabel: string | null;
    isActive: boolean;
    isAssignable: boolean;
    streetAddress: string;
    city: string;
    state: string;
    zipCode: string;
    mainPhone: string;
    publicEmail: string;
    internalEmail: string;
    officeHours: unknown[];
    officeHoursText: string;
    parkingInstructions: string;
    accessInstructions: string;
    accessInstructionsInternal: boolean;
    updatedAt: string;
  };
  contacts: OfficeContactRow[];
  contactTypes: FilterOption[];
  contactCandidates: Array<{
    id: number;
    displayName: string;
    email: string;
  }>;
  version: string;
  capabilities: {
    companyWide: boolean;
    canEditInfo: boolean;
    canEditSensitive: boolean;
    canRestructure: boolean;
    highImpactFields: string[];
  };
  parentOptions: Array<{
    id: number;
    name: string;
    pathLabel: string;
    kind: string;
    stableKey: string;
  }>;
  kindOptions: FilterOption[];
  resourceLinks: OfficeResourceLink[];
  agentPreview: OfficeInfoPayload;
  breadcrumbs: Array<{ name: string; id: number }>;
}

export interface OfficeAdministrationDetailPageProps extends PageProps {
  administration: OfficeAdministrationDetail;
  validation: ValidationErrors;
  preview: {
    highImpact: Array<{
      label: string;
      from: string;
      to: string;
      impact: string;
    }>;
    requiresConfirmation: boolean;
  } | null;
  scope: { level: string; label: string };
}

/**
 * Announcements.
 *
 * Every classification arrives already resolved by the server's presentation
 * adapter: a stable `code`, a human `label`, a semantic `tone`, and an
 * `srLabel` sentence. The page maps tone to a design-system badge and does no
 * classification of its own — there is no second copy of the taxonomy here to
 * drift from `apps/announcements/taxonomy.py`.
 */
export interface AnnouncementBadge {
  code: string;
  label: string;
  tone: StatusTone;
  /** Full sentence for assistive technology; never color alone. */
  srLabel: string;
  /** False when the stored code is unrecognized and a fallback was shown. */
  known: boolean;
}

export interface AnnouncementPriorityBadge extends AnnouncementBadge {
  /** Lower sorts first. The server has already applied it. */
  rank: number;
}

/**
 * One audience selector, already resolved to a label by the server.
 *
 * Selectors combine as a **union**: a reader who matches any one of them sees
 * the announcement. The client never evaluates them — this is a description of
 * who was addressed, not the rule that decided the reader may be here.
 */
export interface AnnouncementAudienceEntry {
  kind: "company" | "role" | "region" | "office" | "user";
  label: string;
  code: string;
  officeId: number | null;
  userId: number | null;
}

/**
 * The optional call-to-action button. Both halves are required by a database
 * constraint, so a payload that exists can always be drawn — there is no
 * "label without a link" state for a renderer to guess about.
 */
export interface AnnouncementCta {
  label: string;
  url: string;
}

/**
 * One inline run inside a body block.
 *
 * The server's block tree is the *only* representation an announcement body
 * takes on the way to a reader — there is no HTML in this payload, so there is
 * nothing to sanitize on arrival and no `dangerouslySetInnerHTML` anywhere in
 * the renderer. Link hrefs already passed the server's scheme allowlist; a
 * refused one arrives as a plain `text` span.
 */
export interface AnnouncementInlineSpan {
  type: "text" | "strong" | "em" | "link";
  value: string;
  href?: string;
}

export interface AnnouncementBlock {
  type: "paragraph" | "heading" | "list" | "quote";
  /** Heading depth, 2 or 3. Present on headings only. */
  level?: number;
  /** Ordered list rather than bulleted. Present on lists only. */
  ordered?: boolean;
  /** Inline content for paragraphs, headings, and quotes. */
  spans?: AnnouncementInlineSpan[];
  /** One span list per list item. Present on lists only. */
  items?: AnnouncementInlineSpan[][];
}

export interface AnnouncementRow {
  id: number;
  slug: string;
  title: string;
  summary: string;
  body: string;
  publishedAt: string | null;
  expiresAt: string | null;
  category: AnnouncementBadge;
  priority: AnnouncementPriorityBadge;
  scope: { level: string; label: string; officeName: string };
  /** Promotes the row to the important tier when sorting. Never audience. */
  isPinned: boolean;
  cta: AnnouncementCta | null;
  /** The body as structured blocks. The only form a reader is shown. */
  bodyBlocks: AnnouncementBlock[];
}

/**
 * One stored file. `url` and every entry in `variants` is a view path that
 * re-runs the announcement's audience check on each request — not a signed or
 * otherwise durable link, so none of them can be shared onward.
 */
export interface AnnouncementMedia {
  id: number;
  role: "hero" | "attachment";
  displayName: string;
  mediaType: string;
  byteSize: number;
  width: number | null;
  height: number | null;
  isImage: boolean;
  url: string;
  /** Generated responsive derivatives, keyed by label. May be empty. */
  variants: Record<string, string>;
}

/** Administrator-only fields. Recipients never receive these. */
export interface AnnouncementMediaAdmin extends AnnouncementMedia {
  processingState: "pending" | "ready" | "quarantined" | "failed";
  processingNote: string;
  isActive: boolean;
  checksum: string;
  sortOrder: number;
}

export interface AnnouncementDetail extends AnnouncementRow {
  audience: AnnouncementAudienceEntry[];
  hero: AnnouncementMedia | null;
  attachments: AnnouncementMedia[];
}

export interface AnnouncementMediaLimits {
  hero: { extensions: string[]; maxBytes: number; minWidth: number };
  attachment: { extensions: string[]; maxBytes: number; maxCount: number };
}

export interface AnnouncementMediaManagerPageProps extends PageProps {
  announcement: { id: number; title: string; status: string };
  media: {
    hero: AnnouncementMediaAdmin | null;
    attachments: AnnouncementMediaAdmin[];
  };
  limits: AnnouncementMediaLimits;
  validation: ValidationErrors;
}

export interface AnnouncementDetailPageProps extends PageProps {
  announcement: AnnouncementDetail;
}

/** One result from the scoped recipient typeahead. Never a full directory. */
export interface AnnouncementRecipientResult {
  id: number;
  name: string;
  email: string;
  officeName: string;
}

export interface AnnouncementFilters {
  category: string;
  priority: string;
  /** Filter keys the server refused to apply because the value was unknown. */
  rejected: string[];
  [key: string]: string | string[];
}

export interface AnnouncementsPageProps extends PageProps {
  feed: ListResponse<AnnouncementRow, AnnouncementFilters>;
  filterOptions: {
    categories: FilterOption[];
    priorities: FilterOption[];
  };
}

export interface TrainingPresentationBadge {
  code: string;
  label: string;
  tone: StatusTone;
  known: boolean;
}

export interface TrainingCompletion {
  status: string;
  label: string;
  progressPercent?: number | null;
  completedAt?: string | null;
  startedAt?: string | null;
}

export interface TrainingRequiredSummary {
  requiredCount: number;
  completedCount: number;
  percent: number;
  remainingCount: number;
  nextItem: { id: number; title: string; detailUrl: string } | null;
}

export interface TrainingQuizChoice {
  id: string;
  label: string;
}

export interface TrainingQuizQuestion {
  id: number;
  prompt: string;
  choices: TrainingQuizChoice[];
  sortOrder: number;
}

export interface TrainingQuizPayload {
  passThresholdPercent: number;
  maxAttempts: number | null;
  feedbackPolicy: string;
  attemptCount: number;
  attemptsRemaining: number | null;
  canAttempt: boolean;
  latestAttempt: {
    attemptNumber: number;
    scorePercent: number;
    passed: boolean;
    submittedAt: string;
  } | null;
  questions: TrainingQuizQuestion[];
}

export interface TrainingSessionRegistration {
  status: string;
  registeredAt: string;
  cancelledAt: string | null;
  attendedAt: string | null;
}

export interface TrainingSessionPayload {
  startsAt: string;
  timezone: string;
  durationMinutes: number;
  capacity: number | null;
  seatsTaken: number;
  seatsRemaining: number | null;
  meetingUrl: string;
  registrationOpensAt: string | null;
  registrationClosesAt: string | null;
  registration: TrainingSessionRegistration | null;
}

export interface TrainingCertificatePayload {
  status: string;
  available: boolean;
  approvedAt: string | null;
  downloadUrl: string | null;
}

export interface TrainingCourseRollup {
  total: number;
  completed: number;
  percent: number;
  modules: { id: number; completed: boolean }[];
}

export interface TrainingRow {
  id: number;
  slug: string;
  title: string;
  summary: string;
  contentType: TrainingPresentationBadge;
  category: TrainingPresentationBadge;
  scope: { level: string; label: string; officeName: string };
  isRequired: boolean;
  estimatedMinutes: number | null;
  toolCode: string | null;
  completion: TrainingCompletion;
  publishedAt: string | null;
  detailUrl: string;
}

export interface TrainingFilters {
  category: string;
  type: string;
  required: string;
  tool: string;
  completion: string;
  view: string;
  q: string;
  rejected?: string[];
  [key: string]: string | string[] | undefined;
}

export interface TrainingEmbed {
  url: string;
  provider: string;
  host?: string;
  available: boolean;
}

export interface TranscriptionSegment {
  startMs: number;
  endMs: number;
  text: string;
}

export interface TrainingTranscription {
  segments: TranscriptionSegment[];
  hasSearchableText: boolean;
}

export interface TrainingMediaItem {
  id: number;
  role: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  url: string;
  processingState?: string;
  isReadable?: boolean;
}

export interface TrainingModuleRow {
  id: number;
  title: string;
  contentType: TrainingPresentationBadge;
  sortOrder: number;
  estimatedMinutes: number | null;
  completion?: TrainingCompletion;
  detailUrl?: string;
}

export interface TrainingDetail extends TrainingRow {
  body: string;
  bodyBlocks: AnnouncementBlock[];
  externalUrl: { url: string; label: string } | null;
  embed: TrainingEmbed | null;
  primaryMedia: TrainingMediaItem | null;
  attachments: TrainingMediaItem[];
  transcription: TrainingTranscription | null;
  modules: TrainingModuleRow[];
  courseRollup?: TrainingCourseRollup | null;
  interactivity: "available" | "unavailable";
  quiz?: TrainingQuizPayload | null;
  liveSession?: TrainingSessionPayload | null;
  certificate?: TrainingCertificatePayload | null;
  versionNumber?: number;
  versionCompletionPolicy?: string;
  canMarkComplete?: boolean;
  canMarkStarted?: boolean;
}

export interface TrainingLearningPageProps extends PageProps {
  library: ListResponse<TrainingRow, TrainingFilters> & {
    requiredSummary?: TrainingRequiredSummary;
  };
  requiredSummary?: TrainingRequiredSummary;
  filterOptions: {
    categories: FilterOption[];
    contentTypes: FilterOption[];
    tools: FilterOption[];
    completions: FilterOption[];
  };
}

export interface TrainingDetailPageProps extends PageProps {
  content: TrainingDetail;
  errors?: ValidationErrors;
}

export interface TrainingLifecycle {
  code: "draft" | "scheduled" | "live" | "expired" | "archived";
  label: string;
  tone: StatusTone;
}

export interface TrainingAdminRow {
  id: number;
  slug: string;
  title: string;
  summary: string;
  lifecycle: TrainingLifecycle;
  status: "draft" | "published" | "archived";
  contentType: { code: string; label: string };
  category: { code: string; label: string } | null;
  isRequired: boolean;
  versionNumber: number;
  versionLabel: string;
  ownerOffice: { id: number; name: string };
  scopeLevel: string;
  audience: AnnouncementAudienceEntry[];
  publishAt: string | null;
  expiresAt: string | null;
  publishedAt: string | null;
  updatedAt: string | null;
  updatedBy: string;
  createdBy: string;
  /** Opaque concurrency token. Sent back on every write; a mismatch is a 409. */
  version: string;
}

export interface TrainingValidationItem {
  field: string;
  message: string;
}

export interface TrainingValidation {
  isPublishable: boolean;
  items: TrainingValidationItem[];
}

export interface TrainingHistoryEntry {
  id: string;
  action: string;
  label: string;
  tone: StatusTone;
  actor: string;
  occurredAt: string;
}

export interface TrainingAdminDetail extends TrainingAdminRow {
  body: string;
  categoryCode: string;
  contentTypeCode: string;
  toolCode: string;
  estimatedMinutes: number | null;
  externalUrl: string;
  embedUrl: string;
  displayOrder: number;
  versionFamily: string;
  versionCompletionPolicy?: string;
  validation: TrainingValidation;
  history: TrainingHistoryEntry[];
  usage: {
    recipientEstimate: number;
    completed: number;
    inProgress: number;
    notStarted: number;
  };
  mediaHref: string;
  quiz?: {
    passThresholdPercent: number;
    maxAttempts: number | null;
    feedbackPolicy: string;
    questions: {
      id: number;
      prompt: string;
      choices: TrainingQuizChoice[];
      correctChoiceIds: string[];
      sortOrder: number;
    }[];
  } | null;
  liveSession?: {
    startsAt: string;
    timezone: string;
    durationMinutes: number;
    capacity: number | null;
    meetingUrl: string;
    registrationOpensAt: string | null;
    registrationClosesAt: string | null;
    seatsTaken: number;
  } | null;
  modules?: {
    id: number;
    title: string;
    contentType: string;
    sortOrder: number;
  }[];
}

export interface TrainingCapabilities {
  canAuthor: boolean;
  canPublish: boolean;
}

export interface TrainingWorkspaceFilters {
  q: string;
  lifecycle: string;
  category: string;
  type: string;
  audience: string;
  author: string;
  office: string;
  required: string;
  publishedFrom: string;
  publishedTo: string;
  [key: string]: string | string[];
}

export interface TrainingCreateSheet {
  open: boolean;
  draft: Record<string, string | string[]>;
}

export interface TrainingAdministrationPageProps extends PageProps {
  trainings: ListResponse<TrainingAdminRow, TrainingWorkspaceFilters>;
  filterOptions: {
    categories: FilterOption[];
    contentTypes: FilterOption[];
    offices: AnnouncementOfficeOption[];
  };
  createOptions: {
    offices: AnnouncementOfficeOption[];
    categories: FilterOption[];
    contentTypes: FilterOption[];
    tools: FilterOption[];
    audience: AnnouncementAudienceOptions;
  };
  createSheet: TrainingCreateSheet | null;
  capabilities: TrainingCapabilities;
  errors: ValidationErrors;
}

export interface TrainingPreviewReach {
  chosen: boolean;
  matched: boolean;
  officeId: number | null;
  officeName: string;
  roleCode: string;
  hasNamedRecipients: boolean;
}

export interface TrainingPreview {
  article: TrainingDetail;
  reach: TrainingPreviewReach;
  roleCode: string;
  officeId: number | null;
}

export interface TrainingWorkspacePageProps extends PageProps {
  content: TrainingAdminDetail | null;
  officeOptions: AnnouncementOfficeOption[];
  categoryOptions: FilterOption[];
  contentTypeOptions: FilterOption[];
  toolOptions: FilterOption[];
  audienceOptions: AnnouncementAudienceOptions;
  capabilities: TrainingCapabilities;
  preview: TrainingPreview | null;
  errors: ValidationErrors;
  posted: Record<string, string[]> | null;
}

export interface TrainingRecipientResult {
  id: number;
  name: string;
  email: string;
  officeName: string;
}

export interface TrainingMediaAdmin {
  id: number;
  role: "primary" | "attachment";
  displayName: string;
  mediaType: string;
  byteSize: number;
  width: number | null;
  height: number | null;
  isImage: boolean;
  url: string;
  variants: Record<string, string>;
  processingState: "pending" | "ready" | "quarantined" | "failed";
  processingNote: string;
  isActive: boolean;
  checksum: string;
  sortOrder: number;
}

export interface TrainingMediaLimits {
  primary: { extensions: string[]; maxBytes: number; minWidth?: number };
  attachment: { extensions: string[]; maxBytes: number; maxCount: number };
}

export interface TrainingMediaManagerPageProps extends PageProps {
  content: { id: number; title: string; status: string };
  media: {
    primary: TrainingMediaAdmin | null;
    attachments: TrainingMediaAdmin[];
  };
  limits: TrainingMediaLimits;
  validation: ValidationErrors;
}

/**
 * The administration workspace.
 *
 * Three grants reach this surface and they are deliberately separate:
 * `canAuthor` writes drafts, `canPublish` moves the lifecycle, `canPin`
 * changes feed order. The page mirrors the server's answer so a control is
 * never offered for an action the save would refuse — and mirroring is all it
 * does. Every one of these is re-derived on the server for every write.
 */
export interface AnnouncementCapabilities {
  canAuthor: boolean;
  canPublish: boolean;
  canPin: boolean;
}

/**
 * The state an administrator reads. Richer than the stored status: "Scheduled",
 * "Live", and "Expired" are all `status: "published"` plus a window test, and
 * the server derives all three from the same predicate the feed applies.
 */
export interface AnnouncementLifecycle {
  code: "draft" | "scheduled" | "live" | "expired" | "archived";
  label: string;
  tone: StatusTone;
}

export interface AnnouncementAdminRow {
  id: number;
  slug: string;
  title: string;
  summary: string;
  lifecycle: AnnouncementLifecycle;
  status: "draft" | "published" | "archived";
  category: AnnouncementBadge;
  priority: AnnouncementPriorityBadge;
  isPinned: boolean;
  ownerOffice: { id: number; name: string };
  scopeLevel: string;
  audience: AnnouncementAudienceEntry[];
  publishAt: string | null;
  expiresAt: string | null;
  publishedAt: string | null;
  updatedAt: string | null;
  updatedBy: string;
  createdBy: string;
  /** Opaque concurrency token. Sent back on every write; a mismatch is a 409. */
  version: string;
}

/** One outstanding item between the draft and publication. */
export interface AnnouncementValidationItem {
  field: string;
  message: string;
}

export interface AnnouncementValidation {
  isPublishable: boolean;
  items: AnnouncementValidationItem[];
}

/** One lifecycle entry, read from the audit trail rather than a second table. */
export interface AnnouncementHistoryEntry {
  id: string;
  action: string;
  label: string;
  tone: StatusTone;
  actor: string;
  occurredAt: string;
}

export interface AnnouncementAdminDetail extends AnnouncementAdminRow {
  body: string;
  categoryCode: string;
  priorityCode: string;
  cta: AnnouncementCta | null;
  validation: AnnouncementValidation;
  history: AnnouncementHistoryEntry[];
  mediaHref: string;
}

/** An office picker entry. `value` is the office id, not a stable code. */
export interface AnnouncementOfficeOption {
  value: number;
  label: string;
}

export interface AnnouncementAudienceOptions {
  canTargetCompany: boolean;
  regions: AnnouncementOfficeOption[];
  offices: AnnouncementOfficeOption[];
  roles: FilterOption[];
}

export interface AnnouncementWorkspaceFilters {
  q: string;
  lifecycle: string;
  category: string;
  priority: string;
  audience: string;
  author: string;
  office: string;
  publishedFrom: string;
  publishedTo: string;
  [key: string]: string | string[];
}

/**
 * State of the create drawer on the queue page.
 *
 * `null` on a normal visit. A rejected create answers with this page instead of
 * the standalone form, flagged open and carrying back what was typed, so the
 * author fixes the field they were already looking at.
 */
export interface AnnouncementCreateSheet {
  open: boolean;
  draft: Record<string, string | string[]>;
}

export interface AnnouncementAdministrationPageProps extends PageProps {
  announcements: ListResponse<AnnouncementAdminRow, AnnouncementWorkspaceFilters>;
  filterOptions: {
    categories: FilterOption[];
    priorities: FilterOption[];
    offices: AnnouncementOfficeOption[];
  };
  /** Everything the create drawer renders, so opening it costs no round trip. */
  createOptions: {
    offices: AnnouncementOfficeOption[];
    categories: FilterOption[];
    priorities: FilterOption[];
    audience: AnnouncementAudienceOptions;
  };
  createSheet: AnnouncementCreateSheet | null;
  capabilities: AnnouncementCapabilities;
  errors: ValidationErrors;
}

/**
 * Whether a chosen effective audience would actually receive the draft.
 *
 * `matched` answers for an office-and-role reader. A person named individually
 * cannot be stood in for by that pair, so `hasNamedRecipients` is reported
 * separately rather than folded into a misleading "no".
 */
export interface AnnouncementPreviewReach {
  chosen: boolean;
  matched: boolean;
  officeId: number | null;
  officeName: string;
  roleCode: string;
  hasNamedRecipients: boolean;
}

export interface AnnouncementPreview {
  article: AnnouncementDetail;
  reach: AnnouncementPreviewReach;
  roleCode: string;
  officeId: number | null;
}

export interface AnnouncementWorkspacePageProps extends PageProps {
  announcement: AnnouncementAdminDetail | null;
  officeOptions: AnnouncementOfficeOption[];
  categoryOptions: FilterOption[];
  priorityOptions: FilterOption[];
  audienceOptions: AnnouncementAudienceOptions;
  capabilities: AnnouncementCapabilities;
  preview: AnnouncementPreview | null;
  errors: ValidationErrors;
  /** What was submitted, echoed back so a rejected save loses no typing. */
  posted: Record<string, string[]> | null;
}

export interface ContractTemplateRow {
  publicId: string;
  stableKey: string;
  name: string;
  description: string;
  status: string;
  statusLabel: string;
  statusTone: string;
  jurisdictionStateCodes: string[];
  companyWide: boolean;
  effectiveFrom: string;
  effectiveUntil: string;
  activeVersionPk?: number | null;
  activeVersionId: string | null;
  /** Version workspace to open: latest draft, else active, else newest. */
  workspaceVersionPk?: number | null;
}

export interface ContractTemplateFieldLayoutItem {
  id: string;
  name: string;
  type: string;
  role: string;
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ContractTemplateVersionDetail {
  id: number;
  publicId: string;
  templatePublicId: string;
  versionLabel: string;
  displayName: string;
  description: string;
  status: string;
  statusLabel: string;
  statusTone: string;
  sourceFormat: string;
  sourceMediaType: string;
  sourceChecksum: string;
  sourcePdfUrl: string;
  fieldLayout: ContractTemplateFieldLayoutItem[];
  fieldAiConfigured: boolean;
  mergeSourceOptions: string[];
  placeholderKeys: string[];
  mergeSchema: Array<Record<string, unknown>>;
  mergeSchemaJson: string;
  previewChecksum: string;
  previewGeneratedAt: string | null;
  previewUrl: string | null;
  validationErrors: unknown[];
  publishedAt: string | null;
  retiredAt: string | null;
  contractsUsingVersion: number;
  version: string;
  template: ContractTemplateRow;
}

export interface ContractTemplateCapabilities {
  canManage: boolean;
  canApprove: boolean;
}

export interface ContractTemplateCreateSheet {
  open: boolean;
  draft: Record<string, unknown>;
}

export interface ContractTemplateAdministrationPageProps extends PageProps {
  templates: ListResponse<
    ContractTemplateRow,
    { q: string; status: string; jurisdiction: string }
  >;
  capabilities: ContractTemplateCapabilities;
  createSheet: ContractTemplateCreateSheet | null;
  errors: ValidationErrors;
  states: StateOption[];
}

export interface ContractTemplateWorkspacePageProps extends PageProps {
  versionDetail: ContractTemplateVersionDetail;
  capabilities: ContractTemplateCapabilities;
  errors: ValidationErrors;
  posted: Record<string, string[]> | null;
}

export interface AgentContractCapabilities {
  canView: boolean;
  canManage: boolean;
  canViewCommission: boolean;
  canViewNotes: boolean;
  canCreateAmendment?: boolean;
  canCreateReplacement?: boolean;
}

export interface AgentContractTermDiffRow {
  key: string;
  label: string;
  before: string;
  after: string;
  changed: boolean;
}

export interface AgentContractTermComparison {
  basePublicId: string;
  baseVersionNumber: number;
  baseStatus: string;
  baseStatusLabel: string;
  baseEffectiveOn: string;
  baseExpiresOn: string | null;
  draftEffectiveOn: string;
  draftExpiresOn: string | null;
  changeKind: string;
  changeKindLabel: string;
  changeSummary: string;
  rows: AgentContractTermDiffRow[];
  effectiveDateNote: string;
}

export interface AgentContractFamilyHistoryRow {
  publicId: string;
  versionNumber: number;
  changeKind: string;
  changeKindLabel: string;
  role: string;
  governing: string;
  status: string;
  statusLabel: string;
  statusTone: string;
  effectiveOn: string;
  expiresOn: string | null;
  isFocus: boolean;
  amendsPublicId: string | null;
  supersedesPublicId: string | null;
  hasArtifact: boolean;
  href: string;
}

export interface AgentContractListRow {
  publicId: string;
  status: string;
  statusLabel: string;
  statusTone: string;
  effectiveOn: string;
  expiresOn: string | null;
  recipientName: string;
  recipientEmail: string;
  officeName: string;
  templateLabel: string;
  updatedAt: string | null;
}

export interface AgentContractAdministrationPageProps extends PageProps {
  contracts: ListResponse<AgentContractListRow, { q: string; status: string }>;
  capabilities: AgentContractCapabilities;
  statusOptions: Array<{ value: string; label: string; tone: string }>;
  errors: ValidationErrors;
}

export interface AgentContractPayeeSummary {
  id: number;
  name: string;
  email: string;
  officeId?: number | null;
  officeName?: string;
}

export interface AgentContractRecipientResult {
  id: number;
  name: string;
  email: string;
  officeId: number | null;
  officeName: string;
  officeState?: string;
  licenseState: string;
  agentIdentifier: string;
}

export interface AgentContractTemplateOption {
  id: number;
  publicId: string;
  versionLabel: string;
  displayName: string;
  templateName: string;
  templateStableKey: string;
  jurisdictionStateCodes: string[];
}

export interface AgentContractCommercialPreview {
  summaryLines: string[];
  breakdown: {
    ruleVersion: string;
    currency: string;
    grossCommission: string | null;
    agentNet: string;
    officeNet: string;
    transactionFee: string;
    mentorAmount: string | null;
    referralAmount: string | null;
    explanation: string[];
  } | null;
  units: Record<string, string>;
}

export interface AgentContractAgreementPreview {
  status: string;
  html?: string;
  message?: string;
  mergeValues?: Record<string, string>;
  templateName?: string;
}

export interface AgentContractWorkspacePageProps extends PageProps {
  contract: Record<string, unknown> & {
    publicId: string;
    status: string;
    statusLabel: string;
    statusTone: string;
    effectiveOn: string;
    expiresOn: string | null;
    templateVersionId: number | null;
    changeKind?: string;
    changeKindLabel?: string;
    changeSummary?: string;
    versionNumber?: number;
    commission?: Record<string, unknown>;
    internalNotes?: string;
    companySignatoryName?: string;
    companySignUrl?: string | null;
  };
  expectedVersion: string;
  capabilities: AgentContractCapabilities;
  allowedActions: string[];
  generatedPdfUrl?: string | null;
  generatedPdfPreviewUrl?: string | null;
  recipient: AgentContractRecipientResult & { agentStatus?: string };
  office: Record<string, unknown>;
  templateOptions: AgentContractTemplateOption[];
  commissionBasisOptions: Array<{ value: string; label: string }>;
  commercialPreview: AgentContractCommercialPreview | null;
  statusOptions: Array<{ value: string; label: string; tone: string }>;
  familyHistory?: AgentContractFamilyHistoryRow[];
  termComparison?: AgentContractTermComparison | null;
  governingTerms?: Record<string, unknown> | null;
  companySignatoryOptions?: Array<{ id: number; name: string; email: string }>;
  errors: ValidationErrors;
  agreementPreview: AgentContractAgreementPreview | null;
}

export interface AgentContractNewPageProps extends PageProps {
  capabilities: AgentContractCapabilities;
  errors: ValidationErrors;
  draft: Record<string, string>;
}

/** Self-service My Contract presentation states (P1-041). */
export type MyContractState =
  | "no_contract"
  | "generating"
  | "generation_failed"
  | "awaiting_signature"
  | "signed"
  | "active"
  | "expired"
  | "superseded"
  | "terminated";

export interface MyContractCommissionSide {
  percent: string | null;
  fixedAmount: string | null;
  capAmount: string | null;
  basis: string;
  notes: string;
}

export interface MyContractCommission {
  agentSplitPercent: string | null;
  officeSplitPercent: string | null;
  transactionFeeAmount: string | null;
  transactionFeePercent: string | null;
  annualCapAmount: string | null;
  mentor: MyContractCommissionSide;
  referral: MyContractCommissionSide;
}

export interface MyContractArtifactMeta {
  publicId: string;
  kind: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  checksum: string;
  rendererVersion?: string | null;
  ruleVersion?: string | null;
  generatedAt?: string | null;
}

export interface MyContractDetail {
  publicId: string;
  familyId: string;
  versionNumber: number;
  changeKind?: string;
  changeKindLabel?: string;
  changeSummary?: string;
  status: string;
  statusLabel: string;
  statusTone: string;
  effectiveOn: string;
  expiresOn: string | null;
  officeName: string;
  partyDisplayName: string;
  sentAt: string | null;
  viewedAt: string | null;
  signedAt: string | null;
  activatedAt: string | null;
  supersededAt: string | null;
  expiredAt: string | null;
  terminatedAt: string | null;
  updatedAt: string | null;
  expectedVersion: string;
  generatedPdf: MyContractArtifactMeta | null;
  signedPdf: MyContractArtifactMeta | null;
  signedPdfFinalization?: {
    status: string;
    error: string | null;
    signaturePublicId: string;
    ready: boolean;
  } | null;
  previewUrl: string | null;
  downloadUrl: string | null;
  artifactKind: string | null;
  verifyUrl?: string | null;
  isCurrentFocus: boolean;
  isGoverning?: boolean;
  amendsPublicId: string | null;
  supersedesPublicId: string | null;
  commission?: MyContractCommission;
  summaryLines?: string[];
  specialArrangements?: string;
  addendaReferences?: string[];
  annualCapAmount?: string | null;
}

export interface MyContractHistoryRow {
  publicId: string;
  versionNumber: number;
  changeKind?: string;
  changeKindLabel?: string;
  role?: string;
  governing?: string;
  status: string;
  statusLabel: string;
  statusTone: string;
  effectiveOn: string;
  expiresOn: string | null;
  isFocus: boolean;
  hasArtifact: boolean;
  href: string;
  amendsPublicId?: string | null;
  supersedesPublicId?: string | null;
}

export interface MyContractNextAction {
  title: string;
  description: string;
  ctaLabel: string;
  ctaKind: string;
  ctaHref: string;
}

export interface MyContractCapabilities {
  canViewCommission: boolean;
  canSign: boolean;
  /** True when Hub signing (and org seal when required) is available. */
  signingReady: boolean;
}

export interface MyContractPageProps extends PageProps {
  state: MyContractState;
  nextAction: MyContractNextAction;
  contract: MyContractDetail | null;
  history: MyContractHistoryRow[];
  capabilities: MyContractCapabilities;
  disclaimer: string;
  empty: { kind: string; title: string; description: string } | null;
}

export interface SigningDisclosure {
  version: string;
  title: string;
  body: string;
  acknowledgementLabel: string;
}

export interface SigningCeremonyContract {
  publicId: string;
  versionNumber: number;
  status: string;
  statusLabel: string;
  effectiveOn: string;
  expectedVersion: string;
  artifactChecksum: string;
  partyDisplayName: string;
  signerEmail: string;
}

export interface SigningCeremonyEmbed {
  intentPublicId: string;
  expiresAt: string;
  reviewPdfUrl: string;
  agentFields: Array<{
    id: string;
    name: string;
    type: string;
    role: string;
    page: number;
    x: number;
    y: number;
    w: number;
    h: number;
  }>;
}

export interface SigningCeremonyRecovery {
  code: string;
  message: string;
}

export interface MyContractSignPageProps extends PageProps {
  canSign: boolean;
  signingReady: boolean;
  recovery: SigningCeremonyRecovery | null;
  disclosure: SigningDisclosure;
  contract: SigningCeremonyContract | null;
  ceremony: SigningCeremonyEmbed | null;
  errors: { fields: Record<string, string[]>; form: string[] };
}

export interface CompanyContractSignPageProps extends PageProps {
  canSign: boolean;
  signingReady: boolean;
  recovery: SigningCeremonyRecovery | null;
  disclosure: SigningDisclosure;
  signerRole: "Company";
  contract:
    | (SigningCeremonyContract & {
        recipientName?: string;
        workspaceUrl?: string;
      })
    | null;
  ceremony: SigningCeremonyEmbed | null;
  errors: { fields: Record<string, string[]>; form: string[] };
}

export interface ReportScopePayload {
  level: string;
  label: string;
}

export interface ReportExportMeta {
  formats: string[];
  syncRowLimit: number;
  ttlHours: number;
  requiresPermission: string;
}

export interface ReportCatalogItem {
  key: string;
  title: string;
  description: string;
  category: string;
  order: number;
  scopes: string[];
  timeGrain: string;
  calculationVersion: number;
  definition: string;
  available: boolean;
  scope: ReportScopePayload;
  export: ReportExportMeta;
  canExport: boolean;
}

export interface ReportsPageProps extends PageProps {
  reports: ReportCatalogItem[];
  scope: ReportScopePayload;
  timezone: string;
  currency: string;
  canExport: boolean;
}

export interface ReportFilterOption {
  value: string;
  label: string;
}

export interface ReportFilterField {
  key: string;
  label: string;
  kind: "text" | "select" | "date" | "office";
  options: ReportFilterOption[];
}

export interface ReportColumnMeta {
  key: string;
  label: string;
  numeric: boolean;
  currency: boolean;
}

export interface ReportSeriesPoint {
  key: string;
  label: string;
  value: number;
}

export interface ReportDetailPayload {
  key: string;
  title: string;
  description: string;
  category: string;
  order: number;
  scopes: string[];
  timeGrain: string;
  calculationVersion: number;
  definition: string;
  available: boolean;
  scope: ReportScopePayload;
  export: ReportExportMeta;
  filters: ReportFilterField[];
  appliedFilters: Record<string, string>;
  rejectedFilters: string[];
  columns: ReportColumnMeta[];
  aggregates: Record<string, unknown>;
  rows: Record<string, unknown>[];
  series: ReportSeriesPoint[];
  chartKind: "bar" | "none";
  emptyReason: string | null;
  dataAsOf: string | null;
  comparisonNote: string;
  canExport: boolean;
  syncRowLimit: number;
  timezone: string;
  currency: string;
  generatedAt: string;
}

export interface ReportDetailPageProps extends PageProps {
  report: ReportDetailPayload;
}

export interface InventoryListFilters {
  q: string;
  category: string;
  tracking_mode: string;
  condition: string;
  state: string;
  owner: string;
  include_retired: string;
  [key: string]: string;
}

export interface AdminInventoryRow {
  publicId: string;
  name: string;
  category: string;
  categoryLabel: string;
  trackingMode: string;
  trackingModeLabel: string;
  totalQuantity: number;
  availabilityState: string;
  availabilityStateLabel: string;
  ownerOffice: { id: number; stableKey: string; name: string };
  version: string;
  detailHref: string;
}

export interface InventoryItemDetail {
  publicId: string;
  name: string;
  category: string;
  categoryLabel: string;
  trackingMode: string;
  trackingModeLabel: string;
  totalQuantity: number;
  effectiveQuantity: number;
  condition: string;
  conditionLabel: string;
  availabilityState: string;
  availabilityStateLabel: string;
  isReservable: boolean;
  storageLocation: string;
  notes: string;
  photoIsPublic: boolean;
  hasPhoto: boolean;
  ownerOffice: { id: number; stableKey: string; name: string };
  createdAt: string;
  updatedAt: string;
  retiredAt?: string | null;
  activatedAt?: string | null;
  assetId?: string;
  serialNumber?: string;
  internalNotes?: string;
  replacementValue?: string;
  replacementCurrency?: string;
}

export interface InventoryAdministrationPageProps extends PageProps {
  items: ListResponse<AdminInventoryRow, InventoryListFilters>;
  writableOffices: { id: number; label: string; kind: string }[];
  createSheet: { open: boolean; draft: Record<string, string> } | null;
  filterOptions: {
    categories: FilterOption[];
    trackingModes: FilterOption[];
    conditions: FilterOption[];
    states: FilterOption[];
    owners: FilterOption[];
  };
  capabilities: { canManage: boolean; canViewSensitive: boolean };
  scope: { level: string; label: string };
  validation: ValidationErrors;
}

export interface InventoryReservationRow {
  publicId: string;
  summary: string;
  startsAt: string;
  endsAt: string;
}

export interface InventoryItemWorkspacePageProps extends PageProps {
  item: InventoryItemDetail | null;
  version: string;
  writableOffices: { id: number; label: string; kind: string }[];
  capabilities: { canManage: boolean; canViewSensitive: boolean };
  filterOptions: {
    categories: FilterOption[];
    trackingModes: FilterOption[];
    conditions: FilterOption[];
  };
  transfers: {
    publicId: string;
    fromOffice: string;
    toOffice: string;
    performedAt: string;
    reason: string;
  }[];
  reservations: InventoryReservationRow[];
  committedQuantity: number;
  availabilityPreview: {
    start: string;
    end: string;
    availableQuantity: number;
    totalQuantity: number;
    physicalState: string;
    physicalStateLabel: string;
    isReservableCatalogState: boolean;
  } | null;
  scope: { level: string; label: string };
  validation: ValidationErrors;
}

export interface OfficeInventoryFilters {
  q: string;
  category: string;
  condition: string;
  pickup: string;
  return: string;
  quantity: string;
  view: string;
  available_only: string;
  [key: string]: string;
}

export interface OfficeInventoryAvailability {
  start: string;
  end: string;
  requestedQuantity: number;
  availableQuantity: number;
  totalQuantity: number;
  isAvailable: boolean;
  reason: string;
  reasonLabel: string;
}

export interface OfficeInventoryItemRow {
  publicId: string;
  name: string;
  category: string;
  categoryLabel: string;
  trackingMode: string;
  trackingModeLabel: string;
  totalQuantity: number;
  condition: string;
  conditionLabel: string;
  ownerOffice: { id: number; name: string };
  hasPhoto: boolean;
  photoHref: string | null;
  detailHref: string;
  storageLocation?: string;
  notes?: string;
  assetId?: string;
  availability: OfficeInventoryAvailability | null;
  myReservation: { status: string; statusLabel: string; returnDue: string } | null;
  reserveHref: string;
}

export interface OfficeInventoryPageProps extends PageProps {
  items: ListResponse<OfficeInventoryItemRow, OfficeInventoryFilters>;
  office: { id: number; name: string } | null;
  filterOptions: {
    categories: FilterOption[];
    conditions: FilterOption[];
  };
  capabilities: { canViewSensitive: boolean };
  dateErrors: string[];
  serviceError: string | null;
  empty: {
    kind: "no-office" | "no-items" | "no-results" | "unavailable-range";
    title: string;
    description: string;
  } | null;
}

export interface OfficeInventoryItemPageProps extends PageProps {
  item: OfficeInventoryItemRow;
  office: { id: number; name: string } | null;
  filters: OfficeInventoryFilters;
  filterOptions: {
    categories: FilterOption[];
    conditions: FilterOption[];
  };
  capabilities: { canViewSensitive: boolean };
  dateErrors: string[];
  serviceError: string | null;
}

export interface InventoryReservationTerms {
  requiresApproval: boolean;
  autoConfirm: boolean;
  maxHorizonDays: number;
  maxDurationDays: number;
  cancelCutoffHours: number;
  approvalLabel: string;
  cancelPolicyLabel: string;
}

export interface InventoryReservationSummary {
  item: {
    publicId: string;
    name: string;
    trackingMode: string;
    requiresApproval: boolean;
    totalQuantity: number;
    storageLocation: string;
    notes: string;
  };
  office: { id: number; name: string };
  pickup: string;
  return: string;
  startsAt: string;
  endsAt: string;
  quantity: number;
  purpose: string;
  availableQuantity: number;
  isAvailable: boolean;
  status: string;
  statusLabel: string;
  terms: InventoryReservationTerms;
  instructions: { storageLocation: string; notes: string };
}

export interface InventoryReservationNewPageProps extends PageProps {
  item: OfficeInventoryItemRow | null;
  draft: {
    item: string;
    pickup: string;
    return: string;
    quantity: string;
    purpose: string;
  };
  review: boolean;
  summary: InventoryReservationSummary | null;
  office: { id: number; name: string } | null;
  links: {
    inventoryHref: string;
    myReservationsHref: string;
    dashboardHref: string;
  };
  errors: ValidationErrors;
}

export type RoomCalendarView = "day" | "week" | "list";

export interface RoomCalendarInterval {
  startsAt: string;
  endsAt: string;
}

export interface RoomCalendarBusyInterval extends RoomCalendarInterval {
  kind: string;
  label: string;
  isMine: boolean;
}

export interface RoomCalendarSlot extends RoomCalendarInterval {
  bookingHref: string;
}

export interface RoomCalendarDay {
  date: string;
  isClosed: boolean;
  openIntervals: RoomCalendarInterval[];
  busyIntervals: RoomCalendarBusyInterval[];
  availableIntervals: RoomCalendarInterval[];
  candidateSlots: RoomCalendarSlot[];
}

export interface RoomCalendarSpace {
  publicId: string;
  /**
   * The office that owns the room. The grid holds more than one: a room
   * published at the region or the head office appears for every branch
   * beneath it, so a row has to be able to say where it is.
   */
  office: { key: string; name: string; timezone: string };
  name: string;
  type: string;
  typeLabel: string;
  capacity: number;
  location: string;
  amenities: { code: string; name: string }[];
  rules: {
    minimumDurationMinutes: number;
    maximumDurationMinutes: number;
    minimumNoticeMinutes: number;
    bookingHorizonDays: number;
    bufferBeforeMinutes: number;
    bufferAfterMinutes: number;
    requiresApproval: boolean;
  };
  days: RoomCalendarDay[];
}

export interface RoomAvailabilityPageProps extends PageProps {
  calendar: {
    view: RoomCalendarView;
    startDate: string;
    days: { date: string }[];
    spaces: RoomCalendarSpace[];
    generatedAt: string;
    timezone: string;
    isTruncated: boolean;
    advisory: string;
  } | null;
  office: { key: string; name: string; timezone: string } | null;
  officeOptions: { key: string; name: string; regionName: string }[];
  filterOptions: {
    spaceTypes: FilterOption[];
    amenities: FilterOption[];
    rooms: FilterOption[];
  };
  filters: {
    date: string;
    view: RoomCalendarView;
    office: string;
    type: string;
    capacity: string;
    amenities: string[];
    space: string;
  };
  capabilities: { canBook: boolean; canChangeOffice: boolean };
  empty: {
    kind: "no-office" | "no-results";
    title: string;
    description: string;
  } | null;
  errors: ValidationErrors;
}

export interface RoomReservationNewPageProps extends PageProps {
  space: {
    publicId: string;
    name: string;
    typeLabel: string;
    capacity: number;
    location: string;
    requiresApproval: boolean;
    minimumDurationMinutes: number;
    maximumDurationMinutes: number;
  } | null;
  draft: {
    startsAt: string;
    endsAt: string;
    purpose: string;
    attendeeCount: string;
  };
  office: { name: string; timezone: string } | null;
  errors: ValidationErrors;
  links: { calendarHref: string };
}

export interface InventoryReservationTimelineEntry {
  id: string;
  action: string;
  actionLabel: string;
  fromStatus: string;
  toStatus: string;
  reason: string;
  notes: string;
  occurredAt: string;
  actor: { id: number; name: string } | null;
  metadata: Record<string, unknown>;
}

export interface InventoryReservationAction {
  action: string;
  label: string;
  targetStatus: string;
  requiresReason: boolean;
  requiresNote: boolean;
  overrideOnly: boolean;
}

export interface InventoryReservationDetailPayload {
  publicId: string;
  reference: string;
  itemName: string;
  itemPublicId: string;
  office: { id: number; name: string };
  owner?: { id: number; name: string; email: string } | null;
  quantity: number;
  purpose: string;
  status: string;
  statusLabel: string;
  expectedVersion: string;
  startsAt: string;
  endsAt: string;
  pickupLabel: string;
  returnLabel: string;
  instructions: { storageLocation: string; notes: string };
  terms: InventoryReservationTerms;
  canCancel: boolean;
  cancelCutoffAt: string | null;
  cancelledAt: string | null;
  checkedOutAt: string | null;
  returnedAt: string | null;
  completedAt: string | null;
  checkoutQuantity: number | null;
  returnQuantity: number | null;
  returnConditionNotes: string;
  createdAt: string;
  timeline: InventoryReservationTimelineEntry[];
  actions: InventoryReservationAction[];
  itemHref: string;
  myReservationsHref: string;
  dashboardHref: string;
  adminHref?: string | null;
}

export interface InventoryReservationDetailPageProps extends PageProps {
  reservation: InventoryReservationDetailPayload;
  errors: ValidationErrors;
  justCreated: boolean;
}

export interface InventoryReservationListRow {
  publicId: string;
  reference: string;
  itemName: string;
  itemPublicId: string;
  officeName: string;
  quantity: number;
  purpose: string;
  status: string;
  statusLabel: string;
  startsAt: string;
  endsAt: string;
  pickupLabel: string;
  returnLabel: string;
  detailHref: string;
  owner?: { id: number; name: string; email: string };
}

export interface AdminReservationsPageProps extends PageProps {
  reservations: ListResponse<
    InventoryReservationListRow,
    { q: string; status: string }
  >;
  filterOptions: { statuses: FilterOption[] };
  can: { approve: boolean; override: boolean };
  scope: { level: string; label: string };
  errors: ValidationErrors;
}

export interface AdminReservationDetailPageProps extends PageProps {
  reservation: InventoryReservationDetailPayload;
  can: { approve: boolean; override: boolean };
  scope: { level: string; label: string };
  errors: ValidationErrors;
}

export interface InventoryReservationsPageProps extends PageProps {
  reservations: ListResponse<InventoryReservationListRow, Record<string, string>>;
  links: {
    inventoryHref: string;
    dashboardHref: string;
  };
  errors: ValidationErrors;
}

export interface ReportExportJobPayload {
  id: number;
  reportKey: string;
  status: "queued" | "running" | "ready" | "failed" | "expired";
  progress: number;
  format: string;
  filters: Record<string, string>;
  requestedAt: string;
  completedAt: string | null;
  expiresAt: string;
  dataAsOf: string | null;
  calculationVersion: number;
  errorMessage: string | null;
  downloadReady: boolean;
  byteSize: number;
}

/* --- Scoped room administration ------------------------------------------ */

export interface SpaceAdminAmenity {
  code: string;
  name: string;
}

export interface SpaceAdminRow {
  publicId: string;
  name: string;
  officeKey: string;
  officeName: string;
  spaceType: string;
  spaceTypeLabel: string;
  capacity: number;
  location: string;
  status: string;
  statusLabel: string;
  isReservable: boolean;
  displayOrder: number;
  amenities: SpaceAdminAmenity[];
}

export interface SpaceAdminCapabilities {
  canManageSpaces: boolean;
  canManageSchedules: boolean;
  canManageReservations: boolean;
  canOverride: boolean;
  canViewSensitive: boolean;
}

export interface SpaceAdminOption {
  value: string;
  label: string;
  regionName?: string;
}

export interface SpaceAdminFilters {
  q: string;
  office: string;
  type: string;
  status: string;
  capacity: string;
  amenities: string[];
}

export interface SpaceAdministrationPageProps extends PageProps {
  spaces: SpaceAdminRow[];
  pagination: PaginationMeta;
  filters: SpaceAdminFilters;
  filterOptions: {
    offices: SpaceAdminOption[];
    spaceTypes: SpaceAdminOption[];
    statuses: SpaceAdminOption[];
    amenities: SpaceAdminOption[];
  };
  capabilities: SpaceAdminCapabilities;
  errors: ValidationErrors;
}

export interface SpaceBookingPolicy {
  minimumDurationMinutes: number;
  maximumDurationMinutes: number;
  bookingHorizonDays: number;
  minimumNoticeMinutes: number;
  bufferBeforeMinutes: number;
  bufferAfterMinutes: number;
  cancellationCutoffMinutes: number;
  requiresApproval: boolean;
  isReservable: boolean;
}

export interface SpaceAdminDetail extends SpaceAdminRow {
  description: string;
  accessInstructions: string;
  updatedAt: string;
  retiredAt: string | null;
  policy: SpaceBookingPolicy;
}

export interface SpaceScheduleInterval {
  weekday: number;
  startsAt: string;
  endsAt: string;
}

export interface SpaceAdminBlock {
  publicId: string;
  kind: string;
  kindLabel: string;
  startsAt: string;
  endsAt: string;
  reason: string;
  visibility: string;
}

export interface SpaceAdminBooking {
  publicId: string;
  reference: string;
  ownerName: string;
  startsAt: string;
  endsAt: string;
  status: string;
  statusLabel: string;
  attendeeCount: number | null;
}

export interface SpaceImpactBooking {
  reference: string;
  publicId: string;
  ownerName: string;
  startsAt: string;
  endsAt: string;
  reason: string;
}

export interface SpaceImpactReport {
  total: number;
  bookings: SpaceImpactBooking[];
}

export interface SpaceAdminMoveTarget {
  value: string;
  label: string;
  capacity: number;
}

export interface SpaceAdministrationWorkspacePageProps extends PageProps {
  space: SpaceAdminDetail;
  schedule: SpaceScheduleInterval[];
  blocks: SpaceAdminBlock[];
  upcomingBookings: SpaceAdminBooking[];
  moveTargets: SpaceAdminMoveTarget[];
  options: {
    spaceTypes: SpaceAdminOption[];
    blockKinds: SpaceAdminOption[];
    visibilities: SpaceAdminOption[];
  };
  capabilities: SpaceAdminCapabilities;
  impact: SpaceImpactReport | null;
  errors: ValidationErrors;
  links: { indexHref: string };
}

/* --- Unified self-service reservations ----------------------------------- */

export type ReservationSourceKey = "room" | "inventory";

export type ReservationTab = "upcoming" | "past" | "cancelled" | "calendar";

export interface MyReservationAction {
  key: string;
  label: string;
  href: string;
  method: "get" | "post";
  destructive: boolean;
  /** Domain state the mutation expects, so a stale tab cannot act blindly. */
  expectedStatus: string;
}

export interface MyReservationSummary {
  sourceId: string;
  source: ReservationSourceKey;
  sourceLabel: string;
  publicId: string;
  reference: string;
  title: string;
  subtitle: string;
  officeName: string;
  timezone: string;
  startsAt: string;
  endsAt: string;
  /** Inventory windows are date-shaped and carry `localDate` instead of a clock. */
  allDay: boolean;
  localDate: string | null;
  displayStatus: string;
  displayStatusLabel: string;
  tone: StatusTone;
  /** The owning domain's own code and words, never flattened away. */
  sourceStatus: string;
  statusLabel: string;
  purpose: string;
  quantity: number | null;
  instructions: string;
  contact: string;
  detailHref: string;
  actions: MyReservationAction[];
}

export interface MyReservationsPageProps extends PageProps {
  reservations: MyReservationSummary[];
  counts: Record<string, number>;
  filters: { tab: ReservationTab; source: string; status: string };
  filterOptions: {
    sources: { value: string; label: string }[];
    statuses: { value: string; label: string }[];
  };
  /** Present only when a source failed; names it rather than counting it. */
  degraded: { failedSources: string[] } | null;
  errors: ValidationErrors;
}

export interface MyReservationDetailPageProps extends PageProps {
  reservation: MyReservationSummary;
  links: { indexHref: string };
  errors: ValidationErrors;
}

/* -------------------------------------------------------------------------- */
/* Marketing resources                                                        */
/* -------------------------------------------------------------------------- */

export interface MarketingPresentationBadge {
  code: string;
  label: string;
  /** Server may send tones outside StatusTone (e.g. "brand"); map at render. */
  tone: string;
  known: boolean;
}

export interface MarketingScope {
  level: string;
  label: string;
  officeName: string;
}

export interface MarketingFileItem {
  id: number;
  role: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  width: number | null;
  height: number | null;
  isImage: boolean;
  url: string;
  previewUrl: string;
  variants: Record<string, string>;
  isReadable: boolean;
  processingState?: "pending" | "ready" | "quarantined" | "failed";
  processingNote?: string;
  isActive?: boolean;
  checksum?: string;
  sortOrder?: number;
}

export interface MarketingLibraryRow {
  id: number;
  slug: string;
  title: string;
  description: string;
  assetType: MarketingPresentationBadge;
  category: MarketingPresentationBadge | null;
  scope: MarketingScope;
  jurisdictionStateCodes: string[];
  brandCodes: string[];
  versionNumber: number;
  versionLabel: string;
  previewUrl: string;
  exportCount: number;
  publishedAt: string | null;
  detailUrl: string;
}

export interface MarketingResourceDetail extends MarketingLibraryRow {
  usageInstructions: string;
  exports: MarketingFileItem[];
  publishAt: string | null;
  expiresAt: string | null;
}

export interface MarketingLibraryFilters {
  category: string;
  type: string;
  jurisdiction: string;
  brand: string;
  q: string;
  rejected: string[];
  [key: string]: string | string[];
}

export interface MarketingResourcesPageProps extends PageProps {
  library: ListResponse<MarketingLibraryRow, MarketingLibraryFilters>;
  filterOptions: {
    categories: FilterOption[];
    assetTypes: FilterOption[];
  };
}

export interface MarketingResourceDetailPageProps extends PageProps {
  asset: MarketingResourceDetail;
}

export interface MarketingLifecycle {
  code: "draft" | "scheduled" | "live" | "expired" | "archived";
  label: string;
  tone: StatusTone;
}

export interface MarketingAdminRow {
  id: number;
  slug: string;
  title: string;
  description: string;
  lifecycle: MarketingLifecycle;
  status: "draft" | "published" | "archived";
  assetType: MarketingPresentationBadge;
  category: MarketingPresentationBadge | null;
  versionNumber: number;
  versionLabel: string;
  ownerOffice: { id: number; name: string };
  scopeLevel: string;
  audience: AnnouncementAudienceEntry[];
  jurisdictionStateCodes: string[];
  brandCodes: string[];
  publishAt: string | null;
  expiresAt: string | null;
  publishedAt: string | null;
  updatedAt: string | null;
  updatedBy: string;
  createdBy: string;
  /** Opaque concurrency token. Sent back on every write; a mismatch is a 409. */
  version: string;
}

export interface MarketingValidationItem {
  field: string;
  message: string;
}

export interface MarketingValidation {
  isPublishable: boolean;
  items: MarketingValidationItem[];
}

export interface MarketingHistoryEntry {
  id: string;
  action: string;
  label: string;
  tone: StatusTone;
  actor: string;
  occurredAt: string;
}

export interface MarketingAdminFiles {
  exports: MarketingFileItem[];
  sources: MarketingFileItem[];
  previews: MarketingFileItem[];
}

export interface MarketingAdminDetail extends MarketingAdminRow {
  usageInstructions: string;
  categoryCode: string;
  assetTypeCode: string;
  displayOrder: number;
  validation: MarketingValidation;
  history: MarketingHistoryEntry[];
  files: MarketingAdminFiles;
  mediaHref: string;
  versionFamily: string;
}

export interface MarketingCapabilities {
  canAuthor: boolean;
  canPublish: boolean;
  canDownloadSources: boolean;
}

export interface MarketingWorkspaceFilters {
  q: string;
  lifecycle: string;
  category: string;
  type: string;
  audience: string;
  author: string;
  office: string;
  publishedFrom: string;
  publishedTo: string;
  [key: string]: string | string[];
}

export interface MarketingCreateSheet {
  open: boolean;
  draft: Record<string, string | string[]>;
}

export interface MarketingAdministrationPageProps extends PageProps {
  assets: ListResponse<MarketingAdminRow, MarketingWorkspaceFilters>;
  filterOptions: {
    categories: FilterOption[];
    assetTypes: FilterOption[];
    offices: AnnouncementOfficeOption[];
  };
  createOptions: {
    offices: AnnouncementOfficeOption[];
    categories: FilterOption[];
    assetTypes: FilterOption[];
    audience: AnnouncementAudienceOptions;
  };
  createSheet: MarketingCreateSheet | null;
  capabilities: MarketingCapabilities;
  errors: ValidationErrors;
}

export interface MarketingPreviewReach {
  chosen: boolean;
  matched: boolean;
  officeId: number | null;
  officeName: string;
  roleCode: string;
  hasNamedRecipients: boolean;
}

export interface MarketingPreviewArticle extends MarketingResourceDetail {
  audience: AnnouncementAudienceEntry[];
}

export interface MarketingPreview {
  article: MarketingPreviewArticle;
  reach: MarketingPreviewReach;
  roleCode: string;
  officeId: number | null;
}

export interface MarketingWorkspacePageProps extends PageProps {
  asset: MarketingAdminDetail | null;
  officeOptions: AnnouncementOfficeOption[];
  categoryOptions: FilterOption[];
  assetTypeOptions: FilterOption[];
  audienceOptions: AnnouncementAudienceOptions;
  capabilities: MarketingCapabilities;
  preview: MarketingPreview | null;
  errors: ValidationErrors;
  posted: Record<string, string[]> | null;
}

export interface MarketingRecipientResult {
  id: number;
  name: string;
  email: string;
  officeName: string;
}

export interface MarketingMediaLimits {
  export: { extensions: string[]; maxBytes: number; maxCount: number };
  source: { extensions: string[]; maxBytes: number; maxCount: number };
}

export interface MarketingMediaManagerPageProps extends PageProps {
  asset: { id: number; title: string; status: string; version: string };
  files: MarketingAdminFiles;
  limits: MarketingMediaLimits;
  capabilities: MarketingCapabilities;
  validation: ValidationErrors;
}

/* -------------------------------------------------------------------------- */
/* Policies & compliance                                                      */
/* -------------------------------------------------------------------------- */

export interface CompliancePresentationBadge {
  code: string;
  label: string;
  tone: string;
  known: boolean;
}

export interface ComplianceScope {
  level: string;
  label: string;
  officeName: string;
}

export interface ComplianceFileItem {
  id: number;
  role: string;
  displayName: string;
  mediaType: string;
  byteSize: number;
  url: string;
  isReadable: boolean;
  processingState?: string;
  processingNote?: string;
  isActive?: boolean;
  checksum?: string;
  sortOrder?: number;
}

export interface ComplianceLibraryRow {
  id: number;
  title: string;
  summary: string;
  status: CompliancePresentationBadge;
  category: CompliancePresentationBadge | null;
  scope: ComplianceScope;
  jurisdictionStateCodes: string[];
  versionNumber: number;
  versionLabel: string;
  isMandatory: boolean;
  publishedAt: string | null;
  detailUrl: string;
  acknowledged: boolean;
  required: boolean;
  dueAt: string | null;
  canAcknowledge: boolean;
  mustOpenDocument: boolean;
  documentAccessed: boolean;
}

export interface CompliancePolicyDetail extends ComplianceLibraryRow {
  body: string;
  documents: ComplianceFileItem[];
  contentChecksum: string;
  acknowledgementDisclosure: string;
  disclosureVersion: number;
  effectiveAt: string | null;
  expiresAt: string | null;
  waived: boolean;
  acknowledgedAt: string | null;
}

export interface ComplianceLibraryFilters {
  category: string;
  jurisdiction: string;
  q: string;
  rejected: string[];
  [key: string]: string | string[];
}

export interface PoliciesCompliancePageProps extends PageProps {
  library: ListResponse<ComplianceLibraryRow, ComplianceLibraryFilters>;
  filterOptions: {
    categories: FilterOption[];
  };
  errors: ValidationErrors;
}

export interface PolicyDetailPageProps extends PageProps {
  policy: CompliancePolicyDetail;
  errors: ValidationErrors;
}

export interface ComplianceCapabilities {
  canAuthor: boolean;
  canApprove: boolean;
  canPublish: boolean;
  canViewAcks: boolean;
  canWaive: boolean;
}

export interface ComplianceAdminRow {
  id: number;
  title: string;
  summary: string;
  status: CompliancePresentationBadge;
  statusCode: string;
  category: CompliancePresentationBadge | null;
  versionNumber: number;
  versionLabel: string;
  ownerOffice: { id: number; name: string };
  scopeLevel: string;
  audience: AnnouncementAudienceEntry[];
  jurisdictionStateCodes: string[];
  isMandatory: boolean;
  effectiveAt: string | null;
  expiresAt: string | null;
  publishedAt: string | null;
  updatedAt: string | null;
  updatedBy: string;
  createdBy: string;
  /** Opaque concurrency token. Sent back on every write; a mismatch is a 409. */
  version: string;
}

export interface ComplianceValidationItem {
  field: string;
  message: string;
}

export interface ComplianceValidation {
  isPublishable: boolean;
  items: ComplianceValidationItem[];
}

export interface ComplianceHistoryEntry {
  id: string;
  action: string;
  label: string;
  tone: StatusTone;
  actor: string;
  occurredAt: string;
}

export interface ComplianceAdminFiles {
  documents: ComplianceFileItem[];
  sources: ComplianceFileItem[];
}

export interface ComplianceAdminDetail extends ComplianceAdminRow {
  body: string;
  categoryCode: string;
  displayOrder: number;
  ownerUserId: number | null;
  acknowledgementDisclosure: string;
  disclosureVersion: number;
  reacknowledgeOnSupersede: boolean;
  contentChecksum: string;
  validation: ComplianceValidation;
  history: ComplianceHistoryEntry[];
  files: ComplianceAdminFiles;
  versionFamily: string;
  capabilities: ComplianceCapabilities | null;
}

export interface ComplianceWorkspaceFilters {
  q: string;
  status: string;
  category: string;
  office: string;
  [key: string]: string | string[];
}

export interface ComplianceAdministrationPageProps extends PageProps {
  policies: ListResponse<ComplianceAdminRow, ComplianceWorkspaceFilters>;
  summary: {
    draft: number;
    inReview: number;
    published: number;
  };
  filterOptions: {
    categories: FilterOption[];
    statuses: FilterOption[];
    offices: AnnouncementOfficeOption[];
  };
  createOptions: {
    offices: AnnouncementOfficeOption[];
    categories: FilterOption[];
    audience: AnnouncementAudienceOptions;
  };
  capabilities: ComplianceCapabilities;
  errors: ValidationErrors;
}

export interface ComplianceMediaLimits {
  document: { extensions: string[]; maxBytes: number; maxCount: number };
  source: { extensions: string[]; maxBytes: number; maxCount: number };
}

export interface ComplianceWorkspacePageProps extends PageProps {
  policy: ComplianceAdminDetail | null;
  officeOptions: AnnouncementOfficeOption[];
  categoryOptions: FilterOption[];
  audienceOptions: AnnouncementAudienceOptions;
  capabilities: ComplianceCapabilities;
  mediaLimits: ComplianceMediaLimits;
  errors: ValidationErrors;
}

export interface ComplianceAckReportRow {
  userId: number;
  userName: string;
  email: string;
  officeName: string;
  policyId: number;
  policyTitle: string;
  status: "pending" | "acknowledged" | "waived" | "overdue" | string;
  dueAt: string | null;
  acknowledgedAt: string | null;
}

export interface ComplianceAckReportFilters {
  policy: string;
  office: string;
  region: string;
  role: string;
  dueFrom: string;
  dueTo: string;
  status: string;
  q: string;
  [key: string]: string;
}

export interface ComplianceAckReportPageProps extends PageProps {
  report: {
    items: ComplianceAckReportRow[];
    totalItems: number;
    summary: {
      pending: number;
      acknowledged: number;
      waived: number;
      overdue: number;
    };
  };
  filterOptions: {
    policies: FilterOption[];
    offices: FilterOption[];
    regions: FilterOption[];
    roles: FilterOption[];
    statuses: FilterOption[];
  };
  filters: ComplianceAckReportFilters;
  capabilities: ComplianceCapabilities;
  errors: ValidationErrors;
}
