import { Link, router } from "@inertiajs/react";
import { Ban, Download, PenLine, Plus, Send, Signature, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Callout,
  EmptyState,
  FormActionBar,
  FormFieldError,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import type {
  SignaturePackageFieldRow,
  SignaturePackageRow,
  SignatureSchema,
  TransactionDocumentPackage,
  TransactionPartyRow,
  TransactionWorkspacePageProps,
} from "@/types";
import type { StatusTone } from "@/types/design-system";

/** Field geometry the server validates in PDF points, top-left origin. */
const FIELD_SIZE: Record<string, { w: number; h: number }> = {
  signature: { w: 200, h: 56 },
  initials: { w: 80, h: 40 },
  date: { w: 140, h: 28 },
  text: { w: 180, h: 28 },
};

const FIELD_NAME_RE = /^[A-Za-z][A-Za-z0-9_.]{0,79}$/;

const MEDIA_TYPE_PDF = "application/pdf";

function packageTone(status: string): StatusTone {
  if (status === "completed") return "success";
  if (status === "declined") return "destructive";
  if (status === "expired") return "warning";
  if (status === "sent" || status === "in_progress") return "info";
  return "neutral";
}

function signerTone(status: string): StatusTone {
  if (status === "signed") return "success";
  if (status === "declined") return "destructive";
  if (status === "expired") return "warning";
  if (status === "invited" || status === "viewed") return "info";
  return "neutral";
}

function localId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `signer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toDateTimeLocal(iso: string | null): string {
  return iso ? iso.slice(0, 16) : "";
}

type DraftSigner = {
  /**
   * What the field layout addresses this signer by. A saved signer keeps its
   * public id so the geometry survives a round trip; a new one gets a local id
   * that the server echoes back as a public id after the first save.
   */
  key: string;
  roleLabel: string;
  displayName: string;
  email: string;
  deliveryMethod: string;
  routingOrder: number;
  partyId: string;
};

type DraftState = {
  title: string;
  routingMode: string;
  expiresAt: string;
  /** Source document *version* ids — what the server resolves a package from. */
  documentKeys: string[];
  signers: DraftSigner[];
  fields: SignaturePackageFieldRow[];
};

type DocumentChoice = {
  versionPublicId: string;
  label: string;
};

/**
 * Every readable PDF version on the deal, newest package first.
 *
 * A package freezes a specific version rather than a document, so an earlier
 * revision stays selectable: a deal can be signing v2 of the disclosure while
 * v3 is still in review.
 */
function documentChoices(documents: TransactionDocumentPackage[]): DocumentChoice[] {
  const rows: DocumentChoice[] = [];
  for (const pkg of documents) {
    for (const version of pkg.versions) {
      if (!version.isReadable || version.mediaType !== MEDIA_TYPE_PDF) continue;
      rows.push({
        versionPublicId: version.publicId,
        label: `${pkg.title} · v${version.versionNumber}${
          version.isCurrent ? " (current)" : ""
        }`,
      });
    }
  }
  return rows;
}

function draftFromPackage(row: SignaturePackageRow): DraftState {
  // A saved field names the package document; a save names the source version.
  const versionOf = new Map(
    row.documents.map((doc) => [doc.publicId, doc.versionPublicId]),
  );
  return {
    title: row.title,
    routingMode: row.routingMode,
    expiresAt: toDateTimeLocal(row.expiresAt),
    documentKeys: row.documents.map((doc) => doc.versionPublicId),
    signers: row.signers.map((signer) => ({
      key: signer.publicId,
      roleLabel: signer.roleLabel,
      displayName: signer.displayName,
      email: signer.email,
      deliveryMethod: signer.deliveryMethod,
      routingOrder: signer.routingOrder,
      partyId: signer.partyPublicId ?? "",
    })),
    fields: (row.fields ?? []).map((field) => ({
      ...field,
      documentKey: versionOf.get(field.documentKey) ?? field.documentKey,
    })),
  };
}

function uniqueFieldName(base: string, taken: Set<string>): string {
  if (!taken.has(base)) return base;
  let index = 2;
  while (taken.has(`${base}${index}`)) index += 1;
  return `${base}${index}`;
}

function defaultFieldName(
  type: string,
  signerIndex: number,
  taken: Set<string>,
): string {
  const suffix = type.charAt(0).toUpperCase() + type.slice(1);
  return uniqueFieldName(`Signer${signerIndex + 1}${suffix}`, taken);
}

/** Signer statuses a reminder can still move. */
const REMINDABLE = new Set(["pending", "invited", "viewed"]);

function SignerList({
  row,
  publicId,
  expectedVersion,
  canRemind,
}: {
  row: SignaturePackageRow;
  publicId: string;
  expectedVersion: string;
  canRemind: boolean;
}) {
  const [reminding, setReminding] = useState("");

  return (
    <ul className="grid gap-2">
      {row.signers.map((signer) => (
        <li
          key={signer.publicId}
          className="border-border/60 flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
        >
          <div className="min-w-0">
            <p className="font-medium">
              {signer.displayName}
              <span className="text-muted-foreground ml-2 text-xs">
                {signer.roleLabel}
              </span>
            </p>
            <p className="text-muted-foreground text-xs">
              {[
                signer.email,
                signer.deliveryMethodLabel,
                `Order ${signer.routingOrder}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            {signer.declineReason ? (
              <p className="text-destructive text-xs">{signer.declineReason}</p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {canRemind && REMINDABLE.has(signer.status) ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={reminding === signer.publicId}
                onClick={() => {
                  setReminding(signer.publicId);
                  router.post(
                    routes.transaction_signature_signer_remind(
                      publicId,
                      row.publicId,
                      signer.publicId,
                    ),
                    { expectedVersion },
                    { preserveScroll: true, onFinish: () => setReminding("") },
                  );
                }}
              >
                <Send className="size-3.5" aria-hidden />
                Remind
              </Button>
            ) : null}
            <StatusBadge
              status={{ label: signer.statusLabel, tone: signerTone(signer.status) }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * Field placement by typed coordinates rather than by dragging a rendered PDF.
 *
 * The contract placer renders the document with pdf.js because a contract
 * template is authored once and reused; a deal package is assembled per deal
 * against documents the broker already knows, and a coordinate form is the
 * form of the tool that works with a keyboard from the first release. The
 * geometry vocabulary is identical, so swapping in a rendered surface later is
 * a change of input, not of contract.
 */
function FieldPlacer({
  draft,
  choices,
  pageCounts,
  onChange,
  disabled,
}: {
  draft: DraftState;
  choices: DocumentChoice[];
  pageCounts: Map<string, number>;
  onChange: (fields: SignaturePackageFieldRow[]) => void;
  disabled: boolean;
}) {
  const chosen = choices.filter((choice) =>
    draft.documentKeys.includes(choice.versionPublicId),
  );
  const [documentKey, setDocumentKey] = useState("");
  const [signerKey, setSignerKey] = useState("");
  const [type, setType] = useState("signature");
  const [page, setPage] = useState(1);
  const [box, setBox] = useState({ x: 72, y: 600, w: 200, h: 56 });
  const [name, setName] = useState("");

  const activeDocument = documentKey || chosen[0]?.versionPublicId || "";
  const activeSigner = signerKey || draft.signers[0]?.key || "";
  const signerIndex = draft.signers.findIndex((signer) => signer.key === activeSigner);
  const pageLimit = pageCounts.get(activeDocument);
  const nameInvalid = name.trim().length > 0 && !FIELD_NAME_RE.test(name.trim());
  const ready = Boolean(activeDocument && activeSigner) && !nameInvalid;

  const takenNames = new Set(draft.fields.map((field) => field.name));

  function append(nextType: string) {
    const size = FIELD_SIZE[nextType] ?? FIELD_SIZE.text;
    const resolved = name.trim()
      ? uniqueFieldName(name.trim(), takenNames)
      : defaultFieldName(nextType, Math.max(signerIndex, 0), takenNames);
    onChange([
      ...draft.fields,
      {
        name: resolved,
        type: nextType,
        signerKey: activeSigner,
        documentKey: activeDocument,
        page,
        x: box.x,
        y: box.y,
        w: size.w,
        h: size.h,
        required: true,
      },
    ]);
    setName("");
  }

  /** A signature and the date beside it — the pair every signer needs to send. */
  function addSignatureBlock() {
    const size = FIELD_SIZE.signature;
    const index = Math.max(signerIndex, 0);
    const signatureName = defaultFieldName("signature", index, takenNames);
    const dateName = defaultFieldName(
      "date",
      index,
      new Set([...takenNames, signatureName]),
    );
    const shared = {
      signerKey: activeSigner,
      documentKey: activeDocument,
      page,
      required: true,
    };
    onChange([
      ...draft.fields,
      {
        ...shared,
        name: signatureName,
        type: "signature",
        x: box.x,
        y: box.y,
        ...size,
      },
      {
        ...shared,
        name: dateName,
        type: "date",
        x: box.x + size.w + 16,
        y: box.y,
        ...FIELD_SIZE.date,
      },
    ]);
  }

  if (chosen.length === 0 || draft.signers.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Choose at least one document and add a signer before placing fields.
      </p>
    );
  }

  return (
    <div className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="field-document">Document</Label>
          <Select
            value={activeDocument}
            onValueChange={setDocumentKey}
            disabled={disabled}
          >
            <SelectTrigger id="field-document">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {chosen.map((choice) => (
                <SelectItem key={choice.versionPublicId} value={choice.versionPublicId}>
                  {choice.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="field-signer">Signer</Label>
          <Select value={activeSigner} onValueChange={setSignerKey} disabled={disabled}>
            <SelectTrigger id="field-signer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {draft.signers.map((signer) => (
                <SelectItem key={signer.key} value={signer.key}>
                  {signer.roleLabel} · {signer.displayName || "Unnamed"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="field-type">Type</Label>
          <Select value={type} onValueChange={setType} disabled={disabled}>
            <SelectTrigger id="field-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(FIELD_SIZE).map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="field-name">Name</Label>
          <Input
            id="field-name"
            value={name}
            disabled={disabled}
            placeholder="Auto-named when left blank"
            aria-invalid={nameInvalid || undefined}
            onChange={(event) => setName(event.target.value)}
          />
          {nameInvalid ? (
            <FormFieldError message="Start with a letter, then letters, digits, underscore, or dot." />
          ) : null}
        </div>
      </div>

      <fieldset className="grid gap-1.5">
        <legend className="text-muted-foreground text-xs font-semibold">
          Position on the page (PDF points, top-left origin)
        </legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <div className="grid gap-1">
            <Label htmlFor="field-page" className="text-muted-foreground text-micro">
              Page
            </Label>
            <Input
              id="field-page"
              type="number"
              min={1}
              max={pageLimit}
              className="h-8 tabular-nums"
              disabled={disabled}
              value={page}
              onChange={(event) =>
                setPage(Math.max(1, Number(event.target.value) || 1))
              }
            />
          </div>
          {(
            [
              { key: "x", label: "X" },
              { key: "y", label: "Y" },
              { key: "w", label: "Width" },
              { key: "h", label: "Height" },
            ] as const
          ).map((axis) => (
            <div key={axis.key} className="grid gap-1">
              <Label
                htmlFor={`field-${axis.key}`}
                className="text-muted-foreground text-micro"
              >
                {axis.label}
              </Label>
              <Input
                id={`field-${axis.key}`}
                type="number"
                min={0}
                className="h-8 tabular-nums"
                disabled={disabled}
                value={box[axis.key]}
                onChange={(event) =>
                  setBox((current) => ({
                    ...current,
                    [axis.key]: Math.max(0, Number(event.target.value) || 0),
                  }))
                }
              />
            </div>
          ))}
        </div>
        {pageLimit ? (
          <p className="text-muted-foreground text-xs">
            This document has {pageLimit} page{pageLimit === 1 ? "" : "s"}.
          </p>
        ) : null}
      </fieldset>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled || !ready}
          onClick={() => append(type)}
        >
          <Plus className="size-3.5" aria-hidden />
          Add field
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled || !ready}
          onClick={addSignatureBlock}
        >
          <Signature className="size-3.5" aria-hidden />
          Add signature block
        </Button>
      </div>

      {draft.fields.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No fields placed. Every signer needs at least one required field before the
          package can be sent.
        </p>
      ) : (
        <ul className="grid gap-1">
          {draft.fields.map((field) => {
            const signer = draft.signers.find((row) => row.key === field.signerKey);
            return (
              <li
                key={field.name}
                className="border-border/60 flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-sm"
              >
                <span className="min-w-0">
                  <span className="font-mono text-xs">{field.name}</span>
                  <span className="text-muted-foreground ml-2 text-xs">
                    {field.type} · {signer?.roleLabel ?? "unassigned"} · page{" "}
                    {field.page}
                    {field.required ? "" : " · optional"}
                  </span>
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={disabled}
                  aria-label={`Remove field ${field.name}`}
                  onClick={() =>
                    onChange(draft.fields.filter((row) => row.name !== field.name))
                  }
                >
                  <Trash2 className="size-3.5" aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function DraftEditor({
  row,
  schema,
  choices,
  parties,
  publicId,
  expectedVersion,
  errors,
}: {
  row: SignaturePackageRow;
  schema: SignatureSchema;
  choices: DocumentChoice[];
  parties: TransactionPartyRow[];
  publicId: string;
  expectedVersion: string;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [draft, setDraft] = useState<DraftState>(() => draftFromPackage(row));
  const [busy, setBusy] = useState(false);

  const pageCounts = useMemo(
    () => new Map(row.documents.map((doc) => [doc.versionPublicId, doc.pageCount])),
    [row.documents],
  );

  function patch(next: Partial<DraftState>) {
    setDraft((current) => ({ ...current, ...next }));
  }

  function toggleDocument(versionPublicId: string, checked: boolean) {
    setDraft((current) => {
      const documentKeys = checked
        ? [...current.documentKeys, versionPublicId]
        : current.documentKeys.filter((key) => key !== versionPublicId);
      return {
        ...current,
        documentKeys,
        // A field on a document that is no longer in the package would be
        // refused on save with an error about a document nobody can see.
        fields: current.fields.filter((field) =>
          documentKeys.includes(field.documentKey),
        ),
      };
    });
  }

  function patchSigner(key: string, next: Partial<DraftSigner>) {
    patch({
      signers: draft.signers.map((signer) =>
        signer.key === key ? { ...signer, ...next } : signer,
      ),
    });
  }

  function addSigner() {
    patch({
      signers: [
        ...draft.signers,
        {
          key: localId(),
          roleLabel: "",
          displayName: "",
          email: "",
          deliveryMethod: "email",
          routingOrder: draft.signers.length + 1,
          partyId: "",
        },
      ],
    });
  }

  function removeSigner(key: string) {
    patch({
      signers: draft.signers.filter((signer) => signer.key !== key),
      fields: draft.fields.filter((field) => field.signerKey !== key),
    });
  }

  function save() {
    setBusy(true);
    router.post(
      routes.transaction_signature_package_save(publicId, row.publicId),
      {
        expectedVersion,
        title: draft.title,
        routingMode: draft.routingMode,
        expiresAt: draft.expiresAt || null,
        documents: draft.documentKeys.map((versionPublicId, index) => ({
          versionPublicId,
          sortOrder: index,
        })),
        signers: draft.signers.map((signer) => ({
          key: signer.key,
          roleLabel: signer.roleLabel,
          displayName: signer.displayName,
          email: signer.email,
          deliveryMethod: signer.deliveryMethod,
          routingOrder: signer.routingOrder,
          partyId: signer.partyId || null,
        })),
        // Only the geometry the server reads; a saved field's public id and
        // label are projections, not input.
        fields: draft.fields.map((field) => ({
          name: field.name,
          type: field.type,
          signerKey: field.signerKey,
          documentKey: field.documentKey,
          page: field.page,
          x: field.x,
          y: field.y,
          w: field.w,
          h: field.h,
          required: field.required,
        })),
      },
      { preserveScroll: true, onFinish: () => setBusy(false) },
    );
  }

  return (
    <div className="border-border/60 grid gap-4 border-t pt-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grid gap-1.5">
          <Label htmlFor={`pkg-title-${row.publicId}`}>Title</Label>
          <Input
            id={`pkg-title-${row.publicId}`}
            value={draft.title}
            onChange={(event) => patch({ title: event.target.value })}
          />
          <FormFieldError messages={errors?.fields?.title} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`pkg-routing-${row.publicId}`}>Routing</Label>
          <Select
            value={draft.routingMode}
            onValueChange={(value) => patch({ routingMode: value })}
          >
            <SelectTrigger id={`pkg-routing-${row.publicId}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {schema.routingModes.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormFieldError messages={errors?.fields?.routingMode} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`pkg-expires-${row.publicId}`}>Expires</Label>
          <Input
            id={`pkg-expires-${row.publicId}`}
            type="datetime-local"
            value={draft.expiresAt}
            onChange={(event) => patch({ expiresAt: event.target.value })}
          />
          <FormFieldError messages={errors?.fields?.expiresAt} />
        </div>
      </div>

      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">Documents</legend>
        {choices.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No ready PDF on this deal yet. Upload one in Documents, then come back.
          </p>
        ) : (
          <ul className="grid gap-1.5">
            {choices.map((choice) => (
              <li key={choice.versionPublicId} className="flex items-center gap-2">
                <Checkbox
                  id={`doc-${row.publicId}-${choice.versionPublicId}`}
                  checked={draft.documentKeys.includes(choice.versionPublicId)}
                  onCheckedChange={(value) =>
                    toggleDocument(choice.versionPublicId, value === true)
                  }
                />
                <Label
                  htmlFor={`doc-${row.publicId}-${choice.versionPublicId}`}
                  className="text-sm font-normal"
                >
                  {choice.label}
                </Label>
              </li>
            ))}
          </ul>
        )}
        <FormFieldError messages={errors?.fields?.documents} />
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">Signers</legend>
        {draft.signers.map((signer, index) => (
          <div
            key={signer.key}
            className="border-border/60 grid gap-3 rounded-md border px-3 py-3 sm:grid-cols-2"
          >
            <div className="grid gap-1.5">
              <Label htmlFor={`signer-role-${signer.key}`}>Role label</Label>
              <Input
                id={`signer-role-${signer.key}`}
                value={signer.roleLabel}
                placeholder="Buyer"
                onChange={(event) =>
                  patchSigner(signer.key, { roleLabel: event.target.value })
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`signer-name-${signer.key}`}>Display name</Label>
              <Input
                id={`signer-name-${signer.key}`}
                value={signer.displayName}
                onChange={(event) =>
                  patchSigner(signer.key, { displayName: event.target.value })
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`signer-email-${signer.key}`}>Email</Label>
              <Input
                id={`signer-email-${signer.key}`}
                type="email"
                value={signer.email}
                onChange={(event) =>
                  patchSigner(signer.key, { email: event.target.value })
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`signer-delivery-${signer.key}`}>Delivery</Label>
              <Select
                value={signer.deliveryMethod}
                onValueChange={(value) =>
                  patchSigner(signer.key, { deliveryMethod: value })
                }
              >
                <SelectTrigger id={`signer-delivery-${signer.key}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {schema.deliveryMethods.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`signer-order-${signer.key}`}>Routing order</Label>
              <Input
                id={`signer-order-${signer.key}`}
                type="number"
                min={1}
                className="tabular-nums"
                value={signer.routingOrder}
                onChange={(event) =>
                  patchSigner(signer.key, {
                    routingOrder: Math.max(1, Number(event.target.value) || 1),
                  })
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`signer-party-${signer.key}`}>Linked party</Label>
              <Select
                value={signer.partyId || "none"}
                onValueChange={(value) =>
                  patchSigner(signer.key, { partyId: value === "none" ? "" : value })
                }
              >
                <SelectTrigger id={`signer-party-${signer.key}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Not linked</SelectItem>
                  {parties.map((party) => (
                    <SelectItem key={party.publicId} value={party.publicId}>
                      {party.displayName} · {party.roleLabel}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-2">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => removeSigner(signer.key)}
              >
                <Trash2 className="size-3.5" aria-hidden />
                Remove signer {index + 1}
              </Button>
            </div>
          </div>
        ))}
        <div>
          <Button type="button" size="sm" variant="outline" onClick={addSigner}>
            <Plus className="size-3.5" aria-hidden />
            Add signer
          </Button>
        </div>
        <FormFieldError messages={errors?.fields?.signers} />
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">Fields</legend>
        <FieldPlacer
          draft={draft}
          choices={choices}
          pageCounts={pageCounts}
          onChange={(fields) => patch({ fields })}
          disabled={busy}
        />
        <FormFieldError messages={errors?.fields?.fields} />
      </fieldset>

      <FormActionBar
        status={
          busy
            ? "Saving…"
            : "Saving replaces the package contents. Only a draft can be edited."
        }
      >
        <Button type="button" disabled={busy || !draft.title.trim()} onClick={save}>
          Save draft
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            router.post(
              routes.transaction_signature_package_send(publicId, row.publicId),
              { expectedVersion },
              { preserveScroll: true, onFinish: () => setBusy(false) },
            );
          }}
        >
          <Send className="size-3.5" aria-hidden />
          Send for signature
        </Button>
      </FormActionBar>
    </div>
  );
}

function PackageCard({
  row,
  schema,
  choices,
  parties,
  publicId,
  expectedVersion,
  canEdit,
  errors,
}: {
  row: SignaturePackageRow;
  schema: SignatureSchema;
  choices: DocumentChoice[];
  parties: TransactionPartyRow[];
  publicId: string;
  expectedVersion: string;
  canEdit: boolean;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const open = !row.isDraft && !row.isTerminal;

  function post(url: string) {
    setBusy(true);
    router.post(
      url,
      { expectedVersion },
      { preserveScroll: true, onFinish: () => setBusy(false) },
    );
  }

  return (
    <SurfaceCard>
      <SurfaceCardContent className="grid gap-4 py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-base font-medium">{row.title}</h3>
            <p className="text-muted-foreground text-sm">
              {row.routingModeLabel} · {row.progress.signed} of {row.progress.total}{" "}
              signed
              {row.expiresAt ? ` · expires ${row.expiresAt.slice(0, 10)}` : ""}
            </p>
          </div>
          <StatusBadge
            status={{ label: row.statusLabel, tone: packageTone(row.status) }}
          />
        </div>

        {row.documents.length > 0 ? (
          <ul className="text-muted-foreground grid gap-1 text-sm">
            {row.documents.map((document) => (
              <li key={document.publicId}>
                {document.displayName} · {document.pageCount} page
                {document.pageCount === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">No documents in this package.</p>
        )}

        {row.signers.length > 0 ? (
          <SignerList
            row={row}
            publicId={publicId}
            expectedVersion={expectedVersion}
            canRemind={canEdit && open}
          />
        ) : null}

        {row.artifacts.length > 0 ? (
          <div className="grid gap-2">
            <h4 className="text-sm font-medium">Artifacts</h4>
            <div className="flex flex-wrap gap-2">
              {row.artifacts.map((artifact) => (
                <Button key={artifact.publicId} asChild size="sm" variant="outline">
                  <a href={artifact.downloadUrl} download>
                    <Download className="size-3.5" aria-hidden />
                    {artifact.kindLabel}
                  </a>
                </Button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {open ? (
            <Button asChild size="sm" variant="outline">
              <Link href={row.ceremonyUrl}>
                <PenLine className="size-3.5" aria-hidden />
                Open signing page
              </Link>
            </Button>
          ) : null}
          {canEdit && row.isDraft ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-expanded={editing}
              onClick={() => setEditing((current) => !current)}
            >
              {editing ? "Close editor" : "Edit package"}
            </Button>
          ) : null}
          {canEdit && !row.isTerminal ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() =>
                post(
                  routes.transaction_signature_package_cancel(publicId, row.publicId),
                )
              }
            >
              <Ban className="size-3.5" aria-hidden />
              Cancel package
            </Button>
          ) : null}
        </div>

        {canEdit && row.isDraft && editing ? (
          <DraftEditor
            row={row}
            schema={schema}
            choices={choices}
            parties={parties}
            publicId={publicId}
            expectedVersion={expectedVersion}
            errors={errors}
          />
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

function CreatePackageCard({
  schema,
  publicId,
  expectedVersion,
  errors,
}: {
  schema: SignatureSchema;
  publicId: string;
  expectedVersion: string;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [title, setTitle] = useState("");
  const [routingMode, setRoutingMode] = useState("ordered");
  const [expiresAt, setExpiresAt] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <SurfaceCard>
      <PanelHeader
        title="New signature package"
        headingLevel="h3"
        description="Opens an empty draft. Documents, signers, and fields are added next."
        divided
      />
      <SurfaceCardContent className="grid gap-4 py-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label htmlFor="new-package-title">Title</Label>
            <Input
              id="new-package-title"
              value={title}
              placeholder="Purchase agreement signatures"
              onChange={(event) => setTitle(event.target.value)}
            />
            <FormFieldError messages={errors?.fields?.title} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="new-package-routing">Routing</Label>
            <Select value={routingMode} onValueChange={setRoutingMode}>
              <SelectTrigger id="new-package-routing">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {schema.routingModes.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="new-package-expires">Expires</Label>
            <Input
              id="new-package-expires"
              type="datetime-local"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
            <FormFieldError messages={errors?.fields?.expiresAt} />
          </div>
        </div>
        <FormActionBar status={busy ? "Creating…" : "Creates a draft you can edit."}>
          <Button
            type="button"
            disabled={busy || !title.trim()}
            onClick={() => {
              setBusy(true);
              router.post(
                routes.transaction_signature_package_create(publicId),
                {
                  expectedVersion,
                  title,
                  routingMode,
                  expiresAt: expiresAt || null,
                },
                {
                  preserveScroll: true,
                  onFinish: () => setBusy(false),
                  onSuccess: () => setTitle(""),
                },
              );
            }}
          >
            <Plus className="size-3.5" aria-hidden />
            Create draft
          </Button>
        </FormActionBar>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function SignaturesPanel({
  signaturePackages = [],
  signatureSchema,
  documents = [],
  parties = [],
  expectedVersion,
  publicId,
  canEdit,
  errors,
}: {
  signaturePackages?: SignaturePackageRow[];
  signatureSchema?: SignatureSchema | null;
  documents?: TransactionDocumentPackage[];
  parties?: TransactionPartyRow[];
  expectedVersion: string;
  publicId: string;
  canEdit: boolean;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const choices = useMemo(() => documentChoices(documents), [documents]);
  const formErrors = errors?.form ?? [];

  if (!signatureSchema) {
    return (
      <EmptyState
        icon={Signature}
        title="Signatures loading"
        description="Signing controls appear when this section finishes loading."
        compact
      />
    );
  }

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-lg font-medium">Signatures</h2>
        <p className="text-muted-foreground text-sm">
          Electronic signature packages built from documents already on this deal.
          Signed PDFs and the certificate of completion are stored here.
        </p>
      </div>

      {formErrors.length > 0 ? (
        <Callout tone="destructive" title="That could not be saved">
          <ul className="grid gap-1" role="alert">
            {formErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Callout>
      ) : null}

      {signaturePackages.length === 0 ? (
        <EmptyState
          icon={Signature}
          title="No signature packages yet"
          description={
            canEdit
              ? "Build a package from a ready PDF on this deal, add signers, then send it."
              : "Packages appear here once someone on this deal builds one."
          }
          compact
        />
      ) : (
        <div className="grid gap-4">
          {signaturePackages.map((row) => (
            <PackageCard
              key={row.publicId}
              row={row}
              schema={signatureSchema}
              choices={choices}
              parties={parties}
              publicId={publicId}
              expectedVersion={expectedVersion}
              canEdit={canEdit}
              errors={errors}
            />
          ))}
        </div>
      )}

      {canEdit ? (
        <CreatePackageCard
          schema={signatureSchema}
          publicId={publicId}
          expectedVersion={expectedVersion}
          errors={errors}
        />
      ) : null}
    </div>
  );
}
