import { clerkMiddleware } from "@clerk/nextjs/server";

const publicPaths = new Set(["/", "/sign-in", "/sign-up"]);

export default clerkMiddleware(async (auth, request) => {
  const path = request.nextUrl.pathname;
  const isPublic = publicPaths.has(path)
    || path.startsWith("/sign-in/")
    || path.startsWith("/sign-up/");
  if (!isPublic) await auth.protect();
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
