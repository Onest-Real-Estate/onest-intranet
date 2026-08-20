import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { FileUploader } from "@/components/design-system/file-uploader";

describe("FileUploader", () => {
  it("shows server failure and retries the same file", async () => {
    const user = userEvent.setup();
    const upload = vi
      .fn()
      .mockRejectedValueOnce(new Error("Your session expired. Sign in and retry."))
      .mockResolvedValueOnce({ name: "agreement.pdf" });
    const { container } = render(<FileUploader upload={upload} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["agreement"], "agreement.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });
    expect(
      await screen.findByText("Your session expired. Sign in and retry."),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Upload complete")).toBeVisible();
    expect(upload).toHaveBeenCalledTimes(2);
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <FileUploader upload={vi.fn()} description="PDF up to 5 MB" />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
