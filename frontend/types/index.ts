import type { ListResponse, StatusTone, ValidationErrors } from "@/types/design-system";

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

export interface DashboardScheduleEvent {
  time: string;
  title: string;
  place: string;
}

export interface DashboardSchedule {
  dateLabel: string;
  events: DashboardScheduleEvent[];
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
  // its provider ships, and renders preview data in the meantime.
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

export interface PageProps {
  user: User | null;
  csrfToken: string;
  requestId: string;
  features: HubFeatures;
  primaryOffice: PrimaryOffice | null;
  shell: ShellSharedProps;
  /** Header badge counts for the signed-in reader; null when signed out. */
  notifications: NotificationShell | null;
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

/** Dashboard page props. Deferred widgets are undefined until Inertia loads them. */
export interface DashboardPageProps extends PageProps {
  greeting: DashboardGreeting;
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
  documents?: DashboardWidget<DashboardDocument[]>;
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
  offices: { id: number; name: string }[];
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

/** The details onboarding collects. Keys mirror `forms.ONBOARDING_FIELD_MAP`. */
export interface OnboardingProfileValues {
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
}

/** Everything a user may maintain about themselves, per `SelfProfileForm`. */
export interface SelfProfileValues extends OnboardingProfileValues {
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
}

export interface OnboardingPageProps extends PageProps {
  initial: OnboardingProfileValues;
  validation: ValidationErrors;
  offices: OfficeGroup[];
  states: StateOption[];
}

export interface ProfilePageProps extends PageProps {
  initial: SelfProfileValues;
  validation: ValidationErrors;
  /** Empty when the signed-in user may not move themselves between offices. */
  offices: OfficeGroup[];
  states: StateOption[];
  languageOptions: LanguageOption[];
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

export interface OnboardingTool {
  key: string;
  label: string;
  state: string;
  status: string;
  statusLabel: string;
  tone: StatusTone;
  updatedAt: string | null;
  updatedBy: string | null;
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

export interface QuickAccessAdministrationPageProps extends PageProps {
  links: ListResponse<QuickAccessLinkRow, { q: string; status: string }>;
  statusOptions: QuickAccessChoice[];
  roleOptions: QuickAccessChoice[];
  officeOptions: QuickAccessOfficeChoice[];
  preview: QuickAccessPreview | null;
  capabilities: QuickAccessCapabilities;
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
