import { createHash, timingSafeEqual } from "node:crypto";

function sameSecret(left: string, right: string): boolean {
  const leftDigest = createHash("sha256").update(left).digest();
  const rightDigest = createHash("sha256").update(right).digest();
  return timingSafeEqual(leftDigest, rightDigest);
}

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET ?? "";
  const authorization = request.headers.get("authorization") ?? "";
  const supplied = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (secret.length < 32 || !sameSecret(supplied, secret)) {
    return Response.json({ detail: "invalid maintenance authentication" }, { status: 401 });
  }
  const apiBase = (process.env.NEXT_PUBLIC_EXERGI_API_URL ?? "").replace(/\/$/, "");
  if (!apiBase) return Response.json({ detail: "maintenance is unavailable" }, { status: 503 });
  try {
    const response = await fetch(`${apiBase}/api/v1/maintenance/daily`, {
      method: "POST",
      headers: { "X-Exergi-Maintenance-Secret": secret },
      cache: "no-store",
    });
    if (!response.ok) return Response.json({ detail: "maintenance run failed" }, { status: 502 });
    return Response.json(await response.json());
  } catch {
    return Response.json({ detail: "maintenance service unavailable" }, { status: 503 });
  }
}
