import { Head, Link, router, usePage } from "@inertiajs/react";
import { AlertTriangle, ArrowLeft, Loader2, PenLine } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { DocusealFormEmbed } from "@/components/DocusealFormEmbed";
import {
  EmptyState,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { routes } from "@/lib/routes";
import type { MyContractSignPageProps } from "@/types";

const POLL_MS = 1500;
const POLL_MAX_MS = 120_000;

function fieldError(
  errors: MyContractSignPageProps["errors"],
  key: string,
): string | undefined {
  return errors.fields[key]?.[0];
}

export default function MyContractSign() {
  const { canSign, signingReady, recovery, disclosure, contract, ceremony, errors } =
    usePage<MyContractSignPageProps>().props;

  const ackId = useId();
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [waitingForRecord, setWaitingForRecord] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);
  const startedAt = useRef<number | null>(null);
  const formErrors = errors.form ?? [];

  useEffect(() => {
    if (!waitingForRecord || !ceremony) return;

    let cancelled = false;
    startedAt.current = Date.now();

    const tick = async () => {
      if (cancelled) return;
      if (startedAt.current !== null && Date.now() - startedAt.current > POLL_MAX_MS) {
        setPollError(
          "Signature confirmation is taking longer than expected. Open My Contract to check status.",
        );
        setWaitingForRecord(false);
        return;
      }
      try {
        const url = `${routes.my_contract_sign_status()}?intent=${encodeURIComponent(
          ceremony.intentPublicId,
        )}&contract=${encodeURIComponent(contract?.publicId ?? "")}`;
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error("status_failed");
        }
        const data = (await response.json()) as { signed?: boolean };
        if (data.signed) {
          router.visit(routes.my_contract(), { replace: true });
          return;
        }
      } catch {
        // Keep polling; transient network blips should not fail the ceremony.
      }
      if (!cancelled) {
        window.setTimeout(tick, POLL_MS);
      }
    };

    void tick();
    return () => {
      cancelled = true;
    };
  }, [waitingForRecord, ceremony, contract?.publicId]);

  function startCeremony() {
    if (!contract || !acknowledged || submitting || !canSign) return;
    setSubmitting(true);
    setPollError(null);
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

  const showEmbed = Boolean(ceremony?.embedSrc) && !waitingForRecord;

  return (
    <>
      <Head title="Sign contract" />
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link href={routes.my_contract()}>
              <ArrowLeft className="size-3.5" aria-hidden />
              My contract
            </Link>
          </Button>
        </div>

        <PageHeader
          title="Sign contract"
          description="Review the disclosure, acknowledge it, then complete your electronic signature on the issued agreement."
        />

        {recovery ? (
          <EmptyState
            icon={AlertTriangle}
            title="Signing unavailable"
            description={recovery.message}
            actions={
              <Button asChild>
                <Link href={routes.my_contract()}>Return to My contract</Link>
              </Button>
            }
          />
        ) : null}

        {!recovery && contract ? (
          <>
            <SurfaceCard>
              <PanelHeader title="Agreement identity" />
              <SurfaceCardContent className="space-y-2 text-sm">
                <p>
                  <span className="text-muted-foreground">Signer: </span>
                  <span className="font-medium">{contract.partyDisplayName}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    ({contract.signerEmail})
                  </span>
                </p>
                <p>
                  <span className="text-muted-foreground">Version: </span>
                  <span className="font-medium">v{contract.versionNumber}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    · {contract.statusLabel} · effective {contract.effectiveOn}
                  </span>
                </p>
                <p className="text-muted-foreground break-all text-xs">
                  Contract id {contract.publicId}
                </p>
                <p className="text-muted-foreground break-all text-xs">
                  PDF checksum {contract.artifactChecksum}
                </p>
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader title={disclosure.title} />
              <SurfaceCardContent className="space-y-4">
                <div className="text-foreground whitespace-pre-wrap text-sm leading-relaxed">
                  {disclosure.body}
                </div>
                <p className="text-muted-foreground text-xs">
                  Disclosure version {disclosure.version}
                </p>
                {!ceremony ? (
                  <div className="flex flex-col gap-4">
                    <div className="flex items-start gap-3">
                      <Checkbox
                        id={ackId}
                        checked={acknowledged}
                        onCheckedChange={(value) => setAcknowledged(value === true)}
                        disabled={submitting || !canSign || !signingReady}
                        aria-describedby={`${ackId}-hint`}
                      />
                      <Label
                        htmlFor={ackId}
                        className="text-sm leading-snug font-normal"
                      >
                        {disclosure.acknowledgementLabel}
                      </Label>
                    </div>
                    <p id={`${ackId}-hint`} className="text-muted-foreground text-xs">
                      Checking this box records informed consent. Your electronic
                      signature is completed in the DocuSeal form that follows—not by
                      this checkbox alone.
                    </p>
                    {fieldError(errors, "consentAccepted") ? (
                      <p className="text-destructive text-sm" role="alert">
                        {fieldError(errors, "consentAccepted")}
                      </p>
                    ) : null}
                    {formErrors.length > 0 ? (
                      <ul className="text-destructive space-y-1 text-sm" role="alert">
                        {formErrors.map((message) => (
                          <li key={message}>{message}</li>
                        ))}
                      </ul>
                    ) : null}
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
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>

            {showEmbed && ceremony ? (
              <SurfaceCard>
                <PanelHeader title="Electronic signature" />
                <SurfaceCardContent className="space-y-3">
                  <p className="text-muted-foreground text-sm">
                    Complete the signature and date fields on the PDF. Success appears
                    only after oNEST stores your signature record.
                  </p>
                  {ceremony.embedsAvailable ? (
                    <div className="min-h-[32rem] overflow-hidden rounded-md border">
                      <DocusealFormEmbed
                        src={ceremony.embedSrc}
                        host={ceremony.docusealHost}
                        protocol={
                          ceremony.docusealProtocol === "http" ? "http" : "https"
                        }
                        email={contract.signerEmail}
                        name={contract.partyDisplayName}
                        allowToResubmit={false}
                        onComplete={() => setWaitingForRecord(true)}
                      />
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-muted-foreground text-sm">
                        Community DocuSeal cannot embed the signing form in the hub.
                        Open the DocuSeal signing page, complete it, then return here
                        while we confirm the signature record.
                      </p>
                      <Button
                        type="button"
                        onClick={() => {
                          window.open(
                            ceremony.embedSrc,
                            "_blank",
                            "noopener,noreferrer",
                          );
                          setWaitingForRecord(true);
                        }}
                      >
                        Open DocuSeal signing form
                      </Button>
                    </div>
                  )}
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}

            {waitingForRecord ? (
              <SurfaceCard>
                <SurfaceCardContent className="flex flex-col items-start gap-3 py-8">
                  <Loader2
                    className="text-muted-foreground size-6 animate-spin"
                    aria-hidden
                  />
                  <p className="font-medium">Confirming your signature…</p>
                  <p className="text-muted-foreground text-sm">
                    Waiting for the durable signature record before showing success.
                  </p>
                  {pollError ? (
                    <p className="text-destructive text-sm" role="alert">
                      {pollError}
                    </p>
                  ) : null}
                  <Button variant="outline" asChild>
                    <Link href={routes.my_contract()}>Open My contract</Link>
                  </Button>
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}
          </>
        ) : null}
      </div>
    </>
  );
}

MyContractSign.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
