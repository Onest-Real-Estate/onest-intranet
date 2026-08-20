#!/usr/bin/env bash
#
# Create the 41 remaining core P1 issues, numbered P1-060 through P1-100, for:
#   Onest-Real-Estate/onest-intranet
#
# This backlog closes the operational gaps left after P0 and P1-019..P1-059:
# administration, notifications, training/content, discoverability/support,
# transaction management, CRM, and MLS-ready property workflows.
#
# The script is idempotent. It detects an existing issue by stable ONEST marker
# first and exact title second, across open and closed issues. On rerun it adds
# missing classification labels to matching issues without overwriting bodies.

set -Eeuo pipefail

readonly REPO="Onest-Real-Estate/onest-intranet"
readonly HOST="github.com"
readonly EXPECTED_ISSUE_COUNT=41
readonly LABEL_SPECS=(
  "P1|D4A72C|High-priority product capability work"
  "type:feature|1D76DB|New product feature or capability"
  "area:frontend|0E8A16|React, Inertia, or browser-facing implementation"
  "area:backend|5319E7|Django, services, APIs, or server-side implementation"
  "area:ui-ux|C5DEF5|User interface, interaction, accessibility, or experience"
  "area:data-model|ED5F00|Database schema, constraints, migrations, or persistence"
  "area:permissions|B60205|Authorization, roles, grants, or organizational scope"
  "area:security|D93F0B|Security, privacy, signing, or protected access"
  "area:admin|FBCA04|Administrative or operational management interface"
  "area:documents|006B75|Files, PDFs, uploads, downloads, or protected storage"
  "area:background-jobs|7057FF|Celery, schedules, retries, or asynchronous work"
  "area:notifications|F9D0C4|In-app, email, reminder, or escalation delivery"
  "area:integrations|0052CC|Internal or third-party integration"
  "area:business-logic|BFDADC|Domain rules, calculations, workflows, or state machines"
  "area:concurrency|E11D21|Transactions, locking, idempotency, or race prevention"
  "area:reporting|0B7285|Metrics, aggregates, trends, exports, or reporting"
  "module:dashboard|0075CA|Personalized and administrative dashboards"
  "module:users|C2E0C6|Users, onboarding, roles, and offices"
  "module:notifications|F9D0C4|Notification center and delivery"
  "module:training|D4C5F9|Training, learning, and progress"
  "module:documents|006B75|Documents and forms library"
  "module:marketing|FEF2C0|Marketing resources"
  "module:compliance|B60205|Policies, acknowledgements, and compliance"
  "module:directory|BFD4F2|Agent directory"
  "module:search|C5DEF5|Global search"
  "module:support|FBCA04|Feedback, support, and platform tasks"
  "module:activity|A2EEEF|Activity timelines"
  "module:reporting|0B7285|Operational reports"
  "module:transactions|5319E7|Real-estate transaction management"
  "module:crm|0E8A16|CRM, leads, buyers, sellers, and automation"
  "module:mls|0052CC|MLS and property workflows"
)

DRY_RUN=0
ASSUME_YES=0
TOTAL=0
CREATED=0
UPDATED=0
SKIPPED=0
FAILED=0
WORK_DIR=""
ISSUE_INDEX=""
AVAILABLE_LABELS=""

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
error() { printf '[ERROR] %s\n' "$*" >&2; }
die() {
  error "$*"
  exit 1
}

usage() {
  printf '%s\n' \
    "Usage: $(basename "$0") [--dry-run] [--yes] [--help]" \
    "" \
    "Creates 41 detailed remaining-core P1 issues (P1-060 through P1-100) in $REPO." \
    "Creates missing classification labels and applies them to new or existing issues." \
    "" \
    "Options:" \
    "  --dry-run  Verify prerequisites and show what would be created or relabeled." \
    "  --yes      Skip the interactive confirmation." \
    "  --help     Show this help text." \
    "" \
    "The target repository and issue range are hard-coded intentionally."
}

