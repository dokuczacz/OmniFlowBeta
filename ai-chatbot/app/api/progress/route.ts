import { NextResponse } from "next/server";

type ProgressRequest = {
  thread_id: string;
  backend_url?: string | null;
  user_id?: string | null;
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const thread_id = searchParams.get("thread_id") || "";
  const backend_url = searchParams.get("backend_url");
  const user_id = searchParams.get("user_id");

  if (!thread_id.trim()) {
    return NextResponse.json({ error: "Missing thread_id" }, { status: 400 });
  }

  const defaultBackendUrl = process.env.OMNIFLOW_BACKEND_URL || "";
  const targetUrl =
    typeof backend_url === "string" && backend_url.trim()
      ? backend_url.trim()
      : defaultBackendUrl;
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
    const resp = await fetch(targetUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(user_id ? { "X-User-Id": user_id } : {}),
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
