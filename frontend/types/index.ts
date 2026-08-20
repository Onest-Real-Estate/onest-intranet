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
  availability: "available" | "unavailable";
  /** Why the figure cannot be shown; present only when unavailable. */
  unavailableReason?: string;
  /** Null while unavailable — an unmeasured metric has no number to round. */
  value: string | null;
  hint: string;
  tone: "neutral" | "success" | "warning" | "destructive";
  trend: "up" | "down" | "flat";
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
  tag: string;
  title: string;
  excerpt: string;
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
  title: string;
  property: string;
  due: string;
  late: boolean;
}

export interface DashboardActionItems {
  total: number;
  items: DashboardActionItem[];
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
  [key: string]: unknown;
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

export interface AdministrationRoleScope {
  value: string;
  label: string;
}

export interface AdministrationRoleOption {
  value: string;
  label: string;
  description?: string;
  protected?: boolean;
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