while (($# > 0)); do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    --yes | -y)
      ASSUME_YES=1
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "Unknown argument: $1"
      ;;
  esac
  shift
done

command -v gh >/dev/null 2>&1 ||
  die "GitHub CLI is not installed. Install it from https://cli.github.com/ and rerun."

info "Checking GitHub CLI authentication for $HOST..."
gh auth status --hostname "$HOST" >/dev/null 2>&1 ||
  die "GitHub CLI is not authenticated. Run: gh auth login --hostname $HOST"

authenticated_user=$(gh api --hostname "$HOST" user --jq '.login') ||
  die "Could not determine the authenticated GitHub user."
info "Authenticated as $authenticated_user."

repo_info=$(gh repo view "$REPO" \
  --json nameWithOwner,hasIssuesEnabled,viewerPermission \
  --jq '[.nameWithOwner, (.hasIssuesEnabled | tostring), .viewerPermission] | @tsv') ||
  die "Cannot access $REPO with the current GitHub CLI account."
IFS=$'\t' read -r resolved_repo issues_enabled viewer_permission <<<"$repo_info"
[[ "$resolved_repo" == "$REPO" ]] || die "Repository identity mismatch."
[[ "$issues_enabled" == "true" ]] || die "GitHub Issues are disabled for $REPO."

case "$viewer_permission" in
  ADMIN | MAINTAIN | WRITE | TRIAGE | READ) ;;
  *) die "Unusable repository permission: $viewer_permission." ;;
esac
info "Repository access verified (permission: $viewer_permission)."

if ((DRY_RUN == 0 && ASSUME_YES == 0)); then
  printf '\nThis will create or relabel up to %d issues in %s.\n' "$EXPECTED_ISSUE_COUNT" "$REPO"
  printf 'Matching existing issues will not have their bodies overwritten.\n'
  read -r -p "Continue? [y/N] " confirmation
  case "$confirmation" in
    y | Y | yes | YES) ;;
    *)
      info "No changes made."
      exit 0
      ;;
  esac
fi

WORK_DIR=$(mktemp -d "/tmp/onest-remaining-p1.XXXXXX") ||
  die "Could not create a temporary working directory."
trap 'rm -rf -- "$WORK_DIR"' EXIT HUP INT TERM

ISSUE_INDEX="$WORK_DIR/existing-issues.tsv"
info "Loading open and closed issues for duplicate detection..."
gh api --hostname "$HOST" --paginate \
  "repos/$REPO/issues?state=all&per_page=100" \
  --jq '.[] | select(.pull_request == null) | [.number, .html_url, .title, (.body // "")] | @tsv' \
  >"$ISSUE_INDEX" ||
  die "Could not load existing issues; creation was blocked to avoid duplicates."

add_available_label() {
  local label="$1"
  if [[ -z "$AVAILABLE_LABELS" ]]; then
    AVAILABLE_LABELS="$label"
  else
    AVAILABLE_LABELS+=$'\n'"$label"
  fi
}

if existing_labels=$(gh label list --repo "$REPO" --limit 500 --json name --jq '.[].name'); then
  for label_spec in "${LABEL_SPECS[@]}"; do
    IFS='|' read -r label_name label_color label_description <<<"$label_spec"
    if grep -Fxq "$label_name" <<<"$existing_labels"; then
      add_available_label "$label_name"
    elif ((DRY_RUN == 1)); then
      info "Dry run: label $label_name is missing and would be created."
    elif gh label create "$label_name" --repo "$REPO" \
      --color "$label_color" --description "$label_description"; then
      add_available_label "$label_name"
      info "Created label: $label_name."
    else
      warn "Could not create label $label_name; affected issues will omit it."
    fi
  done
else
  warn "Could not inspect labels; issue bodies will still contain classifications."
fi

