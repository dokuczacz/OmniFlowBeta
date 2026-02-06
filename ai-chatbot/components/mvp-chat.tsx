"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
};

type RunLog = {
  id: string;
  timestamp: string;
  latencyMs: number | null;
  status: "ok" | "error";
  threadId: string | null;
  messageExcerpt: string;
};

type StreamChunk = Record<string, unknown>;

type RunProgress = {
  schema_version?: string;
  user_id?: string;
  thread_id?: string;
  run_id?: string;
  trace_id?: string;
  status?: string;
  stage?: string;
  message?: string;
  seq?: number;
  ts_utc?: string;
};

function normalizeStreamChunk(chunk: StreamChunk): StreamChunk {
  if (!("data" in chunk)) {
    return chunk;
  }
  const data = chunk.data;
  if (typeof data === "string") {
    try {
      const parsed = JSON.parse(data) as StreamChunk;
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch {
      return chunk;
    }
  }
  if (data && typeof data === "object") {
    return data as StreamChunk;
  }
  return chunk;
}

function extractStreamText(chunk: StreamChunk): string | null {
  if (typeof chunk.message === "string") return chunk.message;
  if (typeof chunk.response === "string") {
    try {
      const parsed = JSON.parse(chunk.response) as StreamChunk;
      if (parsed && typeof parsed.message === "string") {
        return parsed.message;
      }
    } catch {
      return chunk.response;
    }
    return chunk.response;
  }
  if (chunk.response && typeof chunk.response === "object") {
    const response = chunk.response as StreamChunk;
    if (typeof response.message === "string") return response.message;
    return JSON.stringify(response, null, 2);
  }
  if (typeof chunk.content === "string") return chunk.content;
  if (chunk.response && typeof chunk.response === "object") {
    return JSON.stringify(chunk.response, null, 2);
  }
  if (chunk.content && typeof chunk.content === "object") {
    return JSON.stringify(chunk.content, null, 2);
  }
  return null;
}

function parseStreamBuffer(
  buffer: string,
  onChunk: (chunk: StreamChunk) => void
): string {
  let currentIndex = 0;
  let jsonStartIndex = buffer.indexOf("{", currentIndex);

  while (jsonStartIndex !== -1 && jsonStartIndex < buffer.length) {
    let braceCount = 0;
    let inString = false;
    let escapeNext = false;
    let jsonEndIndex = -1;

    for (let i = jsonStartIndex; i < buffer.length; i += 1) {
      const char = buffer[i];
      if (inString) {
        if (escapeNext) {
          escapeNext = false;
        } else if (char === "\\") {
          escapeNext = true;
        } else if (char === '"') {
          inString = false;
        }
      } else {
        if (char === '"') {
          inString = true;
        } else if (char === "{") {
          braceCount += 1;
        } else if (char === "}") {
          braceCount -= 1;
          if (braceCount === 0) {
            jsonEndIndex = i;
            break;
          }
        }
      }
    }

    if (jsonEndIndex === -1) {
      break;
    }

    const jsonString = buffer.slice(jsonStartIndex, jsonEndIndex + 1);
    try {
      const parsed = JSON.parse(jsonString) as StreamChunk;
      if (parsed && typeof parsed === "object") {
        onChunk(parsed);
      }
    } catch {
      jsonStartIndex = buffer.indexOf("{", jsonStartIndex + 1);
      continue;
    }

    buffer = buffer.slice(jsonEndIndex + 1).trimStart();
    currentIndex = 0;
    jsonStartIndex = buffer.indexOf("{", currentIndex);
  }

  return buffer;
}

export function MVPChat({
  backendUrl,
  activeUser,
  chatEnabled,
  streamMode,
  onStatusUpdate = () => {},
}: {
  backendUrl: string;
  activeUser: string;
  chatEnabled: boolean;
  streamMode: string;
  onStatusUpdate?: (status: string, threadId: string | null) => void;
}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [status, setStatus] = useState<"idle" | "sending" | "error">("idle");
  const [error, setError] = useState<string>("");
  const [runs, setRuns] = useState<RunLog[]>([]);
  const [contentType, setContentType] = useState<string | null>(null);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [stickToBottom, setStickToBottom] = useState(true);

  const threadIdRef = useRef<string | null>(null);
  useEffect(() => {
    threadIdRef.current = threadId;
  }, [threadId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!activeUser) {
      setThreadId(null);
      return;
    }
    const stored = localStorage.getItem(`mvp_thread_${activeUser}`);
    if (stored) {
      setThreadId(stored);
    }
  }, [activeUser]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!activeUser) {
      return;
    }
    const key = `mvp_thread_${activeUser}`;
    if (threadId) {
      localStorage.setItem(key, threadId);
    } else {
      localStorage.removeItem(key);
    }
  }, [threadId, activeUser]);

  const appendRun = (
    statusValue: "ok" | "error",
    latencyValue: number | null,
    threadValue: string | null,
    message: string
  ) => {
    setRuns((prev) => [
      {
        id: crypto.randomUUID(),
        timestamp: new Date().toLocaleTimeString(),
        latencyMs: latencyValue,
        status: statusValue,
        threadId: threadValue,
        messageExcerpt:
          message.length > 60 ? `${message.slice(0, 57)}...` : message,
      },
      ...prev,
    ]);
  };

  const updateAssistant = (
    assistantId: string,
    update: (content: string) => string
  ) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === assistantId
          ? { ...message, content: update(message.content) }
          : message
      )
    );
  };

  const setAssistantContent = (assistantId: string, content: string) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === assistantId ? { ...message, content } : message
      )
    );
  };

  const simulateStreaming = async (assistantId: string, text: string) => {
    const chunkSize = 24;
    const delayMs = 12;
    for (let i = 0; i < text.length; i += chunkSize) {
      const part = text.slice(i, i + chunkSize);
      updateAssistant(assistantId, (content) => content + part);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  };

  const toolCallsCount = (data: unknown): number => {
    if (!data || typeof data !== "object") return 0;
    const record = data as Record<string, unknown>;
    if (typeof record.tool_calls_count === "number") return record.tool_calls_count;
    if (Array.isArray(record.tool_calls)) return record.tool_calls.length;
    if (Array.isArray(record.tools)) return record.tools.length;
    return 0;
  };

  const ensureThreadId = () => {
    if (threadIdRef.current) return threadIdRef.current;
    const next = `handle_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
    setThreadId(next);
    threadIdRef.current = next;
    return next;
  };

  const pollRunProgress = async (
    activeThreadId: string,
    abortSignal: AbortSignal
  ): Promise<RunProgress | null> => {
    const params = new URLSearchParams({ thread_id: activeThreadId });
    if (backendUrl?.trim()) params.set("backend_url", backendUrl.trim());
    if (activeUser?.trim()) params.set("user_id", activeUser.trim());
    const resp = await fetch(`/api/progress?${params.toString()}`, {
      method: "GET",
      signal: abortSignal,
    });
    const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
    const rp = data?.run_progress;
    if (!rp || typeof rp !== "object") return null;
    return rp as RunProgress;
  };

  useEffect(() => {
    if (!stickToBottom) return;
    const el = historyRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages, stickToBottom]);

  const handleScroll = () => {
    const el = historyRef.current;
    if (!el) return;
    const threshold = 80;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    setStickToBottom(nearBottom);
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!chatEnabled || !trimmed || status === "sending") return;
    setStatus("sending");
    setError("");
    setLatencyMs(null);
    const activeThreadId = ensureThreadId();
    const ts = new Date().toLocaleTimeString();
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: ts,
    };
    const assistantId = crypto.randomUUID();
    const assistantTs = new Date().toLocaleTimeString();
    setMessages((prev) => [
      ...prev,
      userMsg,
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: assistantTs,
      },
    ]);
    setInput("");

    const started = performance.now();
    let nextThreadId = activeThreadId;
    onStatusUpdate?.("User message sent... waiting for backend", nextThreadId);
    onStatusUpdate?.("Agent is thinking...", nextThreadId);

    const progressAbort = new AbortController();
    let progressTimer: number | null = null;
    let lastSeq = 0;
    const stageLabel = (stage: string) => {
      const key = stage.trim();
      if (key === "grasping_context") return "Grasping context";
      if (key === "looking_more_data") return "Looking for more data (DEEP)";
      if (key === "calling_tools") return "Calling tools";
      if (key === "done") return "Done";
      return stage.trim() || "Working";
    };
    const startProgressPolling = () => {
      const tick = async () => {
        try {
          const rp = await pollRunProgress(nextThreadId, progressAbort.signal);
          if (!rp) return;
          const seq = typeof rp.seq === "number" ? rp.seq : 0;
          if (seq <= lastSeq) return;
          lastSeq = seq;
          const label = stageLabel(String(rp.stage || ""));
          const msg = String(rp.message || "").trim();
          onStatusUpdate?.(msg ? `${label}: ${msg}` : `${label}...`, nextThreadId);
        } catch {
          // ignore transient polling failures
        }
      };
      void tick();
      progressTimer = window.setInterval(() => void tick(), 800);
    };
    startProgressPolling();
    try {
      const requestStream = streamMode === "backend";
      const resp = await fetch("/api/omni", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          thread_id: nextThreadId,
          runtime: "responses",
          backend_url: backendUrl || null,
          user_id: activeUser || null,
          stream: requestStream,
          stream_mode: streamMode,
        }),
      });
      setContentType(resp.headers.get("content-type"));

      if (!resp.ok) {
        const elapsed = Math.round(performance.now() - started);
        setLatencyMs(elapsed);
        const errorText = await resp.text();
        let errorMessage = "Backend error";
        try {
          const parsed = JSON.parse(errorText) as Record<string, unknown>;
          if (typeof parsed.error === "string") {
            errorMessage = parsed.error;
          } else if (errorText.trim()) {
            errorMessage = errorText;
          }
        } catch {
          if (errorText.trim()) {
            errorMessage = errorText;
          }
        }
        setStatus("error");
        setError(errorMessage);
        setAssistantContent(assistantId, `(Error) ${errorMessage}`);
        appendRun("error", elapsed, nextThreadId, trimmed);
        onStatusUpdate?.("Assistant finished (error).", nextThreadId);
        onStatusUpdate?.("Waiting for input...", nextThreadId);
        return;
      }

      const contentTypeHeader = resp.headers.get("content-type") ?? "";
      const treatAsJson =
        !requestStream ||
        !resp.body ||
        contentTypeHeader.includes("application/json") ||
        contentTypeHeader.includes("text/json");

      if (treatAsJson) {
        const data = (await resp.json().catch(() => ({}))) as Record<
          string,
          unknown
        >;
        const assistantText = extractStreamText(data) ?? "";
        if (typeof data.thread_id === "string" && data.thread_id) {
          nextThreadId = data.thread_id;
          setThreadId(data.thread_id);
          threadIdRef.current = data.thread_id;
        }

        const toolsCount = toolCallsCount(data);
        if (toolsCount > 0) {
          onStatusUpdate?.("Agent is collecting data from tools...", nextThreadId);
        }

        const finalText = assistantText || JSON.stringify(data, null, 2);
        if (streamMode === "simulate") {
          onStatusUpdate?.("Rendering response...", nextThreadId);
          await simulateStreaming(assistantId, finalText);
        } else {
          setAssistantContent(assistantId, finalText);
        }

        const elapsed = Math.round(performance.now() - started);
        setLatencyMs(elapsed);
        appendRun("ok", elapsed, nextThreadId, trimmed);
        setStatus("idle");
        onStatusUpdate?.("Assistant finished.", nextThreadId);
        onStatusUpdate?.("Waiting for input...", nextThreadId);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
    let buffer = "";
    let rawText = "";
    let lastContent = "";
    let streamedAny = false;

      const updateThreadId = (candidate: unknown) => {
        if (typeof candidate === "string" && candidate) {
          nextThreadId = candidate;
          setThreadId(candidate);
          threadIdRef.current = candidate;
        }
      };

      const handleChunk = (chunk: StreamChunk) => {
        const normalized = normalizeStreamChunk(chunk);
        updateThreadId(normalized.thread_id ?? normalized.threadId);
        if (normalized.event === "RunStatus") {
      let statusMessage = "";
          if (typeof normalized.content === "string") {
            statusMessage = normalized.content;
          } else if (normalized.content) {
            statusMessage = JSON.stringify(normalized.content);
          }
          if (!statusMessage && normalized.status) {
            statusMessage = String(normalized.status);
          }
          statusMessage = statusMessage.trim();
          if (statusMessage) {
            console.info("Stream status:", statusMessage);
            if (statusMessage.toLowerCase().includes("tool")) {
              onStatusUpdate?.("Agent is collecting data from tools...", nextThreadId);
            } else {
              onStatusUpdate?.(statusMessage, nextThreadId);
            }
          }
          return;
        }
        const text = extractStreamText(normalized);
        if (!text) return;
        const delta = text.startsWith(lastContent)
          ? text.slice(lastContent.length)
          : text;
        lastContent = text;
        if (delta) {
          streamedAny = true;
          updateAssistant(assistantId, (content) => content + delta);
        }
        if (normalized.event === "RunCompleted") {
          onStatusUpdate?.("Assistant finished.", nextThreadId);
          onStatusUpdate?.("Waiting for input...", nextThreadId);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunkText = decoder.decode(value, { stream: true });
        rawText += chunkText;
        buffer += chunkText;
        buffer = parseStreamBuffer(buffer, handleChunk);
      }
      buffer = parseStreamBuffer(buffer, handleChunk);

      const elapsed = Math.round(performance.now() - started);
      setLatencyMs(elapsed);
      appendRun("ok", elapsed, nextThreadId, trimmed);

      if (!streamedAny && rawText.trim()) {
        let fallbackText = rawText.trim();
        let toolsCount = 0;
        try {
          const parsed = JSON.parse(rawText) as StreamChunk;
          toolsCount = toolCallsCount(parsed);
          const extracted = extractStreamText(parsed);
          if (extracted) {
            fallbackText = extracted;
          } else {
            fallbackText = JSON.stringify(parsed, null, 2);
          }
        } catch {
          // keep raw text
        }
        if (toolsCount > 0) {
          onStatusUpdate?.("Agent is collecting data from tools...", nextThreadId);
        }
        if (fallbackText) {
          onStatusUpdate?.("Rendering response...", nextThreadId);
          await simulateStreaming(assistantId, fallbackText);
        }
      }

      setStatus("idle");
      onStatusUpdate?.("Assistant finished.", nextThreadId);
      onStatusUpdate?.("Waiting for input...", nextThreadId);
    } catch (err) {
      const elapsed = Math.round(performance.now() - started);
      setLatencyMs(elapsed);
      setStatus("error");
      const message = err instanceof Error ? err.message : "Request failed";
      setError(message);
      setAssistantContent(assistantId, `(Error) ${message}`);
      appendRun("error", elapsed, nextThreadId, trimmed);
      onStatusUpdate?.("Assistant finished (error).", nextThreadId);
      onStatusUpdate?.("Waiting for input...", nextThreadId);
    } finally {
      try {
        progressAbort.abort();
      } catch {}
      if (progressTimer) {
        window.clearInterval(progressTimer);
      }
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div
        ref={historyRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-2 pb-8 text-sm"
      >
        <div className="mx-auto w-full max-w-2xl space-y-4">
          {messages.length === 0 ? (
            <div className="rounded-xl border border-border/40 bg-muted/20 p-4 text-muted-foreground">
              Brak wiadomosci. Wpisz pierwsza wiadomosc, aby zobaczyc podglad
              interfejsu.
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`space-y-2 rounded-xl border border-border/40 p-4 ${
                  message.role === "user"
                    ? "bg-muted/30"
                    : "bg-background/60"
                }`}
              >
                <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  {message.role === "user" ? "User" : "Assistant"} |{" "}
                  {message.timestamp}
                </div>
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            ))
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-border/40 bg-background/95 px-4 py-4">
        <div className="mx-auto w-full max-w-2xl space-y-3">
          <Textarea
            placeholder="Type your message..."
            rows={4}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSend();
              }
            }}
            disabled={status === "sending" || !chatEnabled}
            className="border-border/60 bg-background/80"
          />
          <div className="flex items-center justify-between">
            <div
              className="text-xs text-muted-foreground"
              style={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                wordBreak: "break-word",
              }}
              title={[
                `Thread: ${threadId || "(none)"}`,
                `Latency: ${latencyMs !== null ? `${latencyMs} ms` : "(none)"}`,
                !activeUser ? "Missing active user" : `Active user: ${activeUser}`,
                contentType ? `Content-Type: ${contentType}` : null,
                status === "error" && error ? `Error: ${error}` : null,
              ]
                .filter(Boolean)
                .join(" | ")}
            >
              Thread: {threadId || "(none)"} | Latency:{" "}
              {latencyMs !== null ? `${latencyMs} ms` : "(none)"}
              {!activeUser ? " | Missing active user" : ""}
              {activeUser ? ` | Active user: ${activeUser}` : ""}
              {contentType ? ` | Content-Type: ${contentType}` : ""}
              {status === "error" && error ? ` | Error: ${error}` : ""}
            </div>
            <Button
              onClick={handleSend}
              disabled={status === "sending" || !chatEnabled}
            >
              {status === "sending" ? "Thinking..." : "Send"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
