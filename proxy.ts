import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";

import { bypassesClerk } from "./app/lib/cron-auth";

const publicPaths = new Set([
  "/", "/sign-in", "/sign-up", "/privacy", "/terms", "/dpa", "/subprocessors",
]);

const clerkProxy = clerkMiddleware(async (auth, request) => {
  const path = request.nextUrl.pathname;
  const isPublic = publicPaths.has(path)
    || path.startsWith("/sign-in/")
    || path.startsWith("/sign-up/");
  if (!isPublic) await auth.protect();
});

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  if (bypassesClerk(request.nextUrl.pathname)) return NextResponse.next();
  return clerkProxy(request, event);
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