lookup_existing_issue() {
  local marker="$1"
  local title="$2"
  local row=""

  row=$(awk -F $'\t' -v marker="$marker" \
    'index($4, marker) { print $1 "\t" $2; exit }' "$ISSUE_INDEX") || return 2
  if [[ -n "$row" ]]; then
    printf '%s\n' "$row"
    return 0
  fi

  row=$(awk -F $'\t' -v title="$title" \
    '$3 == title { print $1 "\t" $2; exit }' "$ISSUE_INDEX") || return 2
  if [[ -n "$row" ]]; then
    printf '%s\n' "$row"
    return 0
  fi
  return 1
}

filter_available_labels() {
  local requested="$1"
  local selected=""
  local label=""
  local old_ifs="$IFS"
  IFS=','
  for label in $requested; do
    if grep -Fxq "$label" <<<"$AVAILABLE_LABELS"; then
      selected="${selected:+$selected,}$label"
    fi
  done
  IFS="$old_ifs"
  printf '%s\n' "$selected"
}

append_classification() {
  local body_file="$1"
  local labels="$2"
  local label=""
  local old_ifs="$IFS"
  printf '\n## Classification\n\n' >>"$body_file"
  IFS=','
  for label in $labels; do
    printf -- '- `%s`\n' "$label" >>"$body_file"
  done
  IFS="$old_ifs"
}

append_delivery_standards() {
  local body_file="$1"
  cat >>"$body_file" <<'DELIVERY_STANDARDS'

## Cross-cutting delivery standards

- Follow the existing Django 6 + Inertia.js + React 19 architecture; Inertia props are camelCase and shared interfaces live in `frontend/types/index.ts`.
- Any `urls.py` change includes `pnpm run routes:generate`; frontend navigation uses the typed route map, never string literals.
- Restricted features use backend authorization policies/permissions plus frontend `PermissionRequired` or `hasPermission`; frontend hiding is never security.
- Apply self, assigned-record, office, region, and company scope before serialization, aggregation, search, download, or background delivery.
- Every model change ships with a new migration; never edit an already-applied migration.
- Sensitive files use protected S3-compatible storage and short-lived authorized access, not permanent public URLs.
- Lifecycle and sensitive changes emit audit/domain events with idempotent after-commit side effects.
- Use existing design-system components and semantic Tailwind tokens; include responsive, keyboard, screen-reader, loading, empty, error, stale, and disabled states.
- Add pytest coverage for backend behavior and Vitest/Testing Library coverage for frontend behavior, including denial, scope, validation, concurrency, and accessibility where relevant.
- Run the complete repository quality gate documented in `AGENTS.md` and update operational/user documentation.
DELIVERY_STANDARDS
}

create_issue() {
  local id="$1"
  local title="$2"
  local specific_labels="$3"
  local labels="P1,type:feature,$specific_labels"
  local available_labels=""
  local marker="ONEST-$id"
  local body_file="$WORK_DIR/$id.md"
  local existing=""
  local status=0
  local existing_number=""
  local existing_url=""
  local created_url=""

  TOTAL=$((TOTAL + 1))
  available_labels=$(filter_available_labels "$labels")
  cat >"$body_file"
  append_classification "$body_file" "$labels"
  append_delivery_standards "$body_file"
  printf '\n<!-- %s -->\n' "$marker" >>"$body_file"

  set +e
  existing=$(lookup_existing_issue "$marker" "$title")
  status=$?
  set -e
  if ((status == 0)); then
    IFS=$'\t' read -r existing_number existing_url <<<"$existing"
    if ((DRY_RUN == 1)); then
      SKIPPED=$((SKIPPED + 1))
      info "Dry run: issue #$existing_number exists; would ensure labels: $labels"
    elif [[ -n "$available_labels" ]] && gh issue edit "$existing_number" \
      --repo "$REPO" --add-label "$available_labels" >/dev/null; then
      UPDATED=$((UPDATED + 1))
      info "Updated labels for $id: issue #$existing_number ($existing_url)."
    elif [[ -z "$available_labels" ]]; then
      SKIPPED=$((SKIPPED + 1))
      warn "Skip $id: matching issue exists, but no requested labels are available."
    else
      FAILED=$((FAILED + 1))
      error "$id: matching issue exists, but label reconciliation failed."
    fi
    return 0
  fi
  if ((status != 1)); then
    FAILED=$((FAILED + 1))
    error "$id: duplicate check failed; creation blocked."
    return 0
  fi

  if ((DRY_RUN == 1)); then
    info "Dry run: would create $id — $title (labels: $labels)"
    return 0
  fi

  if [[ -n "$available_labels" ]]; then
    created_url=$(gh issue create --repo "$REPO" --title "$title" \
      --body-file "$body_file" --label "$available_labels") || status=$?
  else
    created_url=$(gh issue create --repo "$REPO" --title "$title" \
      --body-file "$body_file") || status=$?
  fi
  if ((status == 0)); then
    CREATED=$((CREATED + 1))
    printf '%s\t%s\t%s\t%s\n' "$(basename "$created_url")" "$created_url" "$title" "$marker" >>"$ISSUE_INDEX"
    info "Created $id: $created_url"
  else
    FAILED=$((FAILED + 1))
    error "$id: GitHub rejected issue creation."
  fi
}

