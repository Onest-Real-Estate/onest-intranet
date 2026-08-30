import { Head, router, usePage } from "@inertiajs/react";
import { useEffect, useId, useState } from "react";
import {
  FormErrorSummary,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
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
  AgentContractNewPageProps,
  AgentContractRecipientResult,
  AgentContractTemplateOption,
} from "@/types";

const ACCESS = { all: ["contract.manage_agent_contracts"] };

export default function AgentContractNew() {
  const { capabilities, errors, draft, csrfToken } =
    usePage<AgentContractNewPageProps>().props;
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AgentContractRecipientResult[]>([]);
  const [selected, setSelected] = useState<AgentContractRecipientResult | null>(null);
  const [templates, setTemplates] = useState<AgentContractTemplateOption[]>([]);
  const [templateVersionId, setTemplateVersionId] = useState("");
  const [effectiveOn, setEffectiveOn] = useState(
    draft.effective_on || draft.effectiveOn || new Date().toISOString().slice(0, 10),
  );
  const listId = useId();

  useEffect(() => {
    if (query.trim().length < 2 || !capabilities.canManage) {
      setResults([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void fetch(
        `${routes.agent_contract_recipient_search()}?q=${encodeURIComponent(query)}`,
        { headers: { Accept: "application/json" }, credentials: "same-origin" },
      )
        .then((response) => response.json())
        .then((payload: { results: AgentContractRecipientResult[] }) => {
          setResults(payload.results ?? []);
        })
        .catch(() => setResults([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [capabilities.canManage, query]);

  useEffect(() => {
    if (!selected?.officeId) {
      setTemplates([]);
      setTemplateVersionId("");
      return;
    }
    void fetch(
      `${routes.agent_contract_template_options()}?office_id=${selected.officeId}&effective_on=${encodeURIComponent(effectiveOn)}`,
      { headers: { Accept: "application/json" }, credentials: "same-origin" },
    )
      .then((response) => response.json())
      .then((payload: { results: AgentContractTemplateOption[] }) => {
        setTemplates(payload.results ?? []);
        setTemplateVersionId("");
      })
      .catch(() => {
        setTemplates([]);
        setTemplateVersionId("");
      });
  }, [effectiveOn, selected]);

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="New agent contract" />
        <PageHeader
          title="New agent contract"
          description="Select an in-scope agent and applicable template, then continue into the draft workspace."
        />
        <FormErrorSummary errors={errors} />

        <SurfaceCard>
          <SurfaceCardContent>
            <form
              method="post"
              action={routes.agent_contract_create()}
              className="grid max-w-xl gap-4"
              onSubmit={(event) => {
                if (!selected || !templateVersionId) {
                  event.preventDefault();
                  return;
                }
                event.preventDefault();
                const form = event.currentTarget;
                router.post(form.action, new FormData(form), {
                  preserveScroll: true,
                });
              }}
            >
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <input type="hidden" name="recipient_id" value={selected?.id ?? ""} />
              <input
                type="hidden"
                name="template_version_id"
                value={templateVersionId}
              />
              {selected?.officeId ? (
                <input type="hidden" name="office_id" value={selected.officeId} />
              ) : null}

              <div className="grid gap-2">
                <Label htmlFor="agent-search">Agent</Label>
                <Input
                  id="agent-search"
                  role="combobox"
                  aria-expanded={results.length > 0}
                  aria-controls={listId}
                  aria-autocomplete="list"
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  data-1p-ignore
                  data-lpignore="true"
                  data-form-type="other"
                  value={selected ? `${selected.name} <${selected.email}>` : query}
                  onChange={(event) => {
                    setSelected(null);
                    setQuery(event.target.value);
                  }}
                  placeholder="Search by name or email (2+ characters)"
                  required={!selected}
                />
                {results.length > 0 && !selected ? (
                  <div
                    id={listId}
                    className="rounded-md border border-border bg-surface p-1"
                  >
                    {results.map((row) => (
                      <button
                        key={row.id}
                        type="button"
                        className="w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-muted"
                        onClick={() => {
                          setSelected(row);
                          setQuery("");
                          setResults([]);
                        }}
                      >
                        <span className="font-medium">{row.name}</span>
                        <span className="block text-muted-foreground">
                          {row.email} · {row.officeName}
                          {row.officeState ? ` · ${row.officeState}` : ""}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
                {selected ? (
                  <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                    <p>
                      <span className="text-muted-foreground">Office: </span>
                      {selected.officeName || "—"}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Jurisdiction: </span>
                      {selected.officeState || "Not set on office"}
                    </p>
                    {selected.licenseState ? (
                      <p>
                        <span className="text-muted-foreground">License state: </span>
                        {selected.licenseState}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="grid gap-2">
                <Label htmlFor="effective_on">Effective on</Label>
                <Input
                  id="effective_on"
                  name="effective_on"
                  type="date"
                  value={effectiveOn}
                  onChange={(event) => setEffectiveOn(event.target.value)}
                  required
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="template_version_id">Template version</Label>
                <Select
                  value={templateVersionId || undefined}
                  onValueChange={setTemplateVersionId}
                  disabled={!selected || templates.length === 0}
                >
                  <SelectTrigger id="template_version_id" aria-required>
                    <SelectValue placeholder="Select a published template" />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((option) => (
                      <SelectItem key={option.id} value={String(option.id)}>
                        {option.templateName} ({option.versionLabel})
                        {option.jurisdictionStateCodes?.length
                          ? ` · ${option.jurisdictionStateCodes.join(", ")}`
                          : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!selected ? (
                  <p className="text-sm text-muted-foreground">
                    Select an agent first. Templates are filtered to that office&apos;s
                    jurisdiction.
                  </p>
                ) : templates.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No published active templates apply to{" "}
                    {selected.officeName || "this office"}
                    {selected.officeState ? ` (${selected.officeState})` : ""}. Drafts
                    are excluded; jurisdiction-limited templates (for example VA-only)
                    only appear for matching offices.
                  </p>
                ) : null}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="agent_split_percent">Agent split (%)</Label>
                  <Input
                    id="agent_split_percent"
                    name="agent_split_percent"
                    defaultValue={draft.agent_split_percent || "70"}
                    inputMode="decimal"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="office_split_percent">Office split (%)</Label>
                  <Input
                    id="office_split_percent"
                    name="office_split_percent"
                    defaultValue={draft.office_split_percent || "30"}
                    inputMode="decimal"
                  />
                </div>
              </div>

              <div className="flex gap-3">
                <Button type="submit" disabled={!selected}>
                  Create draft
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => router.get(routes.admin_agent_contracts())}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

AgentContractNew.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "New agent contract",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Agent Contracts", href: routes.admin_agent_contracts() },
          { label: "New" },
        ],
      },
      variant: "standard",
    },
  ] as const;
