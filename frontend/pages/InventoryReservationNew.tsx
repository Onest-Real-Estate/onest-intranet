import { Form, Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, Package } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Callout,
  EmptyState,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useValidationToasts } from "@/hooks/use-validation-toasts";
import { routes } from "@/lib/routes";
import type { InventoryReservationNewPageProps } from "@/types";

/**
 * Agent reservation workflow: draft → server summary → confirm POST.
 *
 * Review reloads from the server so availability/terms are authoritative.
 * Submit carries a one-shot submission key so double-clicks do not duplicate.
 */
export default function InventoryReservationNew() {
  const { item, draft, review, summary, links, errors, office } =
    usePage<InventoryReservationNewPageProps>().props;
  useValidationToasts(errors, { title: "Could not reserve this item" });

  const [pickup, setPickup] = useState(draft.pickup);
  const [returnDate, setReturnDate] = useState(draft.return);
  const [quantity, setQuantity] = useState(draft.quantity || "1");
  const [purpose, setPurpose] = useState(draft.purpose);

  const submissionKey = useMemo(
    () =>
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    [],
  );

  const fieldErrors = errors?.fields ?? {};
  const formErrors = errors?.form ?? [];
  const canConfirm = Boolean(review && summary?.isAvailable);

  function goReview() {
    if (!item) return;
    const params = new URLSearchParams({
      item: item.publicId,
      pickup,
      return: returnDate,
      quantity: String(Math.max(1, Number(quantity) || 1)),
      purpose,
      review: "1",
    });
    router.get(
      `${routes.inventory_reservation_new()}?${params.toString()}`,
      {},
      { preserveScroll: true },
    );
  }

  function goEdit() {
    if (!item) return;
    const params = new URLSearchParams({
      item: item.publicId,
      pickup,
      return: returnDate,
      quantity: String(Math.max(1, Number(quantity) || 1)),
      purpose,
    });
    router.get(
      `${routes.inventory_reservation_new()}?${params.toString()}`,
      {},
      { preserveScroll: true },
    );
  }

  return (
    <div className="grid gap-8">
      <Head title={review ? "Review reservation" : "Reserve inventory"} />
      <div>
        <Button type="button" variant="ghost" size="sm" asChild className="mb-2">
          <Link href={item?.detailHref ?? links.inventoryHref}>
            <ArrowLeft className="size-4" aria-hidden />
            Back
          </Link>
        </Button>
        <PageHeader
          title={review ? "Review reservation" : "Reserve inventory"}
          description={
            review
              ? "Confirm availability and office terms before submitting."
              : "Choose dates, quantity, and purpose. Availability is checked on the server."
          }
          meta={
            office ? (
              <span className="text-muted-foreground text-sm">{office.name}</span>
            ) : undefined
          }
        />
      </div>

      {!item ? (
        <SurfaceCard>
          <EmptyState
            icon={Package}
            title="Choose an inventory item"
            description="Open an item from Office inventory, then start a reservation from there."
            actions={
              <Button asChild>
                <Link href={links.inventoryHref}>Browse office inventory</Link>
              </Button>
            }
          />
        </SurfaceCard>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
          <SurfaceCard>
            <PanelHeader
              title={review ? "Reservation summary" : item.name}
              headingLevel="h2"
              divided
            />
            <SurfaceCardContent className="grid gap-4">
              {formErrors.length ? (
                <ul className="text-destructive grid gap-1 text-sm" role="alert">
                  {formErrors.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              ) : null}

              {review && summary ? (
                <div className="grid gap-4 text-sm">
                  <dl className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <dt className="text-muted-foreground">Item</dt>
                      <dd className="text-foreground font-medium">
                        {summary.item.name}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Office</dt>
                      <dd className="text-foreground">{summary.office.name}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Pickup</dt>
                      <dd className="text-foreground">{summary.pickup}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Return</dt>
                      <dd className="text-foreground">{summary.return}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Quantity</dt>
                      <dd className="text-foreground">{summary.quantity}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Status if submitted</dt>
                      <dd className="text-foreground">{summary.statusLabel}</dd>
                    </div>
                  </dl>
                  {summary.purpose ? (
                    <div>
                      <p className="text-muted-foreground">Purpose</p>
                      <p className="text-foreground">{summary.purpose}</p>
                    </div>
                  ) : null}
                  <StatusBadge
                    status={{
                      label: summary.isAvailable
                        ? `${summary.availableQuantity} available`
                        : "Unavailable for these dates",
                      tone: summary.isAvailable ? "success" : "warning",
                    }}
                  />
                  <Callout title="Terms">
                    <p>{summary.terms.approvalLabel}</p>
                    <p className="mt-1">{summary.terms.cancelPolicyLabel}</p>
                  </Callout>
                  {(summary.instructions.storageLocation ||
                    summary.instructions.notes) && (
                    <div className="grid gap-2">
                      <p className="text-foreground font-medium">
                        Pickup / return instructions
                      </p>
                      {summary.instructions.storageLocation ? (
                        <p className="text-muted-foreground">
                          {summary.instructions.storageLocation}
                        </p>
                      ) : null}
                      {summary.instructions.notes ? (
                        <p className="text-foreground whitespace-pre-line">
                          {summary.instructions.notes}
                        </p>
                      ) : null}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-3">
                    <Button type="button" variant="outline" onClick={goEdit}>
                      Edit details
                    </Button>
                    <Form
                      action={routes.inventory_reservation_create()}
                      method="post"
                      className="contents"
                      disableWhileProcessing
                    >
                      {({ processing }) => (
                        <>
                          <input
                            type="hidden"
                            name="item"
                            value={summary.item.publicId}
                          />
                          <input type="hidden" name="pickup" value={summary.pickup} />
                          <input type="hidden" name="return" value={summary.return} />
                          <input
                            type="hidden"
                            name="quantity"
                            value={String(summary.quantity)}
                          />
                          <input type="hidden" name="purpose" value={summary.purpose} />
                          <input
                            type="hidden"
                            name="submissionKey"
                            value={submissionKey}
                          />
                          <Button type="submit" disabled={!canConfirm || processing}>
                            {processing ? "Submitting…" : "Confirm reservation"}
                          </Button>
                        </>
                      )}
                    </Form>
                  </div>
                </div>
              ) : (
                <div className="grid gap-4">
                  <p className="text-muted-foreground text-sm">
                    Reserving{" "}
                    <span className="text-foreground font-medium">{item.name}</span>
                  </p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <FormField>
                      <FormLabel htmlFor="reservation-pickup">Pickup date</FormLabel>
                      <Input
                        id="reservation-pickup"
                        type="date"
                        value={pickup}
                        onChange={(event) => setPickup(event.target.value)}
                        aria-invalid={Boolean(fieldErrors.pickup)}
                      />
                      <FormFieldError message={fieldErrors.pickup?.[0]} />
                    </FormField>
                    <FormField>
                      <FormLabel htmlFor="reservation-return">Return date</FormLabel>
                      <Input
                        id="reservation-return"
                        type="date"
                        value={returnDate}
                        onChange={(event) => setReturnDate(event.target.value)}
                        aria-invalid={Boolean(fieldErrors.return)}
                      />
                      <FormFieldError message={fieldErrors.return?.[0]} />
                    </FormField>
                    <FormField>
                      <FormLabel htmlFor="reservation-quantity">Quantity</FormLabel>
                      <Input
                        id="reservation-quantity"
                        type="number"
                        min={1}
                        value={quantity}
                        onChange={(event) => setQuantity(event.target.value)}
                        aria-invalid={Boolean(fieldErrors.quantity)}
                      />
                      <FormFieldError message={fieldErrors.quantity?.[0]} />
                    </FormField>
                  </div>
                  <FormField>
                    <FormLabel htmlFor="reservation-purpose">
                      Business purpose
                    </FormLabel>
                    <Textarea
                      id="reservation-purpose"
                      value={purpose}
                      onChange={(event) => setPurpose(event.target.value)}
                      rows={3}
                      maxLength={240}
                    />
                    <FormDescription>
                      Optional — helps the office understand the request.
                    </FormDescription>
                    <FormFieldError message={fieldErrors.purpose?.[0]} />
                  </FormField>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      type="button"
                      onClick={goReview}
                      disabled={!pickup || !returnDate}
                    >
                      Review availability
                    </Button>
                    <Button type="button" variant="outline" asChild>
                      <Link href={links.inventoryHref}>Cancel</Link>
                    </Button>
                  </div>
                </div>
              )}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader title="Need help?" headingLevel="h2" divided />
            <SurfaceCardContent className="text-muted-foreground grid gap-2 text-sm">
              <p>
                Capacity is rechecked when you confirm. If someone else books the last
                unit first, you will be asked to pick another range.
              </p>
              <Button asChild variant="outline" size="sm">
                <Link href={links.myReservationsHref}>My reservations</Link>
              </Button>
            </SurfaceCardContent>
          </SurfaceCard>
        </div>
      )}
    </div>
  );
}

InventoryReservationNew.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Reserve inventory",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Office inventory", href: routes.office_inventory() },
          { label: "Reserve" },
        ],
      },
    },
  ] as const;
