import { KeyRound, ShieldOff, ShieldPlus } from "lucide-react";
import { useRef, useState } from "react";

import {
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
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { AccountStatePayload } from "@/types";

function formatMoment(value: string | null, fallback: string): string {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed.toLocaleString();
}

/**
 * Account access — disable and reactivate, kept apart from the record form.
 *
 * It posts to its own endpoint with its own permission, and it will not submit
 * without a business reason, because "who disabled this and why" is the first
 * question anybody asks about a locked-out account. The confirmation spells
 * out that disabling ends live sessions rather than merely blocking the next
 * sign-in: an administrator doing this at 4pm needs to know the person is
 * signed out mid-task.
 */
export function AccountAccessPanel({
  userId,
  userName,
  csrfToken,
  version,
  state,
}: {
  userId: number;
  userName: string;
  csrfToken: string;
  version: string;
  state: AccountStatePayload;
}) {
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const disabling = state.isActive;
  const action = disabling ? "disable" : "reactivate";
  const reasonReady = reason.trim().length > 0;

  return (
    <SurfaceCard state={state.canManage ? "default" : "read-only"}>
      <PanelHeader
        divided
        title="Account access"
        description="Whether this person can sign in to the hub at all."
        meta={<StatusBadge status={{ label: state.label, tone: state.tone }} />}
      />
      <SurfaceCardContent className="grid gap-4">
        <dl className="grid gap-4 sm:grid-cols-2">
          <ReadOnlyValue label="Last sign-in">
            {formatMoment(state.lastLoginAt, "Never signed in")}
          </ReadOnlyValue>
          <ReadOnlyValue label="Account created">
            {formatMoment(state.joinedAt, "—")}
          </ReadOnlyValue>
        </dl>
        <p className="text-muted-foreground flex items-start gap-2 text-sm leading-5">
          <KeyRound className="mt-0.5 size-4 shrink-0" aria-hidden />
          {state.sessionPolicy}
        </p>
        {state.canManage ? (
          <Button
            ref={triggerRef}
            type="button"
            variant={disabling ? "outline" : "default"}
            className={
              disabling
                ? "text-destructive border-destructive/40 hover:bg-destructive/8"
                : undefined
            }
            onClick={() => setConfirming(true)}
          >
            {disabling ? (
              <ShieldOff className="size-4" aria-hidden />
            ) : (
              <ShieldPlus className="size-4" aria-hidden />
            )}
            {disabling ? "Disable account" : "Reactivate account"}
          </Button>
        ) : (
          <p className="text-muted-foreground text-sm">{state.reason}</p>
        )}
      </SurfaceCardContent>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent fallbackFocusRef={triggerRef}>
          <form
            method="post"
            action={routes.user_account_state(userId)}
            className="grid gap-5"
            onSubmit={() => setSubmitting(true)}
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="expected_version" value={version} />
            <input type="hidden" name="action" value={action} />
            <DialogHeader>
              <span
                className={
                  disabling
                    ? "bg-chip-destructive text-destructive grid size-10 place-items-center rounded-md"
                    : "bg-chip-success text-success grid size-10 place-items-center rounded-md"
                }
              >
                {disabling ? (
                  <ShieldOff className="size-5" aria-hidden />
                ) : (
                  <ShieldPlus className="size-5" aria-hidden />
                )}
              </span>
              <DialogTitle>
                {disabling
                  ? `Disable ${userName}'s account?`
                  : `Reactivate ${userName}'s account?`}
              </DialogTitle>
              <DialogDescription>
                {disabling
                  ? "They are signed out of every device immediately and cannot sign back in until somebody reactivates them."
                  : "They can sign in again from their next visit. Their previous sessions are not restored."}
              </DialogDescription>
            </DialogHeader>
            <FormField>
              <FormLabel htmlFor="account_state_reason">Business reason</FormLabel>
              <Textarea
                id="account_state_reason"
                name="business_reason"
                rows={3}
                required
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={
                  disabling
                    ? "Left the brokerage on 14 March."
                    : "Returned from leave; approved by the principal broker."
                }
              />
              <FormDescription>
                Recorded in the audit trail beside who made the change and when.
              </FormDescription>
            </FormField>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline" disabled={submitting}>
                  Cancel
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={!reasonReady || submitting}
                aria-busy={submitting || undefined}
              >
                {submitting
                  ? "Applying…"
                  : disabling
                    ? "Disable account"
                    : "Reactivate account"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </SurfaceCard>
  );
}
