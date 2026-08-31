import { auth } from "@clerk/nextjs/server";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const SHOP_PATTERN = /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/;

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ detail: "authentication required" }, { status: 401 });
  let body: { shop?: unknown };
  try {
    body = await request.json() as { shop?: unknown };
  } catch {
    return NextResponse.json({ detail: "invalid JSON body" }, { status: 422 });
  }
  const shop = typeof body.shop === "string" ? body.shop.trim().toLowerCase() : "";
  if (!SHOP_PATTERN.test(shop)) {
    return NextResponse.json({ detail: "invalid permanent Shopify domain" }, { status: 422 });
  }
  const cookieStore = await cookies();
  cookieStore.set("exergi_shop", shop, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return NextResponse.json({ status: "SAVED" });
}
