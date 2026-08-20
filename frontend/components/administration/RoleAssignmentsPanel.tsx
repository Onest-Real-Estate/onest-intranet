import { ShieldOff } from "lucide-react";
import { useId, useState } from "react";

import {
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
  FormField,
  FormLabel,
  PanelHeader,
  RoleBadge,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { SelectField } from "@/components/profile/profile-fields";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type {
  AdministrationAssignment,
  AdministrationOfficeOption,
  AdministrationRoleOption,
} from "@/types";
import type { StatusTone, ValidationErrors } from "@/types/design-system";

const STATUS_TONES: Record<string, StatusTone> = {
  active: "success",
  scheduled: "info",
  expired: "neutral",
  revoked: "destructive",
};

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString();
}

/**
 * Live role assignments, and the two things an administrator does with them.
 *
 * Both actions post to the same endpoint the role-assignment service already
 * guards; the panel only offers what the server said this administrator may
 * delegate, and hides the grant form entirely when that set is empty.
 */
export function RoleAssignmentsPanel({
  userId,
  csrfToken,
  assignments,
  roleOptions,
  officeOptions,
  validation,
  editable,
}: {
  userId: number;
  csrfToken: string;
  assignments: AdministrationAssignment[];
  roleOptions: AdministrationRoleOption[];
  officeOptions: AdministrationOfficeOption[];
  validation: ValidationErrors;
  editable: boolean;
}) {
  const [role, setRole] = useState(roleOptions[0]?.value ?? "");
  const [scopeType, setScopeType] = useState(
    roleOptions[0]?.scopes[0]?.value ?? "office",
  );
  const [scopeOffice, setScopeOffice] = useState("");
  const [revoking, setRevoking] = useState<AdministrationAssignment | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const revokeReasonId = useId();

  const selectedRole = roleOptions.find((option) => option.value === role);
  const scopes = selectedRole?.scopes ?? [];
  const needsOffice = scopeType !== "company";

  return (
    <SurfaceCard>
      <PanelHeader
        divided
        title="Roles and scope"
        description="What this person may reach across the hub, and until when."
        meta={
          <span className="text-muted-foreground text-xs font-medium tabular-nums">
            {assignments.length} live
          </span>
        }
      />
      <SurfaceCardContent className="@container grid gap-4">
        <DataTable
          frame="bleed"
          caption="Live and scheduled role assignments"
          rows={assignments}
          rowKey={(row) => String(row.id)}
          emptyTitle="No role assignments"
          emptyDescription="This person falls back to whatever their legacy group grants until a role is assigned."
          columns={[
            {
              id: "role",
              header: "Role",
              cell: (row) => (
                <span className="grid gap-0.5">
                  <RoleBadge
                    code={row.role}
                    label={row.roleLabel}
                    scopeLabel={row.scopeLabel}
                    title={row.roleDescription || undefined}
                  />
                  <span className="text-muted-foreground text-xs @md:hidden">
                    {row.scopeLabel}
                  </span>
                </span>
              ),
            },
            {
              id: "scope",
              header: "Scope",
              cell: (row) => row.scopeLabel,
              className: "hidden @md:table-cell",
              headerClassName: "hidden @md:table-cell",
            },
            {
              id: "status",
              header: "Status",
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
              id: "effective",
              header: "Effective",
              cell: (row) => (
                <span className="text-muted-foreground text-xs">
                  {formatMoment(row.startsAt)} → {formatMoment(row.endsAt)}
                </span>
              ),
              className: "hidden @2xl:table-cell",
              headerClassName: "hidden @2xl:table-cell",
            },
            {
              id: "granted",
              header: "Granted by",
              cell: (row) => row.assignedBy ?? "System",
              className: "hidden @5xl:table-cell",
              headerClassName: "hidden @5xl:table-cell",
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              cell: (row) =>
                editable && row.canRevoke ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="size-8 px-0 @md:h-8 @md:w-auto @md:px-3"
                    onClick={() => {
                      setRevoking(row);
                      setRevokeReason("");
                    }}
                  >
                    <ShieldOff className="size-3.5" aria-hidden />
                    <span className="sr-only">Revoke {row.roleLabel}</span>
                    <span className="hidden @md:inline" aria-hidden>
                      Revoke
                    </span>
                  </Button>
                ) : (
                  <span className="text-muted-foreground text-xs">
                    <span className="@md:hidden">Out of scope</span>
                    <span className="hidden @md:inline">Outside your delegation</span>
                  </span>
                ),
            },
          ]}
        />

        {editable && roleOptions.length > 0 ? (
          <form
            method="post"
            action={routes.user_administration_roles(userId)}
            className="border-border/60 bg-muted/25 -mx-5 -mb-5 grid gap-4 border-t px-5 py-5"
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="action" value="grant" />
            <div className="grid gap-1">
              <h3 className="text-sm font-semibold">Grant a role</h3>
              <p className="text-muted-foreground text-sm leading-5">
                Set the access boundary and, when needed, an effective period.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <SelectField
                  name="role"
                  label="Role"
                  required
                  value={role}
                  onChange={(next) => {
                    setRole(next);
                    const option = roleOptions.find((item) => item.value === next);
                    setScopeType(option?.scopes[0]?.value ?? "office");
                  }}
                  placeholder="Select a role"
                  options={roleOptions.map((option) => ({
                    value: option.value,
                    label: option.label,
                  }))}
                  validation={validation}
                />
                {selectedRole?.description ? (
                  <FormDescription>{selectedRole.description}</FormDescription>
                ) : null}
              </div>
              <SelectField
                name="scope_type"
                label="Scope"
                required
                value={scopeType}
                onChange={setScopeType}
                placeholder="Select a scope"
                options={scopes}
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
                  options={officeOptions.map((office) => ({
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
                validation={validation}
                description="Leave empty to start immediately."
              />
              <DateField
                name="ends_at"
                label="Effective until"
                includeTime
                optional
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
                className="min-h-24 resize-y"
              />
              <FormDescription>
                Recorded in the audit trail alongside who granted it.
              </FormDescription>
            </FormField>
            <div>
              <Button type="submit">Grant role</Button>
            </div>
          </form>
        ) : (
          <p className="text-muted-foreground border-border/60 bg-muted/25 -mx-5 -mb-5 border-t px-5 py-5 text-sm leading-6">
            {editable
              ? "Your own scope does not let you delegate any role. Ask a brokerage-wide administrator."
              : "You can see this person's roles but not change them."}
          </p>
        )}
      </SurfaceCardContent>

      <Dialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke {revoking?.roleLabel}</DialogTitle>
            <DialogDescription>
              This removes {revoking?.scopeLabel} access from the next request onward.
              Say why — the reason is kept with the audit entry.
            </DialogDescription>
          </DialogHeader>
          <form method="post" action={routes.user_administration_roles(userId)}>
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="action" value="revoke" />
            <input type="hidden" name="assignment" value={revoking?.id ?? ""} />
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
                disabled={revokeReason.trim().length === 0}
              >
                Revoke role
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </SurfaceCard>
  );
}
