import { NextResponse } from "next/server";

type OmniRequest = {
  message: string;
  thread_id?: string | null;
  runtime?: string;
  backend_url?: string | null;
  user_id?: string | null;
  stream?: boolean | null;
  stream_mode?: string | null;
  gmail_status?: { authorized: boolean; email?: string | null } | null;
};

function parseBackendPayload(rawText: string): Record<string, unknown> | null {
  const text = rawText.trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    if (parsed && typeof parsed === "object") return parsed;
  } catch {}
  return null;
}

function extractBackendErrorMessage(
  status: number,
  rawText: string,
  parsed: Record<string, unknown> | null
): string {
  if (parsed) {
    const direct = parsed.error;
    if (typeof direct === "string" && direct.trim()) return direct.trim();
    const message = parsed.message;
    if (typeof message === "string" && message.trim()) return message.trim();
  }
  const txt = rawText.trim();
  if (txt) return txt;
  return `Backend returned HTTP ${status}`;
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
  if (body.gmail_status && typeof body.gmail_status === "object") {
    payload.gmail_status = body.gmail_status;
  }

  const targetUrl =
    typeof body.backend_url === "string" && body.backend_url.trim()
      ? body.backend_url.trim()
      : backendUrl;

  try {
    const resp = await fetch(targetUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(body.user_id ? { "X-User-Id": body.user_id } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (body.stream) {
      if (!resp.body) {
        const rawText = await resp.text().catch(() => "");
        const data = parseBackendPayload(rawText);
        if (!resp.ok) {
          return NextResponse.json(
            {
              error: extractBackendErrorMessage(resp.status, rawText, data),
              raw: data ?? rawText,
            },
            { status: resp.status }
          );
        }
        return NextResponse.json(data ?? {}, { status: resp.status });
      }
      return new Response(resp.body, {
        status: resp.status,
        headers: {
          "Content-Type": resp.headers.get("content-type") ?? "application/json",
          "Cache-Control": "no-cache",
        },
      });
    }
    const rawText = await resp.text().catch(() => "");
    const data = parseBackendPayload(rawText);
    if (!resp.ok) {
      return NextResponse.json(
        {
          error: extractBackendErrorMessage(resp.status, rawText, data),
          raw: data ?? rawText,
        },
        { status: resp.status }
      );
    }
    return NextResponse.json(data ?? {});
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 502 }
    );
  }
}
