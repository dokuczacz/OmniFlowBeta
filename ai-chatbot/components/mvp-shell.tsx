"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MVPChat } from "@/components/mvp-chat";

type UserEntry = {
  id: string;
  label: string;
};

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

function normalizeToolCallHandlerUrl(input: string): string {
  const raw = (input || "").trim().replace(/\/+$/, "");
  if (!raw) return "";
  if (raw.includes("/api/tool_call_handler")) return raw;
  if (raw.includes("/api/custom_bridge")) {
    const base = raw.split("/api/")[0]?.replace(/\/+$/, "") ?? "";
    return base ? `${base}/api/tool_call_handler` : raw;
  }
  if (raw.endsWith("/api")) return `${raw}/tool_call_handler`;
  if (raw.includes("/api/")) return raw;
  return `${raw}/api/tool_call_handler`;
}

export function MVPShell({
  initialBackendUrl,
  initialBackendUrlProd,
}: {
  initialBackendUrl: string;
  initialBackendUrlProd?: string;
}) {
  const [backendUrl, setBackendUrl] = useState(
    normalizeToolCallHandlerUrl(initialBackendUrl)
  );
  const [envMode, setEnvMode] = useState("prod");
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [activeUser, setActiveUser] = useState("");
  const [newUser, setNewUser] = useState("");
  const [confirmedUser, setConfirmedUser] = useState("");
  const [streamMode, setStreamMode] = useState("simulate");
  const [hydrated, setHydrated] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Waiting for input...");
  const [statusHistory, setStatusHistory] = useState<
    { id: string; label: string }[]
  >([]);
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [gmailError, setGmailError] = useState<string>("");
  const [gmailBusy, setGmailBusy] = useState<boolean>(false);
  const [gmailRaw, setGmailRaw] = useState<string>("");
  const [gmailPopupBlocked, setGmailPopupBlocked] = useState(false);

  const backendKeyForEnv = (mode: string) =>
    mode === "prod" ? "mvp_backend_url_prod" : "mvp_backend_url_dev";

  const applyEnvPreset = useCallback(
    (mode: string) => {
      const stored = localStorage.getItem(backendKeyForEnv(mode));
      if (stored && stored.trim()) {
        const normalized = normalizeToolCallHandlerUrl(stored);
        if (
          mode === "prod" &&
          normalized.includes("localhost:7071") &&
          initialBackendUrlProd &&
          !initialBackendUrlProd.includes("localhost:7071")
        ) {
          const fixed = normalizeToolCallHandlerUrl(initialBackendUrlProd.trim());
          setBackendUrl(fixed);
          localStorage.setItem("mvp_backend_url_prod", fixed);
          return;
        }
        setBackendUrl(normalized);
        return;
      }
      if (mode === "dev") {
        setBackendUrl("http://localhost:7071/api/tool_call_handler");
        return;
      }
      if (initialBackendUrlProd && initialBackendUrlProd.trim()) {
        setBackendUrl(normalizeToolCallHandlerUrl(initialBackendUrlProd.trim()));
        return;
      }
      if (initialBackendUrl && initialBackendUrl.trim()) {
        setBackendUrl(normalizeToolCallHandlerUrl(initialBackendUrl.trim()));
      }
    },
    [initialBackendUrl, initialBackendUrlProd]
  );
  const logFrontEnd = useCallback(
    (status: string, threadId: string | null) => {
      const payload = {
        user: activeUser || "(none)",
        thread_id: threadId,
        status,
      };
      if (typeof window === "undefined") return;
      fetch("/api/log-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: JSON.stringify(payload) }),
      }).catch(() => {});
    },
    [activeUser]
  );
  const handleStatusUpdate = useCallback(
    (status: string, threadId: string | null) => {
      setStatusMessage(status);
      setStatusHistory((prev) => {
        const entry = {
          id: crypto.randomUUID(),
          label: `${new Date().toLocaleTimeString()} - ${status}`,
        };
        return [entry, ...prev].slice(0, 4);
      });
      logFrontEnd(status, threadId);
    },
    [logFrontEnd]
  );

  useEffect(() => {
    const storedUsers = localStorage.getItem("mvp_users");
    const storedActive = localStorage.getItem("mvp_active_user");
    const storedBackend = localStorage.getItem("mvp_backend_url");
    const storedBackendProd = localStorage.getItem("mvp_backend_url_prod");
    const storedBackendDev = localStorage.getItem("mvp_backend_url_dev");
    const storedEnv = localStorage.getItem("mvp_env_mode");
    const storedConfirmed = localStorage.getItem("mvp_confirmed_user");
    const storedStreamMode = localStorage.getItem("mvp_stream_mode");

    if (storedUsers) {
      try {
        const parsed = JSON.parse(storedUsers) as UserEntry[];
        const normalized = Array.isArray(parsed) ? parsed : [];
        if (storedActive && !normalized.some((user) => user.id === storedActive)) {
          normalized.push({ id: storedActive, label: storedActive });
        }
        setUsers(normalized);
      } catch {
        setUsers(
          storedActive ? [{ id: storedActive, label: storedActive }] : []
        );
      }
    } else if (storedActive) {
      setUsers([{ id: storedActive, label: storedActive }]);
    }
    if (storedActive) setActiveUser(storedActive);
    if (storedConfirmed) setConfirmedUser(storedConfirmed);

    // Migration guard: older builds could accidentally store dev URL as prod URL.
    if (
      storedBackendProd &&
      storedBackendProd.includes("localhost:7071") &&
      initialBackendUrlProd &&
      !initialBackendUrlProd.includes("localhost:7071")
    ) {
      localStorage.setItem(
        "mvp_backend_url_prod",
        normalizeToolCallHandlerUrl(initialBackendUrlProd)
      );
    }

    // Backward-compat: older builds stored only `mvp_backend_url`.
    if (storedBackendProd || storedBackendDev) {
      const nextEnv = storedEnv || "prod";
      setEnvMode(nextEnv);
      const nextUrl =
        (nextEnv === "prod"
          ? localStorage.getItem("mvp_backend_url_prod")
          : storedBackendDev) ||
        storedBackend ||
        initialBackendUrl ||
        "";
      setBackendUrl(normalizeToolCallHandlerUrl(nextUrl));
    } else {
      if (storedBackend) setBackendUrl(normalizeToolCallHandlerUrl(storedBackend));
      if (storedEnv) setEnvMode(storedEnv);
    }
    if (storedStreamMode) setStreamMode(storedStreamMode);

    // Allow env switching + persistence only after first localStorage load.
    setHydrated(true);
  }, []);

  useEffect(() => {
    localStorage.setItem("mvp_users", JSON.stringify(users));
  }, [users]);

  useEffect(() => {
    localStorage.setItem("mvp_active_user", activeUser);
  }, [activeUser]);

  useEffect(() => {
    localStorage.setItem("mvp_confirmed_user", confirmedUser);
  }, [confirmedUser]);

  useEffect(() => {
    if (!activeUser) {
      setConfirmedUser("");
      return;
    }
    if (confirmedUser && confirmedUser !== activeUser) {
      setConfirmedUser("");
    }
  }, [activeUser, confirmedUser]);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem("mvp_backend_url", backendUrl);
  }, [backendUrl, envMode, hydrated]);

  useEffect(() => {
    localStorage.setItem("mvp_env_mode", envMode);
  }, [envMode]);

  // Env switching is handled eagerly in the env dropdown `onChange` to avoid
  // races between initial localStorage hydration and user interaction.

  useEffect(() => {
    localStorage.setItem("mvp_stream_mode", streamMode);
  }, [streamMode]);

  const userOptions = useMemo(() => {
    const base = users.length > 0 ? users : [{ id: "demo", label: "demo" }];
    if (activeUser && !base.some((user) => user.id === activeUser)) {
      return [...base, { id: activeUser, label: activeUser }];
    }
    return base;
  }, [users, activeUser]);

  const handleAddUser = () => {
    const trimmed = newUser.trim();
    if (!trimmed) return;
    if (users.some((user) => user.id === trimmed)) {
      setNewUser("");
      return;
    }
    const entry = { id: trimmed, label: trimmed };
    setUsers((prev) => [...prev, entry]);
    setActiveUser(trimmed);
    setConfirmedUser("");
    setNewUser("");
  };

  const handleConfirmUser = () => {
    if (!activeUser) return;
    setConfirmedUser(activeUser);
  };

  const handleChangeUser = () => {
    setActiveUser("");
    setConfirmedUser("");
  };

  const isUserConfirmed = !!activeUser && confirmedUser === activeUser;

  const gmailCall = async (action: string, payload: Record<string, unknown> = {}) => {
    return gmailCallInternal(action, payload, { background: false });
  };

  const gmailCallInternal = async (
    action: string,
    payload: Record<string, unknown> = {},
    opts: { background: boolean }
  ) => {
    if (!activeUser) {
      setGmailError("Pick active user first.");
      return null;
    }
    if (!opts.background) {
      setGmailBusy(true);
      setGmailError("");
      setGmailRaw("");
    }
    try {
      const resp = await fetch("/api/gmail", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          payload,
          user_id: activeUser,
          backend_url: backendUrl || null,
        }),
      });
      const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
      if (!opts.background) setGmailRaw(JSON.stringify(data, null, 2));
      if (!resp.ok) {
        const msg = (() => {
          // Prefer the full structured payload if it contains diagnostics.
          if (
            data &&
            typeof data === "object" &&
            ("status" in data || "target_url" in data || "body_excerpt" in data)
          ) {
            return JSON.stringify(data, null, 2);
          }
          if (typeof data.message === "string") return data.message;
          if (typeof data.error === "string") return data.error;
          return JSON.stringify(data);
        })();
        if (!opts.background) setGmailError(msg);
        return null;
      }

      // `custom_bridge` returns top-level fields (not wrapped in `{ result: ... }`).
      const result =
        data.result && typeof data.result === "object"
          ? (data.result as Record<string, unknown>)
          : data;
      const nextStatus = result as GmailStatus;
      setGmailStatus((prev) => {
        const prevKey = prev ? JSON.stringify(prev) : "";
        const nextKey = JSON.stringify(nextStatus);
        return prevKey === nextKey ? prev : nextStatus;
      });
      return result as GmailStatus;
    } catch (err) {
      if (!opts.background) {
        setGmailError(err instanceof Error ? err.message : "Request failed");
      }
      return null;
    } finally {
      if (!opts.background) setGmailBusy(false);
    }
  };

  const startOAuthPolling = () => {
    let tries = 0;
    const maxTries = 60; // ~2 min at 2s interval
    const timer = window.setInterval(() => {
      tries += 1;
      void gmailCallInternal("oauth_status", {}, { background: true }).then((next) => {
        if (next?.authorized) {
          window.clearInterval(timer);
        }
      });
      if (tries >= maxTries) {
        window.clearInterval(timer);
      }
    }, 2000);
  };

  useEffect(() => {
    if (!hydrated) return;
    if (!activeUser) {
      setGmailStatus(null);
      setGmailError("");
      return;
    }
    void gmailCallInternal("oauth_status", {}, { background: true });
  }, [activeUser, backendUrl, hydrated]);

  const handleGmailConnect = () => {
    if (!activeUser || gmailBusy) return;

    // Must be opened synchronously from the user click to avoid popup blockers.
    const w = 720;
    const h = 900;
    const left = Math.max(0, Math.floor(window.screenX + (window.outerWidth - w) / 2));
    const top = Math.max(0, Math.floor(window.screenY + (window.outerHeight - h) / 2));
    const popup = window.open(
      "about:blank",
      "omniflow_gmail_oauth",
      `popup=yes,width=${w},height=${h},left=${left},top=${top}`
    );
    setGmailPopupBlocked(!popup);

    void gmailCall("ensure_authorized").then((next) => {
      const url = String(next?.authorize_url || "").trim();
      if (!url) {
        try {
          popup?.close();
        } catch {
          // ignore
        }
        return;
      }
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
    <section className="flex h-screen bg-background/80">
      <aside className="flex w-72 flex-col gap-6 border-r border-border/40 bg-background/90 px-4 py-5 text-sm">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-primary" />
          OmniFlow MVP
        </div>

        <div className="space-y-3 rounded-xl border border-border/40 bg-muted/20 p-3">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Active user
          </div>
          <select
            className="w-full rounded-xl border border-border/60 bg-background px-3 py-2 text-sm"
            value={activeUser}
            onChange={(event) => setActiveUser(event.target.value)}
          >
            <option value="">(none)</option>
            {userOptions.map((user) => (
              <option key={user.id} value={user.id}>
                {user.label}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <Input
              placeholder="Add user id"
              value={newUser}
              onChange={(event) => setNewUser(event.target.value)}
            />
            <Button type="button" onClick={handleAddUser}>
              Add
            </Button>
          </div>
        </div>

        <div className="space-y-3 rounded-xl border border-dashed border-border/50 bg-background/60 p-3">
          <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Environment
          </Label>
          <select
            className="w-full rounded-xl border border-border/60 bg-background px-3 py-2 text-sm"
            value={envMode}
            onChange={(event) => {
              const next = event.target.value;
              setEnvMode(next);
              applyEnvPreset(next);
            }}
            data-testid="mvp-env-select"
          >
            <option value="prod">prod</option>
            <option value="dev">dev</option>
          </select>
          <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Backend URL
          </Label>
          <Input
            value={backendUrl}
            onChange={(event) => setBackendUrl(event.target.value)}
            onBlur={() => {
              const normalized = normalizeToolCallHandlerUrl(backendUrl);
              setBackendUrl(normalized);
              if (hydrated) {
                localStorage.setItem("mvp_backend_url", normalized);
                localStorage.setItem(backendKeyForEnv(envMode), normalized);
              }
            }}
            placeholder={
              initialBackendUrl || "http://localhost:7071/api/tool_call_handler"
            }
            data-testid="mvp-backend-url"
          />
          <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Streaming
          </Label>
          <select
            className="w-full rounded-xl border border-border/60 bg-background px-3 py-2 text-sm"
            value={streamMode}
            onChange={(event) => setStreamMode(event.target.value)}
          >
            <option value="off">off</option>
            <option value="simulate">simulate</option>
          </select>
          <div className="rounded-xl border border-border/50 bg-background/20 px-3 py-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
            {statusMessage}
          </div>
          {statusHistory.length > 0 && (
            <div className="space-y-1 text-[11px] text-muted-foreground/80">
              {statusHistory.map((item) => (
                <div key={item.id}>{item.label}</div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-3 rounded-xl border border-border/40 bg-muted/20 p-3">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Gmail OAuth
          </div>
          <Button
            disabled={!activeUser || gmailBusy || !!gmailStatus?.authorized}
            onClick={handleGmailConnect}
            type="button"
            data-testid="mvp-gmail-connect"
          >
            {gmailStatus?.authorized ? "Connected" : "Connect"}
          </Button>
          {gmailError ? (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-2 py-1 text-xs text-destructive">
              {gmailError}
            </div>
          ) : null}
          {gmailStatus ? (
            <div className="space-y-1 text-xs text-muted-foreground">
              <div>
                <span
                  className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                  style={{
                    backgroundColor: gmailStatus.authorized ? "#16a34a" : "#ef4444",
                  }}
                />
                <span className="align-middle">
                  {gmailStatus.authorized ? "Connected" : "Not connected"}
                </span>
              </div>
              {gmailStatus.email_address ? (
                <div>
                  account: <span className="font-mono">{gmailStatus.email_address}</span>
                </div>
              ) : null}
              {gmailStatus.expires_at ? (
                <div>
                  expires_at: <span className="font-mono">{gmailStatus.expires_at}</span>
                </div>
              ) : null}
              {gmailStatus.redirect_uri ? (
                <div>
                  redirect_uri: <span className="font-mono">{gmailStatus.redirect_uri}</span>
                </div>
              ) : null}
              {gmailStatus.authorize_url ? (
                <button
                  className="inline-flex items-center gap-2 underline underline-offset-4"
                  onClick={handleGmailConnect}
                  type="button"
                  data-testid="mvp-gmail-consent-link"
                  data-authorize-url={gmailStatus.authorize_url}
                >
                  Open Google consent
                </button>
              ) : null}
              {gmailPopupBlocked ? (
                <div className="text-[10px] text-muted-foreground/80">
                  Popup blocked. Opened in current tab instead.
                </div>
              ) : null}
              {gmailRaw ? (
                <details className="pt-2">
                  <summary className="cursor-pointer select-none text-muted-foreground/80">
                    Raw JSON
                  </summary>
                  <pre className="mt-2 max-h-56 overflow-auto rounded-md border border-border/40 bg-background/40 p-2 font-mono text-[10px] leading-snug text-foreground/80">
                    {gmailRaw}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">
              Configure Gmail tokens for this user in storage.
            </div>
          )}
        </div>

        <div className="mt-auto text-xs text-muted-foreground">
          Status: {activeUser ? "Ready" : "Pick active user"}
        </div>
      </aside>

      <main className="relative flex flex-1 flex-col p-4">
        <div className="flex h-full flex-col rounded-xl border border-border/40 bg-background/90">
          <div className="border-b border-border/40 px-4 py-3 text-sm uppercase tracking-[0.2em] text-muted-foreground">
            Conversation
          </div>
          <div className="flex-1 overflow-hidden p-4">
            <MVPChat
              backendUrl={backendUrl}
              activeUser={activeUser}
              chatEnabled={isUserConfirmed}
              streamMode={streamMode}
              onStatusUpdate={(status, threadId) =>
                handleStatusUpdate(status, threadId)
              }
            />
          </div>
        </div>

        {!isUserConfirmed && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 backdrop-blur-sm">
            <div className="w-full max-w-md rounded-xl border border-border/50 bg-background/95 p-6 text-sm shadow-lg">
              <div className="mb-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                Confirm active user
              </div>
              <div className="mb-4 text-base">
                Aktywny uzytkownik:{" "}
                <span className="font-semibold">
                  {activeUser || "(none)"}
                </span>
              </div>
              <div className="mb-4 text-muted-foreground">
                Potwierdz uzytkownika, aby odblokowac czat.
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  onClick={handleConfirmUser}
                  disabled={!activeUser}
                >
                  Confirm
                </Button>
                <Button type="button" variant="secondary" onClick={handleChangeUser}>
                  Change user
                </Button>
              </div>
            </div>
          </div>
        )}
      </main>
    </section>
  );
}
