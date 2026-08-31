import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, CalendarClock, History, PackageCheck, Upload } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  type AccessChange,
  AccessChangeDialog,
} from "@/components/administration/AccessChangeDialog";
import {
  FormActionBar,
  FormErrorSummary,
  FormField,
  FormLabel,
  NativeSelect,
  PageHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { InventoryFormFields } from "@/components/inventory/InventoryFormFields";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { InventoryItemWorkspacePageProps } from "@/types";

const VIEW = { all: ["web.view_inventory"] };

const STATE_TONES: Record<string, "success" | "neutral" | "warning" | "destructive"> = {
  active: "success",
  available: "success",
  temporarily_unavailable: "warning",
  damaged: "destructive",
  lost: "destructive",
  retired: "neutral",
};

const LIFECYCLE_CONFIRM: Record<
  string,
  {
    title: string;
    description: string;
    confirmLabel: string;
    toLabel: string;
    impact: string;
  }
> = {
  mark_temporarily_unavailable: {
    title: "Mark temporarily unavailable?",
    description: "The item stays in inventory but cannot be booked until restored.",
    confirmLabel: "Mark unavailable",
    toLabel: "Temporarily unavailable",
    impact: "Agents will not see this item as reservable until you restore it.",
  },
  mark_damaged: {
    title: "Mark damaged?",
    description:
      "Damaged items remain visible to admins but stop appearing as reservable.",
    confirmLabel: "Mark damaged",
    toLabel: "Damaged",
    impact: "Booking availability is blocked until the item is restored.",
  },
  mark_lost: {
    title: "Mark lost?",
    description: "Lost items remain in the audit trail but cannot be reserved.",
    confirmLabel: "Mark lost",
    toLabel: "Lost",
    impact:
      "Use this when the asset cannot be located. Restore it if it is found again.",
  },
  restore: {
    title: "Restore to available?",
    description:
      "Return this item to the reservable catalog when it is ready to book again.",
    confirmLabel: "Restore available",
    toLabel: "Available",
    impact: "Interval availability still depends on existing reservations.",
  },
  retire: {
    title: "Retire this item?",
    description:
      "Retirement preserves history but removes the item from active inventory.",
    confirmLabel: "Retire item",
    toLabel: "Retired",
    impact:
      "Retired items cannot be edited, transferred, or reserved. This cannot be undone.",
  },
};

function Workspace() {
  const {
    csrfToken,
    item,
    version,
    writableOffices,
    capabilities,
    filterOptions,
    validation,
    transfers,
    reservations,
    committedQuantity,
    availabilityPreview,
  } = usePage<InventoryItemWorkspacePageProps>().props;
  const [submitting, setSubmitting] = useState(false);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);
  const [confirmTransfer, setConfirmTransfer] = useState(false);
  const [transitionReason, setTransitionReason] = useState("");
  const [transferOfficeId, setTransferOfficeId] = useState("");
  const [transferReason, setTransferReason] = useState("");
  const [availStart, setAvailStart] = useState(availabilityPreview?.start ?? "");
  const [availEnd, setAvailEnd] = useState(availabilityPreview?.end ?? "");
  const transferFormRef = useRef<HTMLFormElement>(null);

  const transferDestinations = useMemo(
    () =>
      item ? writableOffices.filter((office) => office.id !== item.ownerOffice.id) : [],
    [item, writableOffices],
  );

  const selectedTransferOffice = transferDestinations.find(
    (office) => String(office.id) === transferOfficeId,
  );

  if (!item) {
    return null;
  }

  const workspaceItem = item;

  function postTransition(action: string) {
    setSubmitting(true);
    router.post(
      routes.admin_inventory_transition(workspaceItem.publicId),
      {
        action,
        expected_version: version,
        reason: transitionReason,
      },
      { onFinish: () => setSubmitting(false) },
    );
  }

  function previewAvailability() {
    router.get(
      routes.admin_inventory_item(workspaceItem.publicId),
      { availability_start: availStart, availability_end: availEnd },
      { preserveState: true, replace: true },
    );
  }

  function submitTransfer(confirmed: boolean) {
    const form = transferFormRef.current;
    if (!form) return;
    const data = new FormData(form);
    if (confirmed) {
      data.set("confirmed", "1");
    }
    setSubmitting(true);
    router.post(routes.admin_inventory_transfer(workspaceItem.publicId), data, {
      onFinish: () => setSubmitting(false),
    });
  }

  const tone = STATE_TONES[workspaceItem.availabilityState] ?? "neutral";
  const confirmCopy = confirmAction ? LIFECYCLE_CONFIRM[confirmAction] : null;
  const lifecycleChanges: AccessChange[] = confirmCopy
    ? [
        {
          label: "Availability state",
          from: item.availabilityStateLabel,
          to: confirmCopy.toLabel,
          impact: confirmCopy.impact,
        },
      ]
    : [];

  const transferChanges: AccessChange[] =
    selectedTransferOffice && confirmTransfer
      ? [
          {
            label: "Owning office",
            from: item.ownerOffice.name,
            to: selectedTransferOffice.label,
            impact:
              committedQuantity > 0
                ? "Active reservation commitments must be cleared before this transfer can succeed."
                : "Reservation history stays keyed to this item after the move.",
          },
        ]
      : [];

  return (
    <>
      <Head title={`${item.name} · Inventory`} />
      <div className="grid gap-8">
        <PageHeader
          title={item.name}
          description={`${item.ownerOffice.name} · ${item.trackingModeLabel}`}
          meta={<StatusBadge status={{ label: item.availabilityStateLabel, tone }} />}
          actions={
            <Button variant="outline" asChild>
              <Link href={routes.admin_inventory()}>
                <ArrowLeft className="size-4" aria-hidden />
                Back to inventory
              </Link>
            </Button>
          }
        />

        <FormErrorSummary errors={validation} />

        {capabilities.canManage ? (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 pt-5">
              <h2 className="text-foreground text-sm font-semibold">Edit item</h2>
              <form
                id="inventory-update-form"
                method="post"
                action={routes.admin_inventory_update(item.publicId)}
                className="grid gap-4"
              >
                <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                <input type="hidden" name="expected_version" value={version} />
                <InventoryFormFields
                  defaults={{
                    name: item.name,
                    category: item.category,
                    condition: item.condition,
                    storageLocation: item.storageLocation,
                    notes: item.notes,
                    internalNotes: item.internalNotes,
                    replacementValue: item.replacementValue,
                    replacementCurrency: item.replacementCurrency,
                    totalQuantity: item.totalQuantity,
                    photoIsPublic: item.photoIsPublic,
                  }}
                  categories={filterOptions.categories}
                  trackingModes={filterOptions.trackingModes}
                  conditions={filterOptions.conditions}
                  writableOffices={writableOffices}
                  canViewSensitive={capabilities.canViewSensitive}
                  includeTrackingFields={false}
                />
                {item.trackingMode === "pooled" ? (
                  <div>
                    <label
                      htmlFor="inv-edit-quantity"
                      className="text-foreground mb-1 block text-sm font-medium"
                    >
                      Total quantity
                    </label>
                    <Input
                      id="inv-edit-quantity"
                      name="total_quantity"
                      type="number"
                      min={Math.max(1, committedQuantity)}
                      defaultValue={String(item.totalQuantity)}
                    />
                    {committedQuantity > 0 ? (
                      <p className="text-muted-foreground mt-1 text-xs">
                        {committedQuantity} unit
                        {committedQuantity === 1 ? "" : "s"} committed to reservations;
                        quantity cannot drop below that.
                      </p>
                    ) : null}
                  </div>
                ) : null}
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    name="photo_is_public"
                    defaultChecked={item.photoIsPublic}
                  />
                  Photo approved for public display
                </label>
                <FormActionBar
                  status={
                    submitting ? "Saving…" : "Changes are recorded in the audit trail."
                  }
                >
                  <Button type="submit" disabled={submitting}>
                    Save changes
                  </Button>
                </FormActionBar>
              </form>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {capabilities.canManage ? (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 pt-5">
              <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
                <Upload className="text-muted-foreground size-4" aria-hidden />
                Item photo
              </h2>
              <p className="text-muted-foreground text-xs">
                {item.hasPhoto
                  ? "Upload a replacement image. Photos use protected storage unless marked public."
                  : "Add a reference photo for admins. Photos use protected storage unless marked public."}
              </p>
              <form
                method="post"
                action={routes.admin_inventory_photo(item.publicId)}
                encType="multipart/form-data"
                className="border-border grid gap-3 rounded-lg border p-4"
              >
                <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                <input type="hidden" name="expected_version" value={version} />
                <FormLabel htmlFor="inventory-photo">Photo file</FormLabel>
                <Input
                  id="inventory-photo"
                  name="photo"
                  type="file"
                  accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
                  required={!item.hasPhoto}
                />
                <Button
                  type="submit"
                  variant="secondary"
                  size="sm"
                  disabled={submitting}
                >
                  {item.hasPhoto ? "Replace photo" : "Upload photo"}
                </Button>
              </form>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4 pt-5">
            <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
              <PackageCheck className="text-muted-foreground size-4" aria-hidden />
              Availability preview
            </h2>
            <p className="text-muted-foreground text-xs">
              Physical state ({item.availabilityStateLabel}) is separate from booking
              availability for a date range.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                type="datetime-local"
                value={availStart ? availStart.slice(0, 16) : ""}
                onChange={(event) => setAvailStart(event.target.value)}
                aria-label="Range start"
              />
              <Input
                type="datetime-local"
                value={availEnd ? availEnd.slice(0, 16) : ""}
                onChange={(event) => setAvailEnd(event.target.value)}
                aria-label="Range end"
              />
            </div>
            <Button type="button" variant="secondary" onClick={previewAvailability}>
              Calculate availability
            </Button>
            {availabilityPreview ? (
              <p className="text-foreground text-sm">
                {availabilityPreview.availableQuantity} of{" "}
                {availabilityPreview.totalQuantity} available for the selected range
                {availabilityPreview.isReservableCatalogState
                  ? ""
                  : " (item is not in a reservable catalog state)"}
              </p>
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-3 pt-5">
            <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
              <CalendarClock className="text-muted-foreground size-4" aria-hidden />
              Reservations
            </h2>
            {reservations.length > 0 ? (
              <ul className="grid gap-2">
                {reservations.map((reservation) => (
                  <li
                    key={reservation.publicId}
                    className="border-border rounded-lg border p-3 text-sm"
                  >
                    <span className="text-foreground block font-medium">
                      {reservation.summary}
                    </span>
                    <span className="text-muted-foreground block text-xs">
                      {reservation.startsAt} → {reservation.endsAt}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">
                No current or upcoming reservations in view.
                {committedQuantity > 0
                  ? ` ${committedQuantity} unit${committedQuantity === 1 ? "" : "s"} committed.`
                  : " Reservation rows will appear here once the booking workflow ships."}
              </p>
            )}
          </SurfaceCardContent>
        </SurfaceCard>

        {capabilities.canManage && !item.retiredAt ? (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-3 pt-5">
              <h2 className="text-foreground text-sm font-semibold">Lifecycle</h2>
              <FormField>
                <FormLabel htmlFor="transition-reason">Reason (optional)</FormLabel>
                <Textarea
                  id="transition-reason"
                  value={transitionReason}
                  onChange={(event) => setTransitionReason(event.target.value)}
                  rows={2}
                  maxLength={500}
                />
              </FormField>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={submitting}
                  onClick={() => setConfirmAction("mark_temporarily_unavailable")}
                >
                  Mark unavailable
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={submitting}
                  onClick={() => setConfirmAction("mark_damaged")}
                >
                  Mark damaged
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={submitting}
                  onClick={() => setConfirmAction("mark_lost")}
                >
                  Mark lost
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={submitting}
                  onClick={() => setConfirmAction("restore")}
                >
                  Restore available
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={submitting}
                  onClick={() => setConfirmAction("retire")}
                >
                  Retire
                </Button>
              </div>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {capabilities.canManage &&
        !item.retiredAt &&
        transferDestinations.length > 0 ? (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 pt-5">
              <h2 className="text-foreground text-sm font-semibold">Transfer office</h2>
              <p className="text-muted-foreground text-xs">
                Move ownership to another office in your scope. Reservation history
                stays on this item.
              </p>
              <form
                ref={transferFormRef}
                id="inventory-transfer-form"
                method="post"
                action={routes.admin_inventory_transfer(item.publicId)}
                className="grid gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!transferOfficeId) return;
                  setConfirmTransfer(true);
                }}
              >
                <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                <input type="hidden" name="expected_version" value={version} />
                <FormField>
                  <FormLabel htmlFor="transfer-to-office" required>
                    Destination office
                  </FormLabel>
                  <NativeSelect
                    id="transfer-to-office"
                    name="to_office"
                    required
                    value={transferOfficeId}
                    onChange={(event) => setTransferOfficeId(event.target.value)}
                  >
                    <option value="">Select destination</option>
                    {transferDestinations.map((office) => (
                      <option key={office.id} value={String(office.id)}>
                        {office.label}
                      </option>
                    ))}
                  </NativeSelect>
                </FormField>
                <FormField>
                  <FormLabel htmlFor="transfer-reason">Reason (optional)</FormLabel>
                  <Textarea
                    id="transfer-reason"
                    name="reason"
                    value={transferReason}
                    onChange={(event) => setTransferReason(event.target.value)}
                    rows={2}
                    maxLength={500}
                  />
                </FormField>
                <Button type="submit" variant="secondary" disabled={submitting}>
                  Review transfer
                </Button>
              </form>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {transfers.length > 0 ? (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-3 pt-5">
              <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
                <History className="text-muted-foreground size-4" aria-hidden />
                Transfer history
              </h2>
              <ul className="grid gap-2">
                {transfers.map((transfer) => (
                  <li
                    key={transfer.publicId}
                    className="border-border rounded-lg border p-3 text-sm"
                  >
                    {transfer.fromOffice} → {transfer.toOffice}
                    {transfer.reason ? (
                      <span className="text-muted-foreground block text-xs">
                        {transfer.reason}
                      </span>
                    ) : null}
                    <span className="text-muted-foreground block text-xs">
                      {transfer.performedAt}
                    </span>
                  </li>
                ))}
              </ul>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
      </div>

      {confirmCopy && confirmAction ? (
        <AccessChangeDialog
          open
          onOpenChange={(open) => {
            if (!open) setConfirmAction(null);
          }}
          title={confirmCopy.title}
          description={confirmCopy.description}
          changes={lifecycleChanges}
          confirmLabel={confirmCopy.confirmLabel}
          submitting={submitting}
          onConfirm={() => {
            const action = confirmAction;
            setConfirmAction(null);
            postTransition(action);
          }}
        />
      ) : null}

      {confirmTransfer && selectedTransferOffice ? (
        <AccessChangeDialog
          open
          onOpenChange={setConfirmTransfer}
          title="Transfer this item?"
          description="The item keeps its history but moves to a new owning office."
          changes={transferChanges}
          confirmLabel="Transfer item"
          submitting={submitting}
          onConfirm={() => {
            setConfirmTransfer(false);
            submitTransfer(true);
          }}
        />
      ) : null}
    </>
  );
}

export default function InventoryItemWorkspace() {
  return (
    <PermissionRequired permission={VIEW}>
      <Workspace />
    </PermissionRequired>
  );
}

InventoryItemWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Inventory item",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Inventory", href: routes.admin_inventory() },
          { label: "Item" },
        ],
      },
      variant: "wide",
    },
  ] as const;
