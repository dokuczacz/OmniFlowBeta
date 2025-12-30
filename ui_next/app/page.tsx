"use client";

import { useMemo, useState } from "react";

type ChatMessage = {
  role: "Użytkownik" | "Asystent";
  text: string;
};

type ToolCall = {
  name: string;
  status: string;
  durationMs: number | null;
  args: string;
};

type InteractionEntry = {
  threadId: string;
  timestamp: string;
  toolCalls: ToolCall[];
};

const modules = [
  {
    id: "chat",
    label: "Chat Operacyjny",
    status: "LIVE",
    summary: "Główne miejsce do rozmów z agentem i monitorowania odpowiedzi.",
    details: [
      "Historia rozmowy z narzędziami i runtime.",
      "Przyciski szybkich komend dla operacji.",
      "Podgląd metadanych z tool_call_handler.",
    ],
  },
  {
    id: "agent",
    label: "Sterowanie Agentem",
    status: "BETA",
    summary: "Zarządzanie agentem, trybem działania oraz priorytetami.",
    details: [
      "Wybór profilu agenta i runtime.",
      "Sekcja zadań i priorytetów do wykonania.",
      "Checkpointy i wyciszenie alertów.",
    ],
  },
  {
    id: "runs",
    label: "Runs & Reports",
    status: "NEW",
    summary: "Szybki przegląd ostatnich uruchomień i metryk.",
    details: [
      "Lista ostatnich runów z czasem i statusem.",
      "Metryki runtime, liczba tool calls, opóźnienia.",
      "Eksport raportu do PDF/CSV (docelowo).",
    ],
  },
  {
    id: "context",
    label: "Context Builder",
    status: "NEXT",
    summary: "Budowanie paczki kontekstu przed wysłaniem do runtime.",
    details: [
      "Źródła HOT/MOD/COLD i selekcja blobów.",
      "Podgląd limitów token/bytes.",
      "Scalanie kontekstu i walidacja wersji.",
    ],
  },
];

const starterMessages: ChatMessage[] = [
  {
    role: "Użytkownik",
    text: "Przygotuj podsumowanie działań z ostatnich 24h i wskaż opóźnienia.",
  },
  {
    role: "Asystent",
    text: "Zebrałem 12 runów. 2 mają opóźnienie > 2s, oba w narzędziu storage.read_many_blobs.",
  },
];

const starterHistory: InteractionEntry[] = [
  {
    threadId: "thread_demo",
    timestamp: "2025-01-07 12:04",
    toolCalls: [
      {
        name: "read_many_blobs",
        status: "success",
        durationMs: 182,
        args: "files=2, max_bytes_per_file=120k",
      },
    ],
  },
];

const contextItems = [
  "blob://hot/briefs/2025-01-07",
  "blob://mod/reports/weekly-ops.pdf",
  "blob://cold/logs/agent-telemetry.json",
];

