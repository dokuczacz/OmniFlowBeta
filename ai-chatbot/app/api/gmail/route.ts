import { NextResponse } from "next/server";

type GmailBridgeRequest = {
  action: string;
  payload?: Record<string, unknown> | null;
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

function deriveCustomBridgeUrl(toolCallHandlerUrl: string): string {
  const input = (toolCallHandlerUrl || "").trim();
  if (!input) return "";
  // Preserve query string from the tool_call_handler URL (e.g. `?code=...`).
  try {
    const url = new URL(input);
    const path = url.pathname.replace(/\/+$/, "");
    if (path.endsWith("/api/custom_bridge")) return url.toString();
    if (path.includes("/api/")) {
      url.pathname = path.replace(/\/api\/[^/]+$/, "/api/custom_bridge");
      return url.toString();
    }
    url.pathname = `${path}/api/custom_bridge`;
    return url.toString();
  } catch {
    if (input.includes("/api/custom_bridge")) return input.replace(/\/+$/, "");
    if (input.includes("/api/")) {
      const base = input.split("/api/")[0]?.replace(/\/+$/, "") ?? "";
      return base ? `${base}/api/custom_bridge` : "";
    }
    return `${input.replace(/\/+$/, "")}/api/custom_bridge`;
  }
}

function pickFunctionKeyFromEnv(): { key: string; source: string | null } {
  // Do not expose the key value; we return only which env var was used.
  const candidates: Array<[string, string | undefined]> = [
    ["OMNIFLOW_AZFUNC_FUNCTION_KEY", process.env.OMNIFLOW_AZFUNC_FUNCTION_KEY],
    ["OMNIFLOW_CUSTOM_BRIDGE_FUNCTION_KEY", process.env.OMNIFLOW_CUSTOM_BRIDGE_FUNCTION_KEY],
    ["OMNIFLOW_AZFUNC_CUSTOM_BRIDGE_KEY", process.env.OMNIFLOW_AZFUNC_CUSTOM_BRIDGE_KEY],
    ["FUNCTION_CODE_CUSTOM_BRIDGE", process.env.FUNCTION_CODE_CUSTOM_BRIDGE],
    ["FUNCTION_CODE_PROXY_ROUTER", process.env.FUNCTION_CODE_PROXY_ROUTER],
    // Common ad-hoc names (fallback).
    ["AZURE_FUNCTION_KEY", process.env.AZURE_FUNCTION_KEY],
    ["AZURE_FUNCTIONS_KEY", process.env.AZURE_FUNCTIONS_KEY],
    ["FUNCTIONS_KEY", process.env.FUNCTIONS_KEY],
    ["X_FUNCTIONS_KEY", process.env.X_FUNCTIONS_KEY],
  ];
  for (const [name, value] of candidates) {
    const v = (value || "").trim();
    if (v) return { key: v, source: name };
  }
  return { key: "", source: null };
}

export async function POST(request: Request) {
  let body: GmailBridgeRequest;
  try {
    body = (await request.json()) as GmailBridgeRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const action = (body.action || "").trim();
  if (!action) {
    return NextResponse.json({ error: "Missing action" }, { status: 400 });
  }

  const defaultBackendUrl = process.env.OMNIFLOW_BACKEND_URL || "";
  const targetBase =
    typeof body.backend_url === "string" && body.backend_url.trim()
      ? body.backend_url.trim()
      : defaultBackendUrl;

  const toolHandlerUrl = normalizeToolCallHandlerUrl(targetBase);
  if (!toolHandlerUrl) {
    return NextResponse.json(
      { error: "Missing OMNIFLOW_BACKEND_URL and backend_url" },
      { status: 500 }
    );
  }

  const targetUrl = deriveCustomBridgeUrl(toolHandlerUrl);
  if (!targetUrl) {
    return NextResponse.json(
      { error: "Could not derive custom_bridge URL" },
      { status: 500 }
    );
  }

  const payload = {
    action,
    user_id: body.user_id ?? null,
    payload: body.payload ?? {},
  };

  try {
    const { key: functionKey, source: functionKeySource } = pickFunctionKeyFromEnv();
    const resp = await fetch(targetUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(body.user_id ? { "X-User-Id": body.user_id } : {}),
        ...(functionKey ? { "x-functions-key": functionKey } : {}),
      },
      body: JSON.stringify(payload),
    });
    const ct = resp.headers.get("content-type") ?? "";
    if (!ct.includes("application/json") && !ct.includes("text/json")) {
      const text = await resp.text().catch(() => "");
      return NextResponse.json(
        {
          error: "custom_bridge returned non-JSON response",
          status: resp.status,
          target_url: targetUrl,
          function_key_present: !!functionKey,
          function_key_source: functionKeySource,
          body_excerpt: text.slice(0, 300),
        },
        { status: 502 }
      );
    }

    const data = await resp.json().catch(() => ({}));
    return NextResponse.json(data, { status: resp.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 502 }
    );
  }
}
