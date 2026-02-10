import { NextResponse } from "next/server";

type ProgressRequest = {
  thread_id: string;
  backend_url?: string | null;
  user_id?: string | null;
};

function normalizeToolCallHandlerUrl(input: string): string {
  const raw = (input || "").trim();
  if (!raw) return "";

  // Preserve `?code=...` and other query params (Azure Functions auth).
  try {
    const url = new URL(raw);
    const path = url.pathname.replace(/\/+$/, "");
    if (path.endsWith("/api/tool_call_handler")) return url.toString();
    if (path.endsWith("/api/custom_bridge")) {
      url.pathname = path.replace(/\/api\/custom_bridge$/, "/api/tool_call_handler");
      return url.toString();
    }
    if (path.endsWith("/api")) {
      url.pathname = `${path}/tool_call_handler`;
      return url.toString();
    }
    if (path.includes("/api/")) return url.toString();
    url.pathname = `${path}/api/tool_call_handler`;
    return url.toString();
  } catch {
    const trimmed = raw.replace(/\/+$/, "");
    if (!trimmed) return "";
    if (trimmed.includes("/api/tool_call_handler")) return trimmed;
    if (trimmed.includes("/api/custom_bridge")) {
      const base = trimmed.split("/api/")[0]?.replace(/\/+$/, "") ?? "";
      return base ? `${base}/api/tool_call_handler` : trimmed;
    }
    if (trimmed.endsWith("/api")) return `${trimmed}/tool_call_handler`;
    if (trimmed.includes("/api/")) return trimmed;
    return `${trimmed}/api/tool_call_handler`;
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const thread_id = searchParams.get("thread_id") || "";
  const backend_url = searchParams.get("backend_url");
  const user_id = searchParams.get("user_id");

  if (!thread_id.trim()) {
    return NextResponse.json({ error: "Missing thread_id" }, { status: 400 });
  }

  const defaultBackendUrl = process.env.OMNIFLOW_BACKEND_URL || "";
  const targetUrl = normalizeToolCallHandlerUrl(
    typeof backend_url === "string" && backend_url.trim()
      ? backend_url.trim()
      : defaultBackendUrl
  );
  if (!targetUrl) {
    return NextResponse.json(
      { error: "Missing OMNIFLOW_BACKEND_URL and backend_url" },
      { status: 500 }
    );
  }

  const payload: ProgressRequest & { action: string } = {
    action: "get_run_progress",
    thread_id: thread_id.trim(),
    user_id: user_id?.trim() || null,
  };

  try {
    const functionKey =
      process.env.OMNIFLOW_AZFUNC_FUNCTION_KEY ||
      process.env.OMNIFLOW_CUSTOM_BRIDGE_FUNCTION_KEY ||
      process.env.OMNIFLOW_AZFUNC_CUSTOM_BRIDGE_KEY ||
      process.env.FUNCTION_CODE_PROXY_ROUTER ||
      "";
    const resp = await fetch(targetUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(user_id ? { "X-User-Id": user_id } : {}),
        ...(functionKey ? { "x-functions-key": functionKey } : {}),
      },
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    return NextResponse.json(data, { status: resp.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 502 }
    );
  }
}
