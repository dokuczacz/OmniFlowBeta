import { NextResponse } from "next/server";

type OmniRequest = {
  message: string;
  thread_id?: string | null;
  runtime?: string;
  backend_url?: string | null;
  user_id?: string | null;
  stream?: boolean | null;
  stream_mode?: string | null;
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

export async function POST(request: Request) {
  const backendUrl = process.env.OMNIFLOW_BACKEND_URL || "";
  if (!backendUrl) {
    return NextResponse.json(
      { error: "Missing OMNIFLOW_BACKEND_URL" },
      { status: 500 }
    );
  }

  let body: OmniRequest;
  try {
    body = (await request.json()) as OmniRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body.message || !body.message.trim()) {
    return NextResponse.json({ error: "Empty message" }, { status: 400 });
  }

  const payload: OmniRequest = {
    message: body.message,
    thread_id: body.thread_id ?? null,
    runtime: body.runtime ?? "responses",
    user_id: body.user_id ?? null,
  };
  if (body.stream) {
    payload.stream = true;
  }
  if (typeof body.stream_mode === "string" && body.stream_mode.trim()) {
    payload.stream_mode = body.stream_mode.trim();
  }

  const targetUrl = normalizeToolCallHandlerUrl(
    typeof body.backend_url === "string" && body.backend_url.trim()
      ? body.backend_url.trim()
      : backendUrl
  );

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
        ...(body.user_id ? { "X-User-Id": body.user_id } : {}),
        ...(functionKey ? { "x-functions-key": functionKey } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (body.stream) {
      if (!resp.body) {
        const data = await resp.json().catch(() => ({}));
        return NextResponse.json(data, { status: resp.status });
      }
      return new Response(resp.body, {
        status: resp.status,
        headers: {
          "Content-Type": resp.headers.get("content-type") ?? "application/json",
          "Cache-Control": "no-cache",
        },
      });
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return NextResponse.json(
        { error: data?.error || "Backend error", raw: data },
        { status: resp.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 502 }
    );
  }
}
