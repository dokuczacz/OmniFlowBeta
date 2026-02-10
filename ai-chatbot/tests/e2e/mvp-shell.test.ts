import { expect, test } from "@playwright/test";

test.describe("MVP Shell sanity", () => {
  test("env switch updates backend url and Gmail connect renders consent link", async ({
    page,
  }) => {
    // Stub /api/gmail so the test doesn't depend on real backend/oauth.
    await page.route("**/api/gmail", async (route) => {
      const req = route.request();
      let body: Record<string, unknown> = {};
      try {
        body = req.postDataJSON() as Record<string, unknown>;
      } catch {
        body = {};
      }
      const action = String(body.action || "");
      if (action === "oauth_status") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "ok",
            action: "oauth_status",
            result: { action: "oauth_status", authorized: false, user_id: "default" },
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          action: "ensure_authorized",
          result: {
            action: "ensure_authorized",
            authorized: false,
            user_id: "default",
            redirect_uri: "https://example.test/api/gmail_oauth_callback",
            authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?state=test",
          },
        }),
      });
    });

    await page.addInitScript(() => {
      // Prevent real popups during E2E.
      // @ts-expect-error test override
      window.open = () =>
        ({
          focus() {},
          location: { href: "about:blank" },
        }) as unknown as Window;

      localStorage.setItem("mvp_active_user", "default");
      localStorage.setItem("mvp_confirmed_user", "default");
      localStorage.setItem("mvp_env_mode", "prod");
      localStorage.setItem(
        "mvp_backend_url_prod",
        "https://agentbackendservice.example.test/api"
      );
      localStorage.setItem(
        "mvp_backend_url_dev",
        "http://localhost:7071/api/tool_call_handler"
      );
    });

    await page.goto("/mvp");

    const backendInput = page.getByTestId("mvp-backend-url");
    const envSelect = page.getByTestId("mvp-env-select");

    await expect(envSelect).toHaveValue("prod");
    // Normalized from ".../api" to ".../api/tool_call_handler"
    await expect(backendInput).toHaveValue(
      "https://agentbackendservice.example.test/api/tool_call_handler"
    );

    await envSelect.selectOption("dev");
    await expect(backendInput).toHaveValue(
      "http://localhost:7071/api/tool_call_handler"
    );

    await envSelect.selectOption("prod");
    await expect(backendInput).toHaveValue(
      "https://agentbackendservice.example.test/api/tool_call_handler"
    );

    await page.getByTestId("mvp-gmail-connect").click();
    const consent = page.getByTestId("mvp-gmail-consent-link");
    await expect(consent).toBeVisible();
    await expect(consent).toHaveAttribute(
      "data-authorize-url",
      /accounts\.google\.com\/o\/oauth2\/v2\/auth/
    );
  });
});