create_issue "P1-060" "[P1] Build role-aware administrative dashboards and dashboard assignment" "module:dashboard,area:frontend,area:backend,area:ui-ux,area:data-model,area:admin,area:permissions,area:reporting,area:security" <<'ISSUE_P1_060'
## Summary

Build the administrative dashboard system and a deterministic way to assign dashboard profiles to roles, offices, regions, and specific users. Assignment controls presentation only; it must never grant access to underlying data.

## Dashboard profiles

Register reusable profiles for Agent, Branch/Office Admin, Branch Manager, Regional Admin/Manager, Broker/Principal Broker, Transaction Coordinator, Compliance, Marketing, Accounting, IT Support, and System Admin. Compose them from an allowlisted widget/provider registry rather than eleven duplicated page implementations.

## Assignment and resolution

- Model active dashboard profiles and assignments targeting a role, user, office, region, or company, with priority, validity window, default flag, creator, and audit timestamps.
- Recommended default precedence: explicit valid user assignment; designated primary-role assignment; highest-priority effective-role assignment; office/region assignment; authenticated fallback.
- Multi-role users may switch among authorized profiles. Remembered selection remains valid only while its assignment and permissions remain active.
- Do not store arbitrary Python paths, SQL, React component names, or executable expressions in editable configuration.
- Assignment changes invalidate dashboard/navigation caches and take effect on the next request.

## Administrative dashboard content

- Scoped agent/onboarding counts, transaction and closing pipeline, contracts awaiting signature, compliance exceptions, tasks, overdue inventory, room utilization, announcements, and operational activity.
- Scope selector lists only authorized offices/regions and is revalidated server-side.
- Quick actions remain independently permission-protected.
- Financial, compliance, security, and document widgets require their own explicit permissions.

## Acceptance criteria

- [ ] Every supported role receives a documented default or safe fallback dashboard.
- [ ] Multi-role resolution is deterministic and never duplicates widgets or aggregates.
- [ ] Branch, region, and company dashboards contain only effective-scope records.
- [ ] Switching/assigning a dashboard never adds Django permissions or data scope.
- [ ] Scoped admins manage assignments only inside their grant boundary.
- [ ] Each deferred widget fails independently and distinguishes zero, unavailable, withheld, stale, loading, and error states.
- [ ] Assignment changes and denied escalation attempts are audited.

## Testing focus

- Table-driven profile resolution for every role/scope, multi-role precedence, assignment expiry/revocation, grant boundaries, aggregate leakage, cache isolation, widget failure, and admin UI accessibility.

## Dependencies

- P0 role/scope/authorization/audit/navigation/design-system foundation and P1-021 through P1-027 dashboard widgets.
ISSUE_P1_060

create_issue "P1-061" "[P1] Build scoped user management interface" "module:users,area:frontend,area:backend,area:ui-ux,area:admin,area:permissions,area:security" <<'ISSUE_P1_061'
## Summary

Build the product-level user administration workspace for searching, reviewing, activating, disabling, and maintaining users without relying on unrestricted Django admin access.