export default function HomePage() {
  const [activeModuleId, setActiveModuleId] = useState(modules[0].id);
  const [knownUsers, setKnownUsers] = useState(["mario_bros", "ops_team"]);
  const [activeUser, setActiveUser] = useState("mario_bros");
  const [newUserId, setNewUserId] = useState("");
  const [backendUrl, setBackendUrl] = useState(
    process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:7071"
  );
  const [threadId, setThreadId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(starterMessages);
  const [history, setHistory] = useState<InteractionEntry[]>(starterHistory);
  const [messageInput, setMessageInput] = useState("");
  const [statusMessage, setStatusMessage] = useState("Gotowy do wysyłki.");
  const [statusError, setStatusError] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [runStats, setRunStats] = useState([
    { label: "Średni runtime", value: "—" },
    { label: "Tool calls", value: "—" },
    { label: "Success rate", value: "—" },
    { label: "Token budget", value: "—" },
  ]);

  const activeModule = useMemo(
    () => modules.find((module) => module.id === activeModuleId) ?? modules[0],
    [activeModuleId]
  );

  const handleAddUser = () => {
    const trimmed = newUserId.trim().toLowerCase();
    if (!trimmed) {
      return;
    }
    if (!knownUsers.includes(trimmed)) {
      setKnownUsers((prev) => [...prev, trimmed]);
    }
    setActiveUser(trimmed);
    setNewUserId("");
  };

  const handleSend = async () => {
    if (!messageInput.trim() || isSending) {
      return;
    }
    const userMessage = messageInput.trim();
    setIsSending(true);
    setStatusError(false);
    setStatusMessage("Wysyłanie do tool_call_handler...");
    setChatMessages((prev) => [...prev, { role: "Użytkownik", text: userMessage }]);
    setMessageInput("");

    try {
      const response = await fetch(`${backendUrl.replace(/\/$/, "")}/api/tool_call_handler`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": activeUser,
        },
        body: JSON.stringify({
          message: userMessage,
          thread_id: threadId,
          runtime: "responses",
        }),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.error ?? "tool_call_handler failed");
      }

      setThreadId(result.thread_id ?? threadId);
      setChatMessages((prev) => [
        ...prev,
        { role: "Asystent", text: result.response ?? "Brak odpowiedzi." },
      ]);

      setRunStats([
        { label: "Średni runtime", value: `${(result.timings?.total_ms ?? 0).toFixed(0)}ms` },
        { label: "Tool calls", value: String(result.tool_calls_count ?? 0) },
        { label: "Runtime", value: result.runtime_used ?? "—" },
        { label: "Thread", value: result.thread_id ?? "—" },
      ]);

      setStatusMessage("Pobrano odpowiedź. Pobieram historię interakcji...");

      const historyResponse = await fetch(`${backendUrl.replace(/\/$/, "")}/api/tool_call_handler`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": activeUser,
        },
        body: JSON.stringify({
          action: "get_interaction_history",
          params: {
            thread_id: result.thread_id ?? threadId,
            limit: 5,
          },
        }),
      });

      const historyResult = await historyResponse.json();
      if (!historyResponse.ok) {
        throw new Error(historyResult?.error ?? "get_interaction_history failed");
      }

      const interactions = historyResult?.result?.interactions ?? [];
      const mappedHistory = interactions.map((entry: any) => ({
        threadId: entry.thread_id ?? "—",
        timestamp: entry.timestamp ?? "—",
        toolCalls: (entry.tool_calls ?? []).map((tool: any) => ({
          name: tool.tool_name ?? tool.name ?? "tool",
          status: tool.status ?? "unknown",
          durationMs: tool.duration_ms ?? null,
          args: tool.arguments
            ? JSON.stringify(tool.arguments)
            : tool.args
              ? String(tool.args)
              : "—",
        })),
      }));

      if (mappedHistory.length > 0) {
        setHistory(mappedHistory);
      }

      setStatusMessage("Historia zaktualizowana.");
    } catch (error) {
      setStatusError(true);
      setStatusMessage(
        error instanceof Error ? error.message : "Nie udało się pobrać danych."
      );
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main>
      <aside className="sidebar">
        <div className="brand">
          <span>Ω</span>
          OmniFlow Beta
        </div>

        <div className="nav-card">
          <p className="label">Moduły</p>
          <ul className="nav-list">
            {modules.map((item) => (
              <li
                key={item.id}
                className={`nav-item ${item.id === activeModuleId ? "active" : ""}`}
                onClick={() => setActiveModuleId(item.id)}
              >
                <span>{item.label}</span>
                <span className="tag">{item.status}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel login-card">
          <p className="label">Szybkie logowanie</p>
          <input className="input" placeholder="user_id" value={activeUser} readOnly />
          <input className="input" placeholder="hasło" type="password" defaultValue="••••••••" />
          <button className="button" type="button">
            Aktywuj sesję
          </button>
          <div className="footer-note">
            UI tylko ustawia nagłówek <strong>X-User-Id</strong>. Dostęp chroni backend.
          </div>
        </div>

        <div className="panel">
          <p className="label">Backend URL</p>
          <input
            className="input"
            value={backendUrl}
            onChange={(event) => setBackendUrl(event.target.value)}
          />
          <div className="footer-note">Używane do wywołań tool_call_handler.</div>
        </div>

        <div className="panel">
          <p className="label">Użytkownicy</p>
          <div className="user-list">
            {knownUsers.map((user) => (
              <button
                key={user}
                type="button"
                className={`user-item ${user === activeUser ? "active" : ""}`}
                onClick={() => setActiveUser(user)}
              >
                <span>{user}</span>
                <span className="tag">active</span>
              </button>
            ))}
          </div>
          <div className="chat-input" style={{ marginTop: 12 }}>
            <input
              className="input"
              placeholder="Nowy user_id"
              value={newUserId}
              onChange={(event) => setNewUserId(event.target.value)}
            />
            <button className="button secondary" type="button" onClick={handleAddUser}>
              Dodaj
            </button>
          </div>
          <div className="footer-note">
            Prosty switch użytkowników jak w poprzednim Streamlit.
          </div>
        </div>
      </aside>

      <section>
        <div className="primary-header">
          <div className="header-left">
            <div className="header-title">Panel Operacyjny Chatbota</div>
            <div className="footer-note">
              Aktualny user: <strong>{activeUser}</strong> · Project: OmniFlow Beta
            </div>
          </div>
          <div className="segmented">
            <span className="active">prod</span>
            <span>dev</span>
          </div>
        </div>

        <div className="panel chat-shell">
          <div className="label">Chat MVP</div>
          <div className={`status-badge ${statusError ? "error" : ""}`}>
            <span />
            {statusMessage}
          </div>
          <div className="chat-history">
            {chatMessages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`message ${message.role === "Asystent" ? "assistant" : ""}`}
              >
                <strong>{message.role}</strong>
                <p>{message.text}</p>
              </div>
            ))}
          </div>

          <div className="chat-input">
            <textarea
              className="input"
              placeholder="Napisz komendę dla agenta..."
              value={messageInput}
              onChange={(event) => setMessageInput(event.target.value)}
            />
            <button className="button" type="button" onClick={handleSend} disabled={isSending}>
              {isSending ? "Wysyłanie..." : "Wyślij"}
            </button>
          </div>
        </div>
      </section>

      <aside className="sidebar">
        <div className="panel">
          <p className="label">Szczegóły modułu</p>
          <div className="module-detail">
            <div>
              <strong>{activeModule.label}</strong>
              <p className="footer-note" style={{ marginTop: 4 }}>
                {activeModule.summary}
              </p>
            </div>
            <ul>
              {activeModule.details.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <p className="label">Runs & Telemetry</p>
          <div className="stats-grid">
            {runStats.map((stat) => (
              <div className="stat" key={stat.label}>
                <span>{stat.label}</span>
                <strong>{stat.value}</strong>
              </div>
            ))}
          </div>
          <div className="footer-note">Thread: {threadId ?? "—"}</div>
        </div>

        <div className="panel">
          <p className="label">Historia & Tool Calls</p>
          <div className="history-list">
            {history.length === 0 ? (
              <div className="footer-note">Brak danych z historii.</div>
            ) : (
              history.map((entry) => (
                <div key={`${entry.threadId}-${entry.timestamp}`} className="history-item">
                  <div className="history-meta">
                    <span>thread: {entry.threadId}</span>
                    <span>{entry.timestamp}</span>
                  </div>
                  <div className="tool-list">
                    {entry.toolCalls.length === 0 ? (
                      <span className="footer-note">Brak tool calls.</span>
                    ) : (
                      entry.toolCalls.map((tool, index) => (
                        <div key={`${tool.name}-${index}`} className="tool-item">
                          <strong>{tool.name}</strong>
                          <span>{tool.args}</span>
                          <span>
                            {tool.status} · {tool.durationMs ?? "—"}ms
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="footer-note">
            UI pobiera wynik z get_interaction_history po każdym tool_call_handler.
          </div>
        </div>

        <div className="panel">
          <p className="label">Context Builder</p>
          <div className="context-list">
            {contextItems.map((item) => (
              <div key={item} className="context-item">
                <span>{item}</span>
                <span className="tag">HOT</span>
              </div>
            ))}
          </div>
          <div className="footer-note">
            Zbuduj preview kontekstu przed wysłaniem do runtime.
          </div>
        </div>
      </aside>
    </main>
  );
}
