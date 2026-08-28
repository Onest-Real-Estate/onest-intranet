import { Head, Link, router, usePage } from "@inertiajs/react";
import { BadgeCheck, CalendarClock, Plus, ShieldCheck, ShieldOff } from "lucide-react";
import { useId, useMemo, useState } from "react";

import {
  type AccessChange,
  AccessChangeDialog,
} from "@/components/administration/AccessChangeDialog";
import {
  CardStateMessage,
  DataTable,
  DateField,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormLabel,
  FormSheet,
  FormSheetBody,
  PageHeader,
  PanelHeader,
  RoleBadge,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { SelectField } from "@/components/profile/profile-fields";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { hasPermission } from "@/lib/permissions";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type {
  RoleAssignmentPreview,
  RoleAssignmentWorkspaceAssignment,
  RoleAssignmentWorkspacePageProps,
} from "@/types";
import type { StatusTone, ValidationErrors } from "@/types/design-system";

const ASSIGN = { all: ["web.assign_user_roles"] };

const STATUS_TONES: Record<string, StatusTone> = {
  active: "success",
  scheduled: "info",
  expired: "neutral",
  revoked: "destructive",
};

const ERROR_LABELS: Record<string, string> = {
  role: "Role",
  scope_type: "Scope",
  scope_office: "Office or region",
  starts_at: "Effective from",
  ends_at: "Effective until",
  business_reason: "Business reason",
  assignment: "Assignment",
};

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString();
}

function toAccessChanges(preview: RoleAssignmentPreview | null): AccessChange[] {
  if (!preview) return [];
  return preview.highImpact.map((item) => ({
    label: item.label,
    from: item.from,
    to: item.to,
    impact: item.impact,
  }));
}

function csrfHeader(token: string): HeadersInit {
  return {
    "X-XSRF-TOKEN": token,
    "X-Requested-With": "XMLHttpRequest",
    Accept: "application/json",
  };
}

/**
 * One person's role assignments: create, edit dates, revoke, with preview.
 */
