import { Head, usePage } from "@inertiajs/react";

import { StatusBadge } from "@/components/design-system";
import { Badge } from "@/components/ui/badge";
import onestLogo from "@/images/onest-logo.png";
import type { PageProps } from "@/types";

export interface TrainingCertificateVerification {
  valid: boolean;
  status: string;
  publicId: string;
  signatureValid?: boolean;
  signatureAlgorithm?: string;
  signatureFingerprint?: string;
  learnerName?: string;
  trainingTitle?: string;
  completedAt?: string | null;
  issuedAt?: string | null;
  verifiedAt?: string;
  message: string;
  verifyUrl?: string;
}

interface Props extends PageProps {
  verification: TrainingCertificateVerification;
}

export default function TrainingCertificateVerify() {
  const { verification } = usePage<Props>().props;
  const tone = verification.valid
    ? ("success" as const)
    : verification.status === "revoked"
      ? ("destructive" as const)
      : ("warning" as const);

  return (
    <div className="bg-background flex min-h-svh items-center justify-center px-6 py-16">
      <Head title="Verify training certificate" />
      <main className="border-border/60 w-full max-w-lg rounded-xl border bg-card p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img src={onestLogo} alt="oNEST" className="h-12 w-auto" />
          <h1 className="text-xl font-semibold tracking-tight">
            Certificate verification
          </h1>
          <StatusBadge
            status={{
              label: verification.valid ? "Verified" : "Not verified",
              tone,
            }}
          />
        </div>

        <p className="text-muted-foreground mb-6 text-center text-sm">
          {verification.message}
        </p>

        {verification.status !== "not_found" ? (
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                Learner
              </dt>
              <dd className="font-medium">{verification.learnerName}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                Training
              </dt>
              <dd className="font-medium">{verification.trainingTitle}</dd>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                  Completed
                </dt>
                <dd>{verification.completedAt || "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                  Issued
                </dt>
                <dd>
                  {verification.issuedAt
                    ? new Date(verification.issuedAt).toLocaleString()
                    : "—"}
                </dd>
              </div>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                Verification ID
              </dt>
              <dd className="font-mono text-xs break-all">{verification.publicId}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1 text-xs uppercase tracking-wide">
                Signature
              </dt>
              <dd className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  {verification.signatureAlgorithm || "hmac-sha256-v1"}
                </Badge>
                <span className="font-mono text-xs">
                  {verification.signatureFingerprint || "—"}
                </span>
                {verification.signatureValid ? (
                  <StatusBadge status={{ label: "Valid", tone: "success" }} />
                ) : (
                  <StatusBadge status={{ label: "Invalid", tone: "destructive" }} />
                )}
              </dd>
            </div>
          </dl>
        ) : null}
      </main>
    </div>
  );
}
