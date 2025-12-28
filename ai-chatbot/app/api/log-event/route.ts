import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

// Note: when running `next dev` from `ai-chatbot/`, `process.cwd()` points to `ai-chatbot`.
// We keep logs in the repo-level `logs/` folder (one level up) so they are easy to find.
const LOG_FILE_REPO = path.resolve(process.cwd(), "..", "logs", "frontend.log");
const LOG_FILE_LOCAL = path.resolve(process.cwd(), "logs", "frontend.log");

async function appendLine(filePath: string, line: string) {
  await fs.promises.mkdir(path.dirname(filePath), { recursive: true });
  await fs.promises.appendFile(filePath, line, "utf-8");
}

export async function GET() {
  try {
    const existsRepo = await fs.promises
      .access(LOG_FILE_REPO)
      .then(() => true)
      .catch(() => false);
    const existsLocal = await fs.promises
      .access(LOG_FILE_LOCAL)
      .then(() => true)
      .catch(() => false);
    return NextResponse.json({
      ok: true,
      exists: existsRepo || existsLocal,
      repo: { exists: existsRepo, logFile: LOG_FILE_REPO },
      local: { exists: existsLocal, logFile: LOG_FILE_LOCAL },
    });
  } catch (error) {
    return NextResponse.json({ ok: false, error: String(error) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const payload = await request.json().catch(() => null);
    const message = payload?.message || "(no message)";
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] ${message}\n`;
    await Promise.all([
      appendLine(LOG_FILE_REPO, line),
      appendLine(LOG_FILE_LOCAL, line),
    ]);
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Frontend log failed", error);
    return NextResponse.json({ ok: false, error: String(error) }, { status: 500 });
  }
}
