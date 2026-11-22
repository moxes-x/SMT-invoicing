import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Providers } from "@/providers";
import { OnboardingPage } from "./onboarding";

function renderPage() {
  const router = createMemoryRouter(
    [
      { path: "/onboarding", element: <OnboardingPage /> },
      { path: "/", element: <p>home</p> },
    ],
    { initialEntries: ["/onboarding"] },
  );
  render(
    <Providers client={new QueryClient()}>
      <RouterProvider router={router} />
    </Providers>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("OnboardingPage", () => {
  it("requires a name and a VAT answer", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Enter your business name.")).toBeInTheDocument();
    expect(screen.getByText("Choose yes or no.")).toBeInTheDocument();
  });

  it("explains ZRA Smart Invoice when the business is VAT-registered", async () => {
    renderPage();
    expect(screen.queryByText(/ZRA Smart Invoice/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Yes"));
    expect(screen.getByText(/ZRA Smart Invoice/)).toBeInTheDocument();
  });

  it("shows server field errors next to the field", async () => {
    document.cookie = "csrftoken=abc";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ phone: ["Enter a valid phone number."] }), { status: 400 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await userEvent.type(screen.getByLabelText("Business name"), "Chanda Salon");
    await userEvent.type(screen.getByLabelText("Phone (optional)"), "12");
    await userEvent.click(screen.getByText("No"));
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Enter a valid phone number.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/businesses/");
    expect(new Headers(init.headers).get("X-CSRFToken")).toBe("abc");
    expect(JSON.parse(init.body)).toMatchObject({ name: "Chanda Salon", vat_registered: false });
  });
});
