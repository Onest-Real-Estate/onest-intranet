import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { routes } from "@/lib/routes";
import type { AgentContractPayeeSummary, AgentContractRecipientResult } from "@/types";

type ContractPayeeSearchProps = {
  id: string;
  name: string;
  label: string;
  disabled?: boolean;
  initialPayee?: AgentContractPayeeSummary | null;
};

function toSummary(row: AgentContractRecipientResult): AgentContractPayeeSummary {
  return {
    id: row.id,
    name: row.name,
    email: row.email,
    officeId: row.officeId,
    officeName: row.officeName,
  };
}

export function ContractPayeeSearch({
  id,
  name,
  label,
  disabled = false,
  initialPayee = null,
}: ContractPayeeSearchProps) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AgentContractRecipientResult[]>([]);
  const [selected, setSelected] = useState<AgentContractPayeeSummary | null>(
    initialPayee,
  );

  useEffect(() => {
    setSelected(initialPayee);
  }, [initialPayee]);

  useEffect(() => {
    if (disabled || selected || query.trim().length < 2) {
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
  }, [disabled, query, selected]);

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <input type="hidden" name={name} value={selected?.id ?? ""} />
      <Input
        id={id}
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
        disabled={disabled}
        value={selected ? `${selected.name} <${selected.email}>` : query}
        onChange={(event) => {
          setSelected(null);
          setQuery(event.target.value);
        }}
        placeholder="Search by name or email (2+ characters)"
      />
      {results.length > 0 && !selected ? (
        <div id={listId} className="rounded-md border border-border bg-surface p-1">
          {results.map((row) => (
            <button
              key={row.id}
              type="button"
              className="w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-muted"
              onClick={() => {
                setSelected(toSummary(row));
                setQuery("");
                setResults([]);
              }}
            >
              <span className="font-medium">{row.name}</span>
              <span className="text-muted-foreground block">
                {row.email} · {row.officeName}
                {row.officeState ? ` · ${row.officeState}` : ""}
              </span>
            </button>
          ))}
        </div>
      ) : null}
      {selected && !disabled ? (
        <div className="flex items-center justify-between gap-2">
          <p className="text-muted-foreground text-sm">
            {selected.officeName || "No office on profile"}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setSelected(null);
              setQuery("");
            }}
          >
            Clear
          </Button>
        </div>
      ) : null}
    </div>
  );
}
