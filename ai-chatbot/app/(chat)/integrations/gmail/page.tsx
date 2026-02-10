"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type GmailStatus = {
  action?: string;
  authorized?: boolean;
  user_id?: string;
  email_address?: string;
  scope?: string;
  expires_at?: string;
  saved_at?: string;
  authorize_url?: string;
  redirect_uri?: string;
  state?: string;
};

const LS_USER_ID = "omniflow_gmail_user_id";
const LS_BACKEND_URL = "omniflow_gmail_backend_url_override";

export default function GmailIntegrationPage() {
  const [userId, setUserId] = useState("");
  const [backendUrlOverride, setBackendUrlOverride] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [raw, setRaw] = useState<string>("");
  const [popupBlocked, setPopupBlocked] = useState(false);

  useEffect(() => {
    const storedUserId = localStorage.getItem(LS_USER_ID);
    const storedBackendUrl = localStorage.getItem(LS_BACKEND_URL);
    if (storedUserId) setUserId(storedUserId);
    if (storedBackendUrl) setBackendUrlOverride(storedBackendUrl);
  }, []);

  useEffect(() => {
    localStorage.setItem(LS_USER_ID, userId);
  }, [userId]);

  useEffect(() => {
    localStorage.setItem(LS_BACKEND_URL, backendUrlOverride);
  }, [backendUrlOverride]);

  const requestBody = useMemo(() => {
    const trimmedUser = userId.trim();
    const trimmedBackend = backendUrlOverride.trim();
    return {
      user_id: trimmedUser || null,
      backend_url: trimmedBackend || null,
    };
  }, [userId, backendUrlOverride]);

  const gmailCall = async (action: string, payload: Record<string, unknown> = {}) => {
    const trimmedUser = userId.trim();
    if (!trimmedUser) {
      setError("Missing user_id");
      return null;
    }
    setBusy(true);
    setError("");
    setRaw("");
    try {
      const resp = await fetch("/api/gmail", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          payload,
          ...requestBody,
        }),
      });
      const data = (await resp.json().catch(() => ({}))) as Record<
        string,
        unknown
      >;
      setRaw(JSON.stringify(data, null, 2));
      if (!resp.ok) {
        const msg =
          typeof data.message === "string"
            ? data.message
            : typeof data.error === "string"
              ? data.error
              : JSON.stringify(data);
        setError(msg);
        return null;
      }
      const result =
        data.result && typeof data.result === "object"
          ? (data.result as GmailStatus)
          : (data as GmailStatus);
      setStatus(result);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const startOAuthPolling = () => {
    let tries = 0;
    const maxTries = 60;
    const timer = window.setInterval(() => {
      tries += 1;
      void gmailCall("oauth_status").then((next) => {
        if (next?.authorized) {
          window.clearInterval(timer);
        }
      });
      if (tries >= maxTries) {
        window.clearInterval(timer);
      }
    }, 2000);
  };

  const handleConnect = () => {
    if (busy || !userId.trim()) return;

    const w = 720;
    const h = 900;
    const left = Math.max(0, Math.floor(window.screenX + (window.outerWidth - w) / 2));
    const top = Math.max(0, Math.floor(window.screenY + (window.outerHeight - h) / 2));
    const popup = window.open(
      "about:blank",
      "omniflow_gmail_oauth",
      `popup=yes,width=${w},height=${h},left=${left},top=${top}`
    );
    setPopupBlocked(!popup);

    void gmailCall("ensure_authorized").then((next) => {
      const url = String(next?.authorize_url || "").trim();
      if (!url) return;
      if (popup) {
        try {
          popup.location.href = url;
          popup.focus();
        } catch {
          window.location.assign(url);
        }
      } else {
        window.location.assign(url);
      }
      startOAuthPolling();
    });
  };

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-6">
      <Card>
        <CardHeader>
          <CardTitle>Gmail Integration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>User ID (OmniFlow)</Label>
            <Input
              placeholder="e.g. default"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>Backend URL override (optional)</Label>
            <Input
              placeholder="Leave empty to use OMNIFLOW_BACKEND_URL"
              value={backendUrlOverride}
              onChange={(e) => setBackendUrlOverride(e.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={busy || !userId.trim()}
              onClick={() => void gmailCall("oauth_status")}
            >
              Status
            </Button>
            <Button
              type="button"
              disabled={busy || !userId.trim()}
              onClick={handleConnect}
            >
              Connect
            </Button>
          </div>

          {error ? (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          {status ? (
            <div className="space-y-2 text-sm text-muted-foreground">
              <div>
                Authorized:{" "}
                <span className="font-mono">{String(!!status.authorized)}</span>
              </div>
              {status.expires_at ? (
                <div>
                  expires_at: <span className="font-mono">{status.expires_at}</span>
                </div>
              ) : null}
              {status.redirect_uri ? (
                <div>
                  redirect_uri:{" "}
                  <span className="font-mono">{status.redirect_uri}</span>
                </div>
              ) : null}
              {status.authorize_url ? (
                <button
                  className="inline-flex items-center gap-2 underline underline-offset-4"
                  onClick={handleConnect}
                  type="button"
                >
                  Open Google consent
                </button>
              ) : null}
              {popupBlocked ? (
                <div className="text-xs text-muted-foreground/80">
                  Popup blocked. Opened in current tab instead.
                </div>
              ) : null}
              {raw ? (
                <details>
                  <summary className="cursor-pointer select-none text-muted-foreground/80">
                    Raw JSON
                  </summary>
                  <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-border/40 bg-background/40 p-2 font-mono text-[11px] leading-snug text-foreground/80">
                    {raw}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              Click Status to check if tokens exist for this `user_id`.
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