## Functional requirements

- Search/filter users by name, email, office, region, role, status, onboarding state, contract state, and last login.
- Show a scoped user detail with profile, office, effective roles/scopes, onboarding, contract summary, training/setup progress, account state, and recent authorized activity.
- Support disable/reactivate, office/status administration, and links to dedicated role-assignment and onboarding workflows.
- Use explicit confirmed service actions for security-sensitive changes; do not mass-assign auth fields through a generic ModelForm.
- Detect stale concurrent edits and show who last changed the record.

## Permissions and privacy

- Company, regional, and branch admins see only users inside effective scope and only fields allowed by field-level permissions.
- IT support access does not imply contract, commission, client, or transaction visibility.
- Prevent out-of-scope enumeration through search, counts, exports, and direct IDs.
- Disabling access invalidates active sessions according to approved policy and emits audit/security events.

## Acceptance criteria

- [ ] Authorized admins can search and manage only in-scope users.
- [ ] Disable/reactivate is confirmed, audited, idempotent, and enforced on subsequent requests.
- [ ] Sensitive fields are omitted without their permissions.
- [ ] Crafted office/user/role parameters cannot broaden access.
- [ ] Empty, no-result, inactive, and concurrent-edit states are actionable.

## Testing focus

- Role × scope × field/action matrix, enumeration resistance, session invalidation, stale edit, filters/pagination, audit events, and accessible admin UI.

## Dependencies

- P0 user/office/role/scope foundation and P1-019/P1-020 profile administration.
ISSUE_P1_061

create_issue "P1-062" "[P1] Build onboarding administration and New Agent List" "module:users,area:frontend,area:backend,area:ui-ux,area:admin,area:permissions,area:reporting" <<'ISSUE_P1_062'
## Summary

Build an operational onboarding workspace and New Agent List so authorized staff can see activation progress, ownership, blockers, and next actions across profile, contract, tools, and training.

## Required state

- User, office, start date, profile completion, Microsoft login, contract generated/signed/active, required training, approved tool-setup states, assigned onboarding admin, outstanding tasks, and derived overall status.
- Define one typed onboarding-state service shared by dashboard, user detail, list, and future assistant integrations; do not duplicate status logic in React.
- Support search/filter/sort by office, assignee, blocker, overall status, start-date range, contract status, and training state.

## Workflow

- Authorized staff assign an onboarding owner, create/resolve operational tasks, resend eligible notices through source services, and navigate to the permitted correction workflow.
- Derived milestones cannot be manually checked off when owned by profile, contract, SSO, or training domains.
- Allow notes only with a documented privacy/retention policy.

## Acceptance criteria

- [ ] Scoped staff see accurate, current onboarding state for only their users.
- [ ] Derived milestones track source records and cannot drift through manual edits.
- [ ] Overall status and blockers are deterministic and documented.
- [ ] Actions delegate to source-domain permissions and are audited.
- [ ] Branch/regional aggregates do not leak sibling/company data.

## Testing focus

- State derivation, scope, filters, source updates, assignment, stale data/cache invalidation, action delegation, query count, and accessible table/empty/error states.

## Dependencies

- P1-061 user administration, contract P1-036..046, and training P1-068..070.
ISSUE_P1_062

create_issue "P1-063" "[P1] Build role and scope assignment administration" "module:users,area:frontend,area:backend,area:ui-ux,area:data-model,area:admin,area:permissions,area:security" <<'ISSUE_P1_063'
## Summary

Build the administration interface for assigning multiple roles with explicit company, region, office, or assigned-record scope and effective dates, using the established role-assignment service.

## Workflow requirements

- Display current/effective/future/expired assignments and the access each produces.
- Create, edit, revoke, and schedule assignments through explicit actions with expected-version conflict detection.
- Restrict available roles and scopes to what the actor may delegate; explain why options are unavailable.
- Preview effective permissions/navigation before confirmation and require confirmation for high-impact grants or last-access removal.
- Prevent self-promotion, over-delegation, scope expansion, invalid role/scope combinations, overlapping duplicate assignments, and removal of the last required agent assignment without an approved outcome.

