import { NextRequest, NextResponse } from "next/server";
import { allowedOrigin, validSession } from "../../../../lib/session";
export const dynamic = "force-dynamic";
async function proxy(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  if (!validSession(req.cookies.get("aiops_session")?.value))
    return NextResponse.json({ error: "Sign in to continue" }, { status: 401 });
  if (req.method !== "GET") {
    const origin = req.headers.get("origin");
    if (!allowedOrigin(origin, req.nextUrl.origin, process.env.APP_ORIGIN))
      return NextResponse.json({ error: "Origin rejected" }, { status: 403 });
  }
  const { path } = await ctx.params;
  const target = path.join("/");
  const allowed =
    /^(incidents(?:\/[a-f0-9-]+(?:\/(?:investigate|verify))?)?|actions\/[a-f0-9-]+\/(?:approve|reject)|health|overview|topology|tools|runbooks\/ingest)$/.test(
      target,
    );
  if (!allowed)
    return NextResponse.json({ error: "Unknown endpoint" }, { status: 404 });
  let query = "";
  if (target === "incidents" && req.method === "GET") {
    const params = new URLSearchParams();
    for (const key of ["limit", "offset"]) {
      const value = req.nextUrl.searchParams.get(key);
      if (value !== null) {
        if (!/^\d{1,9}$/.test(value) || (key === "limit" && (Number(value) < 1 || Number(value) > 100)))
          return NextResponse.json({ error: "Invalid pagination" }, { status: 400 });
        params.set(key, value);
      }
    }
    if (params.size) query = "?" + params.toString();
  }
  try {
    const body = req.method === "GET" ? undefined : await req.text();
    if (body && body.length > 12000)
      return NextResponse.json({ error: "Request too large" }, { status: 413 });
    const r = await fetch(
      (process.env.BACKEND_URL || "http://127.0.0.1:18000") + "/api/" + target + query,
      {
        method: req.method,
        headers: {
          Authorization: "Bearer " + process.env.AIOPS_API_TOKEN,
          "Content-Type": "application/json",
        },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(120000),
      },
    );
    return new NextResponse(await r.text(), {
      status: r.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Operator backend is unavailable. Check its service logs." },
      { status: 502 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
