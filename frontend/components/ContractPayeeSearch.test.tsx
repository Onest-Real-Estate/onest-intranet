import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ContractPayeeSearch } from "./ContractPayeeSearch";

vi.mock("@/lib/routes", () => ({
  routes: {
    agent_contract_recipient_search: () => "/operations/agent-contracts/recipients",
  },
}));

describe("ContractPayeeSearch", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [
            {
              id: 9,
              name: "Mentor Person",
              email: "mentor@example.com",
              officeId: 1,
              officeName: "Fairfax",
              officeState: "VA",
              licenseState: "VA",
              agentIdentifier: "M1",
            },
          ],
        }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("searches recipients and posts the selected payee id", async () => {
    const user = userEvent.setup();
    render(
      <form>
        <ContractPayeeSearch
          id="mentor_payee"
          name="mentor_payee_id"
          label="Mentor payee"
        />
      </form>,
    );

    await user.type(screen.getByLabelText(/mentor payee/i), "men");
    await user.click(await screen.findByRole("option", { name: /mentor person/i }));

    const hidden = document.querySelector(
      'input[name="mentor_payee_id"]',
    ) as HTMLInputElement;
    expect(hidden.value).toBe("9");
    expect(screen.getByText("Mentor Person")).toBeVisible();
  });

  it("hydrates from an initial payee", () => {
    render(
      <ContractPayeeSearch
        id="referral_payee"
        name="referral_payee_id"
        label="Referral payee"
        initialPayee={{
          id: 3,
          name: "Referral Agent",
          email: "ref@example.com",
          officeName: "Harrisburg",
        }}
      />,
    );

    expect(screen.getByText("Referral Agent")).toBeVisible();
    expect(screen.getByText(/ref@example\.com · Harrisburg/)).toBeVisible();
    expect(
      (document.querySelector('input[name="referral_payee_id"]') as HTMLInputElement)
        .value,
    ).toBe("3");
  });

  it("does not search while disabled", async () => {
    const user = userEvent.setup();
    render(
      <ContractPayeeSearch
        id="mentor_payee"
        name="mentor_payee_id"
        label="Mentor payee"
        disabled
      />,
    );

    await user.type(screen.getByLabelText(/mentor payee/i), "men");

    expect(fetch).not.toHaveBeenCalled();
  });
});
