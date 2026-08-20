import type { ListResponse, StatusTone, ValidationErrors } from "@/types/design-system";

export interface User {
  id: number;
  email: string;
  name: string;
  /** Django auth permission codenames, e.g. "user.view_user". */
  permissions: string[];
  /** Role (Django group) names, highest-priority first. */
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
  id: string;
  name: string;
  href: string;
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
  | "documents";

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

/** Dashboard page props. Deferred widgets are undefined until Inertia loads them. */
export interface DashboardPageProps extends PageProps {
  greeting: DashboardGreeting;
  metrics?: DashboardWidget<DashboardMetrics>;
  quickApps?: DashboardWidget<DashboardQuickApp[]>;
  announcements?: DashboardWidget<DashboardAnnouncements>;
  transactions?: DashboardWidget<DashboardTransaction[]>;
  training?: DashboardWidget<DashboardTraining>;
  schedule?: DashboardWidget<DashboardSchedule>;
  actionItems?: DashboardWidget<DashboardActionItems>;
  market?: DashboardWidget<DashboardMarket>;
  documents?: DashboardWidget<DashboardDocument[]>;
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
  /** ISO 8601 calendar date, or "" — the shape an `<input type="date">` wants. */
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
  internalNotes: string;
}

export interface AdministrationAssignment {
  id: number;
  role: string;
  roleLabel: string;
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
  scopes: AdministrationRoleScope[];
}

export interface AdministrationOfficeOption {
  id: number;
  name: string;
  pathLabel: string;
  regionName: string;
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
  contractStatus: ContractStatus;
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
  /** Present only when the subject is in the scoped New Agent List. */
  onboardingState?: OnboardingSummary & { href: string };
}

export interface UserAdministrationPageProps extends PageProps {
  administration: AdministrationPayload;
  validation: ValidationErrors;
  statusOptions: AdministrativeChoice[];
  verificationOptions: AdministrativeChoice[];
}

export interface AdministrationDirectoryRow {
  id: number;
  name: string;
  email: string;
  officeName: string | null;
  agentStatus: string;
  agentIdentifier: string;
  isActive: boolean;
}

export interface UserAdministrationIndexPageProps extends PageProps {
  users: ListResponse<AdministrationDirectoryRow, { q: string }>;
  statusOptions: AdministrativeChoice[];
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
