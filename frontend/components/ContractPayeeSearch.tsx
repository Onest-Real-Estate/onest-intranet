import { useEffect, useState } from "react";

import {
  PersonCombobox,
  type PersonOption,
} from "@/components/administration/PersonCombobox";
import { routes } from "@/lib/routes";
import type { AgentContractPayeeSummary } from "@/types";

type ContractPayeeSearchProps = {
  id: string;
  name: string;
  label: string;
  disabled?: boolean;
  initialPayee?: AgentContractPayeeSummary | null;
  description?: React.ReactNode;
};

/**
 * A payee summary carries less than a search result. The missing fields are
 * presentation-only, so a hydrated selection renders the same way a searched
 * one does instead of waiting for a round trip to look complete.
 */
function toOption(payee: AgentContractPayeeSummary): PersonOption {
  return {
    id: payee.id,
    name: payee.name,
    email: payee.email,
    officeId: payee.officeId ?? null,
    officeName: payee.officeName ?? "",
    licenseState: "",
    agentIdentifier: "",
  };
}

/** Choose the person a mentor or referral share is paid to. */
export function ContractPayeeSearch({
  id,
  name,
  label,
  disabled = false,
  initialPayee = null,
  description,
}: ContractPayeeSearchProps) {
  const [selected, setSelected] = useState<PersonOption | null>(
    initialPayee ? toOption(initialPayee) : null,
  );

  useEffect(() => {
    setSelected(initialPayee ? toOption(initialPayee) : null);
  }, [initialPayee]);

  return (
    <PersonCombobox
      id={id}
      name={name}
      label={label}
      endpoint={routes.agent_contract_recipient_search()}
      value={selected}
      onChange={setSelected}
      disabled={disabled}
      description={description}
    />
  );
}
