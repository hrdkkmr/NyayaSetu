import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MessageCards } from "@/components/conversation/cards";
import { I18nProvider } from "@/lib/i18n";

function renderCards(cards: Parameters<typeof MessageCards>[0]["cards"], interactive = true) {
  const onReply = vi.fn();
  render(
    <I18nProvider>
      <MessageCards cards={cards} caseId="c1" onReply={onReply} interactive={interactive} />
    </I18nProvider>,
  );
  return onReply;
}

describe("MessageCards", () => {
  it("batch confirmation sends yes / no", async () => {
    const onReply = renderCards([{ type: "confirm_facts", keys: ["seller_name"] }]);
    await userEvent.click(screen.getByRole("button", { name: /all correct/i }));
    expect(onReply).toHaveBeenCalledWith("yes");
  });

  it("offers choices and a skip option for choice questions", async () => {
    const onReply = renderCards([{ type: "question", slot: "desired_remedy", confirm: false, value_type: "choice" }]);
    await userEvent.click(screen.getByRole("button", { name: "Refund" }));
    expect(onReply).toHaveBeenCalledWith("refund");
    await userEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(onReply).toHaveBeenCalledWith("skip");
  });

  it("hides quick replies on older messages", () => {
    renderCards([{ type: "confirm_facts", keys: [] }], false);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows rule outcomes with official source links", () => {
    renderCards([{
      type: "rule_outcome", key: "limitation", grounded: true, text: "File within two years.", caveats: [],
      basis: [{ document_key: "cpa_2019", section_ref: "Section 69", summary: "", chunk_id: "x",
                source_url: "https://egazette.gov.in/WriteReadData/2019/210422.pdf",
                document_title: "The Consumer Protection Act, 2019 (No. 35 of 2019)", verification_status: "fetched_official" }],
    }]);
    const link = screen.getByRole("link", { name: /Section 69/ });
    expect(link).toHaveAttribute("href", "https://egazette.gov.in/WriteReadData/2019/210422.pdf");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("renders helpline resources with tel links", () => {
    renderCards([{ type: "resources", items: [{ key: "legal_aid", name: "NALSA", phone: "15100", url: "https://nalsa.gov.in/", use: "Free legal aid" }] }]);
    expect(screen.getByRole("link", { name: /15100/ })).toHaveAttribute("href", "tel:15100");
  });
});