## Security

- Backend grant-boundary checks are authoritative for user, role, scope, validity dates, and delegated permissions.
- Recalculate effective access and invalidate authorization/navigation/dashboard caches immediately.
- Audit successful and denied changes with before/after assignments and request context.

## Acceptance criteria

- [ ] Authorized admins grant only delegable roles inside effective scope.
- [ ] Multi-role and date-bounded assignments resolve deterministically.
- [ ] Hand-crafted over-grants and self-escalation fail server-side.
- [ ] Revocation takes effect on the next request and stale sessions cannot retain cached access.
- [ ] Preview and post-save effective access match.

## Testing focus

- Full actor-role-scope-target matrix, self-escalation, date windows, duplicate overlap, last-role removal, concurrency, cache invalidation, audit, and accessible preview/confirmation UI.

## Dependencies

- P0-006 through P0-010 and P0-012, plus the existing `UserRoleAssignment` service.
ISSUE_P1_063

create_issue "P1-064" "[P1] Build scoped office and regional administration" "module:users,area:frontend,area:backend,area:ui-ux,area:admin,area:permissions,area:security" <<'ISSUE_P1_064'
## Summary

Build product-level office and regional administration for office information, contact assignments, hierarchy visibility, and links to scoped resources, inventory, rooms, announcements, forms, users, and onboarding.

## Functional requirements

- Office list/tree and detail with type, parent/region, active/assignable state, address, contact methods, hours, instructions, and current contact assignments.
- Edit allowed office information and assign Branch Manager, Admin, Broker, Transaction Coordinator, and IT/support contacts with validity dates.
- Regional admins receive aggregate branch navigation without company-wide configuration rights.
- Preview the agent-visible Office Info page after edits.
- Protect stable identity/hierarchy changes behind high-impact permissions and explicit impact analysis.

## Scope and safety

- Branch staff manage only their branch; regional staff manage permitted descendants; company structure changes require company authority.
- Prevent cycles, invalid parent kinds, cross-office contact assignments, duplicate primary contacts, and destructive deletion of referenced offices.
- Sensitive access/emergency instructions remain authenticated and field-protected.

## Acceptance criteria

- [ ] Scoped administrators manage only permitted offices and fields.
- [ ] Hierarchy/contact constraints remain valid under crafted and concurrent requests.
- [ ] Agent-facing office data updates without cross-office cache leakage.
- [ ] Deactivation/hierarchy changes report affected users/resources before commit.
- [ ] Material changes are audited.

## Testing focus

- Office hierarchy/grant matrix, contact validity/uniqueness, impact analysis, inactive office, concurrency, field privacy, cache invalidation, and accessible tree/forms.

## Dependencies

- P0-003 through P0-008 and P1-033 through P1-035.
ISSUE_P1_064

create_issue "P1-065" "[P1] Build general notification model and in-app notification center" "module:notifications,area:frontend,area:backend,area:ui-ux,area:data-model,area:notifications,area:security" <<'ISSUE_P1_065'
## Summary

Create the shared notification domain and in-app notification center used by contracts, transactions, announcements, training, inventory, rooms, leads, and administrative workflows.

## Data and behavior

- Notification type/event identity, recipient, title/summary, priority, mandatory flag, related object, safe typed action, created/available/expires/read/archived timestamps, and deduplication key.
- Store minimal presentation data; resolve sensitive details from authorized source records at view time.
- List unread/all with pagination and type/priority filters; support idempotent mark-read, mark-unread, archive, and mark-all-read.
- Header unread badge/count and a full notification center with accessible live-update behavior if real-time delivery is added.
- Expired/revoked source access must remove sensitive content/action availability.

## Security and scale

- Self-only recipient queries, opaque IDs, no cross-user counts, safe URLs, and bounded indexed pagination.
- Producer service validates recipient, source authorization, mandatory policy, and stable idempotency key.
- Bulk audience fan-out must use background jobs and avoid one request holding thousands of writes.

