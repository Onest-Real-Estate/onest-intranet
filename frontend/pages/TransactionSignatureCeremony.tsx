import { Head, router, usePage } from "@inertiajs/react";
import { AlertTriangle, Check, Loader2, PenLine, ShieldCheck } from "lucide-react";
import { useId, useState } from "react";

import { AuthLayout } from "@/components/AuthLayout";
import { ContractSignaturePad } from "@/components/ContractSignaturePad";
import {
  Callout,
  EmptyState,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type {
  SignatureCeremonyDocument,
  SignatureCeremonyEndpoints,
  SignaturePackageFieldRow,
  TransactionSignatureCeremonyPageProps,
} from "@/types";

/** Types the signer fills with characters; the rest come from the pad. */
const TYPED_FIELD_TYPES = new Set(["text", "date"]);

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

/**
 * A preview GET is the one request an external signer makes that has to prove
 * who they are, and their proof is the link they arrived on rather than a
 * session cookie.
 */
function previewUrl(url: string, endpoints: SignatureCeremonyEndpoints): string {
  if (!endpoints.previewToken || !endpoints.previewTokenParam) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}${endpoints.previewTokenParam}=${encodeURIComponent(
    endpoints.previewToken,
  )}`;
}

function typedFields(documents: SignatureCeremonyDocument[]) {
  return documents.flatMap((document) =>
    document.fields.filter((field) => TYPED_FIELD_TYPES.has(field.type)),
  );
}

function Step({
  index,
  title,
  description,
  state,
  children,
}: {
  index: number;
  title: string;
  description?: string;
  state: "done" | "current" | "upcoming";
  children?: React.ReactNode;
}) {
  return (
    <SurfaceCard className={cn(state === "upcoming" && "opacity-60")}>
      <SurfaceCardContent className="grid gap-4">
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold tabular-nums",
              state === "done"
                ? "bg-chip-success text-success"
                : state === "current"
                  ? "bg-brand-gold text-brand-on-gold"
                  : "bg-muted text-muted-foreground",
            )}
          >
            {state === "done" ? (
              <>
                <Check className="size-4" aria-hidden />
                <span className="sr-only">Step {index} complete</span>
              </>
            ) : (
              <>
                <span aria-hidden>{index}</span>
                <span className="sr-only">Step {index}</span>
              </>
            )}
          </span>
          <div className="grid gap-1">
            <h2 className="text-base leading-6 font-semibold">{title}</h2>
            {description ? (
              <p className="text-muted-foreground max-w-measure text-sm leading-5">
                {description}
              </p>
            ) : null}
          </div>
        </div>
        {children ? <div className="grid gap-4 sm:pl-10">{children}</div> : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

function DocumentReview({
  document,
  endpoints,
  values,
  onValueChange,
}: {
  document: SignatureCeremonyDocument;
  endpoints: SignatureCeremonyEndpoints;
  values: Record<string, string>;
  onValueChange: (name: string, value: string) => void;
}) {
  const typed = document.fields.filter((field) => TYPED_FIELD_TYPES.has(field.type));

  return (
    <div className="grid gap-3">
      <div className="border-border overflow-hidden rounded-lg border">
        <iframe
          title={`${document.displayName} for signing`}
          src={previewUrl(document.previewUrl, endpoints)}
          className="bg-card block h-[min(60vh,32rem)] w-full"
        />
      </div>

      {document.fields.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          Nothing on this document is addressed to you — read it, then sign below.
        </p>
      ) : (
        <div className="grid gap-3">
          <h3 className="text-xs font-semibold tracking-[0.06em] uppercase">
            Fields you are completing on {document.displayName}
          </h3>
          <ul className="text-muted-foreground grid gap-1 text-sm">
            {document.fields
              .filter((field) => !TYPED_FIELD_TYPES.has(field.type))
              .map((field) => (
                <li key={field.publicId ?? field.name}>
                  {field.typeLabel ?? field.type} · page {field.page}
                </li>
              ))}
          </ul>
          {typed.map((field) => (
            <TypedField
              key={field.publicId ?? field.name}
              field={field}
              value={values[field.name] ?? ""}
              onChange={(value) => onValueChange(field.name, value)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TypedField({
  field,
  value,
  onChange,
}: {
  field: SignaturePackageFieldRow;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="grid max-w-sm gap-1.5">
      <Label htmlFor={id}>
        {field.name}
        {field.required ? "" : " (optional)"}
      </Label>
      <Input
        id={id}
        type={field.type === "date" ? "date" : "text"}
        required={field.required}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className="text-muted-foreground text-xs">
        {field.typeLabel ?? field.type} · page {field.page}
      </p>
    </div>
  );
}

export default function TransactionSignatureCeremony() {
  const {
    canSign,
    signingReady,
    recovery,
    disclosure,
    package: pkg,
    signer,
    documents,
    ceremony,
    errors,
    endpoints,
  } = usePage<TransactionSignatureCeremonyPageProps>().props;

  const ackId = useId();
  const dateId = useId();
  const declineId = useId();

  const [acknowledged, setAcknowledged] = useState(false);
  const [starting, setStarting] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [signatureDataUrl, setSignatureDataUrl] = useState("");
  const [signedDate, setSignedDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [values, setValues] = useState<Record<string, string>>({});
  const [declineReason, setDeclineReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const formErrors = errors?.form ?? [];
  const consentError = errors?.fields?.consentAccepted?.[0];
  const showPad = Boolean(ceremony?.intentPublicId);
  const missingRequired = typedFields(documents).some(
    (field) => field.required && !(values[field.name] ?? "").trim(),
  );

  function startCeremony() {
    if (!acknowledged || starting || !canSign) return;
    setStarting(true);
    setActionError(null);
    router.post(
      endpoints.startUrl,
      {
        consentAccepted: true,
        disclosureVersion: disclosure.version,
        expectedVersion: pkg.expectedVersion,
        packagePublicId: pkg.publicId,
      },
      { preserveScroll: true, onFinish: () => setStarting(false) },
    );
  }

  async function postJson(url: string, body: Record<string, unknown>) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken(),
      },
      body: JSON.stringify(body),
    });
    const data = (await response.json()) as {
      ok?: boolean;
      validation?: { fields?: Record<string, string[]>; form?: string[] };
    };
    if (!response.ok || !data.ok) {
      throw new Error(
        data.validation?.form?.[0] ||
          Object.values(data.validation?.fields ?? {})[0]?.[0] ||
          "That did not go through. Try again.",
      );
    }
    return data;
  }

  async function submitSignature() {
    if (!ceremony || completing) return;
    setCompleting(true);
    setActionError(null);
    try {
      await postJson(endpoints.completeUrl, {
        intentPublicId: ceremony.intentPublicId,
        signatureDataUrl,
        signedDate,
        textValues: values,
      });
      // The server decides what a signed package looks like to this signer —
      // a magic-link holder has nowhere else to be sent.
      router.reload();
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : "Could not complete signing. Check your connection and retry.",
      );
    } finally {
      setCompleting(false);
    }
  }

  async function submitDecline() {
    if (declining) return;
    setDeclining(true);
    setActionError(null);
    try {
      await postJson(endpoints.declineUrl, { reason: declineReason });
      router.reload();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Could not record your decline.",
      );
    } finally {
      setDeclining(false);
    }
  }

  return (
    <>
      <Head title={pkg.title || "Sign documents"} />
      <div className="mx-auto grid w-full max-w-3xl gap-8 py-6">
        <PageHeader
          title={pkg.title || "Sign documents"}
          description="Two steps: accept the electronic signature disclosure, then apply your signature to the documents in this package."
        />

        <SurfaceCard>
          <PanelHeader
            title="What you are signing"
            description="Confirm these are correct before you continue."
            divided
          />
          <SurfaceCardContent>
            <dl className="grid gap-4 sm:grid-cols-3">
              <ReadOnlyValue label="Signing as">{signer.displayName}</ReadOnlyValue>
              <ReadOnlyValue label="Role">{signer.roleLabel}</ReadOnlyValue>
              <ReadOnlyValue label="Status">{signer.statusLabel}</ReadOnlyValue>
            </dl>
          </SurfaceCardContent>
        </SurfaceCard>

        {recovery ? (
          <SurfaceCard>
            <EmptyState
              icon={AlertTriangle}
              title="Signing unavailable"
              description={recovery.message}
            />
          </SurfaceCard>
        ) : (
          <div className="grid gap-4">
            <Step
              index={1}
              title={disclosure.title}
              state={showPad ? "done" : "current"}
            >
              {showPad ? null : (
                <>
                  <p className="text-muted-foreground max-w-measure text-sm leading-5 whitespace-pre-wrap">
                    {disclosure.body}
                  </p>
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id={ackId}
                      checked={acknowledged}
                      aria-describedby={consentError ? `${ackId}-error` : undefined}
                      aria-invalid={consentError ? true : undefined}
                      onCheckedChange={(value) => setAcknowledged(value === true)}
                    />
                    <Label htmlFor={ackId} className="text-sm leading-snug">
                      {disclosure.acknowledgementLabel}
                    </Label>
                  </div>
                  {consentError ? (
                    <p
                      id={`${ackId}-error`}
                      className="text-destructive text-sm"
                      role="alert"
                    >
                      {consentError}
                    </p>
                  ) : null}
                  {formErrors.length > 0 ? (
                    <Callout tone="destructive" title="Signing could not start">
                      <ul className="grid gap-1" role="alert">
                        {formErrors.map((message) => (
                          <li key={message}>{message}</li>
                        ))}
                      </ul>
                    </Callout>
                  ) : null}
                  <div>
                    <Button
                      type="button"
                      disabled={!acknowledged || starting || !canSign || !signingReady}
                      onClick={startCeremony}
                    >
                      {starting ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden />
                      ) : (
                        <PenLine className="size-3.5" aria-hidden />
                      )}
                      Continue to electronic signature
                    </Button>
                  </div>
                  {!signingReady ? (
                    <Callout tone="warning" title="Signing is temporarily unavailable">
                      The documents are still readable above. Try signing again later.
                    </Callout>
                  ) : null}
                </>
              )}
            </Step>

            <Step
              index={2}
              title="Review and sign"
              description="Read each document, complete the fields addressed to you, then draw or type your signature."
              state={showPad ? "current" : "upcoming"}
            >
              {showPad ? (
                <>
                  {documents.map((document) => (
                    <DocumentReview
                      key={document.publicId}
                      document={document}
                      endpoints={endpoints}
                      values={values}
                      onValueChange={(name, value) =>
                        setValues((current) => ({ ...current, [name]: value }))
                      }
                    />
                  ))}

                  <ContractSignaturePad onChange={setSignatureDataUrl} />

                  <div className="grid max-w-xs gap-2">
                    <Label htmlFor={dateId}>Signature date</Label>
                    <Input
                      id={dateId}
                      type="date"
                      value={signedDate}
                      onChange={(event) => setSignedDate(event.target.value)}
                    />
                  </div>

                  {actionError ? (
                    <Callout tone="destructive" title="Signing did not complete">
                      <span role="alert">{actionError}</span>
                    </Callout>
                  ) : null}

                  <div className="border-border/60 flex flex-wrap items-center justify-between gap-4 border-t pt-4">
                    <p
                      className="text-muted-foreground flex items-center gap-2 text-sm"
                      aria-live="polite"
                    >
                      <ShieldCheck className="size-4 shrink-0" aria-hidden />
                      {!signatureDataUrl
                        ? "Add your signature to finish."
                        : missingRequired
                          ? "Complete every required field above to finish."
                          : "Success is confirmed only once oNEST stores your signature and certificate."}
                    </p>
                    <Button
                      type="button"
                      disabled={
                        !signatureDataUrl ||
                        !signedDate ||
                        missingRequired ||
                        completing
                      }
                      onClick={() => void submitSignature()}
                    >
                      {completing ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden />
                      ) : (
                        <PenLine className="size-3.5" aria-hidden />
                      )}
                      Apply signature and finish
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground text-sm">
                  Available once you accept the disclosure above.
                </p>
              )}
            </Step>

            <SurfaceCard>
              <SurfaceCardContent className="grid gap-3">
                <h2 className="text-base font-semibold">Decline to sign</h2>
                <p className="text-muted-foreground max-w-measure text-sm leading-5">
                  Declining ends this package for everyone on it. The brokerage is
                  notified and has to build a new one.
                </p>
                <div className="grid max-w-md gap-1.5">
                  <Label htmlFor={declineId}>Reason (optional)</Label>
                  <Textarea
                    id={declineId}
                    rows={2}
                    value={declineReason}
                    onChange={(event) => setDeclineReason(event.target.value)}
                  />
                </div>
                <div>
                  <Button
                    type="button"
                    variant="outline"
                    className="text-destructive hover:bg-chip-destructive hover:text-destructive"
                    disabled={declining || !canSign}
                    onClick={() => void submitDecline()}
                  >
                    {declining ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                    ) : null}
                    Decline to sign
                  </Button>
                </div>
              </SurfaceCardContent>
            </SurfaceCard>
          </div>
        )}
      </div>
    </>
  );
}

/**
 * Hub chrome for a signed-in signer, bare branded chrome for a magic link.
 *
 * An external buyer arriving from an email has no Hub account, so the sidebar,
 * search, and notification badge would be furniture they cannot use — and half
 * of it would 403 on click.
 */
TransactionSignatureCeremony.layout = (
  page: React.ReactElement<TransactionSignatureCeremonyPageProps>,
) =>
  page.props.endpoints?.mode === "magicLink" ? (
    <AuthLayout>{page}</AuthLayout>
  ) : (
    <HubLayout>{page}</HubLayout>
  );
