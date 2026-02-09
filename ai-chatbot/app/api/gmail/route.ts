import { NextResponse } from "next/server";

/**
 * POST /api/gmail – proxy to the custom_bridge Azure Function.
 *
 * Derives the custom_bridge URL from OMNIFLOW_BACKEND_URL by replacing
 * the function name segment (tool_call_handler → custom_bridge).
 */
export async function POST(request: Request) {
  const backendUrl = process.env.OMNIFLOW_BACKEND_URL || "";
  if (!backendUrl) {
    return NextResponse.json(
      { error: "Missing OMNIFLOW_BACKEND_URL" },
      { status: 500 }
    );
  }

  // Derive custom_bridge URL from the main backend URL.
  const bridgeUrl = backendUrl.replace(
    /\/api\/tool_call_handler\b/i,
    "/api/custom_bridge"
  );

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const resp = await fetch(bridgeUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