## Acceptance criteria

- [ ] Domain producers create one in-app notification per recipient/idempotency key.
- [ ] Users can access and mutate only their own notification state.
- [ ] Unread counts remain correct under concurrent reads/updates and duplicate delivery.
- [ ] Revoked/expired source records do not leak details through old notifications.
- [ ] Empty, stale-action, loading, and error states are useful and accessible.

## Testing focus

- Idempotency, self-only access, concurrent read state, pagination/counts, source revocation, safe actions, fan-out, query count, and frontend accessibility.

## Dependencies

- P0 audit/event/background foundation; P1-046 and P1-053 become producers.
ISSUE_P1_065

create_issue "P1-066" "[P1] Add notification preferences and reliable email delivery" "module:notifications,area:frontend,area:backend,area:ui-ux,area:data-model,area:notifications,area:background-jobs,area:security" <<'ISSUE_P1_066'
## Summary

Add user-controlled preferences for optional notification categories and a reliable, observable email-delivery pipeline while preserving mandatory legal, compliance, and security notices.

## Preferences

- Model channel/category preferences with defaults, policy version, timestamps, and a clear mandatory-category override.
- Provide a self-service settings page explaining each category/channel and why mandatory notices cannot be disabled.
- Validate unknown categories safely and preserve sensible defaults when new categories are introduced.

## Delivery pipeline

- Render approved templates with authenticated application links, never permanent sensitive-file URLs.
- Queue after transaction commit with stable delivery keys, bounded retries/backoff, attempt/status timestamps, and terminal failure visibility.
- Revalidate recipient email/account state, source lifecycle, preference, and authorization immediately before send.
- Suppress stale reminders and prevent duplicate sends from event retries or worker restarts.

## Acceptance criteria

- [ ] Optional notices respect saved preferences; mandatory policy notices remain enabled.
- [ ] One logical event produces at most one delivery per recipient/channel/key.
- [ ] Failed delivery is retryable and observable without rolling back domain state.
- [ ] Email contains minimal data and safe authenticated links.
- [ ] New categories have documented default behavior.

## Testing focus

- Preference matrix, mandatory enforcement, after-commit behavior, idempotency, retry/failure, stale source suppression, template safety, account/email changes, and accessible settings UI.

## Dependencies

- P1-065 notification domain and configured SMTP/Celery infrastructure.
ISSUE_P1_066

create_issue "P1-067" "[P1] Build permission-aware global Quick Create" "module:users,area:frontend,area:backend,area:ui-ux,area:permissions,area:business-logic" <<'ISSUE_P1_067'
## Summary

Build the global `+` Quick Create menu for frequently used agent and admin workflows, driven by permissions, scope, active features, and typed routes.

## Required behavior

- Agent actions may include new lead/buyer/seller/transaction, reserve room, and reserve inventory as modules become active.
- Admin actions may include new user, contract, announcement, inventory item, training content, document, room block, and permitted support task.
- Centralize a registered action catalog with stable key, label, icon, required permission, supported scopes, feature dependency, and typed destination builder.
- Do not store executable route builders or arbitrary URLs in editable data.
- Hide unavailable actions before serialization, while every target endpoint re-enforces authorization.

## User experience

- Keyboard-accessible menu/dialog with search when the action set is large, visible scope context, external-navigation disclosure, and useful empty state.
- Preserve current return destination only through validated same-origin paths.
- Mobile and desktop entry points share the same action registry.

## Acceptance criteria

- [ ] Each role/scope sees only available permitted actions.
- [ ] Multi-role users receive a deterministic union without duplicates.
- [ ] Feature-disabled and out-of-scope actions are not serialized.
- [ ] Crafted navigation cannot bypass destination authorization.
- [ ] All links use typed routes and remain accessible on mobile/keyboard.

## Testing focus

- Registry selection across roles/scopes/features, deduplication, safe return path, target denial, responsive menu, focus management, and accessibility.

## Dependencies

- P0 authorization/navigation and relevant destination modules.
ISSUE_P1_067