function RoleAssignmentWorkspacePage() {
  const { csrfToken, workspace, validation, user } =
    usePage<RoleAssignmentWorkspacePageProps>().props;
  const {
    subject,
    assignments,
    effectiveAccess,
    grantVersion,
    options,
    editable,
    administrationHref,
  } = workspace;

  const availableRoles = useMemo(
    () => options.roles.filter((role) => role.available !== false),
    [options.roles],
  );
  const [role, setRole] = useState(availableRoles[0]?.value ?? "");
  const selectedRole =
    options.roles.find((option) => option.value === role) ?? availableRoles[0];
  const availableScopes = (selectedRole?.scopes ?? []).filter(
    (scope) => scope.available !== false,
  );
  const [scopeType, setScopeType] = useState(availableScopes[0]?.value ?? "office");
  const [scopeOffice, setScopeOffice] = useState("");
  const [reason, setReason] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");

  const [preview, setPreview] = useState<RoleAssignmentPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [confirmingGrant, setConfirmingGrant] = useState(false);
  const [grantOpen, setGrantOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [revoking, setRevoking] = useState<RoleAssignmentWorkspaceAssignment | null>(
    null,
  );
  const [revokeReason, setRevokeReason] = useState("");
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);

  const [editing, setEditing] = useState<RoleAssignmentWorkspaceAssignment | null>(
    null,
  );
  const [editStarts, setEditStarts] = useState("");
  const [editEnds, setEditEnds] = useState("");
  const [editReason, setEditReason] = useState("");

  const revokeReasonId = useId();
  const needsOffice = scopeType !== "company" && scopeType !== "assigned_record";
  const canOpenAdmin = hasPermission(user, {
    all: ["user.view_user_administration"],
  });
  const canGrant = editable && availableRoles.length > 0;

  /** Back to a clean draft: only a successful grant clears the form. */
  function resetGrantDraft() {
    const firstRole = availableRoles[0];
    setRole(firstRole?.value ?? "");
    setScopeType(
      (firstRole?.scopes ?? []).filter((scope) => scope.available !== false)[0]
        ?.value ?? "office",
    );
    setScopeOffice("");
    setReason("");
    setStartsAt("");
    setEndsAt("");
    setPreview(null);
  }

  function closeGrantSheet() {
    resetGrantDraft();
    setConfirmingGrant(false);
    setGrantOpen(false);
  }

  async function requestPreview(body: FormData): Promise<RoleAssignmentPreview | null> {
    setPreviewError(null);
    const response = await fetch(routes.admin_assign_roles_preview(subject.id), {
      method: "POST",
      headers: csrfHeader(csrfToken),
      body,
      credentials: "same-origin",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const message =
        payload?.errors?.form?.[0] ??
        "Could not preview this change. Check the fields and try again.";
      setPreviewError(message);
      return null;
    }
    setPreview(payload.preview);
    return payload.preview as RoleAssignmentPreview;
  }

  async function onGrantSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set("action", "grant");
    const result = await requestPreview(data);
    if (!result) return;
    if (result.requiresConfirmation) {
      setConfirmingGrant(true);
      return;
    }
    data.set("confirmed", "1");
    setSubmitting(true);
    router.post(routes.admin_assign_roles_mutate(subject.id), data, {
      onSuccess: () => closeGrantSheet(),
      onFinish: () => setSubmitting(false),
    });
  }

  function confirmGrant() {
    const data = new FormData();
    data.set("action", "grant");
    data.set("role", role);
    data.set("scope_type", scopeType);
    if (needsOffice && scopeOffice) data.set("scope_office", scopeOffice);
    if (startsAt) data.set("starts_at", startsAt);
    if (endsAt) data.set("ends_at", endsAt);
    data.set("business_reason", reason);
    data.set("expected_version", grantVersion);
    data.set("confirmed", "1");
    setSubmitting(true);
    router.post(routes.admin_assign_roles_mutate(subject.id), data, {
      onSuccess: () => closeGrantSheet(),
      onFinish: () => {
        setSubmitting(false);
        setConfirmingGrant(false);
      },
    });
  }

  async function beginRevoke(row: RoleAssignmentWorkspaceAssignment) {
    setRevoking(row);
    setRevokeReason("");
    const data = new FormData();
    data.set("action", "revoke");
    data.set("assignment", String(row.id));
    await requestPreview(data);
  }

  async function onRevokeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!revoking) return;
    const data = new FormData();
    data.set("action", "revoke");
    data.set("assignment", String(revoking.id));
    data.set("business_reason", revokeReason);
    data.set("expected_version", revoking.version);
    const result = preview ?? (await requestPreview(data));
    if (result?.requiresConfirmation || result?.warnings.length) {
      setConfirmingRevoke(true);
      return;
    }
    data.set("confirmed", "1");
    setSubmitting(true);
    router.post(routes.admin_assign_roles_mutate(subject.id), data, {
      onFinish: () => {
        setSubmitting(false);
        setRevoking(null);
      },
    });
  }

  function confirmRevoke() {
    if (!revoking) return;
    const data = new FormData();
    data.set("action", "revoke");
    data.set("assignment", String(revoking.id));
    data.set("business_reason", revokeReason);
    data.set("expected_version", revoking.version);
    data.set("confirmed", "1");
    setSubmitting(true);
    router.post(routes.admin_assign_roles_mutate(subject.id), data, {
      onFinish: () => {
        setSubmitting(false);
        setConfirmingRevoke(false);
        setRevoking(null);
      },
    });
  }

  function onEditSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData();
    data.set("action", "edit");
    data.set("assignment", String(editing.id));
    if (editStarts) data.set("starts_at", editStarts);
    if (editEnds) data.set("ends_at", editEnds);
    data.set("business_reason", editReason);
    data.set("expected_version", editing.version);
    setSubmitting(true);
    router.post(routes.admin_assign_roles_mutate(subject.id), data, {
      onFinish: () => {
        setSubmitting(false);
        setEditing(null);
      },
    });
  }

  return (
    <>
      <Head title={`Roles · ${subject.displayName}`} />
      <div className="flex flex-col gap-6">
        <PageHeader
          title={subject.displayName}
          description={subject.email}
          meta={
            <span className="text-muted-foreground text-sm">
              {subject.office?.pathLabel ?? "No office"} · {effectiveAccess.scopeLabel}
            </span>
          }
          actions={
            <div className="flex items-center gap-2">
              {canGrant ? (
                <Button type="button" onClick={() => setGrantOpen(true)}>
                  <Plus className="size-4" aria-hidden />
                  Grant a role
                </Button>
              ) : null}
              {canOpenAdmin ? (
                <Button asChild variant="outline">
                  <Link href={administrationHref}>Administrative record</Link>
                </Button>
              ) : null}
            </div>
          }
        />

        {hasValidationErrors(validation) ? (
          <FormErrorSummary errors={validation} labels={ERROR_LABELS} />
        ) : null}
        {previewError ? (
          <CardStateMessage state="error">{previewError}</CardStateMessage>
        ) : null}

        <SurfaceCard>
          <PanelHeader
            divided
            title="Effective access now"
            description="Union of live assignments — what the next request will see."
          />
          <SurfaceCardContent className="grid gap-2 text-sm">
            <p>
              <span className="text-muted-foreground">Roles: </span>
              {effectiveAccess.roles.length ? effectiveAccess.roles.join(", ") : "None"}
            </p>
            <p>
              <span className="text-muted-foreground">Reach: </span>
              {effectiveAccess.scopeLabel}
            </p>
            <p className="text-muted-foreground text-xs">
              {effectiveAccess.permissions.length} catalogued permissions ·{" "}
              {effectiveAccess.liveAssignments} live assignment
              {effectiveAccess.liveAssignments === 1 ? "" : "s"}
            </p>
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader
            divided
            title="Assignments"
            description="Current, scheduled, expired, and revoked — and the access each produces."
            meta={
              <span className="text-muted-foreground text-xs tabular-nums">
                {assignments.length}
              </span>
            }
          />
          <SurfaceCardContent>
            <DataTable
              frame="bleed"
              caption="Role assignments for this person"
              rows={assignments}
              rowKey={(row) => String(row.id)}
              emptyTitle="No role assignments"
              emptyDescription="Grant a role to define what they may reach."
              columns={[
                {
                  id: "role",
                  header: "Role",
                  icon: ShieldCheck,
                  cell: (row) => (
                    <span className="grid gap-1">
                      <RoleBadge
                        code={row.role}
                        label={row.roleLabel}
                        scopeLabel={row.scopeLabel}
                      />
                      <span className="text-muted-foreground text-xs">
                        {row.access.orgReach} · {row.access.permissions.length}{" "}
                        permissions
                      </span>
                    </span>
                  ),
                },
                {
                  id: "status",
                  header: "Status",
                  icon: BadgeCheck,
                  cell: (row) => (
                    <StatusBadge
                      status={{
                        label: row.status,
                        tone: STATUS_TONES[row.status] ?? "neutral",
                      }}
                    />
                  ),
                },
                {
                  id: "window",
                  header: "Effective",
                  icon: CalendarClock,
                  cell: (row) => (
                    <span className="text-muted-foreground text-xs">
                      {formatMoment(row.startsAt)} → {formatMoment(row.endsAt)}
                    </span>
                  ),
                  hideBelow: "2xl",
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Actions</span>,
                  cell: (row) =>
                    editable && (row.canEdit || row.canRevoke) ? (
                      <span className="flex flex-wrap gap-2">
                        {row.canEdit ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setEditing(row);
                              setEditStarts(row.startsAt?.slice(0, 16) ?? "");
                              setEditEnds(row.endsAt?.slice(0, 16) ?? "");
                              setEditReason(row.businessReason || "");
                            }}
                          >
                            <CalendarClock className="size-3.5" aria-hidden />
                            Edit dates
                          </Button>
                        ) : null}
                        {row.canRevoke ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => beginRevoke(row)}
                          >
                            <ShieldOff className="size-3.5" aria-hidden />
                            Revoke
                          </Button>
                        ) : null}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        Outside your delegation
                      </span>
                    ),
                },
              ]}
            />
          </SurfaceCardContent>
        </SurfaceCard>

        {!canGrant ? (
          <p className="text-muted-foreground text-sm leading-6">
            {subject.isSelf
              ? "You cannot change your own role assignments."
              : editable
                ? "Your own scope does not let you delegate any role."
                : "You can see these assignments but not change them."}
          </p>
        ) : null}
      </div>

      {canGrant ? (
        <FormSheet
          open={grantOpen}
          onOpenChange={setGrantOpen}
          title="Grant a role"
          description="Preview effective access before anything high-impact is saved."
          footer={
            <div className="flex items-center justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setGrantOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                form="role-grant-form"
                disabled={submitting || reason.trim().length === 0}
                aria-busy={submitting || undefined}
              >
                Preview and grant
              </Button>
            </div>
          }
        >
          <form
            id="role-grant-form"
            onSubmit={onGrantSubmit}
            className="flex min-h-0 flex-col overflow-hidden"
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="action" value="grant" />
            <input type="hidden" name="expected_version" value={grantVersion} />
            <FormSheetBody>
              <div className="grid gap-4">
                {hasValidationErrors(validation) ? (
                  <FormErrorSummary errors={validation} labels={ERROR_LABELS} />
                ) : null}
                {previewError ? (
                  <CardStateMessage state="error">{previewError}</CardStateMessage>
                ) : null}
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-2">
                    <SelectField
                      name="role"
                      label="Role"
                      required
                      value={role}
                      onChange={(next) => {
                        setRole(next);
                        const option = options.roles.find(
                          (item) => item.value === next,
                        );
                        const nextScopes = (option?.scopes ?? []).filter(
                          (scope) => scope.available !== false,
                        );
                        setScopeType(nextScopes[0]?.value ?? "office");
                      }}
                      placeholder="Select a role"
                      options={availableRoles.map((option) => ({
                        value: option.value,
                        label: option.label,
                      }))}
                      validation={validation}
                    />
                    {selectedRole?.description ? (
                      <FormDescription>{selectedRole.description}</FormDescription>
                    ) : null}
                    {options.roles
                      .filter((option) => option.available === false)
                      .slice(0, 3)
                      .map((option) => (
                        <p
                          key={option.value}
                          className="text-muted-foreground text-xs leading-5"
                        >
                          {option.label} unavailable: {option.unavailableReason}
                        </p>
                      ))}
                  </div>
                  <SelectField
                    name="scope_type"
                    label="Scope"
                    required
                    value={scopeType}
                    onChange={setScopeType}
                    placeholder="Select a scope"
                    options={availableScopes.map((scope) => ({
                      value: scope.value,
                      label: scope.label,
                    }))}
                    validation={validation}
                  />
                  {needsOffice ? (
                    <SelectField
                      name="scope_office"
                      label="Office or region"
                      required
                      value={scopeOffice}
                      onChange={setScopeOffice}
                      placeholder="Select the area this covers"
                      options={options.offices.map((office) => ({
                        value: String(office.id),
                        label: office.pathLabel,
                      }))}
                      validation={validation}
                      className="sm:col-span-2"
                    />
                  ) : null}
                  <DateField
                    name="starts_at"
                    label="Effective from"
                    includeTime
                    optional
                    value={startsAt}
                    onChange={setStartsAt}
                    validation={validation}
                    description="Leave empty to start immediately."
                  />
                  <DateField
                    name="ends_at"
                    label="Effective until"
                    includeTime
                    optional
                    value={endsAt}
                    onChange={setEndsAt}
                    validation={validation}
                    description="Leave empty for an open-ended assignment."
                  />
                </div>
                <FormField>
                  <FormLabel htmlFor="business_reason" required>
                    Business reason
                  </FormLabel>
                  <Textarea
                    id="business_reason"
                    name="business_reason"
                    rows={2}
                    required
                    maxLength={500}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="min-h-24 resize-y"
                  />
                </FormField>
                {preview && !confirmingGrant ? (
                  <PreviewSummary preview={preview} />
                ) : null}
              </div>
            </FormSheetBody>
          </form>
        </FormSheet>
      ) : null}

      <AccessChangeDialog
        open={confirmingGrant}
        onOpenChange={setConfirmingGrant}
        title="Confirm high-impact grant"
        description="Review what this person will be able to reach after the grant."
        changes={toAccessChanges(preview)}
        confirmLabel="Grant role"
        submitting={submitting}
        onConfirm={confirmGrant}
      />

      <AccessChangeDialog
        open={confirmingRevoke}
        onOpenChange={setConfirmingRevoke}
        title="Confirm high-impact revocation"
        description="This removes access on their next request."
        changes={toAccessChanges(preview)}
        confirmLabel="Revoke role"
        submitting={submitting}
        onConfirm={confirmRevoke}
      />

      <Dialog
        open={revoking !== null && !confirmingRevoke}
        onOpenChange={(open) => !open && setRevoking(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke {revoking?.roleLabel}</DialogTitle>
            <DialogDescription>
              Removes {revoking?.scopeLabel} access from the next request onward.
            </DialogDescription>
          </DialogHeader>
          {preview ? <PreviewSummary preview={preview} compact /> : null}
          <form onSubmit={onRevokeSubmit}>
            <FormField>
              <FormLabel htmlFor={revokeReasonId} required>
                Business reason
              </FormLabel>
              <Textarea
                id={revokeReasonId}
                name="business_reason"
                rows={3}
                required
                maxLength={500}
                value={revokeReason}
                onChange={(event) => setRevokeReason(event.target.value)}
                className="min-h-28 resize-y"
              />
            </FormField>
            <DialogFooter className="mt-5">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <Button
                type="submit"
                variant="destructive"
                disabled={revokeReason.trim().length === 0 || submitting}
              >
                Continue
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit {editing?.roleLabel} dates</DialogTitle>
            <DialogDescription>
              Change when this assignment is effective. Role and scope stay the same.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onEditSubmit} className="grid gap-4">
            <DateField
              name="starts_at"
              label="Effective from"
              includeTime
              optional
              value={editStarts}
              onChange={setEditStarts}
              validation={validation as ValidationErrors}
            />
            <DateField
              name="ends_at"
              label="Effective until"
              includeTime
              optional
              value={editEnds}
              onChange={setEditEnds}
              validation={validation as ValidationErrors}
            />
            <FormField>
              <FormLabel htmlFor="edit_reason" required>
                Business reason
              </FormLabel>
              <Textarea
                id="edit_reason"
                rows={2}
                required
                maxLength={500}
                value={editReason}
                onChange={(event) => setEditReason(event.target.value)}
              />
            </FormField>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={submitting || editReason.trim().length === 0}
              >
                Save dates
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function PreviewSummary({
  preview,
  compact = false,
}: {
  preview: RoleAssignmentPreview;
  compact?: boolean;
}) {
  return (
    <div
      className="border-border/60 bg-muted/30 grid gap-2 rounded-lg border p-4 text-sm"
      aria-live="polite"
    >
      <p className="font-medium">Access preview</p>
      <p className="text-muted-foreground text-xs leading-5">
        {preview.before.scopeLabel} → {preview.after.scopeLabel}
      </p>
      {!compact ? (
        <>
          {preview.permissionDelta.added.length > 0 ? (
            <p className="text-xs">
              Gains: {preview.permissionDelta.added.slice(0, 6).join(", ")}
              {preview.permissionDelta.added.length > 6 ? "…" : ""}
            </p>
          ) : null}
          {preview.permissionDelta.removed.length > 0 ? (
            <p className="text-xs">
              Loses: {preview.permissionDelta.removed.slice(0, 6).join(", ")}
              {preview.permissionDelta.removed.length > 6 ? "…" : ""}
            </p>
          ) : null}
          {preview.navigationDelta.added.length > 0 ? (
            <p className="text-xs">
              New navigation:{" "}
              {preview.navigationDelta.added.map((item) => item.label).join(", ")}
            </p>
          ) : null}
          {preview.navigationDelta.removed.length > 0 ? (
            <p className="text-xs">
              Navigation removed:{" "}
              {preview.navigationDelta.removed.map((item) => item.label).join(", ")}
            </p>
          ) : null}
        </>
      ) : null}
      {preview.warnings.map((warning) => (
        <p key={warning} className="text-warning-ink text-xs">
          {warning}
        </p>
      ))}
    </div>
  );
}

function RoleAssignmentWorkspace() {
  return (
    <PermissionRequired permission={ASSIGN}>
      <RoleAssignmentWorkspacePage />
    </PermissionRequired>
  );
}

RoleAssignmentWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Assign User Roles",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Assign User Roles", href: routes.admin_assign_roles() },
          { label: "Workspace" },
        ],
        back: { label: "All people", href: routes.admin_assign_roles() },
      },
    },
  ] as const;

export default RoleAssignmentWorkspace;
