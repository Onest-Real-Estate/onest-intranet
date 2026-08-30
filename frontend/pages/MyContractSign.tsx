import { Head, Link, router, usePage } from "@inertiajs/react";
import { AlertTriangle, ArrowLeft, Loader2, PenLine } from "lucide-react";
import { useId, useState } from "react";
import { ContractSignaturePad } from "@/components/ContractSignaturePad";
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

export default function MyContractSign() {
  const { canSign, signingReady, recovery, disclosure, contract, ceremony, errors } =
    usePage<MyContractSignPageProps>().props;

  const ackId = useId();
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
      <div className="grid gap-8">
        <PageHeader
          title="Sign your agent contract"
          description="Review the disclosure, then apply your electronic signature on the agreement PDF."
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
        ) : (
          <div className="grid gap-6">
            {contract ? (
              <SurfaceCard>
                <PanelHeader title="Agreement" />
                <SurfaceCardContent className="text-sm">
                  <p>
                    <span className="text-muted-foreground">Party: </span>
                    {contract.partyDisplayName}
                  </p>
                  <p>
                    <span className="text-muted-foreground">Signer: </span>
                    {contract.signerEmail}
                  </p>
                  <p>
                    <span className="text-muted-foreground">Status: </span>
                    {contract.statusLabel}
                  </p>
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}

            <SurfaceCard>
              <PanelHeader title={disclosure.title} />
              <SurfaceCardContent className="space-y-4">
                <p className="text-muted-foreground whitespace-pre-wrap text-sm">
                  {disclosure.body}
                </p>
                {!showPad ? (
                  <div className="grid gap-3">
                    <div className="flex items-start gap-3">
                      <Checkbox
                        id={ackId}
                        checked={acknowledged}
                        onCheckedChange={(value) => setAcknowledged(value === true)}
                      />
                      <Label htmlFor={ackId} className="text-sm leading-snug">
                        {disclosure.acknowledgementLabel}
                      </Label>
                    </div>
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

            {showPad && ceremony ? (
              <SurfaceCard>
                <PanelHeader title="Electronic signature" />
                <SurfaceCardContent className="space-y-4">
                  <p className="text-muted-foreground text-sm">
                    Review the issued PDF, then draw or type your signature and confirm
                    the signature date. Success appears only after oNEST stores your
                    signature record and certificate of completion.
                  </p>
                  <div className="overflow-hidden rounded-md border">
                    <iframe
                      title="Contract PDF for signing"
                      src={ceremony.reviewPdfUrl}
                      className="bg-card h-[28rem] w-full"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="signed-date">Signature date</Label>
                    <Input
                      id="signed-date"
                      type="date"
                      value={signedDate}
                      onChange={(event) => setSignedDate(event.target.value)}
                    />
                  </div>
                  <ContractSignaturePad onChange={setSignatureDataUrl} />
                  {ceremony.agentFields.length > 0 ? (
                    <ul className="text-muted-foreground grid gap-1 text-xs">
                      {ceremony.agentFields.map((field) => (
                        <li key={field.id}>
                          Page {field.page}: {field.name} ({field.type})
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {completeError ? (
                    <p className="text-destructive text-sm" role="alert">
                      {completeError}
                    </p>
                  ) : null}
                  <Button
                    type="button"
                    disabled={!signatureDataUrl || !signedDate || completing}
                    className={cn(!signatureDataUrl ? "opacity-60" : null)}
                    onClick={() => void submitSignature()}
                  >
                    {completing ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                    ) : (
                      <PenLine className="size-3.5" aria-hidden />
                    )}
                    Apply signature and finish
                  </Button>
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}
          </div>
        )}
      </div>
    </>
  );
}

MyContractSign.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
