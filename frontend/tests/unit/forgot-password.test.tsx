import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "@/app/(auth)/forgot-password/page";
import { I18nProvider } from "@/lib/i18n";

function mockFetch(responses: Array<{ status: number; body: unknown }>) {
  const fetchMock = vi.fn();
  for (const r of responses) {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(r.body), { status: r.status }));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  render(<I18nProvider><ForgotPasswordPage /></I18nProvider>);
}

async function requestCode() {
  await userEvent.type(screen.getByLabelText(/email address/i), "asha@example.com");
  await userEvent.click(screen.getByRole("button", { name: /send code/i }));
}

afterEach(() => vi.unstubAllGlobals());

describe("ForgotPasswordPage", () => {
  it("requests a code, then resets with code and new password", async () => {
    const fetchMock = mockFetch([
      { status: 200, body: { message: "sent" } },
      { status: 200, body: { message: "Your password has been reset." } },
    ]);
    renderPage();
    await requestCode();

    const code = await screen.findByLabelText(/6-digit code/i);
    await userEvent.type(code, "12a3456");
    expect(code).toHaveValue("123456"); // digits only
    await userEvent.type(screen.getByLabelText(/^new password/i), "brand-new-pass-77");
    await userEvent.type(screen.getByLabelText(/confirm new password/i), "brand-new-pass-77");
    await userEvent.click(screen.getByRole("button", { name: /reset password/i }));

    expect(await screen.findByText(/password has been changed/i)).toBeInTheDocument();
    const body = JSON.parse(fetchMock.mock.calls[1][1].body as string);
    expect(body).toEqual({ email: "asha@example.com", code: "123456", new_password: "brand-new-pass-77" });
  });

  it("blocks mismatched passwords and shows server errors", async () => {
    mockFetch([
      { status: 200, body: { message: "sent" } },
      { status: 400, body: { error: { code: "reset_invalid", message: "This code is incorrect." } } },
    ]);
    renderPage();
    await requestCode();
    await userEvent.type(await screen.findByLabelText(/6-digit code/i), "000000");
    await userEvent.type(screen.getByLabelText(/^new password/i), "brand-new-pass-77");
    await userEvent.type(screen.getByLabelText(/confirm new password/i), "different-pass-88");
    await userEvent.click(screen.getByRole("button", { name: /reset password/i }));
    expect(screen.getByText(/do not match/i)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/confirm new password/i));
    await userEvent.type(screen.getByLabelText(/confirm new password/i), "brand-new-pass-77");
    await userEvent.click(screen.getByRole("button", { name: /reset password/i }));
    expect(await screen.findByText(/code is incorrect/i)).toBeInTheDocument();
  });

  it("disables resend during the cooldown", async () => {
    mockFetch([{ status: 200, body: { message: "sent" } }]);
    renderPage();
    await requestCode();
    expect(await screen.findByRole("button", { name: /new code in/i })).toBeDisabled();
  });
});
