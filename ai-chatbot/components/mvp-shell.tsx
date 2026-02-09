"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MVPChat } from "@/components/mvp-chat";

type UserEntry = {
  id: string;
  label: string;
};

export type GmailStatus = {
  authorized: boolean;
  email?: string;
  checkedAt?: string;
};

export function MVPShell({ initialBackendUrl }: { initialBackendUrl: string }) {
  const [backendUrl, setBackendUrl] = useState(initialBackendUrl);
  const [envMode, setEnvMode] = useState("prod");
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [activeUser, setActiveUser] = useState("");
  const [newUser, setNewUser] = useState("");
  const [confirmedUser, setConfirmedUser] = useState("");
  const [streamMode, setStreamMode] = useState("simulate");
  const [statusMessage, setStatusMessage] = useState("Waiting for input...");
  const [statusHistory, setStatusHistory] = useState<
    { id: string; label: string }[]
  >([]);

  // --- Gmail OAuth state ---
  const [gmailStatus, setGmailStatus] = useState<GmailStatus>({ authorized: false });
  const [gmailLoading, setGmailLoading] = useState(false);
  const gmailPopupRef = useRef<Window | null>(null);

  const checkGmailStatus = useCallback(async (userId: string) => {
    if (!userId) return;
    setGmailLoading(true);
    try {
      const resp = await fetch("/api/gmail", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "oauth_status", user_id: userId }),
      });
      const data = await resp.json().catch(() => ({}));
      const result = data?.result ?? data;
      const next: GmailStatus = {
        authorized: !!result?.authorized,
        email: result?.email ?? undefined,
        checkedAt: new Date().toISOString(),
      };
      setGmailStatus(next);
      if (typeof window !== "undefined") {
        localStorage.setItem(`mvp_gmail_status_${userId}`, JSON.stringify(next));
      }
    } catch {
      // keep previous status on transient failures
    } finally {
      setGmailLoading(false);
    }
  }, []);

  const handleConnectGmail = useCallback(async () => {
    if (!activeUser) return;
    setGmailLoading(true);
    try {
      const resp = await fetch("/api/gmail", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "oauth_authorize", user_id: activeUser }),
      });
      const data = await resp.json().catch(() => ({}));
      const authorizeUrl = data?.result?.authorize_url;
      if (!authorizeUrl) {
        setGmailLoading(false);
        return;
      }
      const popup = window.open(authorizeUrl, "gmail_oauth", "width=600,height=700");
      gmailPopupRef.current = popup;

      // Fallback: poll popup.closed every 1s
      const pollTimer = window.setInterval(() => {
        if (popup && popup.closed) {
          window.clearInterval(pollTimer);
          gmailPopupRef.current = null;
          void checkGmailStatus(activeUser);
        }
      }, 1000);
    } catch {
      setGmailLoading(false);
    }
  }, [activeUser, checkGmailStatus]);

  // Listen for postMessage from popup
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === "gmail_oauth_complete") {
        gmailPopupRef.current = null;
        if (activeUser) {
          void checkGmailStatus(activeUser);
        }
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [activeUser, checkGmailStatus]);

  // Restore persisted gmail status on user change
  useEffect(() => {
    if (!activeUser) {
      setGmailStatus({ authorized: false });
      return;
    }
    const stored = localStorage.getItem(`mvp_gmail_status_${activeUser}`);
    if (stored) {
      try {
        setGmailStatus(JSON.parse(stored) as GmailStatus);
      } catch {
        setGmailStatus({ authorized: false });
      }
    } else {
      setGmailStatus({ authorized: false });
    }
  }, [activeUser]);

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
    if (storedBackend) setBackendUrl(storedBackend);
    if (storedEnv) setEnvMode(storedEnv);
    if (storedStreamMode) setStreamMode(storedStreamMode);
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
    localStorage.setItem("mvp_backend_url", backendUrl);
  }, [backendUrl]);

  useEffect(() => {
    localStorage.setItem("mvp_env_mode", envMode);
  }, [envMode]);

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
    void checkGmailStatus(activeUser);
  };

  const handleChangeUser = () => {
    setActiveUser("");
    setConfirmedUser("");
  };

  const isUserConfirmed = !!activeUser && confirmedUser === activeUser;

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

        <div className="space-y-3 rounded-xl border border-border/40 bg-muted/20 p-3">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Gmail
          </div>
          {gmailStatus.authorized ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              <span className="truncate">{gmailStatus.email || "Connected"}</span>
            </div>
          ) : (
            <Button
              type="button"
              variant="secondary"
              className="w-full"
              disabled={gmailLoading || !activeUser}
              onClick={handleConnectGmail}
            >
              {gmailLoading ? "Connecting..." : "Connect Gmail"}
            </Button>
          )}
        </div>

        <div className="space-y-3 rounded-xl border border-dashed border-border/50 bg-background/60 p-3">
          <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Environment
          </Label>
          <select
            className="w-full rounded-xl border border-border/60 bg-background px-3 py-2 text-sm"
            value={envMode}
            onChange={(event) => setEnvMode(event.target.value)}
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
            placeholder={
              initialBackendUrl || "http://localhost:7071/api/tool_call_handler"
            }
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
              gmailStatus={gmailStatus}
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
