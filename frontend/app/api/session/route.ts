import { NextRequest, NextResponse } from "next/server";
import { allowedOrigin, createSession, equal, SESSION_LIFETIME_MS, validSession } from "../../../lib/session";
export const dynamic = "force-dynamic";
const attempts = new Map<string, { count: number; until: number }>();
export async function POST(req: NextRequest) {
  const origin = req.headers.get("origin");
  if (!allowedOrigin(origin, req.nextUrl.origin, process.env.APP_ORIGIN))
    return NextResponse.json({ error: "Origin rejected" }, { status: 403 });
  const key = "login";
  const attempt = attempts.get(key);
  if (attempt && attempt.until > Date.now() && attempt.count >= 10)
    return NextResponse.json(
      { error: "Too many attempts. Try again in one minute." },
      { status: 429 },
    );
  const body = await req.json().catch(() => ({}));
  if (!process.env.AIOPS_ADMIN_PASSWORD || !process.env.SESSION_SECRET)
    return NextResponse.json(
      { error: "Operator authentication is not configured" },
      { status: 503 },
    );
  if (
    typeof body.password !== "string" ||
    !equal(body.password, process.env.AIOPS_ADMIN_PASSWORD)
  ) {
    const prev =
      attempt && attempt.until > Date.now()
        ? attempt
        : { count: 0, until: Date.now() + 60000 };
    attempts.set(key, { ...prev, count: prev.count + 1 });
    return NextResponse.json(
      { error: "Incorrect operator password" },
      { status: 401 },
    );
  }
  attempts.delete(key);
  const token = createSession(process.env.SESSION_SECRET);
  const response = NextResponse.json({ ok: true });
  response.cookies.set("aiops_session", token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.COOKIE_SECURE === "true",
    path: "/",
    maxAge: SESSION_LIFETIME_MS / 1000,
  });
  return response;
}
export async function GET(req: NextRequest) {
  return NextResponse.json({
    authenticated: validSession(req.cookies.get("aiops_session")?.value),
  });
}
export async function DELETE(req: NextRequest) {
  if (!allowedOrigin(req.headers.get("origin"), req.nextUrl.origin, process.env.APP_ORIGIN))
    return NextResponse.json({ error: "Origin rejected" }, { status: 403 });
  const r = NextResponse.json({ ok: true });
  r.cookies.set("aiops_session", "", { maxAge: 0, path: "/" });
  return r;
}
