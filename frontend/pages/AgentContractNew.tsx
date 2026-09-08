import { Head, Link, router, usePage } from "@inertiajs/react";
import { CircleCheck, Info, TriangleAlert } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import {
  PersonCombobox,
  type PersonOption,
} from "@/components/administration/PersonCombobox";
import {
  Callout,
  DateField,
  FormActionBar,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { AgentContractNewPageProps, AgentContractTemplateOption } from "@/types";

const ACCESS = { all: ["contract.manage_agent_contracts"] };

/** ``AgentContract.clean`` refuses a pair that does not reach exactly this. */
const SPLIT_TOTAL = 100;

function parsePercent(raw: string): number | null {
  const value = Number.parseFloat(raw.replace(/,/g, "").trim());
  return Number.isFinite(value) ? value : null;
}

/**
 * The office and jurisdiction that decide which templates apply.
 *
 * These are read off the chosen agent's profile, so they are facts rather than
 * fields — a recessed well and a definition list, not inputs somebody might
 * try to correct here.
 */
function AgentContext({ agent }: { agent: PersonOption }) {
  return (
    <dl className="bg-muted/40 border-border/60 grid gap-4 rounded-lg border p-4 sm:grid-cols-3">
      <ReadOnlyValue label="Office">{agent.officeName || "—"}</ReadOnlyValue>
      <ReadOnlyValue label="Jurisdiction">
        {agent.officeState || (
          <span className="text-muted-foreground">Not set on office</span>
        )}
      </ReadOnlyValue>
      <ReadOnlyValue label="License state">
        {agent.licenseState || (
          <span className="text-muted-foreground">Not on profile</span>
        )}
      </ReadOnlyValue>
    </dl>
  );
}

/**
 * Live arithmetic on the one rule the server will reject the form for.
 *
 * The splits are two free-text percentages that must total 100. Saying so only
 * after a round trip wastes the trip, and saying it in red before anybody has
 * finished typing is nagging — so the note is neutral until both halves are
 * present and only then commits to right or wrong.
 */
function SplitTotal({ agent, office }: { agent: string; office: string }) {
  const left = parsePercent(agent);
  const right = parsePercent(office);
  if (left === null || right === null) {
    return (
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <Info className="size-3.5 shrink-0" aria-hidden />
        The two splits must total {SPLIT_TOTAL}%.
      </p>
    );
  }
  const total = Math.round((left + right) * 1000) / 1000;
  const balanced = total === SPLIT_TOTAL;
  return (
    <p
      className={cn(
        "flex items-center gap-1.5 text-xs tabular-nums",
        balanced ? "text-success" : "text-warning-ink",
      )}
      aria-live="polite"
    >
      {balanced ? (
        <CircleCheck className="size-3.5 shrink-0" aria-hidden />
      ) : (
        <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
      )}
      {balanced
        ? `Splits total ${SPLIT_TOTAL}%.`
        : `Splits total ${total}%. They must reach ${SPLIT_TOTAL}% before this saves.`}
    </p>
  );
}

export default function AgentContractNew() {
  const { capabilities, errors, draft, csrfToken } =
    usePage<AgentContractNewPageProps>().props;
  const [agent, setAgent] = useState<PersonOption | null>(null);
  const [templates, setTemplates] = useState<AgentContractTemplateOption[]>([]);
  const [templatesLoaded, setTemplatesLoaded] = useState(false);
  const [templateVersionId, setTemplateVersionId] = useState("");
  const [effectiveOn, setEffectiveOn] = useState(
    draft.effective_on || draft.effectiveOn || new Date().toISOString().slice(0, 10),
  );
  const [agentSplit, setAgentSplit] = useState(draft.agent_split_percent || "70");
  const [officeSplit, setOfficeSplit] = useState(draft.office_split_percent || "30");
  const [submitting, setSubmitting] = useState(false);
  const templateHelpId = useId();

  useEffect(() => {
    if (!agent?.officeId) {
      setTemplates([]);
      setTemplateVersionId("");
      setTemplatesLoaded(false);
      return;
    }
    const controller = new AbortController();
    setTemplatesLoaded(false);
    fetch(
      `${routes.agent_contract_template_options()}?office_id=${agent.officeId}&effective_on=${encodeURIComponent(effectiveOn)}`,
      {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: controller.signal,
      },
    )
      .then(
        (response) =>
          response.json() as Promise<{ results?: AgentContractTemplateOption[] }>,
      )
      .then((payload) => {
        setTemplates(payload.results ?? []);
        setTemplateVersionId("");
        setTemplatesLoaded(true);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setTemplates([]);
        setTemplateVersionId("");
        setTemplatesLoaded(true);
      });
    return () => controller.abort();
  }, [agent, effectiveOn]);

  const ready = Boolean(agent && templateVersionId);
  const status = useMemo(() => {
    if (!agent) return "Choose an agent to continue.";
    if (!templatesLoaded) return "Loading templates for that office…";
    if (templates.length === 0) return "No template applies to that office and date.";
    if (!templateVersionId) return "Choose a template version to continue.";
    return "Creates a draft you can edit before issuing. Nothing is sent to the agent.";
  }, [agent, templateVersionId, templates.length, templatesLoaded]);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || submitting) return;
    setSubmitting(true);
    const form = event.currentTarget;
    router.post(form.action, new FormData(form), {
      preserveScroll: true,
      onFinish: () => setSubmitting(false),
    });
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="New agent contract" />
        <PageHeader
          title="New agent contract"
          description="Choose an agent and the template that applies to their office, then continue into the draft workspace."
        />
        <FormErrorSummary errors={errors} />

        <form
          method="post"
          action={routes.agent_contract_create()}
          className="grid max-w-2xl gap-6"
          onSubmit={submit}
        >
          <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
          <input type="hidden" name="recipient_id" value={agent?.id ?? ""} />
          <input type="hidden" name="template_version_id" value={templateVersionId} />
          {agent?.officeId ? (
            <input type="hidden" name="office_id" value={agent.officeId} />
          ) : null}

          <SurfaceCard>
            <PanelHeader
              title="Agent"
              description="Office and jurisdiction come from their profile and decide which templates apply."
              divided
            />
            <SurfaceCardContent className="grid gap-4">
              <PersonCombobox
                id="agent-search"
                label="Search agents in your scope"
                endpoint={routes.agent_contract_recipient_search()}
                value={agent}
                onChange={setAgent}
                disabled={!capabilities.canManage}
                required
                invalid={Boolean(errors.fields?.recipient_id)}
                placeholder="Name or email"
              />
              <FormFieldError messages={errors.fields?.recipient_id} />
              {agent ? <AgentContext agent={agent} /> : null}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              title="Template and dates"
              description="Only published, active templates whose jurisdiction covers the office are listed."
              divided
            />
            <SurfaceCardContent className="grid gap-5">
              <DateField
                name="effective_on"
                label="Effective on"
                value={effectiveOn}
                onChange={setEffectiveOn}
                validation={errors}
                required
                description="Changing this re-checks which templates apply."
              />

              <FormField>
                <FormLabel htmlFor="template_version_id" required>
                  Template version
                </FormLabel>
                <Select
                  value={templateVersionId || undefined}
                  onValueChange={setTemplateVersionId}
                  disabled={!agent || templates.length === 0}
                >
                  <SelectTrigger
                    id="template_version_id"
                    className="w-full"
                    {...fieldA11yProps("template_version_id", errors, templateHelpId)}
                  >
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
                <FormDescription id={templateHelpId}>
                  {!agent
                    ? "Choose an agent first."
                    : !templatesLoaded
                      ? "Checking which templates apply…"
                      : templates.length === 0
                        ? "Nothing applies yet — see the note below."
                        : `${templates.length} template${templates.length === 1 ? "" : "s"} apply to this office and date.`}
                </FormDescription>
                <FormFieldError messages={errors.fields?.template_version_id} />
              </FormField>

              {agent && templatesLoaded && templates.length === 0 ? (
                <Callout tone="warning" title="No template applies">
                  Nothing published and active covers{" "}
                  {agent.officeName || "this office"}
                  {agent.officeState ? ` (${agent.officeState})` : ""} on this date.
                  Drafts are excluded, and a jurisdiction-limited template only appears
                  for a matching office.
                </Callout>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              title="Opening commission split"
              description="A starting point for the draft. Both halves stay editable in the workspace."
              divided
            />
            <SurfaceCardContent className="grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField>
                  <FormLabel htmlFor="agent_split_percent" required>
                    Agent split (%)
                  </FormLabel>
                  <Input
                    id="agent_split_percent"
                    name="agent_split_percent"
                    value={agentSplit}
                    onChange={(event) => setAgentSplit(event.target.value)}
                    inputMode="decimal"
                    className="tabular-nums"
                    {...fieldA11yProps("agent_split_percent", errors)}
                  />
                  <FormFieldError
                    id="agent_split_percent_error"
                    messages={errors.fields?.agent_split_percent}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="office_split_percent" required>
                    Office split (%)
                  </FormLabel>
                  <Input
                    id="office_split_percent"
                    name="office_split_percent"
                    value={officeSplit}
                    onChange={(event) => setOfficeSplit(event.target.value)}
                    inputMode="decimal"
                    className="tabular-nums"
                    {...fieldA11yProps("office_split_percent", errors)}
                  />
                  <FormFieldError
                    id="office_split_percent_error"
                    messages={errors.fields?.office_split_percent}
                  />
                </FormField>
              </div>
              <SplitTotal agent={agentSplit} office={officeSplit} />
            </SurfaceCardContent>
          </SurfaceCard>

          <FormActionBar status={status}>
            <Button variant="outline" asChild>
              <Link href={routes.admin_agent_contracts()}>Cancel</Link>
            </Button>
            <Button type="submit" disabled={!ready || submitting}>
              {submitting ? "Creating…" : "Create draft"}
            </Button>
          </FormActionBar>
        </form>
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
