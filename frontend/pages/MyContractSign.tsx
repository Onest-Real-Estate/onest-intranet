import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Loader2,
  PenLine,
  ShieldCheck,
} from "lucide-react";
import { useId, useState } from "react";
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
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { MyContractSignPageProps } from "@/types";

function fieldError(
  errors: MyContractSignPageProps["errors"],
  key: string,
): string | undefined {
  return errors.fields[key]?.[0];
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )XSRF-TOKEN=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

/**
 * A numbered step in the ceremony.
 *
 * Signing is two decisions taken in order — accept the disclosure, then apply
 * the signature — and the page previously showed them as three equal cards
 * with no indication that the second one was waiting on the first. The number
 * carries the sequence; the completed state is a check, not a colour alone.
 */
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

export default function MyContractSign() {
  const { canSign, signingReady, recovery, disclosure, contract, ceremony, errors } =
    usePage<MyContractSignPageProps>().props;

  const ackId = useId();
  const dateId = useId();
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [signatureDataUrl, setSignatureDataUrl] = useState("");
  const [signedDate, setSignedDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [completeError, setCompleteError] = useState<string | null>(null);
  const formErrors = errors.form ?? [];
  const showPad = Boolean(ceremony?.intentPublicId);
  const consentError = fieldError(errors, "consentAccepted");

  function startCeremony() {
    if (!contract || !acknowledged || submitting || !canSign) return;
    setSubmitting(true);
    setCompleteError(null);
    router.post(
      routes.my_contract_sign(),
      {
        consentAccepted: true,
        disclosureVersion: disclosure.version,
        expectedVersion: contract.expectedVersion,
        contractPublicId: contract.publicId,
      },
      {
        preserveScroll: true,
        onFinish: () => setSubmitting(false),
      },
    );
  }

  async function submitSignature() {
    if (!ceremony || completing) return;
    setCompleting(true);
    setCompleteError(null);
    try {
      const response = await fetch(routes.my_contract_sign_complete(), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-XSRF-TOKEN": csrfToken(),
        },
        body: JSON.stringify({
          intentPublicId: ceremony.intentPublicId,
          signatureDataUrl,
          signedDate,
        }),
      });
      const data = (await response.json()) as {
        ok?: boolean;
        signed?: boolean;
        error?: string;
        errors?: { fields?: Record<string, string[]>; form?: string[] };
      };
      if (!response.ok || !data.ok) {
        const message =
          data.error ||
          data.errors?.form?.[0] ||
          data.errors?.fields?.signature?.[0] ||
          data.errors?.fields?.signedDate?.[0] ||
          "Could not complete signing. Try again.";
        setCompleteError(message);
        return;
      }
      router.visit(routes.my_contract(), { replace: true });
    } catch {
      setCompleteError("Could not complete signing. Check your connection and retry.");
    } finally {
      setCompleting(false);
    }
  }

  return (
    <>
      <Head title="Sign contract" />
      <div className="grid max-w-3xl gap-8">
        <PageHeader
          title="Sign your agent contract"
          description="Two steps: accept the electronic signature disclosure, then apply your signature to the agreement."
          actions={
            <Button variant="outline" asChild>
              <Link href={routes.my_contract()}>
                <ArrowLeft className="size-3.5" aria-hidden />
                My contract
              </Link>
            </Button>
          }
        />

        {recovery ? (
          <SurfaceCard>
            <EmptyState
              icon={AlertTriangle}
              title="Signing unavailable"
              description={recovery.message}
              actions={
                <Button variant="outline" asChild>
                  <Link href={routes.my_contract()}>Open My contract</Link>
                </Button>
              }
            />
          </SurfaceCard>
        ) : (
          <div className="grid gap-4">
            {contract ? (
              <SurfaceCard>
                <PanelHeader
                  title="What you are signing"
                  description="Confirm these are correct before you continue."
                  divided
                />
                <SurfaceCardContent>
                  <dl className="grid gap-4 sm:grid-cols-3">
                    <ReadOnlyValue label="Party">
                      {contract.partyDisplayName}
                    </ReadOnlyValue>
                    <ReadOnlyValue label="Signing as">
                      {contract.signerEmail}
                    </ReadOnlyValue>
                    <ReadOnlyValue label="Status">{contract.statusLabel}</ReadOnlyValue>
                  </dl>
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}

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
                  <div className="grid gap-3">
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
                        disabled={
                          !acknowledged || submitting || !canSign || !signingReady
                        }
                        onClick={startCeremony}
                      >
                        {submitting ? (
                          <Loader2 className="size-3.5 animate-spin" aria-hidden />
                        ) : (
                          <PenLine className="size-3.5" aria-hidden />
                        )}
                        Continue to electronic signature
                      </Button>
                    </div>
                    {!signingReady ? (
                      <Callout
                        tone="warning"
                        title="Signing is temporarily unavailable"
                      >
                        You can still review and download the agreement from My
                        contract.
                      </Callout>
                    ) : null}
                  </div>
                </>
              )}
            </Step>

            <Step
              index={2}
              title="Review and sign"
              description="Read the issued PDF, then draw or type your signature and confirm the date."
              state={showPad ? "current" : "upcoming"}
            >
              {showPad && ceremony ? (
                <>
                  <div className="border-border overflow-hidden rounded-lg border">
                    <iframe
                      title="Contract PDF for signing"
                      src={ceremony.reviewPdfUrl}
                      className="bg-card block h-[min(60vh,32rem)] w-full"
                    />
                  </div>

                  {ceremony.agentFields.length > 0 ? (
                    <div className="grid gap-2">
                      <h3 className="text-xs font-semibold tracking-[0.06em] uppercase">
                        Fields you are completing
                      </h3>
                      <ul className="text-muted-foreground grid gap-1 text-sm">
                        {ceremony.agentFields.map((field) => (
                          <li key={field.id}>
                            {field.name} · page {field.page}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

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

                  {completeError ? (
                    <Callout tone="destructive" title="Signing did not complete">
                      <span role="alert">{completeError}</span>
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
                        : "Success is confirmed only once oNEST stores your signature and certificate."}
                    </p>
                    <Button
                      type="button"
                      disabled={!signatureDataUrl || !signedDate || completing}
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
          </div>
        )}
      </div>
    </>
  );
}

MyContractSign.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
