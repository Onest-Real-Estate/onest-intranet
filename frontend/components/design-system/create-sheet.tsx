import type * as React from "react";

import { FormSheet, FormSheetBody } from "@/components/design-system/form-sheet";
import { Button } from "@/components/ui/button";

/**
 * The standard "create one thing" drawer.
 *
 * `FormSheet` gives the slide-over its chrome; this adds the half every
 * administrative console was otherwise rebuilding by hand — a native POST form,
 * the CSRF field, the `context=sheet` marker, and a footer whose submit button
 * reaches the form by `form=` even though it lives outside the scrolling body.
 *
 * **It posts natively, not through the Inertia router.** That is the point of
 * the pattern rather than an oversight: the request carries multipart uploads
 * without a second code path, and a rejected create comes back as a normal
 * Inertia response that re-renders the list page with the drawer reopened and
 * repopulated. Nothing is held in client state that a failed save could lose.
 *
 * The server contract is one field. `context=sheet` tells the create view to
 * answer 422 with the *list* page — drawer open, draft echoed, errors attached
 * — instead of the full-page form it would render for a direct visit. See
 * `apps/announcements/administration_views.py` and
 * `apps/user/views/office_resource_administration_views.py`.
 *
 * Use it for focused, single-object creation. Work that needs full width or a
 * persistent side panel — a preview, a lifecycle, an inheritance hint — belongs
 * on its own page, and this drawer should hand off to that page on success.
 */
export function CreateSheet({
  open,
  onOpenChange,
  title,
  description,
  action,
  csrfToken,
  formId,
  submitLabel,
  cancelLabel = "Cancel",
  encType,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** POST target — always a typed route, never a string literal. */
  action: string;
  csrfToken: string;
  /** Ties the footer's submit button to the form inside the scrolling body. */
  formId: string;
  submitLabel: string;
  cancelLabel?: string;
  /** Set to multipart/form-data when the drawer carries a file field. */
  encType?: string;
  children: React.ReactNode;
}) {
  return (
    <FormSheet
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {cancelLabel}
          </Button>
          <Button type="submit" form={formId}>
            {submitLabel}
          </Button>
        </div>
      }
    >
      <form
        id={formId}
        method="post"
        action={action}
        encType={encType}
        className="flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
        {/* The whole server contract: branch on this to re-open the drawer with
            errors rather than rendering the standalone form page. */}
        <input type="hidden" name="context" value="sheet" />
        <FormSheetBody>
          <div className="grid gap-4">{children}</div>
        </FormSheetBody>
      </form>
    </FormSheet>
  );
}
