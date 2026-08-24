import { Head, router, usePage } from "@inertiajs/react";
import {
  FormErrorSummary,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { ContractTemplateWorkspacePageProps } from "@/types";

const ACCESS = {
  any: ["contract.manage_contract_templates", "contract.approve_contract_templates"],
};

export default function ContractTemplateWorkspace() {
  const { versionDetail, capabilities, errors, csrfToken } =
    usePage<ContractTemplateWorkspacePageProps>().props;

  function postAction(action: "preview" | "publish" | "activate" | "retire") {
    router.post(
      routes.contract_template_action(versionDetail.id),
      { action },
      { preserveScroll: true },
    );
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head
          title={`${versionDetail.displayName || versionDetail.versionLabel} Template`}
        />
        <PageHeader
          title={versionDetail.displayName || versionDetail.versionLabel}
          description={`${versionDetail.template.name} · ${versionDetail.versionLabel} · ${versionDetail.status}`}
          actions={
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => postAction("preview")}
              >
                Generate preview
              </Button>
              {capabilities.canApprove ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => postAction("publish")}
                  >
                    Publish
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => postAction("activate")}
                  >
                    Activate
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => postAction("retire")}
                  >
                    Retire
                  </Button>
                </>
              ) : null}
            </div>
          }
        />
        <FormErrorSummary errors={errors} />

        <SurfaceCard>
          <PanelHeader
            title="Draft workspace"
            description="Upload the protected source, document the merge schema, and use the production render path for synthetic previews."
          />
          <SurfaceCardContent>
            <div className="text-muted-foreground mb-4 grid gap-1 text-xs">
              <span>Source format: {versionDetail.sourceFormat || "Not uploaded"}</span>
              <span>
                Placeholders:{" "}
                {versionDetail.placeholderKeys.length
                  ? versionDetail.placeholderKeys.join(", ")
                  : "None extracted yet"}
              </span>
              <span>
                Preview checksum:{" "}
                {versionDetail.previewChecksum || "No preview generated"}
              </span>
              {versionDetail.previewUrl ? (
                <a
                  href={versionDetail.previewUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  Open stored preview
                </a>
              ) : null}
              <span>
                Contracts using this version: {versionDetail.contractsUsingVersion}
              </span>
            </div>
            {capabilities.canManage ? (
              <form
                method="post"
                action={routes.contract_template_update(versionDetail.id)}
                encType="multipart/form-data"
                className="grid gap-4"
              >
                <input type="hidden" name="_token" value={csrfToken} />
                <input
                  type="hidden"
                  name="expected_version"
                  value={versionDetail.version}
                />
                <div className="grid gap-2">
                  <Label htmlFor="display_name">Display name</Label>
                  <Input
                    id="display_name"
                    name="display_name"
                    defaultValue={versionDetail.displayName}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    name="description"
                    defaultValue={versionDetail.description}
                    rows={4}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="merge_schema_json">Merge schema JSON</Label>
                  <Textarea
                    id="merge_schema_json"
                    name="merge_schema_json"
                    defaultValue={versionDetail.mergeSchemaJson}
                    rows={16}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="source_document">Source document</Label>
                  <Input id="source_document" name="source_document" type="file" />
                </div>
                <Button type="submit">Save draft</Button>
              </form>
            ) : (
              <p className="text-muted-foreground text-sm">
                You can review, preview, publish, and activate this version, but draft
                edits stay restricted to template authors.
              </p>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

ContractTemplateWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Contract Template Workspace",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Contract Templates", href: routes.admin_contract_templates() },
        ],
      },
      variant: "standard",
    },
  ] as const;
